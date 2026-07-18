from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import httpx

from plugins.p115liteassistant.client import (
    PlaybackCopy,
    U115AccessLimitError,
    U115ApiError,
    U115AuthError,
    U115Client,
)
from plugins.p115liteassistant.resilience import retry_call


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
                        "utime": "123",
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
        self.assertEqual(item["mtime"], 123)

    def test_get_item_returns_none_for_open_api_error_payload(self):
        class MissingItemSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/folder/get_info"):
                    return FakeResponse(
                        {"state": False, "code": 20018, "message": "文件或目录不存在"}
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        item = U115Client(
            tokens={"access_token": "token"},
            session=MissingItemSession(),
        ).get_item("/Cloud/Missing.mkv")

        self.assertIsNone(item)

    def test_get_item_raises_for_non_missing_open_api_error(self):
        class FailedItemSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/folder/get_info"):
                    return FakeResponse(
                        {"state": False, "code": 50001, "message": "上游服务异常"}
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        client = U115Client(
            tokens={"access_token": "token"},
            session=FailedItemSession(),
        )

        with self.assertRaisesRegex(U115ApiError, "上游服务异常"):
            client.get_item("/Cloud/Film.mkv")

    def test_get_item_rejects_incomplete_success_payload(self):
        class IncompleteItemSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/folder/get_info"):
                    return FakeResponse(
                        {
                            "state": True,
                            "code": 0,
                            "data": {
                                "file_id": "123",
                                "file_category": "1",
                                "file_name": "Film.mkv",
                                "size_byte": "5",
                                "utime": "123",
                            },
                        }
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        client = U115Client(
            tokens={"access_token": "token"},
            session=IncompleteItemSession(),
        )

        with self.assertRaisesRegex(U115ApiError, "缺少 pick_code"):
            client.get_item("/Cloud/Film.mkv")

    def test_get_item_rejects_file_without_size(self):
        class IncompleteItemSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/folder/get_info"):
                    return FakeResponse(
                        {
                            "state": True,
                            "code": 0,
                            "data": {
                                "file_id": "123",
                                "file_category": "1",
                                "file_name": "Film.mkv",
                                "pick_code": "pickcode",
                                "utime": "123",
                            },
                        }
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        client = U115Client(
            tokens={"access_token": "token"},
            session=IncompleteItemSession(),
        )

        with self.assertRaisesRegex(U115ApiError, "缺少有效文件大小"):
            client.get_item("/Cloud/Film.mkv")

    def test_get_item_rejects_file_without_mtime(self):
        class IncompleteItemSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/folder/get_info"):
                    return FakeResponse(
                        {
                            "state": True,
                            "code": 0,
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

        client = U115Client(
            tokens={"access_token": "token"},
            session=IncompleteItemSession(),
        )

        with self.assertRaisesRegex(U115ApiError, "缺少有效修改时间"):
            client.get_item("/Cloud/Film.mkv")

    def test_response_success_rejects_nonzero_code_with_true_state(self):
        self.assertFalse(
            U115Client._is_response_success(
                {"state": True, "code": 911, "message": "已达到当前访问上限"}
            )
        )

    def test_upload_callback_success_requires_explicit_success_status(self):
        self.assertFalse(U115Client._is_upload_callback_success({}))
        self.assertFalse(
            U115Client._is_upload_callback_success({"message": "callback received"})
        )
        self.assertFalse(
            U115Client._is_upload_callback_success({"state": True, "code": 50001})
        )
        self.assertFalse(
            U115Client._is_upload_callback_success({"state": False, "code": 0})
        )
        self.assertTrue(U115Client._is_upload_callback_success({"state": True}))
        self.assertTrue(U115Client._is_upload_callback_success({"code": 0}))

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

    def test_cookie_login_lists_directories_from_open_api(self):
        class DirectorySession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/ufile/files"):
                    return FakeResponse(
                        {
                            "code": 0,
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
        self.assertEqual(session.requests[0][2]["params"]["o"], "user_utime")
        self.assertEqual(session.requests[0][2]["params"]["asc"], 0)
        self.assertNotIn("custom_order", session.requests[0][2]["params"])
        request_headers = session.requests[0][2]["headers"]
        self.assertEqual(request_headers["Authorization"], "Bearer open-token")
        self.assertNotIn("Cookie", request_headers)
        self.assertTrue(session.requests[0][1].endswith("/open/ufile/files"))
        self.assertNotIn("Content-Type", session.headers)
        self.assertNotIn("Cookie", session.headers)
        self.assertNotIn("Authorization", session.headers)

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
                size = 1150 if offset == 0 else 1
                return FakeResponse(
                    {
                        "code": 0,
                        "count": 1151,
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

        self.assertEqual(len(items), 1151)
        self.assertEqual([request[2]["params"]["offset"] for request in session.requests], [0, 1150])

    def test_open_directory_listing_continues_after_short_page_when_count_remains(self):
        class ShortPageDirectorySession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                offset = kwargs["params"]["offset"]
                size = 2 if offset == 0 else 1
                return FakeResponse(
                    {
                        "code": 0,
                        "count": 3,
                        "data": [
                            {"fid": f"{offset + index}", "fc": "1", "fn": f"Film{offset + index}.mkv"}
                            for index in range(size)
                        ],
                    }
                )

        session = ShortPageDirectorySession()
        client = U115Client(tokens={"access_token": "token"}, session=session)
        client.directory_request_interval = 0

        items = client.get_dir_list("12")

        self.assertEqual(len(items), 3)
        self.assertEqual([request[2]["params"]["offset"] for request in session.requests], [0, 2])

    def test_open_directory_invalid_page_does_not_switch_protocols(self):
        class InvalidDirectorySession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/ufile/files"):
                    return FakeResponse({"code": 0, "data": {"items": []}})
                raise AssertionError(f"unexpected request: {method} {url}")

        session = InvalidDirectorySession()
        client = U115Client(tokens={"access_token": "token"}, session=session)

        with self.assertRaisesRegex(U115ApiError, "目录分页返回了无效响应"):
            client.get_dir_list("12")

        self.assertEqual(len(session.requests), 1)
        self.assertTrue(session.requests[0][1].endswith("/open/ufile/files"))

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

    def test_iter_files_cancels_queued_directories_after_access_limit(self):
        client = U115Client(session=FakeSession())
        client.directory_scan_workers = 1
        client.directory_scan_prefetch = 8
        calls = []
        state_lock = threading.Lock()

        def get_dir_list(cid):
            with state_lock:
                calls.append(cid)
            if cid == "root":
                return [
                    {"cid": str(index), "fc": "0", "fn": f"Dir{index}"}
                    for index in range(8)
                ]
            raise U115AccessLimitError("已达到当前访问上限，请稍后再试")

        client.get_dir_list = get_dir_list

        with self.assertRaises(U115AccessLimitError):
            list(client.iter_files("root"))

        self.assertEqual(calls, ["root", "0"])

    def test_iter_files_interrupts_inflight_retry_wait_after_access_limit(self):
        client = U115Client(session=FakeSession())
        client.directory_scan_workers = 2
        client.directory_scan_prefetch = 2
        workers_started = threading.Barrier(2)
        interrupted = threading.Event()

        def get_dir_list(cid):
            if cid == "root":
                return [
                    {"cid": "1", "fc": "0", "fn": "Dir1"},
                    {"cid": "2", "fc": "0", "fn": "Dir2"},
                ]
            workers_started.wait(timeout=1)
            if cid == "1":
                raise U115AccessLimitError("已达到当前访问上限，请稍后再试")
            try:
                client._wait_for_request_retry(10)
            except U115AccessLimitError:
                interrupted.set()
                raise
            raise AssertionError("in-flight directory retry was not interrupted")

        client.get_dir_list = get_dir_list
        started = time.monotonic()

        with self.assertRaises(U115AccessLimitError):
            list(client.iter_files("root"))

        self.assertTrue(interrupted.is_set())
        self.assertLess(time.monotonic() - started, 2)

    def test_iter_files_stops_open_retries_on_first_access_limit(self):
        class LimitedDirectorySession(FakeSession):
            def __init__(self):
                super().__init__()
                self.directory_requests = 0
                self.request_lock = threading.Lock()

            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/ufile/files"):
                    with self.request_lock:
                        self.directory_requests += 1
                        request_number = self.directory_requests
                    if request_number == 1:
                        return FakeResponse(
                            {
                                "code": 0,
                                "state": True,
                                "data": [
                                    {"cid": "1", "fc": "0", "fn": "Dir1"},
                                    {"cid": "2", "fc": "0", "fn": "Dir2"},
                                ],
                                "count": 2,
                            }
                        )
                    return FakeResponse(
                        {
                            "code": 911,
                            "state": False,
                            "message": "已达到当前访问上限，请稍后再试",
                        }
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        session = LimitedDirectorySession()
        client = U115Client(tokens={"access_token": "token"}, session=session)
        client.directory_scan_workers = 2
        client.directory_scan_prefetch = 2
        client.directory_request_interval = 0
        client.open_access_limit_attempts = 6
        client.open_access_limit_delay = 60

        with self.assertRaises(U115AccessLimitError):
            list(client.iter_files("0"))

        self.assertLessEqual(session.directory_requests, 3)

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

    def test_second_upload_auth_preserves_first_oss_fields(self):
        class SecondAuthSession(FakeSession):
            def __init__(self):
                super().__init__()
                self.init_calls = 0

            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/upload/init"):
                    self.init_calls += 1
                    if self.init_calls == 1:
                        return FakeResponse(
                            {
                                "state": True,
                                "code": 0,
                                "data": {
                                    "code": 700,
                                    "sign_check": "0-0",
                                    "sign_key": "sign-key",
                                    "pick_code": "pick-code",
                                    "bucket": "bucket-name",
                                    "object": "object-name",
                                    "callback": {
                                        "callback": "callback-body",
                                        "callback_var": "callback-var",
                                    },
                                },
                            }
                        )
                    return FakeResponse(
                        {
                            "state": True,
                            "code": 0,
                            "data": {
                                "status": 1,
                                "file_id": "123",
                                "pick_code": "second-pick-code",
                                "bucket": "second-bucket",
                                "object": "second-object",
                                "callback": {
                                    "callback": "second-callback-body",
                                    "callback_var": "second-callback-var",
                                },
                            },
                        }
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        with TemporaryDirectory() as directory:
            media = Path(directory) / "Film.mkv"
            media.write_bytes(b"media")
            session = SecondAuthSession()
            client = U115Client(tokens={"access_token": "token"}, session=session)

            with patch.object(client, "_upload_to_oss") as upload_to_oss:
                result = client.upload_file({"fileid": "9", "path": "/Cloud"}, media)

        self.assertTrue(result.success)
        init_result = upload_to_oss.call_args.args[-1]
        self.assertEqual(init_result["bucket"], "bucket-name")
        self.assertEqual(init_result["object"], "object-name")
        self.assertEqual(init_result["pick_code"], "pick-code")
        self.assertEqual(init_result["callback"]["callback"], "callback-body")
        self.assertEqual(init_result["callback"]["callback_var"], "callback-var")
        self.assertTrue(
            all(request[2]["timeout"] == 120.0 for request in session.requests)
        )

    @staticmethod
    def _upload_api_response(method, endpoint, **_kwargs):
        if method == "GET" and endpoint == "/open/upload/get_token":
            return {
                "code": 0,
                "data": {
                    "AccessKeyId": "access-key",
                    "AccessKeySecret": "access-secret",
                    "SecurityToken": "security-token",
                    "endpoint": "https://oss.example.invalid",
                },
            }
        if method == "POST" and endpoint == "/open/upload/resume":
            return {
                "code": 0,
                "data": {
                    "callback": {
                        "callback": "callback-body",
                        "callback_var": "callback-var",
                    }
                },
            }
        raise AssertionError(f"unexpected upload request: {method} {endpoint}")

    def test_oss_upload_retries_part_from_original_offset(self):
        class RetryBucket:
            def __init__(self):
                self.part_attempts = 0
                self.chunks = []
                self.completed = []
                self.aborted = []

            @staticmethod
            def init_multipart_upload(_object_name, params=None):
                return SimpleNamespace(upload_id="upload-1")

            def upload_part(self, _object_name, _upload_id, _part_number, data):
                self.part_attempts += 1
                self.chunks.append(data.read())
                if self.part_attempts == 1:
                    raise RuntimeError("temporary part failure")
                return SimpleNamespace(etag=f"etag-{self.part_attempts}")

            def complete_multipart_upload(self, object_name, upload_id, parts, headers=None):
                self.completed.append((object_name, upload_id, list(parts), dict(headers or {})))
                response = SimpleNamespace(
                    json=lambda: {"state": True, "code": 0, "message": "ok"}
                )
                return SimpleNamespace(
                    status=200,
                    resp=SimpleNamespace(response=response),
                )

            def abort_multipart_upload(self, object_name, upload_id):
                self.aborted.append((object_name, upload_id))

        with TemporaryDirectory() as directory:
            media = Path(directory) / "Film.mkv"
            media.write_bytes(b"abcde")
            client = U115Client(tokens={"access_token": "token"}, session=FakeSession())
            client.upload_part_attempts = 2
            client.upload_part_retry_delay = 0
            bucket = RetryBucket()

            with patch.object(client, "_request", side_effect=self._upload_api_response), patch(
                "oss2.StsAuth", return_value=Mock()
            ), patch("oss2.Bucket", return_value=bucket), patch(
                "oss2.determine_part_size", return_value=2
            ):
                client._upload_to_oss(
                    media,
                    media.stat().st_size,
                    hashlib.sha1(media.read_bytes()).hexdigest(),
                    "U_1_9",
                    {
                        "bucket": "bucket-name",
                        "object": "object-name",
                        "pick_code": "pick-code",
                    },
                )

        self.assertEqual(bucket.chunks[:2], [b"ab", b"ab"])
        self.assertEqual(bucket.chunks[2:], [b"cd", b"e"])
        self.assertEqual(len(bucket.completed), 1)
        self.assertEqual(bucket.aborted, [])

    def test_oss_upload_refreshes_expired_sts_credentials(self):
        class ExpiredCredentialError(RuntimeError):
            code = "SecurityTokenExpired"

        class ExpiredBucket:
            def __init__(self):
                self.upload_attempts = 0
                self.aborted = []

            @staticmethod
            def init_multipart_upload(_object_name, params=None):
                return SimpleNamespace(upload_id="upload-1")

            def upload_part(self, _object_name, _upload_id, _part_number, _data):
                self.upload_attempts += 1
                raise ExpiredCredentialError("expired")

            def abort_multipart_upload(self, object_name, upload_id):
                self.aborted.append((object_name, upload_id))

        class HealthyBucket:
            def __init__(self):
                self.uploaded_parts = []
                self.completed = []
                self.aborted = []

            def upload_part(self, object_name, upload_id, part_number, data):
                self.uploaded_parts.append(
                    (object_name, upload_id, part_number, data.read())
                )
                return SimpleNamespace(etag="etag-refreshed")

            def complete_multipart_upload(self, object_name, upload_id, parts, headers=None):
                self.completed.append((object_name, upload_id, list(parts), dict(headers or {})))
                response = SimpleNamespace(
                    json=lambda: {"state": True, "code": 0, "message": "ok"}
                )
                return SimpleNamespace(
                    status=200,
                    resp=SimpleNamespace(response=response),
                )

            def abort_multipart_upload(self, object_name, upload_id):
                self.aborted.append((object_name, upload_id))

        with TemporaryDirectory() as directory:
            media = Path(directory) / "Film.mkv"
            media.write_bytes(b"media")
            client = U115Client(tokens={"access_token": "token"}, session=FakeSession())
            client.upload_part_attempts = 2
            client.upload_part_retry_delay = 0
            expired_bucket = ExpiredBucket()
            healthy_bucket = HealthyBucket()

            with patch.object(client, "_request", side_effect=self._upload_api_response) as request_mock, patch(
                "oss2.StsAuth", return_value=Mock()
            ), patch(
                "oss2.Bucket",
                side_effect=[expired_bucket, healthy_bucket],
            ), patch(
                "oss2.determine_part_size", return_value=5
            ):
                client._upload_to_oss(
                    media,
                    media.stat().st_size,
                    hashlib.sha1(media.read_bytes()).hexdigest(),
                    "U_1_9",
                    {
                        "bucket": "bucket-name",
                        "object": "object-name",
                        "pick_code": "pick-code",
                    },
                )

        token_requests = [
            call for call in request_mock.call_args_list if call.args[:2] == ("GET", "/open/upload/get_token")
        ]
        self.assertEqual(len(token_requests), 2)
        self.assertEqual(expired_bucket.upload_attempts, 1)
        self.assertEqual(
            healthy_bucket.uploaded_parts,
            [("object-name", "upload-1", 1, b"media")],
        )
        self.assertEqual(len(healthy_bucket.completed), 1)
        self.assertEqual(expired_bucket.aborted, [])

    def test_oss_upload_aborts_failed_multipart(self):
        class FailedBucket:
            def __init__(self):
                self.aborted = []

            @staticmethod
            def init_multipart_upload(_object_name, params=None):
                return SimpleNamespace(upload_id="upload-1")

            @staticmethod
            def upload_part(_object_name, _upload_id, _part_number, _data):
                raise RuntimeError("permanent part failure")

            def abort_multipart_upload(self, object_name, upload_id):
                self.aborted.append((object_name, upload_id))

        with TemporaryDirectory() as directory:
            media = Path(directory) / "Film.mkv"
            media.write_bytes(b"media")
            client = U115Client(tokens={"access_token": "token"}, session=FakeSession())
            client.upload_part_attempts = 2
            client.upload_part_retry_delay = 0
            bucket = FailedBucket()

            with patch.object(client, "_request", side_effect=self._upload_api_response), patch(
                "oss2.StsAuth", return_value=Mock()
            ), patch("oss2.Bucket", return_value=bucket), patch(
                "oss2.determine_part_size", return_value=5
            ):
                with self.assertRaisesRegex(U115ApiError, "分片 1 上传失败"):
                    client._upload_to_oss(
                        media,
                        media.stat().st_size,
                        hashlib.sha1(media.read_bytes()).hexdigest(),
                        "U_1_9",
                        {
                            "bucket": "bucket-name",
                            "object": "object-name",
                            "pick_code": "pick-code",
                        },
                    )

        self.assertEqual(bucket.aborted, [("object-name", "upload-1")])

    def test_oss_upload_rejects_failed_callback(self):
        class FailedCallbackBucket:
            def __init__(self):
                self.aborted = []

            @staticmethod
            def init_multipart_upload(_object_name, params=None):
                return SimpleNamespace(upload_id="upload-1")

            @staticmethod
            def upload_part(_object_name, _upload_id, _part_number, _data):
                return SimpleNamespace(etag="etag")

            @staticmethod
            def complete_multipart_upload(_object_name, _upload_id, _parts, headers=None):
                response = SimpleNamespace(
                    json=lambda: {
                        "state": False,
                        "code": 50001,
                        "message": "callback failed",
                    }
                )
                return SimpleNamespace(
                    status=200,
                    resp=SimpleNamespace(response=response),
                )

            def abort_multipart_upload(self, object_name, upload_id):
                self.aborted.append((object_name, upload_id))

        callback_response = {
            "code": 0,
            "data": {
                "callback": {
                    "callback": "callback-body",
                    "callback_var": "callback-var",
                }
            },
        }

        def upload_response(method, endpoint, **kwargs):
            if endpoint == "/open/upload/resume":
                return callback_response
            return self._upload_api_response(method, endpoint, **kwargs)

        with TemporaryDirectory() as directory:
            media = Path(directory) / "Film.mkv"
            media.write_bytes(b"media")
            client = U115Client(tokens={"access_token": "token"}, session=FakeSession())
            bucket = FailedCallbackBucket()

            with patch.object(client, "_request", side_effect=upload_response), patch(
                "oss2.StsAuth", return_value=Mock()
            ), patch("oss2.Bucket", return_value=bucket), patch(
                "oss2.determine_part_size", return_value=5
            ):
                with self.assertRaisesRegex(U115ApiError, "上传回调失败"):
                    client._upload_to_oss(
                        media,
                        media.stat().st_size,
                        hashlib.sha1(media.read_bytes()).hexdigest(),
                        "U_1_9",
                        {
                            "bucket": "bucket-name",
                            "object": "object-name",
                            "pick_code": "pick-code",
                        },
                    )

        self.assertEqual(bucket.aborted, [])

    def test_oss_upload_rejects_missing_callback_before_multipart_init(self):
        class UnexpectedBucket:
            def init_multipart_upload(self, *_args, **_kwargs):
                raise AssertionError("multipart upload must not start without callback")

        with TemporaryDirectory() as directory:
            media = Path(directory) / "Film.mkv"
            media.write_bytes(b"media")
            client = U115Client(tokens={"access_token": "token"}, session=FakeSession())
            bucket = UnexpectedBucket()

            def upload_response(method, endpoint, **kwargs):
                if endpoint == "/open/upload/resume":
                    return {"code": 0, "data": {}}
                return self._upload_api_response(method, endpoint, **kwargs)

            with patch.object(client, "_request", side_effect=upload_response), patch(
                "oss2.StsAuth", return_value=Mock()
            ), patch("oss2.Bucket", return_value=bucket), patch(
                "oss2.determine_part_size", return_value=5
            ):
                with self.assertRaisesRegex(U115ApiError, "缺少有效回调参数"):
                    client._upload_to_oss(
                        media,
                        media.stat().st_size,
                        hashlib.sha1(media.read_bytes()).hexdigest(),
                        "U_1_9",
                        {
                            "bucket": "bucket-name",
                            "object": "object-name",
                            "pick_code": "pick-code",
                        },
                    )

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

    def test_cookie_download_url_uses_rsa_and_player_user_agent(self):
        class CookieDownloadSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/android/2.0/ufile/download"):
                    return FakeResponse({"state": True, "data": "encrypted-response"})
                raise AssertionError(f"unexpected request: {method} {url}")

        session = CookieDownloadSession()
        client = U115Client(cookie="UID=1_R2_0; CID=2", session=session)
        client.download_request_interval = 0
        encrypted_payloads = []

        def encrypt(payload):
            encrypted_payloads.append(json.loads(payload))
            return b"encrypted-request"

        with patch(
            "plugins.p115liteassistant.client.rsa_encrypt",
            side_effect=encrypt,
        ), patch(
            "plugins.p115liteassistant.client.rsa_decrypt",
            return_value=b'{"url":"https://download.example/cookie-file"}',
        ):
            url = client.get_download_url(
                "abcdefghijklmnopq",
                user_agent="Player/1.0",
                mode="cookie",
            )

        self.assertEqual(url, "https://download.example/cookie-file")
        self.assertEqual(
            encrypted_payloads,
            [{"pick_code": "abcdefghijklmnopq"}],
        )
        request = session.requests[0]
        self.assertEqual(request[0], "POST")
        self.assertEqual(request[2]["data"], {"data": "encrypted-request"})
        self.assertEqual(request[2]["headers"]["User-Agent"], "Player/1.0")
        self.assertEqual(request[2]["headers"]["Cookie"], "UID=1_R2_0; CID=2")
        self.assertNotIn("Authorization", request[2]["headers"])

    def test_download_url_parser_supports_direct_and_file_id_mappings(self):
        self.assertEqual(
            U115Client._extract_download_url(
                {"url": "https://download.example/direct"}
            ),
            "https://download.example/direct",
        )
        self.assertEqual(
            U115Client._extract_download_url(
                {"123": {"url": {"url": "https://download.example/nested"}}}
            ),
            "https://download.example/nested",
        )

    def test_cookie_playback_directory_uses_open_api_directory_name(self):
        class CookieDirectorySession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if method == "GET" and url.endswith("/open/ufile/files"):
                    return FakeResponse({"code": 0, "data": []})
                if method == "POST" and url.endswith("/open/folder/add"):
                    return FakeResponse(
                        {
                            "code": 0,
                            "data": {"file_id": "99", "file_name": "多端播放"},
                        }
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        session = CookieDirectorySession()
        client = U115Client(
            cookie="UID=1_R2_0; CID=2",
            tokens={"access_token": "open-token"},
            session=session,
        )
        client.directory_request_interval = 0

        directory_id = client._playback_directory_id()

        self.assertEqual(directory_id, "99")
        create_request = next(item for item in session.requests if item[1].endswith("/open/folder/add"))
        self.assertEqual(create_request[2]["data"], {"pid": 0, "file_name": "多端播放"})
        self.assertEqual(create_request[2]["headers"]["Authorization"], "Bearer open-token")

    def test_existing_directory_response_is_resolved_before_next_path_component(self):
        class ExistingDirectorySession(FakeSession):
            def __init__(self):
                super().__init__()
                self.list_calls = 0

            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if method == "GET" and url.endswith("/open/ufile/files"):
                    self.list_calls += 1
                    if self.list_calls == 1:
                        return FakeResponse({"code": 0, "data": []})
                    return FakeResponse(
                        {"code": 0, "data": [{"cid": "99", "fc": "0", "fn": "多端播放"}]}
                    )
                if method == "POST" and url.endswith("/open/folder/add"):
                    return FakeResponse({"state": False, "code": 20004, "message": "目录已存在"})
                raise AssertionError(f"unexpected request: {method} {url}")

        session = ExistingDirectorySession()
        client = U115Client(tokens={"access_token": "open-token"}, session=session)
        client.directory_request_interval = 0

        directory = client.ensure_remote_dir("/多端播放")

        self.assertEqual(directory["fileid"], "99")
        self.assertEqual(directory["path"], "/多端播放")
        self.assertEqual(
            [request[2]["data"] for request in session.requests if request[0] == "POST"],
            [{"pid": 0, "file_name": "多端播放"}],
        )

    def test_ensure_remote_dir_reuses_confirmed_path_ids(self):
        class CachedDirectorySession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if method == "GET" and url.endswith("/open/ufile/files"):
                    cid = kwargs["params"]["cid"]
                    if cid == 0:
                        return FakeResponse(
                            {"code": 0, "data": [{"cid": "10", "fc": "0", "fn": "Cloud"}]}
                        )
                    if cid == 10:
                        return FakeResponse(
                            {"code": 0, "data": [{"cid": "20", "fc": "0", "fn": "Movies"}]}
                        )
                raise AssertionError(f"unexpected request: {method} {url}")

        session = CachedDirectorySession()
        client = U115Client(tokens={"access_token": "token"}, session=session)
        client.directory_request_interval = 0

        first = client.ensure_remote_dir("/Cloud/Movies")
        second = client.ensure_remote_dir("/Cloud/Movies")
        client.clear_remote_dir_cache()
        after_reset = client.ensure_remote_dir("/Cloud/Movies")

        self.assertEqual(first, second)
        self.assertEqual(first, after_reset)
        self.assertEqual(first["fileid"], "20")
        self.assertEqual(len(session.requests), 4)

    def test_open_download_mode_does_not_send_cookie(self):
        class OpenDownloadSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/ufile/downurl"):
                    return FakeResponse(
                        {
                            "code": 0,
                            "data": {"1": {"url": {"url": "https://download.example/open-file"}}},
                        }
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        session = OpenDownloadSession()
        client = U115Client(
            cookie="UID=1_R2_0; CID=2",
            tokens={"access_token": "open-token"},
            session=session,
        )

        url = client.get_download_url(
            "abcdefghijklmnopq",
            user_agent="Player/1.0",
            mode="open",
        )

        self.assertEqual(url, "https://download.example/open-file")
        self.assertEqual(
            session.requests[0][2]["headers"],
            {"User-Agent": "Player/1.0", "Authorization": "Bearer open-token"},
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
            def __init__(self):
                super().__init__()
                self.list_calls = 0

            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/ufile/copy"):
                    return FakeResponse({"code": 0, "state": True})
                if url.endswith("/open/ufile/files"):
                    self.list_calls += 1
                    file_id = "100" if self.list_calls == 1 else "456"
                    pickcode = "old-pickcode" if self.list_calls == 1 else "copy-pickcode"
                    return FakeResponse(
                        {
                            "code": 0,
                            "data": [
                                {
                                    "cid": "99",
                                    "fid": file_id,
                                    "fc": "1",
                                    "fn": "Film.mkv",
                                    "pc": pickcode,
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

    def test_cookie_playback_copy_uses_open_list_and_cookie_mutations(self):
        class CookiePlaybackSession(FakeSession):
            def __init__(self):
                super().__init__()
                self.list_calls = 0

            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/files/copy"):
                    return FakeResponse({"state": True})
                if url.endswith("/open/ufile/files"):
                    self.list_calls += 1
                    file_id = "100" if self.list_calls == 1 else "456"
                    pickcode = (
                        "old-cookie-pickcode"
                        if self.list_calls == 1
                        else "bcdefghijklmnopqr"
                    )
                    return FakeResponse(
                        {
                            "code": 0,
                            "data": [
                                {
                                    "fid": file_id,
                                    "fc": "1",
                                    "fn": "Film.mkv",
                                    "pc": pickcode,
                                }
                            ],
                        }
                    )
                if url.endswith("/rb/delete"):
                    return FakeResponse({"state": True})
                raise AssertionError(f"unexpected request: {method} {url}")

        session = CookiePlaybackSession()
        client = U115Client(
            cookie="UID=1_R2_0; CID=2",
            tokens={"access_token": "open-token"},
            session=session,
        )
        client._playback_dir_id = "99"

        with patch.object(client, "_pickcode_to_file_id", return_value=123):
            copied = client.create_playback_copy("abcdefghijklmnopq", mode="cookie")
        client.delete_file(copied.file_id, mode=copied.auth_mode)

        self.assertEqual(copied, PlaybackCopy("456", "bcdefghijklmnopqr", "cookie"))
        copy_request = next(item for item in session.requests if item[1].endswith("/files/copy"))
        self.assertEqual(copy_request[2]["data"], {"fid": 123, "pid": 99})
        self.assertEqual(copy_request[2]["headers"]["Cookie"], "UID=1_R2_0; CID=2")
        list_request = next(item for item in session.requests if item[1].endswith("/open/ufile/files"))
        self.assertEqual(list_request[2]["params"]["asc"], 0)
        self.assertEqual(list_request[2]["headers"]["Authorization"], "Bearer open-token")
        delete_request = next(item for item in session.requests if item[1].endswith("/rb/delete"))
        self.assertEqual(delete_request[2]["data"], {"fid": 456})

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
            ["files", "copy", "files", "files", "copy", "files"],
        )

    def test_playback_copy_waits_until_new_copy_is_visible(self):
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
                    if self.list_calls <= 2:
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
        client.playback_copy_discovery_delays = (0.0, 0.0)

        with patch.object(client, "_pickcode_to_file_id", return_value=123):
            copied = client.create_playback_copy("original-pickcode")

        self.assertEqual(copied, PlaybackCopy("456", "copy-pickcode", "open"))
        self.assertEqual(session.list_calls, 3)
        self.assertFalse(any(item[1].endswith("/open/ufile/delete") for item in session.requests))

    def test_playback_copy_never_deletes_preexisting_item_when_new_copy_is_missing(self):
        class MissingCopySession(FakeSession):
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
                                    "fid": "100",
                                    "fc": "1",
                                    "fn": "Existing.mkv",
                                    "pc": "existing-pickcode",
                                }
                            ],
                        }
                    )
                if url.endswith("/open/ufile/delete"):
                    raise AssertionError("preexisting item must not be deleted")
                raise AssertionError(f"unexpected request: {method} {url}")

        session = MissingCopySession()
        client = U115Client(tokens={"access_token": "token"}, session=session)
        client._playback_dir_id = "99"
        client.playback_copy_discovery_delays = (0.0, 0.0)

        with patch.object(client, "_pickcode_to_file_id", return_value=123), self.assertRaisesRegex(
            RuntimeError,
            "未发现新副本",
        ):
            client.create_playback_copy("original-pickcode")

        self.assertFalse(any(item[1].endswith("/open/ufile/delete") for item in session.requests))

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

    def test_refresh_access_limit_payload_does_not_fall_back_to_cookie_auth(self):
        class LimitedRefreshSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/refreshToken"):
                    return FakeResponse(
                        {
                            "state": False,
                            "code": 911,
                            "message": "已达到当前访问上限，请稍后再试",
                        }
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        session = LimitedRefreshSession()
        client = U115Client(
            cookie="UID=1; CID=2",
            tokens={
                "access_token": "expired-token",
                "refresh_token": "refresh-token",
                "expires_in": 1,
                "refresh_time": 1,
            },
            session=session,
        )

        with self.assertRaises(U115AccessLimitError):
            client.ensure_upload_ready()

        self.assertEqual(len(session.requests), 1)
        self.assertTrue(session.requests[0][1].endswith("/open/refreshToken"))

    def test_refresh_http_429_does_not_fall_back_to_cookie_auth(self):
        class LimitedRefreshSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/refreshToken"):
                    request = httpx.Request(method, url)
                    return httpx.Response(429, request=request)
                raise AssertionError(f"unexpected request: {method} {url}")

        session = LimitedRefreshSession()
        client = U115Client(
            cookie="UID=1; CID=2",
            tokens={
                "access_token": "expired-token",
                "refresh_token": "refresh-token",
                "expires_in": 1,
                "refresh_time": 1,
            },
            session=session,
        )
        client.http_rate_limit_attempts = 1

        with self.assertRaises(U115AccessLimitError):
            client.ensure_upload_ready()

        self.assertEqual(len(session.requests), 1)
        self.assertTrue(session.requests[0][1].endswith("/open/refreshToken"))

    def test_cookie_open_authorization_propagates_access_limit_payload(self):
        class LimitedAuthorizationSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/authDeviceCode"):
                    return FakeResponse(
                        {
                            "state": False,
                            "code": 911,
                            "message": "已达到当前访问上限，请稍后再试",
                        }
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        session = LimitedAuthorizationSession()
        client = U115Client(
            cookie="UID=1; CID=2",
            tokens={"access_token": "expired-token", "expires_in": 1, "refresh_time": 1},
            session=session,
        )

        with self.assertRaises(U115AccessLimitError):
            client.ensure_upload_ready()

        self.assertEqual(len(session.requests), 1)
        self.assertTrue(session.requests[0][1].endswith("/open/authDeviceCode"))

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

    def test_directory_invalid_token_falls_back_to_cookie_open_authorization(self):
        class CookieFallbackSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/ufile/files"):
                    if kwargs.get("headers", {}).get("Authorization") == "Bearer cookie-token":
                        return FakeResponse(
                            {"code": 0, "data": [{"fid": "1", "fn": "Film.mkv"}]}
                        )
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
            items = client.get_dir_list("12")

        self.assertEqual(items, [{"fid": "1", "fn": "Film.mkv"}])
        self.assertEqual(client.tokens["access_token"], "cookie-token")
        self.assertEqual(
            session.requests[-1][2]["headers"]["Authorization"],
            "Bearer cookie-token",
        )
        self.assertEqual(session.requests[-1][2]["params"]["cid"], 12)
        self.assertNotIn("Authorization", session.headers)

    def test_recovered_open_auth_failure_is_exposed_as_auth_error_once(self):
        class RejectedTokenSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/user/info"):
                    return FakeResponse(
                        {
                            "state": False,
                            "code": 40140125,
                            "message": "access_token 已失效",
                        }
                    )
                if url.endswith("/open/refreshToken"):
                    return FakeResponse(
                        {
                            "code": 0,
                            "data": {
                                "access_token": "recovered-token",
                                "refresh_token": "recovered-refresh",
                                "expires_in": 7200,
                            },
                        }
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        session = RejectedTokenSession()
        client = U115Client(
            tokens={
                "access_token": "invalid-token",
                "refresh_token": "refresh-token",
            },
            session=session,
        )
        operation = Mock(side_effect=client.ensure_upload_ready)

        with self.assertRaises(U115AuthError):
            retry_call(
                operation,
                attempts=3,
                delay=0,
                abort_on=(U115AccessLimitError, U115AuthError),
            )

        self.assertEqual(operation.call_count, 1)
        token_requests = [
            request for request in session.requests if request[1].endswith("/open/user/info")
        ]
        self.assertEqual(len(token_requests), 2)

    def test_open_business_error_mentioning_token_does_not_replay_post(self):
        class BusinessErrorSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/upload/init"):
                    return FakeResponse(
                        {"state": False, "code": 50001, "message": "upload token generation failed"}
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        session = BusinessErrorSession()
        client = U115Client(
            tokens={"access_token": "open-token", "refresh_token": "refresh-token"},
            session=session,
        )

        with self.assertRaisesRegex(U115ApiError, "upload token generation failed"):
            client._request("POST", "/open/upload/init", data={"file_name": "Film.mkv"})

        self.assertEqual(len(session.requests), 1)
        self.assertTrue(session.requests[0][1].endswith("/open/upload/init"))

    def test_get_business_error_is_not_retried(self):
        class BusinessErrorSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                return FakeResponse(
                    {"state": False, "code": 50001, "message": "business failure"}
                )

        session = BusinessErrorSession()
        client = U115Client(cookie="UID=1_R2_0; CID=2", session=session)

        with self.assertRaisesRegex(U115ApiError, "business failure"):
            client._request_url("GET", "https://example.invalid/business")

        self.assertEqual(len(session.requests), 1)

    def test_http_429_retries_get_with_reset_header_and_bound(self):
        class RateLimitSession(FakeSession):
            def __init__(self):
                super().__init__()
                self.attempts = 0

            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                self.attempts += 1
                request = httpx.Request(method, url)
                return httpx.Response(
                    429,
                    headers={"X-RateLimit-Reset": "2"},
                    request=request,
                )

        session = RateLimitSession()
        client = U115Client(session=session)
        client.read_retry_attempts = 3

        with patch("plugins.p115liteassistant.client.time.sleep") as sleeper:
            with self.assertRaises(U115AccessLimitError):
                client._request_url(
                    "GET",
                    "https://example.invalid/rate-limit",
                    require_auth=False,
                )

        self.assertEqual(session.attempts, 3)
        self.assertEqual([call.args[0] for call in sleeper.call_args_list], [7.0, 7.0])

    def test_http_429_retries_post_with_reset_header_and_bound(self):
        class RateLimitSession(FakeSession):
            def __init__(self):
                super().__init__()
                self.attempts = 0

            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                self.attempts += 1
                if self.attempts < 3:
                    return httpx.Response(
                        429,
                        headers={"X-RateLimit-Reset": "2"},
                        request=httpx.Request(method, url),
                    )
                return FakeResponse({"state": True, "code": 0, "data": {"ok": True}})

        session = RateLimitSession()
        client = U115Client(session=session)
        client.http_rate_limit_attempts = 3

        with patch("plugins.p115liteassistant.client.time.sleep") as sleeper:
            payload = client._request_url(
                "POST",
                "https://example.invalid/rate-limit",
                require_auth=False,
            )

        self.assertTrue(payload["state"])
        self.assertEqual(session.attempts, 3)
        self.assertEqual([call.args[0] for call in sleeper.call_args_list], [7.0, 7.0])

    def test_http_503_retries_get_with_exponential_delay(self):
        class TemporaryFailureSession(FakeSession):
            def __init__(self):
                super().__init__()
                self.attempts = 0

            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                self.attempts += 1
                if self.attempts < 3:
                    return httpx.Response(503, request=httpx.Request(method, url))
                return FakeResponse({"state": True, "data": {"ok": True}})

        session = TemporaryFailureSession()
        client = U115Client(session=session)

        with patch("plugins.p115liteassistant.client.time.sleep") as sleeper:
            payload = client._request_url(
                "GET",
                "https://example.invalid/temporary",
                require_auth=False,
            )

        self.assertTrue(payload["state"])
        self.assertEqual(session.attempts, 3)
        self.assertEqual([call.args[0] for call in sleeper.call_args_list], [1.0, 2.0])

    def test_open_access_limit_retries_using_upstream_delay(self):
        class AccessLimitSession(FakeSession):
            def __init__(self):
                super().__init__()
                self.attempts = 0

            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/ufile/files"):
                    self.attempts += 1
                    if self.attempts < 3:
                        return FakeResponse(
                            {
                                "state": False,
                                "code": 911,
                                "message": "已达到当前访问上限，请稍后再试",
                            }
                        )
                    return FakeResponse({"state": True, "data": [], "count": 0})
                raise AssertionError(f"unexpected request: {method} {url}")

        session = AccessLimitSession()
        client = U115Client(tokens={"access_token": "token"}, session=session)
        with patch("plugins.p115liteassistant.client.time.sleep") as sleeper:
            self.assertEqual(client.get_dir_list("0"), [])

        self.assertEqual(session.attempts, 3)
        self.assertEqual([call.args[0] for call in sleeper.call_args_list], [70.0, 70.0])

    def test_open_access_limit_raises_after_bounded_retries(self):
        class AccessLimitSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/open/ufile/files"):
                    return FakeResponse(
                        {
                            "state": False,
                            "code": 911,
                            "message": "已达到当前访问上限，请稍后再试",
                        }
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        session = AccessLimitSession()
        client = U115Client(tokens={"access_token": "token"}, session=session)
        client.open_access_limit_attempts = 3
        with patch("plugins.p115liteassistant.client.time.sleep") as sleeper:
            with self.assertRaisesRegex(U115AccessLimitError, "尝试 3 次"):
                client.get_dir_list("0")

        self.assertEqual(len(session.requests), 3)
        self.assertEqual(sleeper.call_count, 2)

    def test_open_http_429_is_marked_as_access_limit(self):
        class RateLimitSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                return httpx.Response(429, request=httpx.Request(method, url))

        session = RateLimitSession()
        client = U115Client(tokens={"access_token": "token"}, session=session)
        client.read_retry_attempts = 1
        client.http_rate_limit_attempts = 1

        with self.assertRaises(U115AccessLimitError):
            client.get_dir_list("0")

        self.assertEqual(len(session.requests), 1)

    def test_cookie_access_limit_payload_is_marked_as_access_limit(self):
        class CookieLimitSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                return FakeResponse(
                    {
                        "state": False,
                        "code": 911,
                        "message": "已达到当前访问上限，请稍后再试",
                    }
                )

        client = U115Client(cookie="UID=1_R2_0; CID=2", session=CookieLimitSession())

        with self.assertRaises(U115AccessLimitError):
            client._request_url("POST", "https://example.invalid/cookie-limit")

    def test_cookie_access_limit_payload_is_marked_with_no_error(self):
        class CookieLimitSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                return FakeResponse(
                    {
                        "state": False,
                        "code": 911,
                        "message": "已达到当前访问上限，请稍后再试",
                    }
                )

        client = U115Client(cookie="UID=1_R2_0; CID=2", session=CookieLimitSession())

        with self.assertRaises(U115AccessLimitError):
            client._request_url(
                "POST",
                "https://example.invalid/cookie-limit",
                no_error=True,
            )

    def test_checkin_adds_status_stage_to_upstream_error(self):
        class FailedStatusSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/user/points_sign"):
                    return FakeResponse(
                        {"state": False, "message": "服务器开小差了，稍后再试吧"}
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        client = U115Client(
            cookie="UID=1_R2_0; CID=2",
            session=FailedStatusSession(),
        )
        with patch("plugins.p115liteassistant.client.time.sleep"):
            with self.assertRaisesRegex(U115ApiError, "查询 115 签到状态失败.*服务器开小差"):
                client.checkin()

        self.assertEqual(len(client.session.requests), 1)

    def test_checkin_propagates_access_limit_during_status_check(self):
        class LimitedStatusSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if url.endswith("/user/points_sign"):
                    return FakeResponse(
                        {
                            "state": False,
                            "code": 911,
                            "message": "已达到当前访问上限，请稍后再试",
                        }
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        session = LimitedStatusSession()
        client = U115Client(cookie="UID=1_R2_0; CID=2", session=session)

        with self.assertRaises(U115AccessLimitError):
            client.checkin()

        self.assertEqual(len(session.requests), 1)

    def test_checkin_rejects_invalid_success_data_after_bounded_retries(self):
        class InvalidCheckinSession(FakeSession):
            def __init__(self):
                super().__init__()
                self.post_attempts = 0

            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if method == "GET" and url.endswith("/user/points_sign"):
                    return FakeResponse({"state": True, "data": {"is_sign_today": 0}})
                if method == "POST" and url.endswith("/user/points_sign"):
                    self.post_attempts += 1
                    return FakeResponse({"state": True, "data": []})
                raise AssertionError(f"unexpected request: {method} {url}")

        session = InvalidCheckinSession()
        client = U115Client(cookie="UID=1_R2_0; CID=2", session=session)

        with self.assertRaisesRegex(U115ApiError, "签到返回数据无效"):
            client.checkin(retry_delay=0)

        self.assertEqual(session.post_attempts, 3)

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

    def test_checkin_propagates_access_limit_during_post(self):
        class LimitedPostSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.requests.append((method, url, kwargs))
                if method == "GET" and url.endswith("/user/points_sign"):
                    return FakeResponse({"state": True, "data": {"is_sign_today": 0}})
                if method == "POST" and url.endswith("/user/points_sign"):
                    return FakeResponse(
                        {
                            "state": False,
                            "code": 911,
                            "message": "已达到当前访问上限，请稍后再试",
                        }
                    )
                raise AssertionError(f"unexpected request: {method} {url}")

        session = LimitedPostSession()
        client = U115Client(cookie="UID=1_R2_0; CID=2", session=session)

        with self.assertRaises(U115AccessLimitError):
            client.checkin(retry_delay=0)

        self.assertEqual(
            len([request for request in session.requests if request[0] == "POST"]),
            1,
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
