from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import Mock, patch

import httpx

from plugins.p115liteassistant.client import U115ApiError, U115AuthError, U115Client


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        if url.endswith("/open/upload/init"):
            return FakeResponse({"code": 0, "state": True, "data": {"status": 2, "file_id": "123"}})
        if url.endswith("/open/folder/get_info"):
            return FakeResponse(
                {
                    "code": 0,
                    "state": True,
                    "data": {
                        "file_id": "123",
                        "file_category": "1",
                        "file_name": "Film.mkv",
                        "pick_code": "pickcode",
                        "size_byte": "5",
                    },
                }
            )
        raise AssertionError(f"unexpected request: {method} {url}")


class U115ClientTest(unittest.TestCase):
    def test_get_item_normalizes_open_size_byte(self):
        client = U115Client(tokens={"access_token": "token"}, session=FakeSession())

        item = client.get_item("/Cloud/Film.mkv")

        self.assertEqual(item["path"], "/Cloud/Film.mkv")
        self.assertEqual(item["type"], "file")
        self.assertEqual(item["pickcode"], "pickcode")
        self.assertEqual(item["size"], 5)

    def test_qrcode_login_persists_selected_client_cookie(self):
        class QrSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/api/1.0/web/1.0/token/"):
                    return FakeResponse({"code": 0, "data": {"uid": "uid", "time": "time", "sign": "sign", "qrcode": "115://login"}})
                if url.endswith("/get/status/"):
                    return FakeResponse({"code": 0, "data": {"status": 2, "msg": "已确认"}})
                if url.endswith("/app/1.0/115android/1.0/login/qrcode/"):
                    return FakeResponse({"state": True, "data": {"cookie": {"UID": "1", "CID": "2"}}})
                raise AssertionError(f"unexpected request: {method} {url}")

        client = U115Client(session=QrSession())
        result = client.generate_qrcode("115android")
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["client_type"], "115android")
        self.assertEqual(client.check_login()["data"]["status"], 2)
        self.assertEqual(client.cookie, "UID=1; CID=2")

    def test_cookie_login_lists_directories_from_web_api(self):
        class DirectorySession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url == "https://webapi.115.com/files":
                    return FakeResponse(
                        {
                            "state": True,
                            "data": [{"cid": "12", "fc": "0", "fn": "Movies"}],
                        }
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        session = DirectorySession()
        items = U115Client(
            cookie="UID=1; CID=2",
            tokens={"access_token": "open-token"},
            client_type="alipaymini",
            session=session,
        ).get_dir_list("12")

        self.assertEqual(items, [{"cid": "12", "fc": "0", "fn": "Movies"}])
        self.assertEqual(session.requests[0][2]["params"]["cid"], 12)
        self.assertEqual(session.requests[0][2]["params"]["limit"], 1150)
        self.assertEqual(session.requests[0][2]["params"]["custom_order"], 1)
        request_headers = session.requests[0][2]["headers"]
        self.assertIn("iPhone", request_headers["User-Agent"])
        self.assertEqual(request_headers["Cookie"], "UID=1; CID=2")
        self.assertNotIn("Authorization", request_headers)
        self.assertEqual(session.requests[0][1], "https://webapi.115.com/files")
        self.assertNotIn("Content-Type", session.headers)
        self.assertNotIn("Cookie", session.headers)
        self.assertNotIn("Authorization", session.headers)

    def test_cookie_directory_listing_reads_all_pages_without_fixed_delay(self):
        class PagedDirectorySession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                offset = kwargs["params"]["offset"]
                size = 1150 if offset == 0 else 1
                return FakeResponse(
                    {
                        "state": True,
                        "count": 1151,
                        "data": [
                            {"fid": f"{offset + index}", "fc": "1", "fn": f"Film{offset + index}.mkv"}
                            for index in range(size)
                        ],
                    }
                )

        session = PagedDirectorySession()
        client = U115Client(cookie="UID=1; CID=2", session=session)
        client.directory_request_interval = 0

        items = client.get_dir_list("12")

        self.assertEqual(len(items), 1151)
        self.assertEqual([request[2]["params"]["offset"] for request in session.requests], [0, 1150])

    def test_cookie_auth_failure_does_not_fallback_to_login_client_api(self):
        class DirectorySession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url == "https://webapi.115.com/files":
                    return FakeResponse(
                        {"state": False, "errno": 990001, "message": "登录超时，请重新登录"}
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        session = DirectorySession()
        client = U115Client(
            cookie="UID=1_R2_0; CID=2",
            client_type="alipaymini",
            session=session,
        )

        with self.assertRaisesRegex(U115AuthError, "Cookie 已失效"):
            client.get_dir_list()

        self.assertEqual(len(session.requests), 1)
        self.assertEqual(session.requests[0][1], "https://webapi.115.com/files")

    def test_cookie_directory_http_405_is_not_retried(self):
        class MethodNotAllowedResponse:
            def __init__(self, url):
                request = httpx.Request("GET", url)
                self.response = httpx.Response(405, request=request)

            def raise_for_status(self):
                raise httpx.HTTPStatusError(
                    "method not allowed",
                    request=self.response.request,
                    response=self.response,
                )

            @staticmethod
            def json():
                return {"state": False}

        class DirectorySession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                return MethodNotAllowedResponse(url)

        session = DirectorySession()
        client = U115Client(cookie="UID=1; CID=2", session=session)

        with self.assertRaises(httpx.HTTPStatusError):
            client.get_dir_list()

        self.assertEqual(len(session.requests), 1)
        self.assertEqual(session.requests[0][1], "https://webapi.115.com/files")

    def test_cookie_response_with_empty_code_is_successful(self):
        self.assertTrue(U115Client._is_response_success({"state": True, "code": ""}))

    def test_oauth_login_lists_directories_from_open_api(self):
        class DirectorySession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/ufile/files"):
                    return FakeResponse(
                        {
                            "code": 0,
                            "state": True,
                            "data": [{"cid": "12", "fc": "0", "fn": "Movies"}],
                        }
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        session = DirectorySession()
        items = U115Client(tokens={"access_token": "token"}, session=session).get_dir_list("12")

        self.assertEqual(items, [{"cid": "12", "fc": "0", "fn": "Movies"}])
        self.assertTrue(session.requests[0][1].endswith("/open/ufile/files"))
        self.assertEqual(session.requests[0][2]["headers"]["Authorization"], "Bearer token")
        self.assertNotIn("Cookie", session.requests[0][2]["headers"])
        self.assertNotIn("Authorization", session.headers)

    def test_open_directory_listing_reads_all_pages(self):
        class PagedDirectorySession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                offset = kwargs["params"]["offset"]
                size = 1000 if offset == 0 else 1
                return FakeResponse(
                    {
                        "code": 0,
                        "data": [
                            {"fid": f"{offset + index}", "fc": "1", "fn": f"Film{offset + index}.mkv"}
                            for index in range(size)
                        ],
                    }
                )

        session = PagedDirectorySession()
        client = U115Client(tokens={"access_token": "token"}, session=session)
        client.directory_request_interval = 0

        items = client.get_dir_list("12")

        self.assertEqual(len(items), 1001)
        self.assertEqual([request[2]["params"]["offset"] for request in session.requests], [0, 1000])

    def test_iter_files_scans_independent_directories_concurrently(self):
        client = U115Client(session=FakeSession())
        client.directory_scan_workers = 4
        client.directory_scan_prefetch = 8
        state_lock = threading.Lock()
        active = 0
        max_active = 0

        def get_dir_list(cid):
            nonlocal active, max_active
            with state_lock:
                active += 1
                max_active = max(max_active, active)
            try:
                time.sleep(0.03)
                if cid == "root":
                    return [{"cid": str(index), "fc": "0", "fn": f"Dir{index}"} for index in range(8)]
                return [{"fid": f"file-{cid}", "fc": "1", "fn": "Film.mkv", "pc": f"pick-{cid}"}]
            finally:
                with state_lock:
                    active -= 1

        client.get_dir_list = get_dir_list

        files = list(client.iter_files("root"))

        self.assertGreaterEqual(max_active, 2)
        self.assertEqual(
            sorted(item["rel_path"] for item in files),
            [f"Dir{index}/Film.mkv" for index in range(8)],
        )

    def test_upload_requires_login(self):
        with TemporaryDirectory() as directory:
            with self.assertRaises(U115AuthError):
                U115Client(session=FakeSession()).upload_file(
                    {"fileid": "0", "path": "/"}, Path(directory) / "missing.mkv"
                )

    def test_upload_marks_rapid_upload_as_reused(self):
        with TemporaryDirectory() as directory:
            media = Path(directory) / "Film.mkv"
            media.write_bytes(b"media")
            session = FakeSession()

            result = U115Client(tokens={"access_token": "token"}, session=session).upload_file(
                {"fileid": "0", "path": "/Cloud"}, media
            )

            self.assertTrue(result.success)
            self.assertTrue(result.reused)
            self.assertEqual(result.file_item["fileid"], "123")
            self.assertEqual(session.requests[0][2]["data"]["target"], "U_1_0")
            self.assertEqual(len(session.requests), 1)
        request_headers = session.requests[0][2]["headers"]
        self.assertEqual(request_headers["Authorization"], "Bearer token")
        self.assertNotIn("Cookie", request_headers)
        self.assertNotIn("Authorization", session.headers)

    def test_download_url_forwards_playback_user_agent(self):
        class DownloadSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/ufile/downurl"):
                    return FakeResponse(
                        {
                            "code": 0,
                            "data": {"1": {"url": {"url": "https://download.example/file"}}},
                        }
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        session = DownloadSession()
        client = U115Client(tokens={"access_token": "token"}, session=session)

        url = client.get_download_url("pick", user_agent="Player/1.0")

        self.assertEqual(url, "https://download.example/file")
        request = session.requests[0]
        self.assertEqual(
            request[2]["headers"],
            {"User-Agent": "Player/1.0", "Authorization": "Bearer token"},
        )

    def test_download_url_is_one_qps_while_download_streams_remain_concurrent(self):
        class DownloadSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/ufile/downurl"):
                    pickcode = kwargs["data"]["pick_code"]
                    return FakeResponse(
                        {
                            "code": 0,
                            "data": {
                                pickcode: {
                                    "url": {"url": f"https://download.example/{pickcode}"}
                                }
                            },
                        }
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        stream_barrier = threading.Barrier(2)
        stream_lock = threading.Lock()
        sleep_delays = []
        active_streams = 0
        max_active_streams = 0

        class DownloadResponse:
            def __enter__(self):
                nonlocal active_streams, max_active_streams
                with stream_lock:
                    active_streams += 1
                    max_active_streams = max(max_active_streams, active_streams)
                stream_barrier.wait(timeout=1)
                return self

            def __exit__(self, *_args):
                nonlocal active_streams
                with stream_lock:
                    active_streams -= 1

            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def iter_bytes():
                return iter((b"media",))

        session = DownloadSession()
        client = U115Client(tokens={"access_token": "token"}, session=session)

        with TemporaryDirectory() as directory, patch(
            "plugins.p115liteassistant.client.time.monotonic", return_value=100.0
        ), patch(
            "plugins.p115liteassistant.client.time.sleep",
            side_effect=lambda delay: sleep_delays.append(delay),
        ), patch(
            "plugins.p115liteassistant.client.httpx.stream",
            side_effect=lambda *_args, **_kwargs: DownloadResponse(),
        ), ThreadPoolExecutor(max_workers=2) as executor:
            outputs = [Path(directory) / f"{pickcode}.mkv" for pickcode in ("one", "two")]
            futures = [
                executor.submit(client.download_file, pickcode, output)
                for pickcode, output in zip(("one", "two"), outputs)
            ]
            for future in futures:
                future.result(timeout=2)

            self.assertEqual([output.read_bytes() for output in outputs], [b"media", b"media"])

        self.assertEqual(sleep_delays, [1.0])
        self.assertEqual(max_active_streams, 2)
        self.assertEqual(len(session.requests), 2)

    def test_playback_copy_uses_upstream_copy_directory_and_returns_latest_pickcode(self):
        class PlaybackSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/ufile/copy"):
                    return FakeResponse({"code": 0, "state": True})
                if url.endswith("/open/ufile/files"):
                    return FakeResponse(
                        {
                            "code": 0,
                            "data": [
                                {
                                    "cid": "99",
                                    "fid": "456",
                                    "fc": "1",
                                    "fn": "Film.mkv",
                                    "pc": "copy-pickcode",
                                }
                            ],
                        }
                    )
                if url.endswith("/open/ufile/delete"):
                    return FakeResponse({"code": 0, "state": True})
                raise AssertionError(f"unexpected request: {method} {url}")

        session = PlaybackSession()
        client = U115Client(tokens={"access_token": "token"}, session=session)
        client._playback_dir_id = "99"

        with patch.object(client, "_pickcode_to_file_id", return_value=123):
            copied = client.create_playback_copy("original-pickcode")
        client.delete_file(copied.file_id)

        self.assertEqual(copied.file_id, "456")
        self.assertEqual(copied.pickcode, "copy-pickcode")
        copy_request = next(item for item in session.requests if item[1].endswith("/open/ufile/copy"))
        self.assertEqual(copy_request[2]["data"], {"file_id": 123, "pid": 99})
        self.assertEqual(
            copy_request[2]["headers"],
            {"User-Agent": client.ios_user_agent, "Authorization": "Bearer token"},
        )
        list_request = next(item for item in session.requests if item[1].endswith("/open/ufile/files"))
        self.assertEqual(list_request[2]["params"]["o"], "user_ptime")
        self.assertEqual(list_request[2]["params"]["asc"], 0)
        self.assertEqual(list_request[2]["params"]["custom_order"], 2)
        delete_request = next(item for item in session.requests if item[1].endswith("/open/ufile/delete"))
        self.assertEqual(delete_request[2]["data"], {"file_ids": 456})
        self.assertEqual(
            delete_request[2]["headers"],
            {"User-Agent": client.ios_user_agent, "Authorization": "Bearer token"},
        )

    def test_playback_copy_serializes_copy_and_latest_lookup_across_files(self):
        class ConcurrentPlaybackSession(FakeSession):
            def __init__(self):
                super().__init__()
                self.state_lock = threading.Lock()
                self.operations = []
                self.latest_file_id = 0
                self.copy_calls = 0
                self.second_copy_started = threading.Event()

            def request(self, method, url, **kwargs):
                if url.endswith("/open/ufile/copy"):
                    file_id = int(kwargs["data"]["file_id"])
                    with self.state_lock:
                        self.operations.append(("copy", file_id))
                        self.latest_file_id = file_id
                        self.copy_calls += 1
                        copy_call = self.copy_calls
                    if copy_call == 1:
                        self.second_copy_started.wait(timeout=0.1)
                    else:
                        self.second_copy_started.set()
                    return FakeResponse({"code": 0, "state": True})
                if url.endswith("/open/ufile/files"):
                    with self.state_lock:
                        file_id = self.latest_file_id
                        self.operations.append(("files", file_id))
                    return FakeResponse(
                        {
                            "code": 0,
                            "data": [
                                {
                                    "fid": str(100 + file_id),
                                    "fc": "1",
                                    "fn": f"Film{file_id}.mkv",
                                    "pc": f"copy-{file_id}",
                                }
                            ],
                        }
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        session = ConcurrentPlaybackSession()
        client = U115Client(tokens={"access_token": "token"}, session=session)
        client._playback_dir_id = "99"
        barrier = threading.Barrier(3)

        def create_copy(pickcode):
            barrier.wait()
            return client.create_playback_copy(pickcode)

        with patch.object(client, "_pickcode_to_file_id", side_effect=lambda value: int(value)), ThreadPoolExecutor(
            max_workers=2
        ) as executor:
            futures = [executor.submit(create_copy, pickcode) for pickcode in ("1", "2")]
            barrier.wait()
            copies = [future.result(timeout=2) for future in futures]

        self.assertEqual({copy.pickcode for copy in copies}, {"copy-1", "copy-2"})
        self.assertEqual(
            [operation for operation, _file_id in session.operations],
            ["copy", "files", "copy", "files"],
        )

    def test_playback_copy_best_effort_cleans_up_when_first_list_is_empty(self):
        class CleanupSession(FakeSession):
            def __init__(self):
                super().__init__()
                self.list_calls = 0

            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/ufile/copy"):
                    return FakeResponse({"code": 0, "state": True})
                if url.endswith("/open/ufile/files"):
                    self.list_calls += 1
                    if self.list_calls == 1:
                        return FakeResponse({"code": 0, "data": []})
                    return FakeResponse(
                        {
                            "code": 0,
                            "data": [{"fid": "456", "fc": "1", "fn": "Film.mkv", "pc": "copy-pickcode"}],
                        }
                    )
                if url.endswith("/open/ufile/delete"):
                    return FakeResponse({"code": 0, "state": True})
                raise AssertionError(f"unexpected request: {method} {url}")

        session = CleanupSession()
        client = U115Client(tokens={"access_token": "token"}, session=session)
        client._playback_dir_id = "99"

        with patch.object(client, "_pickcode_to_file_id", return_value=123), self.assertRaisesRegex(
            RuntimeError,
            "复制多端播放文件后未找到副本",
        ):
            client.create_playback_copy("original-pickcode")

        self.assertEqual(session.list_calls, 2)
        delete_request = next(item for item in session.requests if item[1].endswith("/open/ufile/delete"))
        self.assertEqual(delete_request[2]["data"], {"file_ids": 456})

    def test_cookie_login_authorizes_open_api_before_upload(self):
        class CookieUploadSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/authDeviceCode"):
                    return FakeResponse({"code": 0, "data": {"uid": "open-uid"}})
                if url.endswith("/api/2.0/prompt.php") or url.endswith("/api/2.0/slogin.php"):
                    return FakeResponse({"state": True})
                if url.endswith("/open/deviceCodeToToken"):
                    return FakeResponse(
                        {
                            "code": 0,
                            "data": {
                                "access_token": "open-token",
                                "refresh_token": "refresh-token",
                                "expires_in": 7200,
                            },
                        }
                    )
                if url.endswith("/open/user/info"):
                    return FakeResponse({"code": 0, "data": {"user_id": "1"}})
                return super().request(method, url, **kwargs)

        with TemporaryDirectory() as directory, patch.object(U115Client, "_open_client_id", return_value="app-id"):
            media = Path(directory) / "Film.mkv"
            media.write_bytes(b"media")
            token_saver = Mock()
            session = CookieUploadSession()
            client = U115Client(cookie="UID=1; CID=2", session=session, token_saver=token_saver)

            client.ensure_upload_ready()
            result = client.upload_file({"fileid": "0", "path": "/Cloud"}, media)

        self.assertTrue(result.success)
        self.assertTrue(result.reused)
        self.assertEqual(client.tokens["access_token"], "open-token")
        self.assertNotIn("Authorization", session.headers)
        prompt_request = next(
            request for request in session.requests if request[1].endswith("/api/2.0/prompt.php")
        )
        self.assertEqual(prompt_request[2]["headers"]["Cookie"], "UID=1; CID=2")
        self.assertNotIn("Authorization", prompt_request[2]["headers"])
        token_saver.assert_called_once()
        auth_request = next(request for request in session.requests if request[1].endswith("/open/authDeviceCode"))
        self.assertEqual(auth_request[2]["data"]["client_id"], "app-id")
        upload_request = next(request for request in session.requests if request[1].endswith("/open/upload/init"))
        self.assertEqual(upload_request[2]["data"]["target"], "U_1_0")
        self.assertEqual(upload_request[2]["headers"]["Authorization"], "Bearer open-token")
        self.assertNotIn("Cookie", upload_request[2]["headers"])

    def test_expired_open_token_is_refreshed_and_persisted(self):
        class RefreshSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/refreshToken"):
                    return FakeResponse(
                        {
                            "code": 0,
                            "data": {
                                "access_token": "new-token",
                                "refresh_token": "new-refresh",
                                "expires_in": 7200,
                            },
                        }
                    )
                if url.endswith("/open/user/info"):
                    return FakeResponse({"code": 0, "data": {"user_id": "1"}})
                raise AssertionError(f"unexpected request: {method} {url}")

        token_saver = Mock()
        session = RefreshSession()
        client = U115Client(
            tokens={
                "access_token": "expired-token",
                "refresh_token": "old-refresh",
                "expires_in": 1,
                "refresh_time": 1,
            },
            session=session,
            token_saver=token_saver,
        )

        client.ensure_upload_ready()

        self.assertEqual(client.tokens["access_token"], "new-token")
        user_request = next(
            request for request in session.requests if request[1].endswith("/open/user/info")
        )
        self.assertEqual(user_request[2]["headers"]["Authorization"], "Bearer new-token")
        self.assertNotIn("Cookie", user_request[2]["headers"])
        self.assertNotIn("Authorization", session.headers)
        token_saver.assert_called_once()
        self.assertEqual(token_saver.call_args.args[0]["refresh_token"], "new-refresh")

    def test_http_401_preflight_refreshes_open_token(self):
        class UnauthorizedResponse:
            def __init__(self, url):
                request = httpx.Request("GET", url)
                self.response = httpx.Response(401, request=request)

            def raise_for_status(self):
                raise httpx.HTTPStatusError(
                    "unauthorized",
                    request=self.response.request,
                    response=self.response,
                )

            def json(self):
                return {"code": 401}

        class RefreshAfter401Session(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/user/info"):
                    if kwargs.get("headers", {}).get("Authorization") == "Bearer new-token":
                        return FakeResponse({"code": 0, "data": {"user_id": "1"}})
                    return UnauthorizedResponse(url)
                if url.endswith("/open/refreshToken"):
                    return FakeResponse(
                        {
                            "code": 0,
                            "data": {
                                "access_token": "new-token",
                                "refresh_token": "new-refresh",
                                "expires_in": 7200,
                            },
                        }
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        session = RefreshAfter401Session()
        client = U115Client(
            tokens={"access_token": "invalid-token", "refresh_token": "refresh-token"},
            session=session,
        )
        client.read_retry_delay = 0

        client.ensure_upload_ready()

        self.assertEqual(client.tokens["access_token"], "new-token")
        self.assertEqual(
            session.requests[-1][2]["headers"]["Authorization"],
            "Bearer new-token",
        )
        self.assertNotIn("Authorization", session.headers)

    def test_invalid_token_falls_back_to_cookie_open_authorization(self):
        class CookieFallbackSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/user/info"):
                    if kwargs.get("headers", {}).get("Authorization") == "Bearer cookie-token":
                        return FakeResponse({"code": 0, "data": {"user_id": "1"}})
                    return FakeResponse({"state": False, "code": 40140125, "message": "access_token 已失效"})
                if url.endswith("/open/refreshToken"):
                    return FakeResponse({"code": 401, "message": "refresh_token 已失效"})
                if url.endswith("/open/authDeviceCode"):
                    return FakeResponse({"code": 0, "data": {"uid": "open-uid"}})
                if url.endswith("/api/2.0/prompt.php") or url.endswith("/api/2.0/slogin.php"):
                    return FakeResponse({"state": True})
                if url.endswith("/open/deviceCodeToToken"):
                    return FakeResponse(
                        {
                            "code": 0,
                            "data": {
                                "access_token": "cookie-token",
                                "refresh_token": "cookie-refresh",
                                "expires_in": 7200,
                            },
                        }
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        session = CookieFallbackSession()
        client = U115Client(
            cookie="UID=1; CID=2",
            tokens={"access_token": "invalid-token", "refresh_token": "invalid-refresh"},
            session=session,
        )
        client.read_retry_delay = 0

        with patch.object(U115Client, "_open_client_id", return_value="app-id"):
            client.ensure_upload_ready()

        self.assertEqual(client.tokens["access_token"], "cookie-token")
        self.assertEqual(
            session.requests[-1][2]["headers"]["Authorization"],
            "Bearer cookie-token",
        )
        self.assertNotIn("Authorization", session.headers)

    def test_checkin_retries_failed_post_requests(self):
        class CheckinSession(FakeSession):
            def __init__(self):
                super().__init__()
                self.post_attempts = 0

            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if method == "GET" and url.endswith("/user/points_sign"):
                    return FakeResponse({"state": True, "data": {"is_sign_today": 0}})
                if method == "POST" and url.endswith("/user/points_sign"):
                    self.post_attempts += 1
                    if self.post_attempts < 3:
                        return FakeResponse({"state": False, "message": "temporary failure"})
                    return FakeResponse(
                        {"state": True, "data": {"continuous_day": 8, "points_num": 15}}
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        session = CheckinSession()
        with patch("plugins.p115liteassistant.client.time.time", return_value=1_700_000_000):
            result = U115Client(cookie="UID=1_R2_0; CID=2", session=session).checkin(
                retry_delay=0
            )

        self.assertEqual(session.post_attempts, 3)
        self.assertEqual(result["continuous_day"], 8)
        self.assertEqual(result["points_num"], 15)
        self.assertTrue(
            all(
                request[1] == "https://proapi.115.com/android/2.0/user/points_sign"
                for request in session.requests
            )
        )
        expected_token = hashlib.sha1(
            b"1-Points_Sign@#115-1700000000"
        ).hexdigest()
        post_requests = [request for request in session.requests if request[0] == "POST"]
        self.assertTrue(
            all(
                request[2]["data"]
                == {"token": expected_token, "token_time": 1_700_000_000}
                for request in post_requests
            )
        )
        self.assertTrue(
            all(request[2]["headers"]["Cookie"] == "UID=1_R2_0; CID=2" for request in session.requests)
        )
        self.assertTrue(
            all("Authorization" not in request[2]["headers"] for request in session.requests)
        )

    def test_checkin_requires_numeric_uid_from_cookie(self):
        client = U115Client(cookie="CID=2", session=FakeSession())

        with self.assertRaisesRegex(U115AuthError, "缺少有效 UID"):
            client.checkin()

    def test_checkin_surfaces_upstream_error_after_retries(self):
        class CheckinSession(FakeSession):
            def __init__(self):
                super().__init__()
                self.post_attempts = 0

            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if method == "GET" and url.endswith("/user/points_sign"):
                    return FakeResponse({"state": True, "data": {"is_sign_today": 0}})
                if method == "POST" and url.endswith("/user/points_sign"):
                    self.post_attempts += 1
                    return FakeResponse({"state": False, "message": "服务器开小差了，稍后再试吧"})
                raise AssertionError(f"unexpected request: {method} {url}")

        session = CheckinSession()
        client = U115Client(cookie="UID=1_R2_0; CID=2", session=session)

        with self.assertRaisesRegex(U115ApiError, "服务器开小差了"):
            client.checkin(retry_delay=0)

        self.assertEqual(session.post_attempts, 3)
