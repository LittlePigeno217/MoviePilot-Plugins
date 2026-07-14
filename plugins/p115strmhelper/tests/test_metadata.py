import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from metadata import MetadataSync, _is_sidecar  # noqa: E402


def test_is_sidecar():
    assert _is_sidecar("movie.nfo") and _is_sidecar("poster.jpg") and _is_sidecar("s.srt")
    assert not _is_sidecar("a.mkv")


def test_download_file(tmp_path):
    client = MagicMock()
    client.get_download_url.return_value = "https://dl/x"
    client.session.get.return_value = MagicMock(content=b"data", raise_for_status=lambda: None)
    ms = MetadataSync(client)
    dest = tmp_path / "movie.nfo"
    assert ms.download_file("pc", dest) is True
    assert dest.read_bytes() == b"data"


def test_download_file_no_url_returns_false(tmp_path):
    client = MagicMock()
    client.get_download_url.return_value = None
    ms = MetadataSync(client)
    assert ms.download_file("pc", tmp_path / "x.nfo") is False


def test_sync_for_filters_and_skips_existing(tmp_path):
    client = MagicMock()
    client.get_download_url.return_value = "https://dl/x"
    client.session.get.return_value = MagicMock(content=b"x", raise_for_status=lambda: None)
    ms = MetadataSync(client)
    strm = tmp_path / "a.strm"
    strm.write_text("u")
    siblings = [
        {"name": "a.nfo", "pickcode": "p1"},
        {"name": "b.mkv", "pickcode": "p2"},   # 非 sidecar，跳过
        {"name": "poster.jpg", "pickcode": "p3"},
    ]
    assert ms.sync_for({}, strm, siblings) == 2


def test_sync_for_skips_already_downloaded(tmp_path):
    client = MagicMock()
    client.get_download_url.return_value = "https://dl/x"
    client.session.get.return_value = MagicMock(content=b"x", raise_for_status=lambda: None)
    ms = MetadataSync(client)
    strm = tmp_path / "a.strm"
    strm.write_text("u")
    (tmp_path / "a.nfo").write_text("existing")  # 已存在
    assert ms.sync_for({}, strm, [{"name": "a.nfo", "pickcode": "p1"}]) == 0
