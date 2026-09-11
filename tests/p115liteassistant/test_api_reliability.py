from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
from time import sleep, time
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from p115pickcode import id_to_pickcode
from app.plugins.p115liteassistant import P115LiteAssistant
from app.plugins.p115liteassistant.api import Api as ProductionApi
from app.plugins.p115liteassistant.client import PlaybackCopy, U115AccessLimitError, UploadResult
from app.plugins.p115liteassistant.log_utils import safe_error_text
from app.plugins.p115liteassistant.records import IncrementalRecordStore
from app.plugins.p115liteassistant.upload_watch import (
    PendingUploadQueue,
    UploadCandidate,
    file_signature,
    mapping_revision,
)
from app.plugins.p115liteassistant.strm import build_redirect_signature


from tests.p115liteassistant.helpers import make_test_journal


def Api(client_provider, store, *args, journal=None, **kwargs):
    return ProductionApi(
        client_provider, store, *args,
        journal=journal or make_test_journal(store), **kwargs
    )


VALID_PICKCODE = id_to_pickcode(1)
COPY_PICKCODE = id_to_pickcode(2)
TEST_REDIRECT_SECRET = "test-redirect-secret-0123456789abcdef"
VALID_SIGNATURE = build_redirect_signature(TEST_REDIRECT_SECRET, VALID_PICKCODE)


class FakeStore:
    def __init__(self):
        self.config = {
            "enabled": True,
            "checkin_enabled": True,
            "checkin_time_range": "06:00-09:00",
        }
        self.history = []
        self.schedule = {"next_run_ts": 0}

    def get_config(self):
        return dict(self.config)

    def update_config(self, updates):
        self.config.update(dict(updates))
        return dict(self.config)

    def append_history(self, entry):
        self.history.append(entry)

    def get_history(self):
        return list(self.history)

    def get_checkin_schedule(self):
        return dict(self.schedule)

    def save_checkin_schedule(self, state):
        self.schedule = dict(state)

    @staticmethod
    def get_redirect_secret():
        return TEST_REDIRECT_SECRET


class FakeClient:
    def __init__(self):
        self.browse_calls = 0
        self.download_calls = 0
        self.download_requests = []
        self.copy_calls = []
        self.deleted = []
        self.checkin_calls = 0

    def is_authenticated(self) -> bool:
        return False

    def get_dir_list(self, cid):
        self.browse_calls += 1
        return [
            {"fn": "Zeta", "cid": "2"},
            {"fn": "Alpha", "cid": "1"},
        ]

    def get_download_url(self, pickcode, user_agent="", mode=""):
        self.download_calls += 1
        self.download_requests.append((pickcode, user_agent))
        return f"https://download.example/{pickcode}?t={int(time()) + 3600}"

    def create_playback_copy(self, pickcode, mode=""):
        self.copy_calls.append(pickcode)
        return PlaybackCopy(file_id="copy-file-id", pickcode=COPY_PICKCODE, auth_mode=mode)

    def delete_file(self, file_id, mode=""):
        self.deleted.append(file_id)

    def checkin(self):
        self.checkin_calls += 1
        return {"already": False, "continuous_day": 3, "points_num": 5, "message": "签到成功"}


class CoordinatedDownloadClient(FakeClient):
    def __init__(self):
        super().__init__()
        self._download_call_lock = threading.Lock()
        self._download_call_count = 0
        self._second_download_started = threading.Event()

    def get_download_url(self, pickcode, user_agent="", mode=""):
        with self._download_call_lock:
            self._download_call_count += 1
            call_number = self._download_call_count
        if call_number == 1:
            self._second_download_started.wait(timeout=0.1)
        else:
            self._second_download_started.set()
        return super().get_download_url(pickcode, user_agent=user_agent, mode=mode)


class ApiReliabilityTest(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.store = FakeStore()
        self.api = Api(lambda: self.client, self.store)

    @staticmethod
    def request(user_agent="Player/1.0"):
        return Request(
            {
                "type": "http",
                "method": "GET",
                "scheme": "http",
                "server": ("127.0.0.1", 3001),
                "path": "/redirect",
                "query_string": b"",
                "headers": [(b"user-agent", user_agent.encode("utf-8"))],
            }
        )

    @staticmethod
    def signed_redirect(api, request, file_name=""):
        return api.redirect(
            request,
            VALID_PICKCODE,
            file_name,
            VALID_SIGNATURE,
        )

    def test_plugin_startup_recovers_before_watchers(self):
        plugin = object.__new__(P115LiteAssistant)
        plugin._store = Mock()
        plugin._api = Mock()
        plugin._api.cloud_task_lock = threading.Lock()
        plugin._life_monitor = Mock()
        plugin._strm_watch = Mock()
        plugin._upload_watch = Mock()
        plugin._upload_watch_config_signature = Mock(return_value=(True, ()))
        order = []
        plugin._recover_strm_commits = Mock(
            side_effect=lambda _stage: order.append("recover") or []
        )
        plugin._migrate_legacy_allowlist_on_startup = Mock(
            side_effect=lambda: order.append("migrate")
        )
        plugin._sync_life_monitor = Mock(side_effect=lambda: order.append("life"))
        plugin._sync_strm_watch = Mock(side_effect=lambda: order.append("strm"))
        plugin._sync_upload_watch = Mock(side_effect=lambda: order.append("upload"))

        plugin.init_plugin()

        self.assertEqual(order, ["recover", "migrate", "life", "strm", "upload"])
        self.assertFalse(plugin._strm_recovery_blocked)

    def test_plugin_startup_recovery_failure_stops_all_watchers(self):
        from app.plugins.p115liteassistant.strm import StrmRecoveryBlockedError

        plugin = object.__new__(P115LiteAssistant)
        plugin._store = Mock()
        plugin._api = Mock()
        plugin._api.cloud_task_lock = threading.Lock()
        plugin._life_monitor = Mock()
        plugin._strm_watch = Mock()
        plugin._upload_watch = Mock()
        plugin._recover_strm_commits = Mock(
            side_effect=StrmRecoveryBlockedError("broken")
        )
        plugin._migrate_legacy_allowlist_on_startup = Mock()
        plugin._sync_life_monitor = Mock()
        plugin._sync_strm_watch = Mock()
        plugin._sync_upload_watch = Mock()

        plugin.init_plugin()

        plugin._life_monitor.stop.assert_called_once_with()
        plugin._strm_watch.stop.assert_called_once_with()
        plugin._upload_watch.stop.assert_called_once_with()
        plugin._sync_life_monitor.assert_not_called()
        plugin._sync_strm_watch.assert_not_called()
        plugin._sync_upload_watch.assert_not_called()
        self.assertTrue(plugin._strm_recovery_blocked)

    @staticmethod
    def recovery_plugin(config=None):
        plugin = object.__new__(P115LiteAssistant)
        plugin._store = Mock()
        plugin._store.get_config.return_value = dict(config or {})
        plugin._api = Mock()
        plugin._api.cloud_task_lock = threading.Lock()
        plugin._life_monitor = Mock()
        plugin._strm_watch = Mock()
        plugin._upload_watch = Mock()
        plugin._client = Mock()
        plugin._client_signature = ("old",)
        plugin._upload_watch_signature = None
        plugin._strm_recovery_blocked = True
        return plugin


    def test_client_profile_is_part_of_cache_signature_and_token_save_does_not_rebuild(self):
        plugin = object.__new__(P115LiteAssistant)
        plugin._store = Mock()
        plugin._store.get_config.return_value = {
            "cookie": "cookie", "tokens": {"access_token": "token"},
            "login_client_type": "web", "rate_limit_profile": "balanced",
        }
        plugin._store.update_config = Mock()
        plugin._client = None
        plugin._client_signature = None
        with patch("app.plugins.p115liteassistant.U115Client") as client_type:
            first = plugin._get_client()
            plugin._save_client_tokens({"access_token": "fresh"})
            second = plugin._get_client()
            self.assertIs(first, second)
            client_type.assert_called_once()
            self.assertEqual(plugin._client_signature, ("cookie", "web", "balanced"))

            plugin._store.get_config.return_value["rate_limit_profile"] = "conservative"
            plugin._get_client()
            self.assertEqual(client_type.call_count, 2)
            self.assertEqual(
                client_type.call_args.kwargs["rate_limit_profile"], "conservative"
            )

    def test_config_save_keeps_components_stopped_when_recovery_still_blocked(self):
        from app.plugins.p115liteassistant.strm import StrmRecoveryBlockedError

        plugin = self.recovery_plugin({"enabled": True})
        plugin._recover_strm_commits = Mock(
            side_effect=StrmRecoveryBlockedError("broken")
        )

        plugin._on_config_saved()

        plugin._life_monitor.stop.assert_called_once_with()
        plugin._strm_watch.stop.assert_called_once_with()
        plugin._upload_watch.stop.assert_called_once_with()
        plugin._life_monitor.start.assert_not_called()
        plugin._strm_watch.start.assert_not_called()
        plugin._upload_watch.start.assert_not_called()
        self.assertTrue(plugin._strm_recovery_blocked)

    def test_config_save_restarts_components_after_recovery_succeeds(self):
        config = {
            "enabled": True,
            "life_monitor_enabled": True,
            "strm_mappings": [{"enabled": True}],
            "strm_delete_cloud_on_missing": True,
            "strm_delete_watch": True,
            "upload_mappings": [{"id": "movies", "source": "/media"}],
        }
        plugin = self.recovery_plugin(config)
        plugin._upload_watch_signature = plugin._upload_watch_config_signature(config)
        plugin._recover_strm_commits = Mock(return_value=[])

        plugin._on_config_saved()

        plugin._recover_strm_commits.assert_called_once_with("保存配置")
        plugin._life_monitor.start.assert_called_once_with()
        plugin._strm_watch.start.assert_called_once_with()
        plugin._upload_watch.start.assert_called_once_with()
        self.assertFalse(plugin._strm_recovery_blocked)

    def test_sync_components_defend_against_recovery_block(self):
        plugin = self.recovery_plugin(
            {
                "enabled": True,
                "life_monitor_enabled": True,
                "strm_mappings": [{"enabled": True}],
                "strm_delete_cloud_on_missing": True,
                "strm_delete_watch": True,
                "upload_mappings": [{"source": "/media"}],
            }
        )

        plugin._sync_life_monitor()
        plugin._sync_strm_watch()
        plugin._sync_upload_watch()

        plugin._life_monitor.stop.assert_called_once_with()
        plugin._strm_watch.stop.assert_called_once_with()
        plugin._upload_watch.stop.assert_called_once_with()
        plugin._life_monitor.start.assert_not_called()
        plugin._strm_watch.start.assert_not_called()
        plugin._upload_watch.start.assert_not_called()

    def test_recovery_alert_bypasses_disabled_strm_notification_and_deduplicates(self):
        plugin = object.__new__(P115LiteAssistant)
        plugin._store = Mock()
        plugin._store.get_config.return_value = {"strm_notify": False}
        plugin._strm_journal = Mock()
        plugin._strm_journal.recover_all.side_effect = RuntimeError("broken")
        plugin._strm_recovery_alerted = False
        plugin.post_message = Mock()

        for _ in range(2):
            with self.assertRaisesRegex(Exception, "broken"):
                plugin._recover_strm_commits("插件启动")

        plugin.post_message.assert_called_once()
        self.assertEqual(plugin.post_message.call_args.kwargs["mtype"].name, "Plugin")
        self.assertNotIn("strm_notify", plugin.post_message.call_args.kwargs)

    def test_cloud_task_recovers_before_target(self):
        order = []
        done = threading.Event()
        api = Api(
            lambda: self.client,
            self.store,
            recover_strm_commits=lambda stage: order.append(("recover", stage)) or [],
        )

        result = api._start(
            "strm",
            lambda: (order.append(("target", "")), done.set()),
            "started",
        )

        self.assertTrue(result["success"])
        self.assertTrue(done.wait(1))
        self.assertEqual([item[0] for item in order], ["recover", "target"])

    def test_cloud_task_recovery_failure_blocks_target_and_drain(self):
        from app.plugins.p115liteassistant.strm import StrmRecoveryBlockedError

        attempted = threading.Event()
        target = Mock(side_effect=lambda: attempted.set())
        api = Api(
            lambda: self.client,
            self.store,
            recover_strm_commits=lambda _stage: (_ for _ in ()).throw(
                StrmRecoveryBlockedError("broken journal")
            ),
        )
        drained = threading.Event()
        api._drain_pending_tasks = Mock(side_effect=lambda _kind: drained.set())

        self.assertTrue(api._start("upload", target, "started")["success"])
        for _ in range(100):
            if "upload" not in api._running:
                break
            sleep(0.01)
        self.assertFalse(attempted.is_set())
        self.assertFalse(drained.is_set())
        target.assert_not_called()

    def test_browse_115_sorts_and_caches_short_lived_results(self):
        first = self.api.browse_115("0")
        second = self.api.browse_115("0")

        self.assertEqual([item["name"] for item in first["items"]], ["Alpha", "Zeta"])
        self.assertEqual(second["items"], first["items"])
        self.assertEqual(self.client.browse_calls, 1)

    def test_config_save_cannot_replace_internal_tokens(self):
        self.store.config["tokens"] = {"access_token": "internal"}

        result = self.api.save_config({"enabled": False, "tokens": {"access_token": "injected"}})

        self.assertTrue(result["success"])
        self.assertFalse(self.store.config["enabled"])
        self.assertEqual(self.store.config["tokens"], {"access_token": "internal"})

    def test_config_save_clears_old_open_tokens_when_cookie_account_changes(self):
        self.store.config.update(
            {
                "cookie": "UID=1_R2_0; CID=old",
                "tokens": {"access_token": "old-account"},
            }
        )

        result = self.api.save_config({"cookie": "UID=2_R2_0; CID=new"})

        self.assertTrue(result["success"])
        self.assertEqual(self.store.config["tokens"], {})

    def test_config_save_validates_redirect_mode_and_moviepilot_address(self):
        invalid_mode = self.api.save_config({"link_redirect_mode": "fallback"})
        invalid_address = self.api.save_config({"moviepilot_address": "moviepilot:3000"})
        valid = self.api.save_config(
            {
                "link_redirect_mode": "OPEN",
                "moviepilot_address": "https://moviepilot.example/mp",
            }
        )
        partial = self.api.save_config({"enabled": False})

        self.assertFalse(invalid_mode["success"])
        self.assertFalse(invalid_address["success"])
        self.assertTrue(valid["success"])
        self.assertTrue(partial["success"])
        self.assertEqual(self.store.config["link_redirect_mode"], "open")

    def test_trigger_strm_rejects_invalid_configuration_before_starting_thread(self):
        missing_address = self.api.trigger_strm()
        self.store.config.update(
            {
                "moviepilot_address": "https://moviepilot.example",
                "strm_mappings": [
                    {
                        "enabled": True,
                        "source_cid": "root",
                        "target_dir": "",
                    }
                ],
            }
        )
        missing_target = self.api.trigger_strm()

        self.assertFalse(missing_address["success"])
        self.assertIn("MoviePilot", missing_address["message"])
        self.assertFalse(missing_target["success"])
        self.assertIn("输出目录", missing_target["message"])

        self.store.config["strm_mappings"][0]["target_dir"] = "/strm"
        with patch.object(self.api, "_start", return_value={"success": True}) as start:
            valid = self.api.trigger_strm()

        self.assertTrue(valid["success"])
        start.assert_called_once()

    @staticmethod
    def _gap_row(row_id, channel_id, missing=None, channel_ids=None):
        row = {
            "id": row_id,
            "channel_id": channel_id,
            "missing": [2] if missing is None else missing,
        }
        if channel_ids is not None:
            row["channel_ids"] = channel_ids
        return row

    def _configure_gap_mappings(self):
        mappings = [
            {
                "id": "tv-a",
                "enabled": True,
                "source_cid": "101",
                "target_dir": "/strm/a",
            },
            {
                "id": "tv-b",
                "enabled": True,
                "source_cid": "102",
                "target_dir": "/strm/b",
            },
        ]
        self.store.config.update(
            {
                "moviepilot_address": "https://moviepilot.example",
                "strm_mappings": mappings,
            }
        )
        return mappings

    def test_gap_fill_triggers_single_enabled_mapping(self):
        mappings = self._configure_gap_mappings()
        self.api._ledger_rows = Mock(
            return_value=([self._gap_row("tv|A|2026|1", "tv-a")], {})
        )
        captured = {}

        def start(kind, target, message):
            captured.update(kind=kind, message=message)
            target()
            return {"success": True, "message": message, "data": {}}

        self.api._start = Mock(side_effect=start)
        self.api.run_strm = Mock()

        result = self.api.task_gap_fill({"row_ids": "tv|A|2026|1"})

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["triggered"], 1)
        self.assertEqual(result["data"]["mapping_ids"], ["tv-a"])
        self.assertEqual(captured["kind"], "strm")
        self.assertIn("同步 1 条 STRM 通道", captured["message"])
        self.api._ledger_rows.assert_called_once_with(with_seeding=False)
        self.api.run_strm.assert_called_once_with(
            "https://moviepilot.example",
            [mappings[0]],
            manual=True,
            strm_incremental=True,
        )

    def test_gap_fill_forces_incremental_when_global_setting_is_full(self):
        mappings = self._configure_gap_mappings()
        self.store.config["strm_incremental"] = False
        self.api._ledger_rows = Mock(
            return_value=([self._gap_row("tv|A|2026|1", "tv-a")], {})
        )

        def start(_kind, target, _message):
            target()
            return {"success": True}

        self.api._start = Mock(side_effect=start)
        self.api.run_strm = Mock()

        self.api.task_gap_fill({"row_ids": ["tv|A|2026|1"]})

        self.api.run_strm.assert_called_once_with(
            "https://moviepilot.example",
            [mappings[0]],
            manual=True,
            strm_incremental=True,
        )

    def test_gap_fill_deduplicates_rows_on_same_mapping(self):
        self._configure_gap_mappings()
        self.api._ledger_rows = Mock(
            return_value=(
                [
                    self._gap_row("tv|A|2026|1", "tv-a"),
                    self._gap_row("tv|B|2026|1", "tv-a"),
                ],
                {},
            )
        )
        self.api._start = Mock(return_value={"success": True})

        result = self.api.task_gap_fill(
            {"row_ids": ["tv|A|2026|1", "tv|B|2026|1"]}
        )

        self.assertEqual(result["data"]["triggered"], 1)
        self.assertEqual(result["data"]["deduplicated"], 1)
        self.assertEqual(result["data"]["skipped"], 0)
        self.assertEqual(result["data"]["mapping_ids"], ["tv-a"])

    def test_gap_fill_counts_each_invalid_mapping_reason(self):
        self._configure_gap_mappings()
        self.store.config["strm_mappings"].append(
            {
                "id": "tv-off",
                "enabled": False,
                "source_cid": "103",
                "target_dir": "/strm/off",
            }
        )
        self.store.config["upload_mappings"] = [
            {"id": "upload-a", "enabled": True, "source": "/inbox"}
        ]
        rows = [
            self._gap_row("missing-channel", ""),
            self._gap_row("untracked", "untracked"),
            self._gap_row("once", "once:99"),
            self._gap_row("upload", "upload-a"),
            self._gap_row("disabled", "tv-off"),
            self._gap_row("deleted", "tv-deleted"),
        ]
        self.api._ledger_rows = Mock(return_value=(rows, {}))
        self.api._start = Mock()

        result = self.api.task_gap_fill({"row_ids": [row["id"] for row in rows]})

        self.assertFalse(result["success"])
        self.assertEqual(result["data"]["triggered"], 0)
        self.assertEqual(result["data"]["skipped"], 6)
        self.assertEqual(
            result["data"]["reasons"],
            {
                "missing_channel": 1,
                "untracked": 1,
                "once_mapping": 1,
                "upload_mapping": 1,
                "disabled_mapping": 1,
                "missing_mapping": 1,
            },
        )
        self.api._start.assert_not_called()

    def test_gap_fill_skips_stale_or_no_longer_missing_rows(self):
        self._configure_gap_mappings()
        self.api._ledger_rows = Mock(
            return_value=([self._gap_row("complete", "tv-a", missing=[])], {})
        )
        self.api._start = Mock()

        result = self.api.task_gap_fill(
            {"row_ids": ["gone", "complete", "gone"]}
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["data"]["requested"], 2)
        self.assertEqual(
            result["data"]["reasons"], {"not_found": 1, "no_missing": 1}
        )
        self.api._start.assert_not_called()

    def test_gap_fill_busy_does_not_queue_and_preserves_summary(self):
        self._configure_gap_mappings()
        self.api._ledger_rows = Mock(
            return_value=([self._gap_row("tv|A|2026|1", "tv-a")], {})
        )
        self.api.run_strm = Mock()
        self.api._cloud_task_lock.acquire()
        try:
            result = self.api.task_gap_fill({"row_ids": ["tv|A|2026|1"]})
        finally:
            self.api._cloud_task_lock.release()

        self.assertFalse(result["success"])
        self.assertIn("115 数据任务正在运行", result["message"])
        self.assertEqual(result["data"]["mapping_ids"], ["tv-a"])
        self.assertFalse(self.api._upload_queue)
        self.assertFalse(self.api._pending_sweep_all)
        self.assertEqual(self.api._pending_sweep_paths, set())
        self.api.run_strm.assert_not_called()

    def test_gap_fill_runs_two_mappings_in_one_task_in_config_order(self):
        mappings = self._configure_gap_mappings()
        self.api._ledger_rows = Mock(
            return_value=(
                [
                    self._gap_row("tv|B|2026|1", "tv-b"),
                    self._gap_row("tv|A|2026|1", "tv-a"),
                ],
                {},
            )
        )
        captured = []

        def start(kind, target, message):
            captured.append((kind, message))
            target()
            return {"success": True}

        self.api._start = Mock(side_effect=start)
        self.api.run_strm = Mock()

        result = self.api.task_gap_fill(
            {"row_ids": ["tv|B|2026|1", "tv|A|2026|1"]}
        )

        self.assertEqual(result["data"]["mapping_ids"], ["tv-a", "tv-b"])
        self.assertEqual(result["data"]["triggered"], 2)
        self.api._start.assert_called_once()
        self.api.run_strm.assert_called_once_with(
            "https://moviepilot.example",
            mappings,
            manual=True,
            strm_incremental=True,
        )
        self.assertEqual(captured[0][0], "strm")

    def test_gap_fill_runs_all_mappings_for_one_multi_mapping_row(self):
        mappings = self._configure_gap_mappings()
        self.api._ledger_rows = Mock(
            return_value=(
                [
                    self._gap_row(
                        "tv|A|2026|1",
                        "tv-a",
                        channel_ids=["tv-a", "tv-b"],
                    )
                ],
                {},
            )
        )
        captured = []

        def start(kind, target, message):
            captured.append((kind, message))
            target()
            return {"success": True}

        self.api._start = Mock(side_effect=start)
        self.api.run_strm = Mock()

        result = self.api.task_gap_fill({"row_ids": ["tv|A|2026|1"]})

        self.assertEqual(result["data"]["mapping_ids"], ["tv-a", "tv-b"])
        self.assertEqual(result["data"]["triggered"], 2)
        self.api._start.assert_called_once()
        self.api.run_strm.assert_called_once_with(
            "https://moviepilot.example",
            mappings,
            manual=True,
            strm_incremental=True,
        )
        self.assertEqual(captured[0][0], "strm")

    def test_gap_fill_preflight_rejects_invalid_selected_mapping_before_start(self):
        invalid_cases = (
            ({"moviepilot_address": "ftp://moviepilot.example"}, "MoviePilot"),
            ({"source_cid": ""}, "源目录"),
            ({"target_dir": ""}, "输出目录"),
        )
        for updates, message in invalid_cases:
            with self.subTest(updates=updates):
                self._configure_gap_mappings()
                if "moviepilot_address" in updates:
                    self.store.config["moviepilot_address"] = updates["moviepilot_address"]
                else:
                    self.store.config["strm_mappings"][0].update(updates)
                self.api._ledger_rows = Mock(
                    return_value=([self._gap_row("tv|A|2026|1", "tv-a")], {})
                )
                self.api._start = Mock()

                result = self.api.task_gap_fill({"row_ids": ["tv|A|2026|1"]})

                self.assertFalse(result["success"])
                self.assertIn(message, result["message"])
                self.api._start.assert_not_called()

    def test_gap_fill_preflight_ignores_invalid_unselected_mapping(self):
        self._configure_gap_mappings()
        self.store.config["strm_mappings"][1]["target_dir"] = ""
        self.api._ledger_rows = Mock(
            return_value=([self._gap_row("tv|A|2026|1", "tv-a")], {})
        )
        self.api._start = Mock(return_value={"success": True})

        result = self.api.task_gap_fill({"row_ids": ["tv|A|2026|1"]})

        self.assertTrue(result["success"])
        self.api._start.assert_called_once()

    def test_gap_fill_validates_row_id_shape_and_limit(self):
        self.assertFalse(self.api.task_gap_fill({})["success"])
        self.assertFalse(self.api.task_gap_fill({"row_ids": []})["success"])
        self.assertFalse(self.api.task_gap_fill({"row_ids": ["ok", 1]})["success"])
        too_many = [f"row-{index}" for index in range(201)]
        result = self.api.task_gap_fill({"row_ids": too_many})
        self.assertFalse(result["success"])
        self.assertIn("200", result["message"])

    def test_trigger_upload_validates_strm_generation_before_starting_thread(self):
        self.store.config.update(
            {
                "upload_generate_strm": True,
                "upload_mappings": [
                    {
                        "enabled": True,
                        "source": "/source",
                        "target": "/cloud",
                        "strm_target": "",
                    }
                ],
            }
        )
        missing_address = self.api.trigger_upload()
        self.store.config["moviepilot_address"] = "https://moviepilot.example"
        missing_target = self.api.trigger_upload()

        self.assertFalse(missing_address["success"])
        self.assertIn("MoviePilot", missing_address["message"])
        self.assertFalse(missing_target["success"])
        self.assertIn("输出目录", missing_target["message"])

        self.store.config["upload_mappings"][0]["strm_target"] = "/strm"
        with patch.object(self.api, "_start", return_value={"success": True}) as start:
            valid = self.api.trigger_upload({"incremental": False})

        self.assertTrue(valid["success"])
        start.assert_called_once()

    def test_config_change_invalidates_redirect_cache(self):
        self.store.config["link_redirect_mode"] = "cookie"
        modes = []
        real_get_download_url = self.client.get_download_url

        def get_download_url(pickcode, user_agent="", mode=""):
            modes.append(mode)
            return real_get_download_url(pickcode, user_agent=user_agent, mode=mode)

        with patch.object(self.client, "get_download_url", side_effect=get_download_url):
            first = self.signed_redirect(self.api, self.request("Player-A"))
            saved = self.api.save_config({"link_redirect_mode": "open"})
            second = self.signed_redirect(self.api, self.request("Player-A"))

        self.assertTrue(saved["success"])
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(modes, ["cookie", "open"])

    def test_redirect_uses_pickcode_and_user_agent_cache(self):
        request = self.request("Player-A")
        first = self.signed_redirect(self.api, request, "电影.mkv")
        second = self.signed_redirect(self.api, request, "电影.mkv")

        self.assertIn(f"https://download.example/{VALID_PICKCODE}", first.headers["location"])
        self.assertEqual(second.headers["location"], first.headers["location"])
        self.assertEqual(self.client.download_calls, 1)
        self.assertEqual(self.client.download_requests, [(VALID_PICKCODE, "Player-A")])
        self.assertTrue(first.headers["content-disposition"].startswith("inline;"))
        self.assertIn("filename*=UTF-8''", first.headers["content-disposition"])

    def test_redirect_rejects_invalid_pickcode_before_requesting_115(self):
        response = self.api.redirect(self.request(), "pick")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.download_calls, 0)

    def test_redirect_rejects_unsigned_valid_pickcode(self):
        response = self.api.redirect(self.request(), VALID_PICKCODE)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.download_calls, 0)

    def test_redirect_signature_cannot_authorize_another_pickcode(self):
        response = self.api.redirect(
            self.request(),
            COPY_PICKCODE,
            sign=VALID_SIGNATURE,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.download_calls, 0)

    def test_redirect_route_is_anonymous_and_supports_media_probe_methods(self):
        plugin = object.__new__(P115LiteAssistant)
        plugin._api = self.api
        route = next(item for item in plugin.get_api() if item["path"] == "/redirect")
        app = FastAPI()
        app.add_api_route(route["path"], route["endpoint"], methods=route["methods"])

        self.assertTrue(route["allow_anonymous"])
        self.assertEqual(set(route["methods"]), {"GET", "POST", "HEAD"})
        with TestClient(app) as client:
            for method in route["methods"]:
                response = client.request(
                    method,
                    "/redirect",
                    params={
                        "pickcode": VALID_PICKCODE,
                        "file_name": "电影.iso",
                        "sign": VALID_SIGNATURE,
                    },
                    follow_redirects=False,
                )
                self.assertEqual(response.status_code, 302, method)
                self.assertIn(VALID_PICKCODE, response.headers["location"])
                self.assertTrue(response.headers["content-disposition"].startswith("inline;"))
                self.assertIn("filename*=UTF-8''", response.headers["content-disposition"])

    def test_same_playback_copies_file_for_second_user_agent_and_schedules_cleanup(self):
        self.store.config["same_playback"] = True
        first = self.signed_redirect(self.api, self.request("Player-A"))

        with patch.object(self.api, "_schedule_playback_copy_cleanup") as cleanup:
            second = self.signed_redirect(self.api, self.request("Player-B"))

        self.assertIn(f"https://download.example/{VALID_PICKCODE}", first.headers["location"])
        self.assertIn(f"https://download.example/{COPY_PICKCODE}", second.headers["location"])
        self.assertEqual(self.client.copy_calls, [VALID_PICKCODE])
        self.assertEqual(self.client.download_requests[-1], (COPY_PICKCODE, "Player-B"))
        cleanup.assert_called_once()
        self.assertEqual(cleanup.call_args.args[:3], (self.client, "copy-file-id", "cookie"))
        self.assertGreater(cleanup.call_args.args[3], 3600)

    def test_redirect_singleflight_rechecks_same_user_agent_cache(self):
        client = CoordinatedDownloadClient()
        api = Api(lambda: client, self.store)
        barrier = threading.Barrier(3)

        def redirect():
            barrier.wait()
            return self.signed_redirect(api, self.request("Player-A"))

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(redirect) for _ in range(2)]
            barrier.wait()
            responses = [future.result(timeout=2) for future in futures]

        self.assertEqual(client.download_requests, [(VALID_PICKCODE, "Player-A")])
        self.assertEqual(responses[0].headers["location"], responses[1].headers["location"])
        self.assertEqual(api._redirect_flights, {})

    def test_same_playback_serializes_first_requests_for_different_user_agents(self):
        client = CoordinatedDownloadClient()
        self.store.config["same_playback"] = True
        api = Api(lambda: client, self.store)
        barrier = threading.Barrier(3)

        def redirect(user_agent):
            barrier.wait()
            return self.signed_redirect(api, self.request(user_agent))

        with patch.object(api, "_schedule_playback_copy_cleanup") as cleanup, ThreadPoolExecutor(
            max_workers=2
        ) as executor:
            futures = [executor.submit(redirect, user_agent) for user_agent in ("Player-A", "Player-B")]
            barrier.wait()
            responses = [future.result(timeout=2) for future in futures]

        self.assertEqual(client.copy_calls, [VALID_PICKCODE])
        self.assertEqual(
            {pickcode for pickcode, _user_agent in client.download_requests},
            {VALID_PICKCODE, COPY_PICKCODE},
        )
        self.assertEqual(
            {response.headers["location"].split("?")[0] for response in responses},
            {
                f"https://download.example/{VALID_PICKCODE}",
                f"https://download.example/{COPY_PICKCODE}",
            },
        )
        cleanup.assert_called_once()
        self.assertEqual(cleanup.call_args.args[:3], (client, "copy-file-id", "cookie"))
        self.assertGreater(cleanup.call_args.args[3], 3600)

    def test_same_playback_schedules_copy_cleanup_when_download_url_fails(self):
        self.store.config["same_playback"] = True
        self.signed_redirect(self.api, self.request("Player-A"))

        with patch.object(self.client, "get_download_url", side_effect=RuntimeError("downurl failed")), patch(
            "app.plugins.p115liteassistant.api.retry_call", side_effect=lambda operation, **_kwargs: operation()
        ), patch.object(self.api, "_schedule_playback_copy_cleanup") as cleanup:
            response = self.signed_redirect(self.api, self.request("Player-B"))

        self.assertEqual(response.status_code, 502)
        cleanup.assert_called_once_with(self.client, "copy-file-id", "cookie", 0.0)

    def test_same_playback_schedules_copy_cleanup_when_ttl_is_invalid(self):
        self.store.config["same_playback"] = True
        self.signed_redirect(self.api, self.request("Player-A"))

        with patch.object(
            self.client,
            "get_download_url",
            return_value="https://download.example/copy-without-expiry",
        ), patch.object(self.api, "_schedule_playback_copy_cleanup") as cleanup:
            response = self.signed_redirect(self.api, self.request("Player-B"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "https://download.example/copy-without-expiry")
        cleanup.assert_called_once_with(self.client, "copy-file-id", "cookie", 300)

    def test_strm_execution_writes_start_and_summary_logs(self):
        self.store.config.update({"strm_incremental": True, "strm_mappings": []})

        with patch("app.plugins.p115liteassistant.api.logger") as task_logger:
            result = self.api.run_strm("http://moviepilot:3000")

        self.assertEqual(result, [])
        info_messages = [call.args[0] for call in task_logger.info.call_args_list]
        warning_messages = [call.args[0] for call in task_logger.warning.call_args_list]
        self.assertTrue(any("【STRM同步】开始执行" in message for message in info_messages))
        self.assertTrue(any("【STRM同步】执行完成" in message for message in info_messages))
        self.assertTrue(any("没有启用的目录映射" in message for message in warning_messages))

    def test_upload_execution_writes_start_and_summary_logs(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            self.store.config.update(
                {
                    "local_path_allowlist": [str(source)],
                    "upload_mappings": [
                        {"enabled": True, "source": str(source), "target": "/target"}
                    ],
                }
            )
            upload_result = {
                "kind": "upload",
                "uploaded": 1,
                "instant": 0,
                "skipped": 0,
                "deleted": 0,
                "errors": 1,
                "duration_ms": 25,
                "errors_detail": [
                    {
                        "path": str(source / "fail.mkv"),
                        "target": "/target/fail.mkv",
                        "message": "失败",
                    }
                ],
            }

            with patch("app.plugins.p115liteassistant.api.DirectoryUploader") as uploader, patch(
                "app.plugins.p115liteassistant.api.logger"
            ) as task_logger, patch(
                "app.helper.directory.DirectoryHelper.get_dirs", return_value=[]
            ):
                uploader.return_value.run.return_value = upload_result
                result = self.api.run_upload(incremental=True)

        self.assertEqual(result, upload_result)
        self.assertTrue(any("【目录上传】开始执行" in call.args[0] for call in task_logger.info.call_args_list))
        self.assertTrue(any("【目录上传】执行完成" in call.args[0] for call in task_logger.warning.call_args_list))

    def test_checkin_execution_writes_result_log(self):
        with patch("app.plugins.p115liteassistant.api.logger") as task_logger:
            result = self.api.run_checkin()

        self.assertTrue(result["success"])
        info_messages = [call.args[0] for call in task_logger.info.call_args_list]
        self.assertTrue(any("【115签到】开始执行" in message for message in info_messages))
        self.assertTrue(any("本次积分 5" in message for message in info_messages))

    def test_redirect_failure_writes_redacted_plugin_log(self):
        with patch.object(self.client, "get_download_url", side_effect=RuntimeError("apikey=secret")), patch(
            "app.plugins.p115liteassistant.api.retry_call", side_effect=lambda operation, **_kwargs: operation()
        ), patch("app.plugins.p115liteassistant.api.logger") as task_logger:
            response = self.signed_redirect(self.api, self.request())

        self.assertEqual(response.status_code, 502)
        error_message = task_logger.error.call_args.args[0]
        self.assertIn("【302取链】", error_message)
        self.assertNotIn("secret", error_message)

    def test_redirect_does_not_repeat_access_limit_cycle(self):
        with patch.object(
            self.client,
            "get_download_url",
            side_effect=U115AccessLimitError("已达到当前访问上限"),
        ) as get_download_url:
            response = self.signed_redirect(self.api, self.request())

        self.assertEqual(response.status_code, 502)
        get_download_url.assert_called_once()

    def test_strm_access_limit_stops_remaining_mappings(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            self.store.config.update(
                {
                    "local_path_allowlist": [str(root)],
                    "strm_mappings": [
                        {"enabled": True, "source_cid": "first", "target_dir": str(first)},
                        {"enabled": True, "source_cid": "second", "target_dir": str(second)},
                    ],
                }
            )
            with patch("app.plugins.p115liteassistant.api.StrmGenerator") as generator, patch(
                "app.plugins.p115liteassistant.api.logger"
            ) as task_logger, patch(
                "app.helper.directory.DirectoryHelper.get_dirs", return_value=[]
            ):
                generator.return_value.run_mapping.side_effect = U115AccessLimitError(
                    "已达到当前访问上限"
                )
                result = self.api.run_strm("http://moviepilot:3000")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["mapping"], "first")
        self.assertEqual(generator.return_value.run_mapping.call_count, 1)
        self.assertTrue(
            any("延后剩余 1 个映射" in call.args[0] for call in task_logger.warning.call_args_list)
        )

    def test_task_start_failure_releases_running_state(self):
        with patch("app.plugins.p115liteassistant.api.threading.Thread.start", side_effect=RuntimeError("start failed")), patch(
            "app.plugins.p115liteassistant.api.logger"
        ) as task_logger:
            result = self.api._start("strm", lambda: None, "STRM 同步已开始")

        self.assertFalse(result["success"])
        self.assertNotIn("strm", self.api._running)
        self.assertTrue(any("任务启动失败" in call.args[0] for call in task_logger.error.call_args_list))

    def test_cloud_tasks_are_mutually_exclusive(self):
        started = threading.Event()
        release = threading.Event()

        def block_upload():
            started.set()
            release.wait(2)

        first = self.api._start("upload", block_upload, "目录上传已开始")
        self.assertTrue(first["success"])
        self.assertTrue(started.wait(1))
        try:
            second = self.api._start("strm", lambda: None, "STRM 同步已开始")
            self.assertFalse(second["success"])
            self.assertIn("数据任务正在运行", second["message"])
        finally:
            release.set()

        for _ in range(20):
            if not self.api._running:
                break
            sleep(0.01)
        self.assertFalse(self.api._running)

    def test_auto_upload_busy_state_is_distinct_and_exposed(self):
        candidate = UploadCandidate(
            "/media/Film.mkv", "/media", "movies", (1, 2, 3), "transfer", time()
        )
        self.api._cloud_task_lock.acquire()
        try:
            first = self.api.queue_upload_file(candidate)
            second = self.api.queue_upload_file(candidate)
            status = self.api.status()
        finally:
            self.api._cloud_task_lock.release()

        self.assertTrue(first["success"])
        self.assertTrue(second["success"])
        self.assertTrue(status["pending_upload"])
        self.assertEqual(status["pending_upload_source"], "transfer")
        self.assertEqual(status["pending_upload_count"], 1)
        self.assertIsNotNone(status["pending_upload_queued_at"])

    def test_pending_upload_is_not_taken_when_retry_cannot_start(self):
        candidate = UploadCandidate(
            "/media/Film.mkv", "/media", "movies", (1, 2, 3), "watch", time()
        )
        self.api._upload_queue.enqueue(candidate)
        with patch.object(self.api, "_start", return_value={"success": False, "message": "启动失败"}):
            self.api._drain_pending_upload()
        status = self.api._upload_queue.snapshot()
        self.assertTrue(status["pending"])
        self.assertEqual(status["count"], 1)

    def test_failed_upload_batch_retries_after_unlock_and_converges_without_new_event(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve(); movie = root / "Film.mkv"; movie.write_bytes(b"media")
            mapping = {"id": "movies", "source": str(root), "target": "/Cloud", "enabled": True}
            self.store.config.update({
                "enabled": True, "local_path_allowlist": [str(root)],
                "upload_mappings": [mapping], "upload_media_extensions": ".mkv",
            })
            candidate = UploadCandidate(
                str(movie), str(root), "movies", file_signature(movie), "watch", time(),
                mapping_revision(mapping, self.store.config, canonical_source=str(root)),
            )
            calls = []
            def run(_candidates, _url):
                calls.append(self.api._cloud_task_lock.locked())
                if len(calls) == 1:
                    raise U115AccessLimitError("瞬时限流")
                return {"errors": 0, "errors_detail": [], "deferred": 0}
            self.api._UPLOAD_RETRY_DELAYS = (0.03, 0.05, 0.05)
            with patch.object(self.api, "run_upload_files", side_effect=run):
                result = self.api.queue_upload_file(candidate)
                self.assertTrue(result["success"])
                for _ in range(200):
                    if len(calls) >= 2 and not self.api._upload_queue and not self.api._running:
                        break
                    sleep(0.01)

            self.assertEqual(calls, [True, True])
            self.assertFalse(self.api._cloud_task_lock.locked())
            self.assertFalse(self.api._upload_queue)
            self.assertIn(candidate.key, self.api._upload_queue._processed)
            self.assertFalse(self.api._upload_queue.enqueue(candidate))
            self.api.stop_upload_retry_scheduler()

    def test_success_over_time_budget_finishes_deleted_candidate_without_restore(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve(); movie = root / "Film.mkv"; movie.write_bytes(b"media")
            mapping = {"id": "movies", "source": str(root), "target": "/Cloud", "enabled": True}
            self.store.config.update({"upload_mappings": [mapping], "upload_media_extensions": ".mkv"})
            candidate = UploadCandidate(
                str(movie), str(root), "movies", file_signature(movie), "watch", time(),
                mapping_revision(mapping, self.store.config, canonical_source=str(root)),
            )
            self.api._upload_queue.enqueue(candidate)
            def delete_and_succeed(_candidates, _url):
                movie.unlink()
                return {"errors": 0, "deleted": 1}
            with patch.object(self.api, "run_upload_files", side_effect=delete_and_succeed), patch(
                "app.plugins.p115liteassistant.api.monotonic", side_effect=[0.0, 121.0, 122.0, 123.0]
            ), patch.object(self.api._upload_queue, "restore", wraps=self.api._upload_queue.restore) as restore:
                self.api._run_upload_batch()
            restore.assert_not_called()
            self.assertFalse(movie.exists())
            self.assertFalse(self.api._upload_queue)
            self.assertFalse(self.api._upload_queue.enqueue(candidate))

    def test_retry_exhaustion_stays_bounded_until_wake_and_stop_cancels_timer(self):
        candidate = UploadCandidate(
            "/media/Film.mkv", "/media", "movies", (1, 2, 3), "watch", time()
        )
        self.api._upload_queue.enqueue(candidate)
        self.api._UPLOAD_RETRY_DELAYS = (60.0,)
        self.assertTrue(self.api._schedule_upload_retry())
        timer = self.api._upload_retry_timer
        with patch.object(self.api, "_drain_pending_upload") as drain:
            self.api.wake_pending_upload()
            drain.assert_called_once_with()
        self.assertIsNone(self.api._upload_retry_timer)
        self.assertEqual(self.api._upload_retry_attempt, 0)
        self.assertFalse(timer.is_alive())

        self.api._UPLOAD_RETRY_DELAYS = (60.0,)
        self.assertTrue(self.api._schedule_upload_retry())
        timer = self.api._upload_retry_timer
        self.api.stop_upload_retry_scheduler(timeout=0.2)
        self.assertFalse(timer.is_alive())
        self.assertIsNone(self.api._upload_retry_timer)
        self.assertFalse(self.api._drain_pending_upload())

    def test_api_file_upload_ignores_unrelated_unmounted_mapping(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve(); movie = root / "Film.mkv"; movie.write_bytes(b"media")
            mapping = {"id": "movies", "source": str(root), "target": "/Cloud", "enabled": True}
            unrelated = {"id": "tv", "source": str(root / "missing"), "target": "/Cloud/TV", "enabled": True}
            self.store.config.update({
                "local_path_allowlist": [str(root)], "upload_mappings": [mapping, unrelated],
                "upload_media_extensions": ".mkv",
            })
            candidate = UploadCandidate(
                str(movie), str(root), "movies", file_signature(movie), "watch", time(),
                mapping_revision(mapping, self.store.config, canonical_source=str(root)),
            )
            with patch("app.plugins.p115liteassistant.api.DirectoryUploader") as uploader, patch(
                "app.helper.directory.DirectoryHelper.get_dirs", return_value=[]
            ):
                uploader.return_value.run_files.return_value = {"errors": 0}
                result = self.api.run_upload_files([candidate])
            self.assertEqual(result["errors"], 0)
            execution_config = uploader.call_args.args[2]
            self.assertEqual([item["id"] for item in execution_config["upload_mappings"]], ["movies"])

    def test_manual_upload_entries_do_not_touch_automatic_queue_methods(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.store.config.update({"local_path_allowlist": [str(root)], "upload_mappings": []})
            queue = Mock(spec=PendingUploadQueue)
            self.api._upload_queue = queue
            with patch.object(self.api, "_start", return_value={"success": False, "message": "忙", "data": {}}):
                self.api.trigger_upload({"incremental": True})
                self.api.task_upload_once({"source": str(root), "target": "/Cloud"})
            queue.take.assert_not_called()
            queue.clear_invalid.assert_not_called()
            queue.finish.assert_not_called()
            queue.restore.assert_not_called()

    def test_completed_sweep_gives_pending_upload_first_chance(self):
        calls = []
        with patch.object(
            self.api,
            "_drain_pending_upload",
            side_effect=lambda: calls.append("upload"),
        ), patch.object(
            self.api,
            "_drain_pending_sweep",
            side_effect=lambda: calls.append("sweep"),
        ):
            self.api._drain_pending_tasks("sweep")
        self.assertEqual(calls, ["upload", "sweep"])

    def test_error_text_redacts_credentials_and_limits_length(self):
        message = safe_error_text(
            RuntimeError("cookie=UID=123; CID=456; access_token='secret'; Authorization: Bearer abc " + "x" * 600)
        )

        self.assertNotIn("123", message)
        self.assertNotIn("456", message)
        self.assertNotIn("secret", message)
        self.assertNotIn("Bearer abc", message)
        self.assertLessEqual(len(message), 503)

    def test_scheduled_checkin_runs_once_and_records_the_day(self):
        result = self.api.run_scheduled_checkin()
        repeated = self.api.run_scheduled_checkin()

        self.assertTrue(result["success"])
        self.assertTrue(repeated["success"])
        self.assertEqual(self.client.checkin_calls, 1)
        self.assertTrue(self.store.schedule["last_done_date"])
        self.assertGreater(self.store.schedule["next_run_ts"], 0)

    def test_scheduled_checkin_keeps_retry_slot_when_cloud_task_is_busy(self):
        self.store.schedule["next_run_ts"] = time() - 1
        self.assertTrue(self.api._cloud_task_lock.acquire(blocking=False))
        try:
            result = self.api.run_scheduled_checkin()
        finally:
            self.api._cloud_task_lock.release()

        self.assertFalse(result["success"])
        self.assertTrue(result["busy"])
        self.assertGreater(self.store.schedule["next_run_ts"], time())


class SweepOrchestrationTest(unittest.TestCase):
    """反向删除的排队语义：抢不到 115 数据任务锁的事件不能丢。"""

    class SweepStore(FakeStore):
        def __init__(self, target_dir):
            super().__init__()
            self.config.update(
                {
                    "strm_delete_cloud_on_missing": True,
                    "strm_mappings": [
                        {
                            "id": "movies",
                            "enabled": True,
                            "source_cid": "1",
                            "target_dir": str(target_dir),
                        }
                    ],
                }
            )
            self.pending = {}

        def get_strm_records(self):
            return {}

        def save_strm_records(self, records):
            return None

        def get_strm_delete_pending(self):
            return dict(self.pending)

        def save_strm_delete_pending(self, batches):
            self.pending = dict(batches)

        def pop_strm_delete_batch(self, batch_id):
            return self.pending.pop(str(batch_id), None)

    def _api(self, target_dir):
        return Api(FakeClient, self.SweepStore(target_dir))

    def test_empty_scope_is_not_a_full_sweep(self):
        """空列表表示「没有待处理路径」，绝不能被当成「清理所有记录」。"""
        with TemporaryDirectory() as directory:
            api = self._api(directory)

            self.assertEqual(api._take_sweep_scope(), ([], False))

    def test_queued_paths_are_taken_once(self):
        with TemporaryDirectory() as directory:
            api = self._api(directory)

            api._queue_sweep_scope(["/media/A.strm", "/media/B.strm", "  "])

            self.assertEqual(
                api._take_sweep_scope(),
                (["/media/A.strm", "/media/B.strm"], True),
            )
            self.assertEqual(api._take_sweep_scope(), ([], False))

    def test_full_sweep_wins_over_partial_scope(self):
        with TemporaryDirectory() as directory:
            api = self._api(directory)

            api._queue_sweep_scope(["/media/A.strm"])
            api._queue_sweep_scope(None)

            self.assertEqual(api._take_sweep_scope(), (None, True))

    def test_auto_trigger_queues_when_cloud_lock_is_busy(self):
        """定时巡检与监听上报抢不到锁不算失败，排队等补跑。"""
        with TemporaryDirectory() as directory:
            api = self._api(directory)
            api._cloud_task_lock.acquire()
            try:
                result = api.queue_strm_sweep(["/media/A.strm"])
            finally:
                api._cloud_task_lock.release()

            self.assertTrue(result["success"])
            self.assertIn("排队", result["message"])
            self.assertEqual(api._pending_sweep_paths, {"/media/A.strm"})

    def test_upload_batches_release_cloud_lock_for_real_sweep_then_continue(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            store = self.SweepStore(root)
            mapping = {"id": "movies", "source": str(root), "target": "/Cloud", "enabled": True}
            store.config.update({
                "enabled": True, "local_path_allowlist": [str(root)],
                "upload_mappings": [mapping], "upload_media_extensions": ".mkv",
            })
            api = Api(FakeClient, store)
            candidates = []
            for name in ("A.mkv", "B.mkv"):
                path = root / name; path.write_bytes(name.encode())
                candidates.append(UploadCandidate(
                    str(path), str(root), "movies", file_signature(path), "watch", time(),
                    mapping_revision(mapping, store.config, canonical_source=str(root)),
                ))
            api._upload_queue.maxsize = 10
            # 批大小保持生产常量 1；两个候选证明 upload 会分成两次独立锁持有。
            for candidate in candidates: api._upload_queue.enqueue(candidate)
            store_order = []
            def upload_run(batch, _url):
                store_order.append(("upload", Path(batch[0].file_path).name, api._cloud_task_lock.locked()))
                if len([item for item in store_order if item[0] == "upload"]) == 1:
                    api._queue_sweep_scope([str(root / "gone.strm")])
                return {"errors": 0, "errors_detail": [], "deferred": 0}
            def sweep_run(_scope):
                store_order.append(("sweep", "gone.strm", api._cloud_task_lock.locked()))
                return []
            with patch.object(api, "run_upload_files", side_effect=upload_run), patch.object(
                api, "run_strm_sweep", side_effect=sweep_run
            ):
                api._drain_pending_upload()
                for _ in range(300):
                    if len(store_order) >= 3 and not api._running and not api._upload_queue:
                        break
                    sleep(0.01)

            self.assertEqual([item[0] for item in store_order], ["upload", "sweep", "upload"])
            self.assertTrue(all(item[2] for item in store_order))
            self.assertFalse(api._cloud_task_lock.locked())

    def test_failed_sweep_requeues_taken_scope(self):
        with TemporaryDirectory() as directory:
            api = self._api(directory)
            api._queue_sweep_scope(["/media/A.strm"])
            with patch.object(
                api,
                "run_strm_sweep",
                side_effect=RuntimeError("boom"),
            ):
                with self.assertRaises(RuntimeError):
                    api._sweep_worker()
            self.assertEqual(api._pending_sweep_paths, {"/media/A.strm"})

    def test_manual_trigger_rejects_when_cloud_lock_is_busy(self):
        with TemporaryDirectory() as directory:
            api = self._api(directory)
            api._cloud_task_lock.acquire()
            try:
                result = api.trigger_strm_sweep()
            finally:
                api._cloud_task_lock.release()

            self.assertFalse(result["success"])
            self.assertIn("115 数据任务正在运行", result["message"])

    def test_trigger_rejected_when_switch_is_off(self):
        with TemporaryDirectory() as directory:
            api = self._api(directory)
            api._store.config["strm_delete_cloud_on_missing"] = False

            result = api.trigger_strm_sweep()

            self.assertFalse(result["success"])
            self.assertIn("未开启", result["message"])

    def test_confirm_requires_existing_batch(self):
        with TemporaryDirectory() as directory:
            api = self._api(directory)

            self.assertFalse(api.confirm_strm_delete({})["success"])
            self.assertFalse(api.confirm_strm_delete({"batch_id": "nope"})["success"])

    def test_dismiss_drops_batch_without_touching_cloud(self):
        with TemporaryDirectory() as directory:
            api = self._api(directory)
            api._store.pending = {
                "abcd": {"id": "abcd", "mapping_id": "movies", "count": 3, "items": []}
            }

            result = api.dismiss_strm_delete({"batch_id": "abcd"})

            self.assertTrue(result["success"])
            self.assertEqual(api._store.pending, {})

    def test_confirm_puts_batch_back_when_task_cannot_start(self):
        """确认后任务起不来，批次要放回去 —— 用户点一次不能就这么丢了。"""
        with TemporaryDirectory() as directory:
            api = self._api(directory)
            batch = {
                "id": "abcd",
                "mapping_id": "movies",
                "count": 1,
                "items": [{"path": str(Path(directory) / "Film.strm")}],
            }
            api._store.pending = {"abcd": batch}
            api._cloud_task_lock.acquire()
            try:
                result = api.confirm_strm_delete({"batch_id": "abcd"})
            finally:
                api._cloud_task_lock.release()

            self.assertFalse(result["success"])
            self.assertIn("abcd", api._store.pending)


class ServiceRegistrationTest(unittest.TestCase):
    """定时任务注册：签到与反向删除巡检各自独立开关。"""

    class ServiceStore(FakeStore):
        def __init__(self, config):
            super().__init__()
            self.config.update(config)

    class ApiStub:
        """get_service / get_api 只需要这些入口存在。"""

        def run_scheduled_checkin(self):
            return None

        def run_scheduled_strm_sweep(self):
            return None

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    @staticmethod
    def _plugin(config):
        plugin = object.__new__(P115LiteAssistant)
        plugin._store = ServiceRegistrationTest.ServiceStore(config)
        plugin._api = ServiceRegistrationTest.ApiStub()
        return plugin

    def _job_ids(self, config):
        return [item["id"] for item in self._plugin(config).get_service()]

    def test_disabled_plugin_registers_nothing(self):
        self.assertEqual(self._job_ids({"enabled": False, "checkin_enabled": True}), [])

    def test_checkin_only(self):
        self.assertEqual(
            self._job_ids({"checkin_enabled": True, "strm_delete_cloud_on_missing": False}),
            ["p115liteassistant_checkin"],
        )

    def test_sweep_registered_when_switch_and_cron_are_set(self):
        self.assertEqual(
            self._job_ids(
                {
                    "checkin_enabled": False,
                    "strm_delete_cloud_on_missing": True,
                    "strm_delete_sweep_cron": "37 */2 * * *",
                }
            ),
            ["p115liteassistant_strm_sweep"],
        )

    def test_blank_cron_disables_sweep_job(self):
        self.assertEqual(
            self._job_ids(
                {
                    "checkin_enabled": False,
                    "strm_delete_cloud_on_missing": True,
                    "strm_delete_sweep_cron": "   ",
                }
            ),
            [],
        )

    def test_invalid_cron_does_not_break_checkin_registration(self):
        """巡检 cron 写坏了不能把签到任务一起带走。"""
        self.assertEqual(
            self._job_ids(
                {
                    "checkin_enabled": True,
                    "strm_delete_cloud_on_missing": True,
                    "strm_delete_sweep_cron": "not a cron",
                }
            ),
            ["p115liteassistant_checkin"],
        )

    def test_sweep_endpoints_are_registered(self):
        plugin = self._plugin({})
        routes = plugin.get_api()
        paths = {(item["path"], tuple(item["methods"])) for item in routes}

        self.assertIn(("/strm/sweep", ("POST",)), paths)
        self.assertIn(("/strm/sweep/pending", ("GET",)), paths)
        self.assertIn(("/strm/sweep/confirm", ("POST",)), paths)
        self.assertIn(("/strm/sweep/dismiss", ("POST",)), paths)
        gap_fill = next(item for item in routes if item["path"] == "/task/gap-fill")
        self.assertEqual(gap_fill["methods"], ["POST"])
        self.assertEqual(gap_fill["auth"], "bear")
        self.assertTrue(callable(gap_fill["endpoint"]))


class PendingReviewApiTest(unittest.TestCase):
    """待确认批次的审查接口：完整清单、批量确认、批量驳回。"""

    class ReviewStore(SweepOrchestrationTest.SweepStore):
        pass

    def _api(self, directory, batches):
        api = Api(FakeClient, self.ReviewStore(directory))
        api._store.pending = batches
        return api

    @staticmethod
    def _batch(batch_id, count, created):
        return {
            "id": batch_id,
            "mapping_id": "movies",
            "mapping": "/影视",
            "created_at": created,
            "updated_at": created,
            "reason": "超过阈值",
            "count": count,
            "items_truncated": False,
            "items": [
                {
                    "record_key": f"movies:S/{batch_id}{i}.mkv",
                    "path": f"/media/Strm/{batch_id}{i}.strm",
                    "cloud_path": f"/影视/{batch_id}{i}.mkv",
                    "name": f"{batch_id}{i}.mkv",
                }
                for i in range(count)
            ],
        }

    def test_summary_lists_batches_newest_first(self):
        with TemporaryDirectory() as directory:
            api = self._api(directory, {
                "aaa": self._batch("aaa", 2, "2026-09-01T00:00:00"),
                "bbb": self._batch("bbb", 3, "2026-09-02T00:00:00"),
            })

            batches = api.strm_delete_pending()["data"]["batches"]

            self.assertEqual([b["id"] for b in batches], ["bbb", "aaa"])
            self.assertEqual([b["count"] for b in batches], [3, 2])
            self.assertEqual(len(batches[0]["samples"]), 3)

    def test_single_batch_returns_full_list_with_paging(self):
        with TemporaryDirectory() as directory:
            api = self._api(directory, {"aaa": self._batch("aaa", 5, "2026-09-01T00:00:00")})

            page = api.strm_delete_pending(batch_id="aaa", offset=0, limit=2)["data"]
            self.assertEqual(page["total"], 5)
            self.assertEqual(len(page["items"]), 2)
            self.assertEqual(page["items"][0]["path"], "/media/Strm/aaa0.strm")
            self.assertIn("cloud_path", page["items"][0])

            tail = api.strm_delete_pending(batch_id="aaa", offset=4, limit=2)["data"]
            self.assertEqual(len(tail["items"]), 1)
            self.assertEqual(tail["items"][0]["name"], "aaa4.mkv")

    def test_paged_batch_detail_and_confirm_read_every_item(self):
        with TemporaryDirectory() as directory:
            batch = self._batch("aaa", 2005, "2026-09-01T00:00:00")
            overflow = batch["items"][2000:]
            batch["items"] = batch["items"][:2000]
            from app.plugins.p115liteassistant.reverse_delete import store_pending_batch_items
            store_pending_batch_items(batch, batch["items"] + overflow)
            api = self._api(directory, {"aaa": batch})

            detail = api.strm_delete_pending(batch_id="aaa", offset=2000, limit=10)["data"]
            self.assertEqual(detail["total"], 2005)
            self.assertEqual([item["name"] for item in detail["items"]], [
                f"aaa{index}.mkv" for index in range(2000, 2005)
            ])
            with patch.object(api, "_start", return_value={"success": False, "message": "忙"}) as start:
                result = api.confirm_strm_delete({"batch_id": "aaa"})
            self.assertFalse(result["success"])
            submitted = start.call_args.args[2]
            self.assertIn("2005 个媒体", submitted)
            self.assertEqual(api._store.pending["aaa"]["status"], "pending")

            # 模拟进程在前 2000 条 journal 提交并 checkpoint 后重启，只续跑尾页。
            api._store.pending["aaa"]["status"] = "claimed"
            api._store.pending["aaa"]["checkpoint"] = {
                "page": 10, "offset": 2000, "processed": 2000
            }
            calls = []
            def run_page(paths, **kwargs):
                calls.append((list(paths), kwargs))
                return [{"action": "delete"}]
            def run_now(_kind, target, message):
                target()
                return {"success": True, "message": message, "data": {}}
            with patch.object(api, "run_strm_sweep", side_effect=run_page), patch.object(
                api, "_start", side_effect=run_now
            ):
                resumed = api.confirm_strm_delete({"batch_id": "aaa"})
            self.assertTrue(resumed["success"])
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(calls[0][0]), 5)
            self.assertTrue(calls[0][0][0].endswith("aaa2000.strm"))
            self.assertNotIn("aaa", api._store.pending)

    def test_bad_page_metadata_keeps_status_detail_and_confirm_fail_closed(self):
        with TemporaryDirectory() as directory:
            batch = self._batch("bad", 2001, "2026-09-01T00:00:00")
            from app.plugins.p115liteassistant.reverse_delete import store_pending_batch_items
            store_pending_batch_items(batch, batch["items"])
            # _batch 只有 2001 项且 store 后会生成一页 overflow；损坏页号不能冒泡 ValueError。
            batch["item_pages"][0]["page"] = "not-a-number"
            api = self._api(directory, {"bad": batch})
            summary = api.strm_delete_pending()
            detail = api.strm_delete_pending(batch_id="bad")
            confirm = api.confirm_strm_delete({"batch_id": "bad"})
            self.assertTrue(summary["success"])
            self.assertEqual(summary["data"]["batches"][0]["samples"], [])
            self.assertTrue(detail["success"])
            self.assertEqual(detail["data"]["total"], 0)
            self.assertFalse(confirm["success"])
            self.assertIn("明细不完整", confirm["message"])

    def test_unknown_batch_id_is_rejected(self):
        with TemporaryDirectory() as directory:
            api = self._api(directory, {})

            self.assertFalse(api.strm_delete_pending(batch_id="nope")["success"])

    def test_dismiss_accepts_multiple_batches(self):
        with TemporaryDirectory() as directory:
            api = self._api(directory, {
                "aaa": self._batch("aaa", 2, "2026-09-01T00:00:00"),
                "bbb": self._batch("bbb", 3, "2026-09-02T00:00:00"),
            })

            result = api.dismiss_strm_delete({"batch_ids": ["aaa", "bbb"]})

            self.assertTrue(result["success"])
            self.assertIn("2 个批次", result["message"])
            self.assertEqual(api._store.pending, {})

    def test_confirm_restores_every_batch_when_task_cannot_start(self):
        with TemporaryDirectory() as directory:
            api = self._api(directory, {
                "aaa": self._batch("aaa", 2, "2026-09-01T00:00:00"),
                "bbb": self._batch("bbb", 3, "2026-09-02T00:00:00"),
            })
            api._cloud_task_lock.acquire()
            try:
                result = api.confirm_strm_delete({"batch_ids": ["aaa", "bbb"]})
            finally:
                api._cloud_task_lock.release()

            self.assertFalse(result["success"])
            self.assertEqual(sorted(api._store.pending), ["aaa", "bbb"])

    def test_confirm_reports_how_many_batches_and_files(self):
        with TemporaryDirectory() as directory:
            api = self._api(directory, {
                "aaa": self._batch("aaa", 2, "2026-09-01T00:00:00"),
                "bbb": self._batch("bbb", 3, "2026-09-02T00:00:00"),
            })

            def run_now(_kind, target, message):
                target()
                return {"success": True, "message": message, "data": {}}
            with patch.object(api, "run_strm_sweep", return_value=[{"action": "delete"}]), patch.object(
                api, "_start", side_effect=run_now
            ):
                result = api.confirm_strm_delete({"batch_ids": ["aaa", "bbb"]})

            self.assertTrue(result["success"])
            self.assertIn("2 个批次", result["message"])
            self.assertIn("5 个媒体", result["message"])
            self.assertEqual(api._store.pending, {})

class ReviewClaimConcurrencyRegressionTest(unittest.TestCase):
    def _api(self, directory):
        store = SweepOrchestrationTest.SweepStore(directory)
        store.pending = {
            "batch": {
                "id": "batch", "mapping_id": "movies", "mapping": "/影视", "count": 1,
                "items": [{"path": str(Path(directory) / "Film.strm")}], "status": "pending",
                "checkpoint": {"page": 0, "offset": 0, "processed": 0},
            }
        }
        return Api(FakeClient, store), store

    def test_two_threads_confirm_same_batch_only_one_claims(self):
        with TemporaryDirectory() as directory:
            api, store = self._api(directory)
            first_in_start = threading.Event(); release = threading.Event()
            def start(_kind, _target, message):
                first_in_start.set(); release.wait(timeout=2)
                return {"success": True, "message": message, "data": {}}
            results = []
            with patch.object(api, "_start", side_effect=start):
                first = threading.Thread(target=lambda: results.append(
                    api.confirm_strm_delete({"batch_id": "batch"})))
                second = threading.Thread(target=lambda: results.append(
                    api.confirm_strm_delete({"batch_id": "batch"})))
                first.start(); self.assertTrue(first_in_start.wait(1)); second.start()
                second.join(timeout=2); release.set(); first.join(timeout=2)
            self.assertEqual(sum(bool(item["success"]) for item in results), 1)
            self.assertEqual(store.pending["batch"]["status"], "claimed")
            self.assertTrue(store.pending["batch"]["claim_token"])

    def test_checkpoint_never_moves_back_for_same_owner(self):
        with TemporaryDirectory() as directory:
            api, store = self._api(directory)
            store.pending["batch"].update({"status": "claimed", "claim_token": "owner"})
            store.pending["batch"]["checkpoint"] = {"page": 2, "offset": 200, "processed": 200}
            api._checkpoint_strm_delete_batch("batch", claim_token="owner", page=1, offset=100)
            self.assertEqual(store.pending["batch"]["checkpoint"]["offset"], 200)

    def test_claimed_batch_dismiss_is_rejected_and_kept(self):
        with TemporaryDirectory() as directory:
            api, store = self._api(directory)
            store.pending["batch"].update({"status": "claimed", "claim_token": "owner"})
            result = api.dismiss_strm_delete({"batch_id": "batch"})
            self.assertFalse(result["success"])
            self.assertIn("正在执行", result["message"])
            self.assertIn("batch", store.pending)


class LeaseAndCapacityRegressionTest(unittest.TestCase):
    def test_real_upload_chain_cancels_before_second_file_and_worker_releases_lock(self):
        class UploadStore(FakeStore):
            def __init__(self, root, mapping):
                super().__init__()
                self.config.update({
                    "enabled": True,
                    "local_path_allowlist": [str(root)],
                    "upload_mappings": [mapping],
                    "upload_media_extensions": ".mkv",
                })
                self.upload_records = IncrementalRecordStore()
                self.conflicts = {}

            def get_upload_records(self):
                return self.upload_records

            def save_upload_records(self, records):
                self.upload_records = records

            def get_upload_conflicts(self):
                return dict(self.conflicts)

            def save_upload_conflicts(self, conflicts):
                self.conflicts = dict(conflicts)

            def get_recent_uploaded_media(self, extensions):
                return self.upload_records.recent_media(extensions)

        class BlockingUploadClient(FakeClient):
            def __init__(self):
                super().__init__()
                self.first_started = threading.Event()
                self.release_first = threading.Event()
                self.uploaded = []
                self.worker_ident = None

            @staticmethod
            def ensure_upload_ready():
                return None

            @staticmethod
            def ensure_remote_dir(path):
                return {"fileid": "1", "path": path}

            def upload_file(self, _target, local_path):
                self.worker_ident = threading.get_ident()
                self.uploaded.append(Path(local_path).name)
                if len(self.uploaded) == 1:
                    self.first_started.set()
                    self.release_first.wait(timeout=2)
                return UploadResult(success=True, reused=False)

        class TrackingLock:
            def __init__(self):
                self._lock = threading.Lock()
                self.release_ident = None

            def acquire(self, blocking=True):
                return self._lock.acquire(blocking=blocking)

            def release(self):
                self.release_ident = threading.get_ident()
                self._lock.release()

            def locked(self):
                return self._lock.locked()

        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            paths = [root / "A.mkv", root / "B.mkv"]
            for path in paths:
                path.write_bytes(path.name.encode())
            mapping = {"id": "movies", "source": str(root), "target": "/Cloud", "enabled": True}
            store = UploadStore(root, mapping)
            client = BlockingUploadClient()
            api = Api(lambda: client, store)
            tracking_lock = TrackingLock()
            api._cloud_task_lock = tracking_lock
            first_completed = threading.Event()
            release_completion_checkpoint = threading.Event()
            original_checkpoint = api._task_checkpoint

            def checkpoint(**state):
                cancelled = original_checkpoint(**state)
                progress = state.get("progress") or {}
                if state.get("phase") == "upload-file-complete" and progress.get("current") == 1:
                    first_completed.set()
                    release_completion_checkpoint.wait(timeout=2)
                return cancelled

            api._task_checkpoint = checkpoint
            candidates = [
                UploadCandidate(
                    str(path), str(root), "movies", file_signature(path), "watch", time(),
                    mapping_revision(mapping, store.config, canonical_source=str(root)),
                )
                for path in paths
            ]

            result = api._start(
                "upload",
                lambda: api.run_upload_files(candidates),
                "started",
            )
            self.assertTrue(result["success"])
            self.assertTrue(client.first_started.wait(1))
            task = next(item for item in api.status()["tasks"] if item["kind"] == "upload")
            self.assertEqual(task["phase"], "upload-file-start")
            self.assertEqual(task["current_item"], str(paths[0]))
            self.assertEqual(task["progress"], {"current": 0, "total": 2})
            self.assertTrue(tracking_lock.locked())

            client.release_first.set()
            self.assertTrue(first_completed.wait(1))
            completed = next(item for item in api.status()["tasks"] if item["kind"] == "upload")
            self.assertEqual(completed["phase"], "upload-file-complete")
            self.assertEqual(completed["current_item"], str(paths[0]))
            self.assertEqual(completed["progress"], {"current": 1, "total": 2})
            self.assertTrue(api.cancel_task({"kind": "upload"})["success"])
            release_completion_checkpoint.set()
            api.join_task_threads(timeout=2)

            self.assertEqual(client.uploaded, ["A.mkv"])
            self.assertEqual(
                store.upload_records.to_dict().keys(),
                {str(paths[0])},
            )
            self.assertFalse(api._task_threads)
            self.assertNotIn("upload", api._running)
            self.assertFalse(tracking_lock.locked())
            self.assertEqual(tracking_lock.release_ident, client.worker_ident)

    def test_lease_status_fields_and_cooperative_cancel_checkpoint(self):
        store = FakeStore(); api = Api(lambda: FakeClient(), store)
        entered = threading.Event(); release = threading.Event()
        def target():
            api._task_checkpoint(phase="scan", current_item="A", progress={"current": 1, "total": 2})
            entered.set(); release.wait(2)
            api._task_checkpoint(phase="scan", current_item="B", progress=2, raise_if_cancelled=True)
        self.assertTrue(api._start("upload", target, "started")["success"])
        self.assertTrue(entered.wait(1))
        task = api.status()["tasks"][0]
        self.assertTrue(task["holder"].startswith("p115liteassistant-upload:"))
        self.assertIsInstance(task["started_at"], float)
        self.assertGreaterEqual(task["age"], 0)
        self.assertGreaterEqual(task["last_progress"], 0)
        self.assertEqual(task["phase"], "scan")
        self.assertEqual(task["current_item"], "A")
        self.assertEqual(task["progress"], {"current": 1, "total": 2})
        self.assertTrue(api.cancel_task("upload")["success"])
        release.set(); api.join_task_threads(timeout=2)
        self.assertNotIn("upload", api._running)
        self.assertFalse(api._cloud_task_lock.locked())

    def test_sweep_4097_paths_compress_to_full_marker(self):
        with TemporaryDirectory() as directory:
            api = Api(FakeClient, SweepOrchestrationTest.SweepStore(directory))
            api._queue_sweep_scope([f"/media/{index}.strm" for index in range(4097)])
            self.assertTrue(api._pending_sweep_all)
            self.assertEqual(api._pending_sweep_paths, set())
            self.assertEqual(api._take_sweep_scope(), (None, True))


class UploadCompatibilityRegressionTest(unittest.TestCase):
    def test_queue_upload_and_legacy_auto_payloads_merge_while_busy(self):
        api = Api(lambda: FakeClient(), FakeStore())
        api._cloud_task_lock.acquire()
        try:
            results = [api.queue_upload("external"), api.trigger_upload(None),
                       api.trigger_upload(False), api.trigger_upload({"auto": True, "source": "hook"})]
        finally:
            api._cloud_task_lock.release()
        self.assertTrue(all(item["success"] for item in results))
        self.assertTrue(api._pending_auto_upload)
        self.assertEqual(api._pending_auto_upload_count, 4)
        self.assertIn("external", api._pending_auto_upload_source)

    def test_disabled_pending_candidates_do_not_execute_on_wake(self):
        store = FakeStore(); store.config["enabled"] = False
        api = Api(lambda: FakeClient(), store)
        candidate = UploadCandidate("/media/a.mkv", "/media", "m", (1, 1, 1))
        api._upload_queue.enqueue(candidate)
        with patch.object(api, "_start") as start:
            api.wake_pending_upload()
        start.assert_not_called()
        self.assertTrue(api._upload_queue)
