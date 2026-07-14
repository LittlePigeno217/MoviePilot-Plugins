import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# app.log 在测试环境不可用时打桩
app_mod = types.ModuleType("app")
log_mod = types.ModuleType("app.log")
log_mod.logger = MagicMock()
app_mod.log = log_mod
sys.modules.setdefault("app", app_mod)
sys.modules.setdefault("app.log", log_mod)

from redirect import RedirectResolver  # noqa: E402


def test_resolve_returns_url():
    client = MagicMock()
    client.get_download_url.return_value = "https://dl/x"
    assert RedirectResolver(client).resolve("pc") == "https://dl/x"


def test_resolve_empty_pickcode():
    assert RedirectResolver(MagicMock()).resolve("") is None


def test_resolve_swallows_error():
    client = MagicMock()
    client.get_download_url.side_effect = RuntimeError("boom")
    assert RedirectResolver(client).resolve("pc") is None
