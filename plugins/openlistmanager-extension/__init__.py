from app.plugins import _PluginBase
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel
import time

class OpenListManagerExtensionConfig(BaseModel):
    enabled: bool = False
    some_field: str = ""

class OpenListManagerExtension(_PluginBase):
    """
    OpenList管理器扩展插件 - 增强OpenList管理功能
    """
    # 插件基本信息
    plugin_name = "OpenList管理器扩展"
    plugin_desc = "增强OpenList管理器的功能。"
    plugin_icon = "Alist_B.png"
    plugin_version = "0.1"
    plugin_author = "Your Name"
    author_url = "https://github.com/yourusername/MoviePilot-Plugins"
    plugin_config_prefix = "openlist_extension_"
    plugin_order = 2
    auth_level = 1

    def __init__(self):
        super().__init__()
        self._enable = False
        self._some_field = ""

    def init_plugin(self, config: dict = None):
        if config:
            self._config = OpenListManagerExtensionConfig(**config)
            self._enable = self._config.enabled
            self._some_field = self._config.some_field

    def get_state(self) -> bool:
        return self._enable

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/activity",
                "endpoint": self.get_activity,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取活动记录"
            }
        ]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VCard",
                        "props": {"variant": "outlined", "class": "mb-3"},
                        "content": [
                            {
                                "component": "VCardText",
                                "content": [
                                    {
                                        "component": "VRow",
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 6},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "enabled",
                                                            "label": "启用插件",
                                                            "color": "primary"
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 6},
                                                "content": [
                                                    {
                                                        "component": "VTextField",
                                                        "props": {
                                                            "model": "some_field",
                                                            "label": "配置项",
                                                            "placeholder": "输入配置值"
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": self._enable,
            "some_field": self._some_field
        }

    def get_activity(self):
        """
        获取活动记录
        """
        return [
            {
                "action": "插件已启动",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            },
            {
                "action": "配置已更新",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        ]

    def get_render_mode(self) -> Tuple[str, str]:
        """
        获取插件渲染模式
        :return: 1、渲染模式，支持：vue/vuetify，默认vuetify
        :return: 2、组件路径，默认 dist/assets
        """
        return "vue", "dist/assets"
