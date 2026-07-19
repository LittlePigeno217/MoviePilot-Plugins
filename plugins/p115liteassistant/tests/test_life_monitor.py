from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic, sleep, time
import unittest
from unittest.mock import patch

import httpx
from p115pickcode import id_to_pickcode

from plugins.p115liteassistant.life_monitor import LifeEventRetryError, LifeMonitor


VALID_PICKCODE = id_to_pickcode(101)
COPY_PICKCODE = id_to_pickcode(102)


class FakeStore:
    def __init__(self, target: str):
        self.config = {
            "enabled": True,
            "life_monitor_enabled": True,
            "moviepilot_address": "http://moviepilot:3000",
            "strm_download_sidecars": True,
            "upload_sidecar_extensions": ".nfo",
            "strm_mappings": [
                {
                    "id": "movies",
                    "enabled": True,
                    "source_cid": "10",
                    "source_path": "/Movies",
                    "target_dir": target,
                }
            ],
        }
        self.records = {}
        self.cursor = {"from_time": 100, "from_id": 0}
        self.api_state = {}
        self.paths = {}

    def get_config(self):
        return dict(self.config)

    def get_strm_records(self):
        return dict(self.records)

    def save_strm_records(self, records):
        self.records = dict(records)

    def get_redirect_secret(self):
        return "life-test-secret-0123456789abcdef"

    def get_life_cursor(self):
        return dict(self.cursor)

    def save_life_cursor(self, from_time, from_id):
        self.cursor = {"from_time": from_time, "from_id": from_id}

    def get_life_api_state(self):
        return dict(self.api_state)

    def save_life_api_state(self, state):
        self.api_state = dict(state)

    def get_life_paths(self):
        return dict(self.paths)

    def save_life_paths(self, paths):
        self.paths = dict(paths)


class FakeClient:
    def __init__(self):
        self.items = {
            "501": {
                "fileid": "501",
                "path": "/Movies/Film.mkv",
                "type": "file",
                "name": "Film.mkv",
                "pickcode": VALID_PICKCODE,
                "size": 10,
                "mtime": 101,
            },
            "502": {
                "fileid": "502",
                "path": "/Movies/Copy.mkv",
                "type": "file",
                "name": "Copy.mkv",
                "pickcode": COPY_PICKCODE,
                "size": 11,
                "mtime": 102,
            },
            "10": {
                "fileid": "10",
                "path": "/Movies",
                "type": "dir",
                "name": "Movies",
                "mtime": 100,
            },
        }
        self.enabled_calls = 0
        self.lookup_ids = []
        self.directory_children = {}
        self.downloads = []

    def enable_life_events(self):
        self.enabled_calls += 1

    def get_item_by_id(self, file_id):
        self.lookup_ids.append(str(file_id))
        item = self.items.get(str(file_id))
        return dict(item) if item else None

    def iter_files(self, file_id):
        return iter([dict(item) for item in self.directory_children.get(str(file_id), [])])

    def get_life_events_page(self, **_kwargs):
        return {"events": [], "count": 0}

    def download_file(self, pickcode, output, create_parent=True):
        self.downloads.append((pickcode, Path(output)))
        if create_parent:
            Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(f"sidecar:{pickcode}", encoding="utf-8")


class LifeMonitorTest(unittest.TestCase):
    def monitor(self, target):
        self.client = FakeClient()
        self.store = FakeStore(target)
        return LifeMonitor(lambda: self.client, self.store, moviepilot_url_provider=lambda: "http://moviepilot:3000")

    def test_restart_request_survives_a_still_stopping_thread(self):
        with TemporaryDirectory() as directory:
            monitor = self.monitor(directory)
            first_enable_started = Event()
            release_first_enable = Event()
            enable_calls = 0

            def enable_life_events():
                nonlocal enable_calls
                enable_calls += 1
                if enable_calls == 1:
                    first_enable_started.set()
                    release_first_enable.wait(2)

            self.client.enable_life_events = enable_life_events
            try:
                monitor.start()
                self.assertTrue(first_enable_started.wait(1))
                monitor.stop(timeout=0)
                monitor.start()
                release_first_enable.set()

                deadline = monotonic() + 2
                while enable_calls < 2 and monotonic() < deadline:
                    sleep(0.01)

                self.assertGreaterEqual(enable_calls, 2)
                self.assertTrue(monitor.is_running)
            finally:
                release_first_enable.set()
                monitor.stop()

    def test_create_copy_rename_and_delete_keep_records_consistent(self):
        with TemporaryDirectory() as directory:
            monitor = self.monitor(directory)
            monitor.process_events(
                [
                    {"id": 1, "update_time": 101, "type": 2, "file_id": "501"},
                    {"id": 2, "update_time": 102, "type": 23, "file_id": "502"},
                ]
            )
            film = Path(directory) / "Film.strm"
            copy = Path(directory) / "Copy.strm"
            self.assertTrue(film.is_file())
            self.assertTrue(copy.is_file())
            self.assertIn("movies:Film.mkv", self.store.records)
            self.assertIn("movies:Copy.mkv", self.store.records)

            self.client.items["501"] = {
                **self.client.items["501"],
                "path": "/Movies/Renamed.mkv",
                "name": "Renamed.mkv",
                "mtime": 103,
            }
            monitor.process_events([{"id": 3, "update_time": 103, "type": 24, "file_id": "501"}])
            renamed = Path(directory) / "Renamed.strm"
            self.assertFalse(film.exists())
            self.assertTrue(renamed.is_file())
            self.assertIn("movies:Renamed.mkv", self.store.records)
            self.assertNotIn("movies:Film.mkv", self.store.records)

            monitor.process_events(
                [
                    {
                        "id": 4,
                        "update_time": 104,
                        "type": 22,
                        "file_id": "501",
                        "parent_id": "10",
                        "file_name": "Renamed.mkv",
                    }
                ]
            )
            self.assertFalse(renamed.exists())
            self.assertNotIn("movies:Renamed.mkv", self.store.records)
            self.assertTrue(copy.exists())

    def test_failed_event_does_not_advance_cursor(self):
        with TemporaryDirectory() as directory:
            monitor = self.monitor(directory)
            with self.assertRaises(Exception):
                monitor.process_events([{"id": 1, "update_time": 101, "type": 2, "file_id": "missing"}])
            self.assertEqual(self.store.cursor, {"from_time": 100, "from_id": 0})

    def test_batch_failure_keeps_first_cursor_and_record(self):
        with TemporaryDirectory() as directory:
            monitor = self.monitor(directory)
            with self.assertRaises(Exception):
                monitor.process_events(
                    [
                        {"id": 1, "update_time": 101, "type": 2, "file_id": "501"},
                        {"id": 2, "update_time": 102, "type": 2, "file_id": "missing"},
                    ]
                )

            self.assertEqual(self.store.cursor, {"from_time": 101, "from_id": 1})
            self.assertTrue((Path(directory) / "Film.strm").is_file())
            self.assertIn("movies:Film.mkv", self.store.records)

    def test_rename_to_non_media_removes_previous_strm(self):
        with TemporaryDirectory() as directory:
            monitor = self.monitor(directory)
            monitor.process_events([{"id": 1, "update_time": 101, "type": 2, "file_id": "501"}])
            self.client.items["501"] = {
                **self.client.items["501"],
                "path": "/Movies/Film.txt",
                "name": "Film.txt",
                "mtime": 102,
            }

            monitor.process_events([{"id": 2, "update_time": 102, "type": 24, "file_id": "501"}])

            self.assertFalse((Path(directory) / "Film.strm").exists())
            self.assertNotIn("movies:Film.mkv", self.store.records)
            self.assertEqual(self.store.paths["501"]["path"], "/Movies/Film.txt")

    def test_directory_move_scans_children_and_updates_paths(self):
        with TemporaryDirectory() as directory:
            monitor = self.monitor(directory)
            self.client.items["20"] = {
                "fileid": "20",
                "path": "/Movies/NewFolder",
                "type": "dir",
                "name": "NewFolder",
                "mtime": 102,
            }
            self.client.directory_children["20"] = [
                {
                    "fileid": "503",
                    "name": "Episode.mkv",
                    "pickcode": VALID_PICKCODE,
                    "size": 12,
                    "mtime": 102,
                    "rel_path": "Episode.mkv",
                }
            ]
            self.store.paths["20"] = {"path": "/Movies/OldFolder", "type": "dir"}

            monitor.process_events([{"id": 1, "update_time": 102, "type": 6, "file_id": "20", "parent_id": "10", "file_name": "NewFolder"}])

            self.assertTrue((Path(directory) / "NewFolder" / "Episode.strm").is_file())
            self.assertIn("movies:NewFolder/Episode.mkv", self.store.records)
            self.assertEqual(self.store.paths["20"]["path"], "/Movies/NewFolder")

    def test_directory_move_infers_old_path_and_removes_stale_children(self):
        with TemporaryDirectory() as directory:
            monitor = self.monitor(directory)
            self.client.items["20"] = {
                "fileid": "20",
                "path": "/Movies/NewFolder",
                "type": "dir",
                "name": "NewFolder",
                "mtime": 102,
            }
            self.client.directory_children["20"] = [
                {
                    "fileid": "503",
                    "name": "Episode.mkv",
                    "pickcode": VALID_PICKCODE,
                    "size": 12,
                    "mtime": 102,
                    "rel_path": "Episode.mkv",
                }
            ]
            old_episode = Path(directory) / "OldFolder" / "Episode.strm"
            old_stale = Path(directory) / "OldFolder" / "Removed.strm"
            old_episode.parent.mkdir(parents=True)
            old_episode.write_text("old", encoding="utf-8")
            old_stale.write_text("stale", encoding="utf-8")
            self.store.records.update(
                {
                    "movies:OldFolder/Episode.mkv": {
                        "path": str(old_episode),
                        "mapping_id": "movies",
                        "file_id": "503",
                        "cloud_path": "/Movies/OldFolder/Episode.mkv",
                    },
                    "movies:OldFolder/Removed.mkv": {
                        "path": str(old_stale),
                        "mapping_id": "movies",
                        "file_id": "505",
                        "cloud_path": "/Movies/OldFolder/Removed.mkv",
                    },
                }
            )

            monitor.process_events(
                [{"id": 1, "update_time": 102, "type": 6, "file_id": "20"}]
            )

            self.assertFalse(old_episode.exists())
            self.assertFalse(old_stale.exists())
            self.assertNotIn("movies:OldFolder/Removed.mkv", self.store.records)
            self.assertTrue((Path(directory) / "NewFolder" / "Episode.strm").is_file())

    def test_directory_move_and_delete_keep_sidecar_records_consistent(self):
        with TemporaryDirectory() as directory:
            monitor = self.monitor(directory)
            self.client.items["20"] = {
                "fileid": "20",
                "path": "/Movies/NewFolder",
                "type": "dir",
                "name": "NewFolder",
                "mtime": 102,
            }
            self.client.directory_children["20"] = [
                {
                    "fileid": "504",
                    "name": "Film.nfo",
                    "pickcode": VALID_PICKCODE,
                    "size": 12,
                    "mtime": 102,
                    "rel_path": "Film.nfo",
                }
            ]
            old_output = Path(directory) / "OldFolder" / "Film.nfo"
            old_output.parent.mkdir(parents=True)
            old_output.write_text("metadata", encoding="utf-8")
            self.store.records["movies:sidecar:OldFolder/Film.nfo"] = {
                "fingerprint": f"{VALID_PICKCODE}:12",
                "path": str(old_output),
                "kind": "sidecar",
                "mapping_id": "movies",
                "file_id": "504",
                "cloud_path": "/Movies/OldFolder/Film.nfo",
            }
            self.store.paths.update(
                {
                    "20": {"path": "/Movies/OldFolder", "type": "dir"},
                    "504": {"path": "/Movies/OldFolder/Film.nfo", "type": "file"},
                }
            )

            monitor.process_events([{"id": 1, "update_time": 102, "type": 6, "file_id": "20"}])

            moved_output = Path(directory) / "NewFolder" / "Film.nfo"
            self.assertFalse(old_output.exists())
            self.assertEqual(moved_output.read_text(encoding="utf-8"), "metadata")
            self.assertNotIn("movies:sidecar:OldFolder/Film.nfo", self.store.records)
            self.assertIn("movies:sidecar:NewFolder/Film.nfo", self.store.records)

            monitor.process_events([{"id": 2, "update_time": 103, "type": 22, "file_id": "504"}])

            self.assertFalse(moved_output.exists())
            self.assertNotIn("movies:sidecar:NewFolder/Film.nfo", self.store.records)

    def test_sidecar_create_and_update_downloads_latest_content(self):
        with TemporaryDirectory() as directory:
            monitor = self.monitor(directory)
            self.client.items["504"] = {
                "fileid": "504",
                "path": "/Movies/Film.nfo",
                "type": "file",
                "name": "Film.nfo",
                "pickcode": VALID_PICKCODE,
                "size": 12,
                "mtime": 101,
            }

            monitor.process_events(
                [{"id": 1, "update_time": 101, "type": 2, "file_id": "504"}]
            )

            output = Path(directory) / "Film.nfo"
            self.assertEqual(output.read_text(encoding="utf-8"), f"sidecar:{VALID_PICKCODE}")
            self.assertIn("movies:sidecar:Film.nfo", self.store.records)

            self.client.items["504"].update(
                {"pickcode": COPY_PICKCODE, "size": 13, "mtime": 102}
            )
            monitor.process_events(
                [{"id": 2, "update_time": 102, "type": 2, "file_id": "504"}]
            )

            self.assertEqual(output.read_text(encoding="utf-8"), f"sidecar:{COPY_PICKCODE}")
            self.assertEqual(len(self.client.downloads), 2)
            self.assertEqual(
                self.store.records["movies:sidecar:Film.nfo"]["fingerprint"],
                f"{COPY_PICKCODE}:13",
            )

    def test_sidecar_download_failure_keeps_cursor_and_record_state(self):
        with TemporaryDirectory() as directory:
            monitor = self.monitor(directory)
            self.client.items["504"] = {
                "fileid": "504",
                "path": "/Movies/Film.nfo",
                "type": "file",
                "name": "Film.nfo",
                "pickcode": VALID_PICKCODE,
                "size": 12,
                "mtime": 101,
            }
            self.client.download_file = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                OSError("read-only filesystem")
            )

            with self.assertRaises(LifeEventRetryError):
                monitor.process_events(
                    [{"id": 1, "update_time": 101, "type": 2, "file_id": "504"}]
                )

            self.assertEqual(self.store.cursor, {"from_time": 100, "from_id": 0})
            self.assertNotIn("movies:sidecar:Film.nfo", self.store.records)
            self.assertFalse((Path(directory) / "Film.nfo").exists())

    def test_cid_is_not_treated_as_file_id(self):
        with TemporaryDirectory() as directory:
            monitor = self.monitor(directory)
            with self.assertRaises(Exception):
                monitor.process_events(
                    [
                        {
                            "id": 1,
                            "update_time": 101,
                            "type": 2,
                            "cid": "501",
                            "path": "/Movies/Film.mkv",
                        }
                    ]
                )

            self.assertNotIn("501", self.client.lookup_ids)

    def test_delete_failure_keeps_record_and_cursor(self):
        with TemporaryDirectory() as directory:
            monitor = self.monitor(directory)
            monitor.process_events([{"id": 1, "update_time": 101, "type": 2, "file_id": "501"}])
            output = Path(directory) / "Film.strm"

            with patch(
                "plugins.p115liteassistant.life_monitor.Path.unlink",
                side_effect=OSError("read-only filesystem"),
            ):
                with self.assertRaises(Exception):
                    monitor.process_events([{"id": 2, "update_time": 102, "type": 22, "file_id": "501"}])

            self.assertEqual(self.store.cursor, {"from_time": 101, "from_id": 1})
            self.assertIn("movies:Film.mkv", self.store.records)
            self.assertTrue(output.is_file())

    def test_ios_405_uses_web_and_records_fallback(self):
        with TemporaryDirectory() as directory:
            monitor = self.monitor(directory)
            response = httpx.Response(
                405,
                request=httpx.Request("GET", "https://proapi.115.com/ios/behavior/detail"),
            )
            apps = []

            def get_page(**kwargs):
                apps.append(kwargs["app"])
                if kwargs["app"] == "ios":
                    raise httpx.HTTPStatusError(
                        "405",
                        request=response.request,
                        response=response,
                    )
                return {"events": [], "count": 0}

            self.client.get_life_events_page = get_page
            self.assertEqual(monitor._fetch_events(100, 0), [])
            self.assertEqual(apps, ["ios", "web"])
            self.assertEqual(self.store.api_state["ios_405_count"], 1)

    def test_pagination_uses_cursor_and_stops_at_boundary(self):
        with TemporaryDirectory() as directory:
            monitor = self.monitor(directory)
            monitor.EVENT_PAGE_COOLDOWN = 0
            monitor.FIRST_EVENT_PAGE_SIZE = 2
            base = int(time())
            calls = []

            def get_page(**kwargs):
                calls.append(kwargs)
                if kwargs["offset"] == 0:
                    return {
                        "events": [
                            {"id": 3, "update_time": base + 3, "type": 2},
                            {"id": 2, "update_time": base + 2, "type": 2},
                        ],
                        "count": 4,
                    }
                return {
                    "events": [
                        {"id": 4, "update_time": base + 4, "type": 2},
                        {"id": 1, "update_time": base, "type": 2},
                    ],
                    "count": 4,
                }

            self.client.get_life_events_page = get_page
            events = monitor._fetch_events(base, 0)

            self.assertEqual([event["id"] for event in events], [1, 2, 3, 4])
            self.assertEqual(
                [(call["offset"], call["limit"]) for call in calls],
                [(0, 2), (2, 1000)],
            )
            self.assertTrue(all(call["date"] for call in calls))

    def test_pagination_is_not_capped_before_reaching_all_events(self):
        with TemporaryDirectory() as directory:
            monitor = self.monitor(directory)
            monitor.EVENT_PAGE_COOLDOWN = 0
            monitor.FIRST_EVENT_PAGE_SIZE = 1
            monitor.EVENT_PAGE_SIZE = 1

            def get_page(**kwargs):
                offset = kwargs["offset"]
                return {
                    "events": [
                        {
                            "id": offset + 1,
                            "update_time": 101 + offset,
                            "type": 2,
                        }
                    ],
                    "count": 65,
                }

            self.client.get_life_events_page = get_page
            events = monitor._fetch_events(100, 0)

            self.assertEqual(len(events), 65)
            self.assertEqual(events[0]["id"], 1)
            self.assertEqual(events[-1]["id"], 65)

    def test_repeated_pagination_page_keeps_cursor_for_retry(self):
        with TemporaryDirectory() as directory:
            monitor = self.monitor(directory)
            monitor.EVENT_PAGE_COOLDOWN = 0
            monitor.FIRST_EVENT_PAGE_SIZE = 2
            monitor.EVENT_PAGE_SIZE = 2

            def get_page(**_kwargs):
                return {
                    "events": [
                        {"id": 2, "update_time": 102, "type": 2},
                        {"id": 1, "update_time": 101, "type": 2},
                    ],
                    "count": 10,
                }

            self.client.get_life_events_page = get_page
            with self.assertRaises(LifeEventRetryError):
                monitor._fetch_events(100, 0)


if __name__ == "__main__":
    unittest.main()
