"""pytest 夹具：为单测打桩 MoviePilot 运行时依赖（apscheduler / app.*），
放在 tests/（非包目录），加载时不会触发插件包的 __init__。"""
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

# 让测试可直接 import 插件内模块（models/store/strm/...）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _stub(name, **attrs):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    for key, val in attrs.items():
        setattr(mod, key, val)
    return mod


# apscheduler.triggers.cron.CronTrigger
_stub("apscheduler")
_stub("apscheduler.triggers")
_cron = _stub("apscheduler.triggers.cron")


class _CronTrigger:
    @staticmethod
    def from_crontab(expr):
        return ("cron", expr)


_cron.CronTrigger = _CronTrigger

# app.*
_stub("app")
_stub("app.log", logger=MagicMock())
_stub("app.core")
_stub(
    "app.core.config",
    settings=types.SimpleNamespace(
        LIBRARY_PATH="/tmp", API_TOKEN="TOK", U115_APP_ID="", U115_AUTH_SERVER=""
    ),
)


class _PluginBase:  # 最小桩
    def __init__(self):
        pass

    def save_data(self, *a, **k):
        pass

    def get_data(self, *a, **k):
        return None


_stub("app.plugins", _PluginBase=_PluginBase)


class _Scheduler:
    def remove_plugin_job(self, *a, **k):
        pass


_stub("app.scheduler", Scheduler=_Scheduler)
