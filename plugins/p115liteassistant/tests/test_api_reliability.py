from pathlib import Path
import unittest
from unittest.mock import patch

from plugins.p115liteassistant.api import Api
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
        self.checkin_calls = 0

    def get_dir_list(self, cid):
        self.browse_calls += 1
        return [
            {"fn": "Zeta", "cid": "2"},
            {"fn": "Alpha", "cid": "1"},
        ]

    def get_download_url(self, pickcode):
        self.download_calls += 1
        return f"https://download.example/{pickcode}"

    def checkin(self):
        self.checkin_calls += 1
        return {"already": False, "continuous_day": 3, "points_num": 5, "message": "签到成功"}


class ApiReliabilityTest(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.store = FakeStore()
        self.api = Api(lambda: self.client, self.store, lambda: "token")

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

    def test_redirect_uses_short_lived_pickcode_cache(self):
        first = self.api.redirect("pick", "token")
        second = self.api.redirect("pick", "token")

        self.assertEqual(first.headers["location"], "https://download.example/pick")
        self.assertEqual(second.headers["location"], "https://download.example/pick")
        self.assertEqual(self.client.download_calls, 1)

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
            response = self.api.redirect("pick", "token")

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
