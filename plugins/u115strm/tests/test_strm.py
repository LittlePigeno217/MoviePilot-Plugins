import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models import Mapping  # noqa: E402
from store import Store  # noqa: E402
from strm import StrmGenerator, build_strm_url, MEDIA_EXTS  # noqa: E402


class FakeHost:
    def __init__(self):
        self._d = {}

    def save_data(self, k, v):
        self._d[k] = v

    def get_data(self, k=None):
        return self._d.get(k)


class FakeClient:
    def __init__(self, files):
        self._files = files

    def iter_files(self, cid, recursive=True):
        return iter(self._files)


def test_build_strm_url():
    url = build_strm_url("http://mp:3001/", "pc1", "tok")
    assert url == "http://mp:3001/api/v1/plugin/U115Strm/redirect?pickcode=pc1&apikey=tok"


def test_build_strm_url_quotes_special():
    url = build_strm_url("http://mp:3001", "p c/1", "a b")
    assert "pickcode=p%20c/1" in url or "pickcode=p%20c%2F1" in url
    assert "apikey=a%20b" in url


def test_generate_and_incremental_skip(tmp_path):
    files = [
        {"name": "a.mkv", "pickcode": "pcA", "size": 100, "rel_path": "movies/a.mkv"},
        {"name": "note.txt", "pickcode": "pcB", "size": 5, "rel_path": "movies/note.txt"},
    ]
    store = Store(FakeHost())
    gen = StrmGenerator(FakeClient(files), store, "http://mp:3001", "tok", incremental=True)
    m = Mapping("m1", True, "10", "/movies", str(tmp_path))
    h1 = gen.run_mapping(m)
    assert h1.added == 1 and h1.skipped == 0          # 只有 a.mkv 是媒体
    strm = tmp_path / "movies" / "a.strm"
    assert strm.exists()
    assert "pickcode=pcA" in strm.read_text(encoding="utf-8")
    h2 = gen.run_mapping(m)                            # 二次跑，增量跳过
    assert h2.added == 0 and h2.skipped == 1


def test_changed_size_triggers_update(tmp_path):
    store = Store(FakeHost())
    m = Mapping("m1", True, "10", "/movies", str(tmp_path))
    gen1 = StrmGenerator(
        FakeClient([{"name": "a.mkv", "pickcode": "pcA", "size": 100, "rel_path": "a.mkv"}]),
        store, "http://mp:3001", "tok", incremental=True,
    )
    gen1.run_mapping(m)
    gen2 = StrmGenerator(
        FakeClient([{"name": "a.mkv", "pickcode": "pcA", "size": 200, "rel_path": "a.mkv"}]),
        store, "http://mp:3001", "tok", incremental=True,
    )
    h = gen2.run_mapping(m)
    assert h.updated == 1 and h.skipped == 0


def test_metadata_mirror_invoked_for_sidecar(tmp_path):
    mirrored = []

    class FakeMeta:
        def mirror(self, item, target_dir):
            mirrored.append((item["name"], target_dir))
            return True

    files = [
        {"name": "a.mkv", "pickcode": "pcA", "size": 1, "rel_path": "a.mkv"},
        {"name": "a.nfo", "pickcode": "pcN", "size": 2, "rel_path": "a.nfo"},
    ]
    gen = StrmGenerator(
        FakeClient(files), Store(FakeHost()), "http://mp:3001", "tok",
        incremental=True, metadata_sync=FakeMeta(),
    )
    gen.run_mapping(Mapping("m1", True, "10", "/", str(tmp_path)))
    assert mirrored == [("a.nfo", str(tmp_path))]


def test_media_exts_covers_common():
    assert ".mkv" in MEDIA_EXTS and ".mp4" in MEDIA_EXTS
