from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
from time import time
import unittest
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from p115pickcode import id_to_pickcode
from plugins.p115liteassistant import P115LiteAssistant
from plugins.p115liteassistant.api import Api
from plugins.p115liteassistant.client import PlaybackCopy
from plugins.p115liteassistant.log_utils import safe_error_text
from plugins.p115liteassistant.strm import build_redirect_signature


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

    def test_local_directory_root_is_filesystem_root(self):
        self.assertEqual(Api._local_roots(), [Path("/").resolve()])

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
            "plugins.p115liteassistant.api.retry_call", side_effect=lambda operation, **_kwargs: operation()
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
            response = self.signed_redirect(self.api, self.request())

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
