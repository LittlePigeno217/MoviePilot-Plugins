import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from client import U115Client  # noqa: E402


def _client_with_response(payload):
    client = U115Client(cookie="ck")
    fake_resp = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: payload,
    )
    client.session = MagicMock()
    client.session.request.return_value = fake_resp
    return client


def test_get_download_url_extracts_nested_url():
    client = _client_with_response({"code": 0, "data": {"123": {"url": {"url": "https://dl.115/xyz"}}}})
    assert client.get_download_url("pc123") == "https://dl.115/xyz"


def test_get_download_url_extracts_flat_url():
    client = _client_with_response({"code": 0, "data": {"123": {"url": "https://dl.115/flat"}}})
    assert client.get_download_url("pc123") == "https://dl.115/flat"


def test_get_download_url_empty_pickcode():
    client = U115Client(cookie="ck")
    assert client.get_download_url("") is None


def test_iter_files_recurses_dirs():
    client = U115Client(cookie="ck")
    responses = {
        "0": [{"cid": "10", "fn": "movies"}],
        "10": [{"fid": "99", "fn": "a.mkv", "pc": "pcA", "s": 100}],
    }
    client.get_dir_list = lambda cid="0": responses.get(str(cid), [])
    files = list(client.iter_files("0", recursive=True))
    assert len(files) == 1
    assert files[0]["name"] == "a.mkv"
    assert files[0]["pickcode"] == "pcA"
    assert files[0]["rel_path"] == "movies/a.mkv"
    assert files[0]["size"] == 100


def test_iter_files_non_recursive_skips_subdirs():
    client = U115Client(cookie="ck")
    responses = {
        "0": [{"cid": "10", "fn": "movies"}, {"fid": "5", "fn": "top.mp4", "pc": "pcT", "s": 1}],
        "10": [{"fid": "99", "fn": "a.mkv", "pc": "pcA", "s": 100}],
    }
    client.get_dir_list = lambda cid="0": responses.get(str(cid), [])
    files = list(client.iter_files("0", recursive=False))
    assert len(files) == 1
    assert files[0]["name"] == "top.mp4"
