import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from app.plugins.p115liteassistant.upload_watch import (
    UPLOAD_DEDUP_MAX,
    PendingUploadQueue,
    StabilityTracker,
    UploadCandidate,
    UploadWatcher,
    _UploadEventHandler,
    file_signature,
    mapping_revision,
)
from app.plugins.p115liteassistant import P115LiteAssistant


class UploadWatcherTest(unittest.TestCase):
    @patch("app.plugins.p115liteassistant.upload_watch.logger.warning")
    def test_missing_watchdog_reports_file_path_fallback(self, warning):
        tracker = Mock()
        tracker.configure.return_value = [Path("/media")]
        watcher = UploadWatcher(lambda: {}, tracker)
        watcher._observer_factory = None
        watcher.start()
        tracker.submit_path.assert_not_called()
        self.assertIn("可靠整理路径", warning.call_args.args[0])

    def test_report_change_only_submits_files_and_move_only_uses_dest(self):
        tracker = Mock()
        tracker._extensions.return_value = {".mkv"}
        tracker.submit_path.return_value = True
        watcher = UploadWatcher(lambda: {}, tracker)
        self.assertFalse(watcher.report_change("/media/folder", is_directory=True))
        self.assertFalse(watcher.report_change("/media/a.txt"))
        self.assertTrue(watcher.report_change("/media/a.mkv"))
        event = type("Event", (), {"src_path": "/old/a.mkv", "dest_path": "/media/b.mkv", "is_directory": False})()
        _UploadEventHandler(watcher).on_moved(event)
        tracker.submit_path.assert_any_call("/media/b.mkv", source="watch")
        self.assertNotIn("/old/a.mkv", [call.args[0] for call in tracker.submit_path.call_args_list])

    def test_duplicate_events_and_signature_override_stay_one_pending(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            movie = root / "Film.mkv"
            movie.write_bytes(b"a")
            config = {"upload_mappings": [{"id": "m", "source": str(root), "target": "/Cloud"}], "upload_media_extensions": ".mkv"}
            tracker = StabilityTracker(lambda: config, Mock())
            tracker.configure()
            tracker._accepting = True
            for _ in range(100):
                self.assertTrue(tracker.submit_path(str(movie)))
            self.assertEqual(len(tracker._pending), 1)
            old = next(iter(tracker._pending.values())).last_signature
            movie.write_bytes(b"changed")
            os.utime(movie, None)
            tracker.submit_path(str(movie))
            self.assertEqual(len(tracker._pending), 1)
            self.assertNotEqual(next(iter(tracker._pending.values())).last_signature, old)

    def test_stability_requires_three_equal_ticks_and_stat_runs_without_tracker_lock(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            movie = root / "Film.mkv"
            movie.write_bytes(b"a")
            ready = Mock()
            config = {"upload_mappings": [{"id": "m", "source": str(root), "target": "/Cloud"}], "upload_media_extensions": ".mkv"}
            tracker = StabilityTracker(lambda: config, ready, interval=0.01, checks=3)
            tracker.configure(); tracker._accepting = True
            tracker.submit_path(str(movie))
            original = file_signature
            def unlocked(path):
                self.assertTrue(tracker._lock.acquire(blocking=False))
                tracker._lock.release()
                return original(path)
            with patch("app.plugins.p115liteassistant.upload_watch.file_signature", side_effect=unlocked):
                self.assertEqual(tracker.tick(), 0)
                self.assertEqual(tracker.tick(), 0)
                self.assertEqual(tracker.tick(), 1)
            ready.assert_called_once()

    def test_path_boundary_symlink_and_deleted_file_are_fail_closed(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "root"; root.mkdir()
            outside = Path(directory) / "outside.mkv"; outside.write_bytes(b"x")
            link = root / "link.mkv"; link.symlink_to(outside)
            config = {"upload_mappings": [{"id": "m", "source": str(root), "target": "/Cloud"}], "upload_media_extensions": ".mkv"}
            ready = Mock(); tracker = StabilityTracker(lambda: config, ready, checks=1)
            tracker.configure(); tracker._accepting = True
            self.assertFalse(tracker.submit_path(str(outside)))
            self.assertFalse(tracker.submit_path(str(link)))
            movie = root / "gone.mkv"; movie.write_bytes(b"x")
            self.assertTrue(tracker.submit_path(str(movie))); movie.unlink()
            self.assertEqual(tracker.tick(), 0)
            self.assertFalse(tracker._pending); ready.assert_not_called()


    def test_sidecar_disabled_is_rejected_before_tracker_and_does_not_block_media(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            movie = root / "Film.mkv"; movie.write_bytes(b"media")
            sidecar = root / "Film.nfo"; sidecar.write_text("nfo", encoding="utf-8")
            ready = Mock()
            config = {
                "upload_mappings": [{"id": "m", "source": str(root), "target": "/Cloud"}],
                "upload_media_extensions": ".mkv",
                "upload_sidecar_extensions": ".nfo",
                "upload_include_sidecars": False,
            }
            tracker = StabilityTracker(lambda: config, ready, checks=1)
            tracker.configure(); tracker._accepting = True
            self.assertFalse(tracker.submit_path(str(sidecar)))
            self.assertTrue(tracker.submit_path(str(movie)))
            self.assertEqual(len(tracker._pending), 1)
            self.assertEqual(tracker.tick(), 1)
            ready.assert_called_once()

    def test_mapping_revision_covers_every_routing_and_side_effect_field(self):
        with TemporaryDirectory() as directory:
            root = str(Path(directory).resolve())
            base_mapping = {
                "id": "m", "source": root, "target": "/Old",
                "strm_target": str(Path(directory) / "strm"), "enabled": True,
            }
            base_config = {
                "upload_mappings": [base_mapping], "upload_media_extensions": ".mkv",
                "upload_sidecar_extensions": ".nfo", "upload_include_sidecars": False,
                "upload_delete_source": False, "upload_generate_strm": False,
            }
            baseline = mapping_revision(base_mapping, base_config, canonical_source=root)
            mutations = [
                ("target", lambda m, c: m.__setitem__("target", "/New")),
                ("strm_target", lambda m, c: m.__setitem__("strm_target", str(Path(directory) / "new-strm"))),
                ("enabled", lambda m, c: m.__setitem__("enabled", False)),
                ("media_extensions", lambda m, c: c.__setitem__("upload_media_extensions", ".mp4")),
                ("sidecar_extensions", lambda m, c: c.__setitem__("upload_sidecar_extensions", ".srt")),
                ("include_sidecars", lambda m, c: c.__setitem__("upload_include_sidecars", True)),
                ("delete_source", lambda m, c: c.__setitem__("upload_delete_source", True)),
                ("generate_strm", lambda m, c: c.__setitem__("upload_generate_strm", True)),
            ]
            for name, mutate in mutations:
                mapping = dict(base_mapping); config = dict(base_config); config["upload_mappings"] = [mapping]
                mutate(mapping, config)
                with self.subTest(field=name):
                    self.assertNotEqual(
                        mapping_revision(mapping, config, canonical_source=root), baseline
                    )

    def test_real_config_sync_clears_tracker_queue_and_unstarted_inflight_only(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            paths = {name: root / f"{name}.mkv" for name in ("tracker", "queued", "unstarted", "started")}
            for path in paths.values(): path.write_bytes(path.name.encode())
            config = {
                "enabled": True,
                "upload_mappings": [{"id": "m", "source": str(root), "target": "/Old", "enabled": True}],
                "upload_media_extensions": ".mkv", "upload_include_sidecars": False,
            }
            queue = PendingUploadQueue()
            tracker = StabilityTracker(lambda: config, Mock())
            tracker.configure(); tracker._accepting = True
            self.assertTrue(tracker.submit_path(str(paths["tracker"])))
            old_revision = mapping_revision(config["upload_mappings"][0], config, canonical_source=str(root))
            candidates = {
                name: UploadCandidate(str(path), str(root), "m", file_signature(path), "watch", 1, old_revision)
                for name, path in paths.items() if name != "tracker"
            }
            queue.enqueue(candidates["unstarted"]); queue.enqueue(candidates["started"])
            taken = queue.take(2)
            queue.enqueue(candidates["queued"])
            started = next(item for item in taken if item.file_path == str(paths["started"]))
            other = next(item for item in taken if item.file_path == str(paths["unstarted"]))
            self.assertTrue(queue.mark_started(started))

            plugin = object.__new__(P115LiteAssistant)
            plugin._store = Mock(); plugin._store.get_config.side_effect = lambda: config
            plugin._api = Mock(); plugin._api.clear_invalid_upload_candidates.side_effect = queue.clear_invalid
            plugin._upload_stability = tracker; plugin._upload_watch = Mock()
            plugin._strm_recovery_blocked = False
            config["upload_mappings"][0]["target"] = "/New"

            plugin._sync_upload_watch()

            self.assertFalse(tracker._pending)
            self.assertNotIn(candidates["queued"].key, queue._queued)
            self.assertNotIn(other.key, queue._inflight)
            self.assertIn(started.key, queue._inflight)

    def test_queue_fifo_override_capacity_and_processed_ttl(self):
        clock = 100.0
        def candidate(name, signature=(1, 1, 1), queued=1.0):
            return UploadCandidate(f"/root/{name}", "/root", "m", signature, "watch", queued)
        queue = PendingUploadQueue(maxsize=2, ttl=10)
        a = candidate("a.mkv"); b = candidate("b.mkv"); newer = candidate("a.mkv", (2, 2, 2))
        self.assertTrue(queue.enqueue(a)); self.assertTrue(queue.enqueue(b)); self.assertTrue(queue.enqueue(newer))
        self.assertFalse(queue.enqueue(candidate("c.mkv")))
        self.assertEqual([x.file_path for x in queue.take(2)], [a.file_path, b.file_path])
        queue.finish(newer, processed=True)
        self.assertFalse(queue.enqueue(newer))
        processed_at = queue._processed[newer.key][1]
        with patch("app.plugins.p115liteassistant.upload_watch.monotonic", return_value=processed_at + 100):
            self.assertTrue(queue.enqueue(newer))
        self.assertEqual(UPLOAD_DEDUP_MAX, 4096)


if __name__ == "__main__":
    unittest.main()

class UploadCapacityRegressionTest(unittest.TestCase):
    def test_4097_stable_keys_busy_consumer_falls_back_to_full_rescan(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = {
                "enabled": True,
                "upload_mappings": [{"id": "m", "source": str(root), "target": "/Cloud"}],
                "upload_media_extensions": ".mkv",
            }
            queue = PendingUploadQueue(maxsize=4096)
            rescans = []
            def ready(candidate):
                outcome = queue.offer(candidate)
                if outcome == "full":
                    return {"success": False, "data": {"accepted": False, "full": True}}
                return {"success": True, "data": {"accepted": True}}
            tracker = StabilityTracker(
                lambda: config, ready, checks=1, maxsize=5000,
                full_rescan_callback=lambda source: rescans.append(source) or True,
            )
            tracker.configure(); tracker._accepting = True
            for index in range(4097):
                path = root / f"{index}.mkv"; path.write_bytes(b"x")
                self.assertTrue(tracker.submit_path(str(path)))
            self.assertEqual(tracker.tick(), 4096)
            self.assertEqual(len(queue._queued), 4096)
            self.assertTrue(tracker._full_rescan)
            self.assertEqual(tracker.tick(), 1)
            self.assertEqual(rescans, ["stability-full"])
            self.assertFalse(tracker._full_rescan)

    def test_stability_capacity_4097_compresses_atomically_to_full_marker(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = {"upload_mappings": [{"id": "m", "source": str(root), "target": "/Cloud"}],
                      "upload_media_extensions": ".mkv"}
            tracker = StabilityTracker(lambda: config, Mock(), maxsize=4096)
            tracker.configure(); tracker._accepting = True
            for index in range(4097):
                path = root / f"{index}.mkv"; path.write_bytes(b"x")
                self.assertTrue(tracker.submit_path(str(path)))
            self.assertEqual(len(tracker._pending), 0)
            self.assertTrue(tracker._full_rescan)
