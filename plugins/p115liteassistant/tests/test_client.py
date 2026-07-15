from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import httpx

from plugins.p115liteassistant.client import U115AuthError, U115Client


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
                    },
                }
            )
        raise AssertionError(f"unexpected request: {method} {url}")


class U115ClientTest(unittest.TestCase):
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
        items = U115Client(cookie="UID=1; CID=2", client_type="alipaymini", session=session).get_dir_list("12")

        self.assertEqual(items, [{"cid": "12", "fc": "0", "fn": "Movies"}])
        self.assertEqual(session.requests[0][2]["params"]["cid"], 12)
        self.assertEqual(session.requests[0][2]["params"]["limit"], 1150)
        self.assertEqual(session.requests[0][2]["params"]["custom_order"], 1)
        self.assertIn("iPhone", session.requests[0][2]["headers"]["User-Agent"])
        self.assertEqual(session.requests[0][1], "https://webapi.115.com/files")
        self.assertNotIn("Content-Type", session.headers)

    def test_cookie_login_falls_back_to_device_api_from_uid(self):
        class DirectorySession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url == "https://webapi.115.com/files":
                    return FakeResponse({"state": False, "code": 500, "error": "temporary failure"})
                if url == "https://proapi.115.com/115android/2.0/ufile/files":
                    return FakeResponse(
                        {
                            "state": True,
                            "code": "",
                            "data": [
                                {
                                    "category_id": "12",
                                    "category_name": "Movies",
                                    "file_category": "0",
                                }
                            ],
                        }
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        session = DirectorySession()
        client = U115Client(cookie="UID=1_F3_0; CID=2", session=session)
        client.read_retry_delay = 0
        items = client.get_dir_list()

        self.assertEqual(session.requests[-1][1], "https://proapi.115.com/115android/2.0/ufile/files")
        self.assertEqual(client._item_name(items[0]), "Movies")
        self.assertEqual(client._item_id(items[0]), "12")

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
            self.assertEqual(session.headers["Authorization"], "Bearer token")

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
        self.assertEqual(session.headers["Authorization"], "Bearer open-token")
        token_saver.assert_called_once()
        auth_request = next(request for request in session.requests if request[1].endswith("/open/authDeviceCode"))
        self.assertEqual(auth_request[2]["data"]["client_id"], "app-id")
        upload_request = next(request for request in session.requests if request[1].endswith("/open/upload/init"))
        self.assertEqual(upload_request[2]["data"]["target"], "U_1_0")

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
        self.assertEqual(session.headers["Authorization"], "Bearer new-token")
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
                    if self.headers.get("Authorization") == "Bearer new-token":
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
        self.assertEqual(session.headers["Authorization"], "Bearer new-token")

    def test_invalid_token_falls_back_to_cookie_open_authorization(self):
        class CookieFallbackSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/user/info"):
                    if self.headers.get("Authorization") == "Bearer cookie-token":
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
        self.assertEqual(session.headers["Authorization"], "Bearer cookie-token")

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
        result = U115Client(cookie="UID=1; CID=2", session=session).checkin(retry_delay=0)

        self.assertEqual(session.post_attempts, 3)
        self.assertEqual(result["continuous_day"], 8)
        self.assertEqual(result["points_num"], 15)
