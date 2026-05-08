from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Tuple

from app.plugins import _PluginBase


class TemplateVuetifyPlugin(_PluginBase):
    plugin_name = "Vuetify-插件模板"
    plugin_desc = "MoviePilot V2 Vuetify JSON 插件模板。"
    plugin_icon = "Moviepilot_A.png"
    plugin_version = "1.0.0"
    plugin_author = "your-name"
    author_url = "https://github.com/your-name"
    plugin_config_prefix = "templatevuetify_"
    plugin_order = 50
    auth_level = 1

    _enabled: bool = False
    _notify: bool = True
    _message: str = "Hello MoviePilot"
    _last_run: str | None = None

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

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                            "color": "primary",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "notify",
                                            "label": "发送通知",
                                            "color": "info",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 12},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "message",
                                            "label": "展示文本",
                                            "placeholder": "请输入要展示的文本",
                                            "prepend-inner-icon": "mdi-message-text-outline",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": "这是 Vuetify JSON 模板，可按业务扩展更多字段、动作和说明。",
                                        },
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ], {
            "enabled": False,
            "notify": True,
            "message": "Hello MoviePilot",
        }

    def get_page(self) -> List[dict]:
        return [
            {
                "component": "VAlert",
                "props": {
                    "type": "success" if self._enabled else "warning",
                    "variant": "tonal",
                    "title": self.plugin_name,
                    "text": self._message,
                },
            },
            {
                "component": "VCard",
                "props": {"class": "mt-3"},
                "content": [
                    {
                        "component": "VCardText",
                        "text": f"最近执行时间：{self.get_data('last_run') or self._last_run or '未执行'}",
                    }
                ],
            },
        ]

    def stop_service(self):
        pass
