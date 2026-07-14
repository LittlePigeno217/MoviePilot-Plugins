import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 打桩 app.log / app.core.config
app = types.ModuleType("app")
log = types.ModuleType("app.log")
log.logger = MagicMock()
core = types.ModuleType("app.core")
conf = types.ModuleType("app.core.config")
conf.settings = types.SimpleNamespace(LIBRARY_PATH="/tmp")
app.log = log
app.core = core
core.config = conf
for _n, _m in [("app", app), ("app.log", log), ("app.core", core), ("app.core.config", conf)]:
    sys.modules.setdefault(_n, _m)

from store import Store  # noqa: E402
from api import Api  # noqa: E402


class FakeHost:
    def __init__(self):
        self._d = {}

    def save_data(self, k, v):
        self._d[k] = v

    def get_data(self, k=None):
        return self._d.get(k)


def _api(client):
    return Api(lambda: client, Store(FakeHost()), lambda: "TOK")


def test_redirect_bad_apikey():
    resp = _api(MagicMock()).redirect("pc", "WRONG")
    assert resp.status_code == 403


def test_redirect_success():
    client = MagicMock()
    client.get_download_url.return_value = "https://dl/x"
    resp = _api(client).redirect("pc", "TOK")
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://dl/x"


def test_redirect_resolve_fail_404():
    client = MagicMock()
    client.get_download_url.return_value = None
    resp = _api(client).redirect("pc", "TOK")
    assert resp.status_code == 404


def test_save_and_get_config_hides_tokens():
    api = _api(MagicMock())
    api.save_config({"moviepilot_url": "http://mp:3001", "incremental": False})
    got = api.get_config()
    assert got["data"]["moviepilot_url"] == "http://mp:3001"
    assert got["data"]["incremental"] is False
    assert "tokens" not in got["data"]


def test_browse_115_filters_dirs():
    client = MagicMock()
    client.get_dir_list.return_value = [{"cid": "10", "fn": "movies"}, {"fid": "5", "fn": "a.mkv"}]
    resp = _api(client).browse_115("0")
    assert resp["success"] and len(resp["data"]["items"]) == 1
    assert resp["data"]["items"][0]["name"] == "movies"
    assert resp["data"]["items"][0]["cid"] == "10"


def test_run_sync_skips_disabled_mappings():
    client = MagicMock()
    client.iter_files.return_value = iter([])
    api = _api(client)
    api.save_config({
        "moviepilot_url": "http://mp:3001",
        "mappings": [
            {"id": "m1", "enabled": False, "source_cid": "1", "source_path": "/a", "target_dir": "/t1"},
            {"id": "m2", "enabled": True, "source_cid": "2", "source_path": "/b", "target_dir": "/t2"},
        ],
    })
    entries = api.run_sync()
    assert len(entries) == 1
    assert entries[0].mapping_id == "m2"
