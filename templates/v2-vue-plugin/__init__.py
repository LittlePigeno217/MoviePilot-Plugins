from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.plugins import _PluginBase


class TemplatePlugin(_PluginBase):
    plugin_name = "Vue-插件模板"
    plugin_desc = "MoviePilot V2 Vue 模块联邦插件模板。"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/Moviepilot_A.png"
    plugin_version = "1.0.0"
    plugin_author = "your-name"
    author_url = "https://github.com/your-name"
    plugin_config_prefix = "templateplugin_"
    plugin_order = 50
    auth_level = 1

    _enabled: bool = False
    _notify: bool = True
    _message: str = "Hello MoviePilot"
    _last_run: Optional[str] = None

    def init_plugin(self, config: dict = None):
        config = config or {}
        self._enabled = bool(config.get("enabled", False))
        self._notify = bool(config.get("notify", True))
        self._message = str(config.get("message") or "Hello MoviePilot")
        self._last_run = self.get_data("last_run")

    def get_state(self) -> bool:
        return bool(self._enabled)

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_render_mode(self) -> Tuple[str, Optional[str]]:
        return "vue", "dist/assets"

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        return None, self._get_config()

    def get_page(self) -> List[dict]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/config",
                "endpoint": self._get_config,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取插件配置",
            },
            {
                "path": "/config",
                "endpoint": self._save_config,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "保存插件配置",
            },
            {
                "path": "/status",
                "endpoint": self._get_status,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取插件状态",
            },
            {
                "path": "/run",
                "endpoint": self._run_once,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "执行一次示例动作",
            },
        ]

    def _get_config(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "notify": self._notify,
            "message": self._message,
        }

    def _save_config(self, config_payload: dict = None) -> Dict[str, Any]:
        config_payload = config_payload or {}
        self._enabled = bool(config_payload.get("enabled", self._enabled))
        self._notify = bool(config_payload.get("notify", self._notify))
        self._message = str(config_payload.get("message") or self._message or "Hello MoviePilot")

        new_config = {
            "enabled": self._enabled,
            "notify": self._notify,
            "message": self._message,
        }
        self.update_config(new_config)
        self.init_plugin(new_config)
        return {"success": True, "message": "配置已保存", "data": self._get_config()}

    def _get_status(self) -> Dict[str, Any]:
        return {
            "success": True,
            "data": {
                "enabled": self._enabled,
                "notify": self._notify,
                "message": self._message,
                "last_run": self.get_data("last_run") or self._last_run,
            },
        }

    def _run_once(self) -> Dict[str, Any]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._last_run = now
        self.save_data("last_run", now)
        return {
            "success": True,
            "message": "模板动作执行成功",
            "data": {
                "message": self._message,
                "last_run": now,
            },
        }

    def stop_service(self):
        pass
