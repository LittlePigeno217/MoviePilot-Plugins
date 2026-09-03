"""本地 STRM 删除监听：防抖、误报保护、批量退化与启停。

不依赖真的 watchdog —— 注入一个假 Observer，事件直接从 report_removed 灌进去。
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.plugins.p115liteassistant.strm_watch import StrmDeleteWatcher


class FakeObserver:
    def __init__(self):
        self.scheduled = []
        self.started = False
        self.stopped = False

    def schedule(self, _handler, path, recursive=False):
        self.scheduled.append((str(path), bool(recursive)))

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def join(self, timeout=None):
        return None


class WatcherHarness:
    """收集监听器上报的批次。"""

    def __init__(self, config):
        self.config = config
        self.reported = []
        self.observer = FakeObserver()
        self.watcher = StrmDeleteWatcher(
            lambda: dict(self.config),
            self.reported.append,
            observer_factory=lambda: self.observer,
        )
        # 单测里不等 30 秒，防抖单独用一个用例覆盖
        self.watcher.DEBOUNCE_SECONDS = 0.0


def config_for(*target_dirs, enabled=True):
    return {
        "strm_mappings": [
            {"id": f"m{index}", "enabled": enabled, "source_cid": "1", "target_dir": str(path)}
            for index, path in enumerate(target_dirs)
        ]
    }


class ReportFilterTest(unittest.TestCase):
    """哪些事件该收、哪些该扔。"""

    def _harness(self, directory):
        return WatcherHarness(config_for(directory))

    def test_only_strm_files_are_collected(self):
        with TemporaryDirectory() as directory:
            harness = self._harness(directory)

            harness.watcher.report_removed(str(Path(directory) / "Film.nfo"))
            harness.watcher.report_removed(str(Path(directory) / "Film.mkv"))
            harness.watcher.report_removed(str(Path(directory) / "Film.strm"))

            self.assertEqual(
                harness.watcher.drain_once(), [str(Path(directory) / "Film.strm")]
            )

    def test_directory_event_is_collected_regardless_of_suffix(self):
        with TemporaryDirectory() as directory:
            harness = self._harness(directory)
            removed = Path(directory) / "Season 01"

            harness.watcher.report_removed(str(removed), is_directory=True)

            self.assertEqual(harness.watcher.drain_once(), [str(removed)])

    def test_blank_path_is_ignored(self):
        with TemporaryDirectory() as directory:
            harness = self._harness(directory)

            harness.watcher.report_removed("")
            harness.watcher.report_removed("   ")

            self.assertEqual(harness.watcher.drain_once(), [])
            self.assertEqual(harness.reported, [])

    def test_restored_path_is_dropped(self):
        """刮削器常「删掉再写回」，路径又出现了就当没发生过。"""
        with TemporaryDirectory() as directory:
            harness = self._harness(directory)
            restored = Path(directory) / "Film.strm"
            restored.write_text("back\n", encoding="utf-8")

            harness.watcher.report_removed(str(restored))

            self.assertEqual(harness.watcher.drain_once(), [])
            self.assertEqual(harness.reported, [])

    def test_debounce_holds_event_until_quiet(self):
        with TemporaryDirectory() as directory:
            harness = self._harness(directory)
            harness.watcher.DEBOUNCE_SECONDS = 3600.0

            harness.watcher.report_removed(str(Path(directory) / "Film.strm"))

            self.assertEqual(harness.watcher.drain_once(), [])
            self.assertEqual(harness.reported, [])


class DispatchTest(unittest.TestCase):
    """上报语义：小批量给路径，大批量退化为整体巡检。"""

    def test_small_batch_reports_paths(self):
        with TemporaryDirectory() as directory:
            harness = WatcherHarness(config_for(directory))
            paths = [str(Path(directory) / f"Film{index}.strm") for index in range(3)]
            for path in paths:
                harness.watcher.report_removed(path)

            harness.watcher.drain_once()

            self.assertEqual(len(harness.reported), 1)
            self.assertEqual(sorted(harness.reported[0]), sorted(paths))

    def test_large_batch_falls_back_to_full_sweep(self):
        """一次几百条更像掉盘而不是手动删，交给缺失比例熔断把关。"""
        with TemporaryDirectory() as directory:
            harness = WatcherHarness(config_for(directory))
            harness.watcher.MAX_BATCH_PATHS = 2
            for index in range(3):
                harness.watcher.report_removed(str(Path(directory) / f"Film{index}.strm"))

            harness.watcher.drain_once()

            self.assertEqual(harness.reported, [None])

    def test_dispatch_failure_does_not_break_the_loop(self):
        with TemporaryDirectory() as directory:
            def boom(_paths):
                raise RuntimeError("编排层炸了")

            watcher = StrmDeleteWatcher(lambda: config_for(directory), boom, lambda: FakeObserver())
            watcher.DEBOUNCE_SECONDS = 0.0
            watcher.report_removed(str(Path(directory) / "Film.strm"))

            # 不抛出即通过：监听线程不能被一次上报失败带走
            self.assertEqual(len(watcher.drain_once()), 1)

    def test_drained_events_are_not_reported_twice(self):
        with TemporaryDirectory() as directory:
            harness = WatcherHarness(config_for(directory))
            harness.watcher.report_removed(str(Path(directory) / "Film.strm"))

            harness.watcher.drain_once()
            harness.watcher.drain_once()

            self.assertEqual(len(harness.reported), 1)


class LifecycleTest(unittest.TestCase):
    """目录发现与启停。"""

    def test_watch_dirs_skips_missing_disabled_and_duplicates(self):
        with TemporaryDirectory() as directory:
            existing = Path(directory) / "media"
            existing.mkdir()
            gone = Path(directory) / "not-mounted"
            config = {
                "strm_mappings": [
                    {"id": "a", "enabled": True, "target_dir": str(existing)},
                    {"id": "b", "enabled": True, "target_dir": str(existing)},
                    {"id": "c", "enabled": True, "target_dir": str(gone)},
                    {"id": "d", "enabled": False, "target_dir": str(existing)},
                    {"id": "e", "enabled": True, "target_dir": "   "},
                ]
            }
            harness = WatcherHarness(config)

            self.assertEqual(harness.watcher.watch_dirs(), [existing.resolve()])

    def test_start_schedules_each_dir_then_stop_clears_pending(self):
        with TemporaryDirectory() as directory:
            media = Path(directory) / "media"
            media.mkdir()
            harness = WatcherHarness(config_for(media))

            harness.watcher.start()
            try:
                self.assertTrue(harness.watcher.is_running)
                self.assertEqual(
                    harness.observer.scheduled, [(str(media.resolve()), True)]
                )
                self.assertTrue(harness.observer.started)
                harness.watcher.report_removed(str(media / "Film.strm"))
            finally:
                harness.watcher.stop(timeout=1.0)

            self.assertFalse(harness.watcher.is_running)
            self.assertTrue(harness.observer.stopped)
            self.assertEqual(harness.watcher.drain_once(), [])

    def test_start_without_any_watchable_dir_is_quiet(self):
        with TemporaryDirectory() as directory:
            harness = WatcherHarness(config_for(Path(directory) / "not-mounted"))

            harness.watcher.start()

            self.assertFalse(harness.watcher.is_running)
            self.assertEqual(harness.observer.scheduled, [])
            self.assertFalse(harness.observer.started)

    def test_start_without_watchdog_is_quiet(self):
        with TemporaryDirectory() as directory:
            media = Path(directory) / "media"
            media.mkdir()
            watcher = StrmDeleteWatcher(lambda: config_for(media), lambda _paths: None)
            watcher._observer_factory = None

            watcher.start()

            self.assertFalse(watcher.is_running)

    def test_watched_dir_disappearing_is_detected(self):
        with TemporaryDirectory() as directory:
            media = Path(directory) / "media"
            media.mkdir()
            harness = WatcherHarness(config_for(media))
            harness.watcher._watched = [media]

            self.assertTrue(harness.watcher._watched_dirs_alive())
            media.rmdir()
            self.assertFalse(harness.watcher._watched_dirs_alive())
