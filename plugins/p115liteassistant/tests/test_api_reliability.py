from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
from time import time
import unittest
from unittest.mock import patch

from fastapi import Request
from plugins.p115liteassistant.api import Api
from plugins.p115liteassistant.client import PlaybackCopy
from plugins.p115liteassistant.log_utils import safe_error_text


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

    def get_checkin_schedule(self):
        return dict(self.schedule)

    def save_checkin_schedule(self, state):
        self.schedule = dict(state)


class FakeClient:
    def __init__(self):
        self.browse_calls = 0
        self.download_calls = 0
        self.download_requests = []
        self.copy_calls = []
        self.deleted = []
        self.checkin_calls = 0

    def get_dir_list(self, cid):
        self.browse_calls += 1
        return [
            {"fn": "Zeta", "cid": "2"},
            {"fn": "Alpha", "cid": "1"},
        ]

    def get_download_url(self, pickcode, user_agent=""):
        self.download_calls += 1
        self.download_requests.append((pickcode, user_agent))
        return f"https://download.example/{pickcode}?t={int(time()) + 3600}"

    def create_playback_copy(self, pickcode):
        self.copy_calls.append(pickcode)
        return PlaybackCopy(file_id="copy-file-id", pickcode="copy-pickcode")

    def delete_file(self, file_id):
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

    def get_download_url(self, pickcode, user_agent=""):
        with self._download_call_lock:
            self._download_call_count += 1
            call_number = self._download_call_count
        if call_number == 1:
            self._second_download_started.wait(timeout=0.1)
        else:
            self._second_download_started.set()
        return super().get_download_url(pickcode, user_agent=user_agent)


class ApiReliabilityTest(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.store = FakeStore()
        self.api = Api(lambda: self.client, self.store, lambda: "token")

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

    def test_browse_115_sorts_and_caches_short_lived_results(self):
        first = self.api.browse_115("0")
        second = self.api.browse_115("0")

        self.assertTrue(first["success"])
        self.assertEqual([item["name"] for item in first["data"]["items"]], ["Alpha", "Zeta"])
        self.assertEqual(second["data"], first["data"])
        self.assertEqual(self.client.browse_calls, 1)

    def test_config_save_cannot_replace_internal_tokens(self):
        self.store.config["tokens"] = {"access_token": "internal"}

        result = self.api.save_config({"enabled": False, "tokens": {"access_token": "injected"}})

        self.assertTrue(result["success"])
        self.assertFalse(self.store.config["enabled"])
        self.assertEqual(self.store.config["tokens"], {"access_token": "internal"})

    def test_local_directory_root_is_filesystem_root(self):
        self.assertEqual(Api._local_roots(), [Path("/").resolve()])

    def test_redirect_uses_pickcode_and_user_agent_cache(self):
        request = self.request("Player-A")
        first = self.api.redirect(request, "pick", "token")
        second = self.api.redirect(request, "pick", "token")

        self.assertIn("https://download.example/pick", first.headers["location"])
        self.assertEqual(second.headers["location"], first.headers["location"])
        self.assertEqual(self.client.download_calls, 1)
        self.assertEqual(self.client.download_requests, [("pick", "Player-A")])

    def test_same_playback_copies_file_for_second_user_agent_and_schedules_cleanup(self):
        self.store.config["same_playback"] = True
        first = self.api.redirect(self.request("Player-A"), "pick", "token")

        with patch.object(self.api, "_schedule_playback_copy_cleanup") as cleanup:
            second = self.api.redirect(self.request("Player-B"), "pick", "token")

        self.assertIn("https://download.example/pick", first.headers["location"])
        self.assertIn("https://download.example/copy-pickcode", second.headers["location"])
        self.assertEqual(self.client.copy_calls, ["pick"])
        self.assertEqual(self.client.download_requests[-1], ("copy-pickcode", "Player-B"))
        cleanup.assert_called_once_with(self.client, "copy-file-id")

    def test_redirect_singleflight_rechecks_same_user_agent_cache(self):
        client = CoordinatedDownloadClient()
        api = Api(lambda: client, self.store, lambda: "token")
        barrier = threading.Barrier(3)

        def redirect():
            barrier.wait()
            return api.redirect(self.request("Player-A"), "pick", "token")

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(redirect) for _ in range(2)]
            barrier.wait()
            responses = [future.result(timeout=2) for future in futures]

        self.assertEqual(client.download_requests, [("pick", "Player-A")])
        self.assertEqual(responses[0].headers["location"], responses[1].headers["location"])
        self.assertEqual(api._redirect_flights, {})

    def test_same_playback_serializes_first_requests_for_different_user_agents(self):
        client = CoordinatedDownloadClient()
        self.store.config["same_playback"] = True
        api = Api(lambda: client, self.store, lambda: "token")
        barrier = threading.Barrier(3)

        def redirect(user_agent):
            barrier.wait()
            return api.redirect(self.request(user_agent), "pick", "token")

        with patch.object(api, "_schedule_playback_copy_cleanup") as cleanup, ThreadPoolExecutor(
            max_workers=2
        ) as executor:
            futures = [executor.submit(redirect, user_agent) for user_agent in ("Player-A", "Player-B")]
            barrier.wait()
            responses = [future.result(timeout=2) for future in futures]

        self.assertEqual(client.copy_calls, ["pick"])
        self.assertEqual(
            {pickcode for pickcode, _user_agent in client.download_requests},
            {"pick", "copy-pickcode"},
        )
        self.assertEqual(
            {response.headers["location"].split("?")[0] for response in responses},
            {"https://download.example/pick", "https://download.example/copy-pickcode"},
        )
        cleanup.assert_called_once_with(client, "copy-file-id")

    def test_same_playback_schedules_copy_cleanup_when_download_url_fails(self):
        self.store.config["same_playback"] = True
        self.api.redirect(self.request("Player-A"), "pick", "token")

        with patch.object(self.client, "get_download_url", side_effect=RuntimeError("downurl failed")), patch(
            "plugins.p115liteassistant.api.retry_call", side_effect=lambda operation, **_kwargs: operation()
        ), patch.object(self.api, "_schedule_playback_copy_cleanup") as cleanup:
            response = self.api.redirect(self.request("Player-B"), "pick", "token")

        self.assertEqual(response.status_code, 502)
        cleanup.assert_called_once_with(self.client, "copy-file-id")

    def test_same_playback_schedules_copy_cleanup_when_ttl_is_invalid(self):
        self.store.config["same_playback"] = True
        self.api.redirect(self.request("Player-A"), "pick", "token")

        with patch.object(
            self.client,
            "get_download_url",
            return_value="https://download.example/copy-without-expiry",
        ), patch.object(self.api, "_schedule_playback_copy_cleanup") as cleanup:
            response = self.api.redirect(self.request("Player-B"), "pick", "token")

        self.assertEqual(response.status_code, 502)
        cleanup.assert_called_once_with(self.client, "copy-file-id")

    def test_strm_execution_writes_start_and_summary_logs(self):
        self.store.config.update({"strm_incremental": True, "strm_mappings": []})

        with patch("plugins.p115liteassistant.api.logger") as task_logger:
            result = self.api.run_strm("http://moviepilot:3000")

        self.assertEqual(result, [])
        info_messages = [call.args[0] for call in task_logger.info.call_args_list]
        warning_messages = [call.args[0] for call in task_logger.warning.call_args_list]
        self.assertTrue(any("【STRM同步】开始执行" in message for message in info_messages))
        self.assertTrue(any("【STRM同步】执行完成" in message for message in info_messages))
        self.assertTrue(any("没有启用的目录映射" in message for message in warning_messages))

    def test_upload_execution_writes_start_and_summary_logs(self):
        self.store.config["upload_mappings"] = [{"enabled": True, "source": "/source", "target": "/target"}]
        upload_result = {
            "kind": "upload",
            "uploaded": 1,
            "instant": 0,
            "skipped": 0,
            "deleted": 0,
            "errors": 1,
            "duration_ms": 25,
            "errors_detail": [{"path": "/source/fail.mkv", "target": "/target/fail.mkv", "message": "失败"}],
        }

        with patch("plugins.p115liteassistant.api.DirectoryUploader") as uploader, patch(
            "plugins.p115liteassistant.api.logger"
        ) as task_logger:
            uploader.return_value.run.return_value = upload_result
            result = self.api.run_upload(incremental=True)

        self.assertEqual(result, upload_result)
        self.assertTrue(any("【目录上传】开始执行" in call.args[0] for call in task_logger.info.call_args_list))
        self.assertTrue(any("【目录上传】执行完成" in call.args[0] for call in task_logger.warning.call_args_list))

    def test_checkin_execution_writes_result_log(self):
        with patch("plugins.p115liteassistant.api.logger") as task_logger:
            result = self.api.run_checkin()

        self.assertTrue(result["success"])
        info_messages = [call.args[0] for call in task_logger.info.call_args_list]
        self.assertTrue(any("【115签到】开始执行" in message for message in info_messages))
        self.assertTrue(any("本次积分 5" in message for message in info_messages))

    def test_redirect_failure_writes_redacted_plugin_log(self):
        with patch.object(self.client, "get_download_url", side_effect=RuntimeError("apikey=secret")), patch(
            "plugins.p115liteassistant.api.retry_call", side_effect=lambda operation, **_kwargs: operation()
        ), patch("plugins.p115liteassistant.api.logger") as task_logger:
            response = self.api.redirect(self.request(), "pick", "token")

        self.assertEqual(response.status_code, 502)
        error_message = task_logger.error.call_args.args[0]
        self.assertIn("【302取链】", error_message)
        self.assertNotIn("secret", error_message)

    def test_task_start_failure_releases_running_state(self):
        with patch("plugins.p115liteassistant.api.threading.Thread.start", side_effect=RuntimeError("start failed")), patch(
            "plugins.p115liteassistant.api.logger"
        ) as task_logger:
            result = self.api._start("strm", lambda: None, "STRM 同步已开始")

        self.assertFalse(result["success"])
        self.assertNotIn("strm", self.api._running)
        self.assertTrue(any("任务启动失败" in call.args[0] for call in task_logger.error.call_args_list))

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
