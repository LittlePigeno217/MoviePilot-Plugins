"""插件类冒烟测试：在打桩的 MoviePilot 依赖下导入真实包并校验结构。"""
import sys
from pathlib import Path

# 把 plugins/ 目录加入 path，以便 import u115strm 包（触发真实 __init__）
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import u115strm  # noqa: E402
from u115strm import U115Strm  # noqa: E402


def _new():
    return U115Strm()


def test_class_metadata():
    assert U115Strm.plugin_version == "1.0.0"
    assert U115Strm.auth_level == 1
    assert U115Strm.plugin_config_prefix == "u115strm_"


def test_get_render_mode_is_vue():
    assert _new().get_render_mode() == ("vue", "dist/assets")


def test_get_api_has_all_routes():
    plugin = _new()
    apis = plugin.get_api()
    paths = {(a["path"], a["methods"][0]) for a in apis}
    assert ("/qrcode", "POST") in paths
    assert ("/browse_115", "GET") in paths
    assert ("/browse_local", "GET") in paths
    assert ("/config", "GET") in paths
    assert ("/config", "POST") in paths
    assert ("/sync", "POST") in paths
    assert ("/history", "GET") in paths
    assert ("/redirect", "GET") in paths
    # /redirect 用 apikey，其余用 bear
    redirect = next(a for a in apis if a["path"] == "/redirect")
    assert redirect["auth"] == "apikey"
    assert all(a["auth"] == "bear" for a in apis if a["path"] != "/redirect")


def test_get_state_false_without_mappings():
    assert _new().get_state() is False


def test_get_service_empty_without_cron():
    assert _new().get_service() == []


def test_endpoints_are_callable():
    plugin = _new()
    for a in plugin.get_api():
        assert callable(a["endpoint"])
