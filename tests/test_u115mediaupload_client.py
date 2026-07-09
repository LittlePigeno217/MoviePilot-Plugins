from pathlib import Path

import pytest

from plugins.u115mediaupload.client import U115AuthError, U115Client


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        if url.endswith("/open/upload/init"):
            return FakeResponse(
                {
                    "code": 0,
                    "state": True,
                    "data": {
                        "status": 2,
                        "file_id": "123",
                    },
                }
            )
        if url.endswith("/open/folder/get_info"):
            return FakeResponse(
                {
                    "code": 0,
                    "state": True,
                    "data": {
                        "file_id": "123",
                        "file_category": "1",
                        "file_name": "Film.mkv",
                        "pick_code": "pick",
                        "size_byte": 5,
                        "utime": 1,
                    },
                }
            )
        raise AssertionError(f"unexpected request {method} {url}")


def test_client_requires_authentication(tmp_path):
    client = U115Client(session=FakeSession())

    with pytest.raises(U115AuthError):
        client.upload_file({"fileid": "0", "path": "/"}, tmp_path / "missing.mkv")


def test_client_returns_reuse_result_for_instant_upload(tmp_path):
    media = tmp_path / "Film.mkv"
    media.write_bytes(b"media")
    session = FakeSession()
    client = U115Client(cookie="UID=1; CID=2", session=session)

    result = client.upload_file({"fileid": "0", "path": "/Cloud"}, Path(media))

    assert result.success is True
    assert result.reused is True
    assert result.file_item["fileid"] == "123"
    init_request = session.requests[0]
    assert init_request[0] == "POST"
    assert init_request[1].endswith("/open/upload/init")
    assert init_request[2]["data"]["file_name"] == "Film.mkv"
    assert init_request[2]["data"]["target"] == "U_1_0"
