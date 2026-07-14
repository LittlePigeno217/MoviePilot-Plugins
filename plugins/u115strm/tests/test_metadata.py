import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from metadata import MetadataSync, is_sidecar  # noqa: E402


def test_is_sidecar():
    assert is_sidecar("movie.nfo") and is_sidecar("poster.jpg") and is_sidecar("s.srt")
    assert not is_sidecar("a.mkv")


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


def test_mirror_downloads_sidecar_by_rel_path(tmp_path):
    client = MagicMock()
    client.get_download_url.return_value = "https://dl/x"
    client.session.get.return_value = MagicMock(content=b"x", raise_for_status=lambda: None)
    ms = MetadataSync(client)
    item = {"name": "a.nfo", "pickcode": "p1", "rel_path": "movies/a.nfo"}
    assert ms.mirror(item, str(tmp_path)) is True
    assert (tmp_path / "movies" / "a.nfo").read_bytes() == b"x"


def test_mirror_skips_non_sidecar(tmp_path):
    ms = MetadataSync(MagicMock())
    assert ms.mirror({"name": "a.mkv", "pickcode": "p", "rel_path": "a.mkv"}, str(tmp_path)) is False


def test_mirror_skips_existing(tmp_path):
    client = MagicMock()
    client.get_download_url.return_value = "https://dl/x"
    client.session.get.return_value = MagicMock(content=b"x", raise_for_status=lambda: None)
    ms = MetadataSync(client)
    (tmp_path / "a.nfo").write_text("existing")
    item = {"name": "a.nfo", "pickcode": "p1", "rel_path": "a.nfo"}
    assert ms.mirror(item, str(tmp_path)) is False
