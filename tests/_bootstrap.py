"""单测引导薄壳：定位 MoviePilot 后端并把本仓 ``plugins/`` 暴露为 ``app.plugins``。

与官方插件仓一致，测试必须通过生产命名空间 ``app.plugins.<plugin_id>`` 导入插件，
不要把插件目录直接加入 ``sys.path`` 后使用顶层包名——后者会让同一份源码产生两个
模块身份，导致事件订阅、类状态与插件实例重复创建。

后端定位顺序：

1. 环境变量 ``MOVIEPILOT_BACKEND_PATH``
2. 工作区同级布局 ``<workspace>/MoviePilot``

后端存在且带 ``app/testing`` 时，引导逻辑委托主程序共享实现（``prepare_v1_backend`` 即
「后端 + 本仓 ``plugins/``」）；后端较旧则退回本地命名空间注册。后端缺失时不抛异常，
只记录原因，让自带宿主桩的用例仍可独立运行。
"""

from __future__ import annotations

import os
import sys
from importlib import import_module
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType

_TESTS_DIR = Path(__file__).resolve().parent
_PLUGINS_REPO = _TESTS_DIR.parent
_WORKSPACE_ROOT = _PLUGINS_REPO.parent

#: 本仓插件源码目录（单一目录，跨 V2 / V3 共用一套实现）
PLUGINS_DIR = _PLUGINS_REPO / "plugins"

#: 引导失败的原因，供用例给出可读提示；None 表示引导成功
bootstrap_error: str | None = None


def resolve_backend_path() -> Path | None:
    """返回 MoviePilot 后端根目录；找不到时返回 ``None``。"""
    candidates = []
    env = os.environ.get("MOVIEPILOT_BACKEND_PATH")
    if env:
        candidates.append(Path(env).expanduser())
    candidates.append(_WORKSPACE_ROOT / "MoviePilot")
    for path in candidates:
        if (path / "app").is_dir():
            return path
    return None


def _register_namespace() -> None:
    """本地兜底：把 ``plugins/`` 追加到真实 ``app.plugins`` 包的 ``__path__``。

    只在后端存在但不带 ``app/testing`` 共享引导时使用。这里必须扩展**真实**的
    ``app`` 包，不能另建同名占位模块——否则会遮蔽后端的 ``app.core`` 等子包。
    """
    import_module("app")
    try:
        app_plugins = import_module("app.plugins")
    except ImportError:
        # 后端没有 app/plugins 包时，在真实 app 包下补一个命名空间子包
        app_pkg = sys.modules["app"]
        app_plugins = ModuleType("app.plugins")
        app_plugins.__spec__ = ModuleSpec("app.plugins", loader=None, is_package=True)
        app_plugins.__path__ = []  # type: ignore[attr-defined]
        sys.modules["app.plugins"] = app_plugins
        app_pkg.plugins = app_plugins  # type: ignore[attr-defined]

    search_path = list(getattr(app_plugins, "__path__", []))
    if str(PLUGINS_DIR) not in search_path:
        search_path.append(str(PLUGINS_DIR))
        app_plugins.__path__ = search_path  # type: ignore[attr-defined]


def prepare_backend() -> None:
    """单测引导：后端入 ``sys.path`` + 暴露本仓 ``plugins/``。"""
    global bootstrap_error

    if not PLUGINS_DIR.is_dir():
        bootstrap_error = f"未找到插件目录: {PLUGINS_DIR}"
        return

    backend = resolve_backend_path()
    if backend is None:
        bootstrap_error = (
            "未找到 MoviePilot 后端（app/ 不存在）。请将后端置于插件仓同级目录，"
            "或设置环境变量 MOVIEPILOT_BACKEND_PATH。"
            "仅依赖自带宿主桩的用例不受影响。"
        )
        return

    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    try:
        import_module("app.testing.bootstrap").prepare_v1_backend(_PLUGINS_REPO)
    except Exception:
        # 后端不带 app/testing 共享引导时退回本地注册
        _register_namespace()

    bootstrap_error = None
