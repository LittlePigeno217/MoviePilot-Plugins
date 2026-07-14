import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models import SyncRecord, HistoryEntry  # noqa: E402
from store import Store  # noqa: E402


class FakeHost:
    def __init__(self):
        self._data = {}

    def save_data(self, key, value):
        self._data[key] = value

    def get_data(self, key=None):
        return self._data.get(key)


def test_config_merges_defaults():
    store = Store(FakeHost())
    cfg = store.get_config()
    assert cfg["incremental"] is True
    assert cfg["mappings"] == []
    store.save_config({**cfg, "moviepilot_url": "http://x:3001"})
    assert store.get_config()["moviepilot_url"] == "http://x:3001"


def test_sync_record_roundtrip():
    store = Store(FakeHost())
    store.set_sync_record(SyncRecord("k1", "pc1", "sha1", "/out/a.strm"))
    state = store.get_sync_state()
    assert state["k1"]["pickcode"] == "pc1"


def test_bulk_set_sync_records():
    store = Store(FakeHost())
    store.bulk_set_sync_records([
        SyncRecord("k1", "pc1", "s1", "/a.strm"),
        SyncRecord("k2", "pc2", "s2", "/b.strm"),
    ])
    assert set(store.get_sync_state().keys()) == {"k1", "k2"}


def test_history_keeps_latest_n():
    store = Store(FakeHost())
    for i in range(5):
        store.append_history(HistoryEntry(f"t{i}", "m", 1, 0, 0, 0, 10), keep=3)
    hist = store.get_history()
    assert len(hist) == 3
    assert hist[0]["time"] == "t4"  # 最新在前
