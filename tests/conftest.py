"""pytest 全局引导：把本仓 ``plugins/`` 暴露为生产命名空间 ``app.plugins``。

本仓插件在单一 ``plugins/`` 目录下开发，同时兼容 V2 与 V3，不区分代际目录。
"""

from __future__ import annotations

from ._bootstrap import prepare_backend


def pytest_configure(config) -> None:
    """收集用例前把 ``plugins/`` 暴露为 ``app.plugins``。"""
    prepare_backend()
