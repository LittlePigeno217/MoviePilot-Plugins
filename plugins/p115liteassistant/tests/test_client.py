from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

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
                if url == "https://proapi.115.com/alipaymini/files":
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
        self.assertEqual(session.requests[0][1], "https://proapi.115.com/alipaymini/files")
        self.assertNotIn("Content-Type", session.headers)

    def test_cookie_login_infers_the_device_api_from_uid(self):
        class DirectorySession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url == "https://proapi.115.com/115android/2.0/ufile/files":
                    return FakeResponse({"state": True, "data": []})
                raise AssertionError(f"unexpected request: {method} {url}")

        session = DirectorySession()
        U115Client(cookie="UID=1_F3_0; CID=2", session=session).get_dir_list()

        self.assertEqual(session.requests[0][1], "https://proapi.115.com/115android/2.0/ufile/files")

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

            result = U115Client(cookie="UID=1; CID=2", session=session).upload_file(
                {"fileid": "0", "path": "/Cloud"}, media
            )

            self.assertTrue(result.success)
            self.assertTrue(result.reused)
            self.assertEqual(result.file_item["fileid"], "123")
            self.assertEqual(session.requests[0][2]["data"]["target"], "U_1_0")

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
