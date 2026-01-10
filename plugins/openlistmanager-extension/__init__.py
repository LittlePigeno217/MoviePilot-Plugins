from app.plugins import _PluginBase
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel
import requests
import time
import json
import os
import hashlib
import asyncio
import aiohttp
from pathlib import Path
from datetime import datetime
from contextlib import AsyncExitStack
import aiofiles
from app.core.config import settings
from app.log import logger
from app.schemas.types import EventType
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# 导入通知相关模块
try:
    from app.schemas import Notification, NotificationType, MessageChannel
    from app.helper.notification import NotificationHelper
    from app.utils.http import RequestUtils
    NOTIFICATION_AVAILABLE = True
except ImportError:
    NOTIFICATION_AVAILABLE = False
    logger.warning("通知模块不可用，将使用简化通知")

try:
    from app.modules.filemanager.storages.alist import Alist
    from app.utils.url import UrlUtils
    ALIST_AVAILABLE = True
except ImportError:
    ALIST_AVAILABLE = False
    logger.warning("MoviePilot OpenList模块不可用，将使用手动配置")


class OpenListManagerConfig(BaseModel):
    enabled: bool = False
    openlist_url: str = ""
    openlist_token: str = ""
    directory_pairs: str = ""
    enable_custom_suffix: bool = False
    custom_suffix: str = ""
    cron: str = "30 3 * * *"
    use_moviepilot_config: bool = True
    enable_wechat_notify: bool = False
    onlyonce: bool = False
    clear_cache: bool = False


class OpenListManagerExtension(_PluginBase):
    """
    OpenList管理器扩展插件 - 实现OpenList多目录间文件复制与管理
    """
    # 插件基本信息
    plugin_name = "OpenList管理器扩展"
    plugin_desc = "OpenList多元化的管理插件扩展。"
    plugin_icon = "Alist_B.png"
    plugin_version = "0.1"
    plugin_author = "Your Name"
    author_url = "https://github.com/yourusername/MoviePilot-Plugins"
    plugin_config_prefix = "openlist_extension_"
    plugin_order = 2
    auth_level = 1

    # 文件后缀配置
    DEFAULT_VIDEO_SUFFIXES = [
        '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', 
        '.m4v', '.3gp', '.ts', '.mts', '.m2ts', '.vob', '.ogv',
        '.mpg', '.mpeg', '.rm', '.rmvb', '.asf', '.divx'
    ]
    CUSTOM_SUFFIXES = ['.srt', '.ass', '.nfo', '.jpg', '.png']

    def __init__(self):
        super().__init__()
        self._scheduler: Optional[BackgroundScheduler] = None
        self._plugin_dir: Path = Path(__file__).parent

        self._enable = False
        self._cron = ""
        self._onlyonce = False
        self._clearcache = False
        self._openlist_url = ""
        self._openlist_token = ""
        self._directory_pairs = ""
        self._enablecustomsuffix = False
        self._usemoviepilotconfig = True
        self._notify = False

        self._openlist_instance: Any = None
        self._notification_helper: Any = None

        self._task_status: Dict[str, Any] = {}
        self._copied_files: Dict[str, Any] = {}
        self._target_files_count: int = 0
        
        self._default_card_image = "https://raw.githubusercontent.com/LittlePigeno217/MoviePilot-Plugins/main/icons/Alist_B.png"
        
        self._previous_completed_count: int = 0
        self._previous_completed_files: List[str] = []

    def _get_default_task_status(self) -> Dict[str, Any]:
        """获取默认任务状态"""
        return {
            "status": "idle",
            "progress": 0,
            "message": "",
            "last_run": None,
            "start_time": None,
            "end_time": None,
            "total_files": 0,
            "copied_files": 0,
            "skipped_files": 0,
            "current_pair": "",
            "total_pairs": 0,
            "completed_pairs": 0
        }

    def _get_current_suffixes(self) -> List[str]:
        all_suffixes = self.DEFAULT_VIDEO_SUFFIXES.copy()
        if self._enablecustomsuffix:
            for suffix in self.CUSTOM_SUFFIXES:
                if suffix not in all_suffixes:
                    all_suffixes.append(suffix)
        return all_suffixes

    def _is_media_file(self, filename: str) -> bool:
        """判断文件是否为媒体文件"""
        current_suffixes = self._get_current_suffixes()
        return any(filename.endswith(suffix) for suffix in current_suffixes)
    
    def _generate_file_key(self, source_path: str, target_path: str) -> str:
        """生成文件唯一标识"""
        key_string = f"{source_path}->{target_path}"
        return hashlib.md5(key_string.encode()).hexdigest()

    def init_plugin(self, config: dict = None):
        self.stop_service()

        if config:
            self._config = OpenListManagerConfig(**config)
            self._enable = self._config.enabled
            self._cron = self._config.cron
            self._onlyonce = self._config.onlyonce
            self._clearcache = self._config.clear_cache
            self._openlist_url = self._config.openlist_url.rstrip('/')
            self._openlist_token = self._config.openlist_token
            self._directory_pairs = self._config.directory_pairs
            self._enablecustomsuffix = self._config.enable_custom_suffix
            self._usemoviepilotconfig = self._config.use_moviepilot_config
            self._notify = self._config.enable_wechat_notify

        self._init_moviepilot_openlist()
        if NOTIFICATION_AVAILABLE:
            self._notification_helper = NotificationHelper()

        if self._clearcache:
            logger.info("正在清空插件数据...")
            self._clear_all_data()
            self._clearcache = False
            self._update_config()

        logger.info("正在恢复插件状态数据...")
        self._task_status = self.get_data("openlistmanager_task_status") or self._get_default_task_status()
        self._copied_files = self.get_data("openlistmanager_copied_files") or {}
        self._target_files_count = self.get_data("openlistmanager_target_files_count") or 0

        logger.info(f"恢复数据完成: 任务状态={self._task_status.get('status')}, " 
                   f"复制文件记录={len(self._copied_files)}个, "
                   f"目标文件数={self._target_files_count}")

        self._scheduler = BackgroundScheduler(timezone=settings.TZ)
        if self._enable and self._cron:
            try:
                self._scheduler.add_job(func=self.execute_copy_task,
                                       trigger=CronTrigger.from_crontab(self._cron),
                                       name=self.plugin_name)
                logger.info(f"{self.plugin_name}: 已按 CRON '{self._cron}' 计划定时任务。")
            except Exception as err:
                logger.error(f"{self.plugin_name}: 定时任务配置错误: {err}")

        if self._onlyonce:
            logger.info("开始执行OpenList管理任务")
            import threading
            threading.Thread(target=self.execute_copy_task, daemon=True).start()
            self._onlyonce = False
            self._update_config()

        if self._scheduler.get_jobs():
            self._scheduler.start()

    def _init_moviepilot_openlist(self):
        """初始化MoviePilot OpenList实例"""
        if not ALIST_AVAILABLE:
            logger.warning("MoviePilot OpenList模块不可用，请确保安装了正确版本的MoviePilot")
            return
            
        try:
            self._openlist_instance = Alist()
            logger.info("MoviePilot OpenList实例初始化成功")
            
            if self._usemoviepilotconfig:
                self._update_openlist_config_from_instance()
                
except Exception as e:
            logger.error(f"初始化MoviePilot OpenList实例失败: {str(e)}")

    def _update_openlist_config_from_instance(self):
        if not self._openlist_instance:
            return
            
        try:
            if hasattr(self._openlist_instance, '_Alist__get_base_url'):
                base_url = self._openlist_instance._Alist__get_base_url
                if base_url:
                    self._openlist_url = base_url.rstrip('/')
                    logger.info(f"从MoviePilot OpenList实例获取地址: {self._openlist_url}")
            
            if hasattr(self._openlist_instance, '_Alist__get_valuable_toke'):
                token = self._openlist_instance._Alist__get_valuable_toke
                if token:
                    self._openlist_token = token
                    logger.info("从MoviePilot OpenList实例获取Token成功")
                    
except Exception as e:
            logger.error(f"从MoviePilot OpenList实例获取配置失败: {str(e)}")

    def get_state(self) -> bool:
        return self._enable

    def _update_config(self):
        self.update_config({
            "onlyonce": self._onlyonce,
            "clear_cache": self._clearcache,
            "cron": self._cron,
            "enabled": self._enable,
            "openlist_url": self._openlist_url,
            "openlist_token": self._openlist_token,
            "directory_pairs": self._directory_pairs,
            "enable_custom_suffix": self._enablecustomsuffix,
            "use_moviepilot_config": self._usemoviepilotconfig,
            "enable_wechat_notify": self._notify
        })

    def _clear_all_data(self):
        self._task_status = self._get_default_task_status()
        self._copied_files = {}
        self._target_files_count = 0
        self._previous_completed_count = 0
        self._previous_completed_files = []
        
        self.save_data("openlistmanager_task_status", self._task_status)
        self.save_data("openlistmanager_copied_files", self._copied_files)
        self.save_data("openlistmanager_target_files_count", self._target_files_count)
        
        logger.info("插件数据已全部清空")

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/status",
                "endpoint": self.get_status,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取任务状态"
            },
            {
                "path": "/run",
                "endpoint": self.run_task,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "执行复制任务"
            },
            {
                "path": "/activity",
                "endpoint": self.get_activity,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取活动记录"
            }
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        if self._enable and self._cron:
            return [
                {
                    "id": "OpenListManagerExtensionTask",
                    "name": "OpenList管理器扩展任务",
                    "trigger": CronTrigger.from_crontab(self._cron),
                    "func": self.execute_copy_task,
                    "kwargs": {}
                }
            ]
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        openlist_available = ALIST_AVAILABLE
        
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VCard",
                        "props": {"variant": "outlined", "class": "mb-3", "style": "border-radius: 8px;"},
                        "content": [
                            {
                                "component": "VCardText",
                                "props": {"class": "pa-3"},
                                "content": [
                                    {
                                        "component": "div",
                                        "props": {"class": "d-flex align-center mb-3"},
                                        "content": [
                                            {
                                                "component": "VAvatar",
                                                "props": {"color": "primary", "size": "32", "class": "mr-2"},
                                                "content": [
                                                    {
                                                        "component": "VIcon",
                                                        "props": {"icon": "mdi-cog", "size": "20"},
                                                        "text": ""
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "div",
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-subtitle-1 font-weight-bold"},
                                                        "text": "基本设置"
                                                    },
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-caption text-grey-darken-1"},
                                                        "text": "配置插件的基本运行参数"
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        "component": "VRow",
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 6, "md": 3},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "enabled",
                                                            "label": "启动插件",
                                                            "color": "primary",
                                                            "hideDetails": "auto"
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 6, "md": 3},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "enable_custom_suffix",
                                                            "label": "刮削文件",
                                                            "color": "primary",
                                                            "hint": "额外复制字幕(.srt,.ass)、元数据(.nfo)、封面图(.jpg,.png)文件",
                                                            "persistentHint": True
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 6, "md": 3},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "onlyonce",
                                                            "label": "立即运行复制任务",
                                                            "color": "success",
                                                            "hideDetails": "auto"
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 6, "md": 3},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "clear_cache",
                                                            "label": "清理统计",
                                                            "color": "warning",
                                                            "hideDetails": "auto"
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        "component": "VDivider",
                                        "props": {"class": "my-3"}
                                    },
                                    {
                                        "component": "VRow",
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 4},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "enable_wechat_notify",
                                                            "label": "发送通知",
                                                            "color": "primary",
                                                            "hint": "当有复制任务时发送企业微信卡片通知",
                                                            "persistentHint": True
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 4},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "use_moviepilot_config",
                                                            "label": "使用MoviePilot的内置OpenList",
                                                            "color": "primary",
                                                            "hint": "使用MoviePilot中已配置的OpenList实例",
                                                            "persistentHint": True,
                                                            "disabled": not openlist_available
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 4},
                                                "content": [
                                                    {
                                                        "component": "VTextField",
                                                        "props": {
                                                            "model": "cron",
                                                            "label": "执行周期",
                                                            "placeholder": "0 2 * * *",
                                                            "hint": "Cron表达式，默认每天凌晨2点执行复制任务",
                                                            "persistentHint": True,
                                                            "prependIcon": "mdi-clock-outline"
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        "component": "VDivider",
                                        "props": {"class": "my-3"}
                                    },
                                    {
                                        "component": "VRow",
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 6},
                                                "content": [
                                                    {
                                                        "component": "VTextField",
                                                        "props": {
                                                            "model": "openlist_url",
                                                            "label": "OpenList地址",
                                                            "placeholder": "http://localhost:5244",
                                                            "hint": "请输入完整的OpenList服务地址，如果使用MoviePilot配置则此项可留空",
                                                            "persistentHint": True,
                                                            "prependIcon": "mdi-link",
                                                            "disabled": self._usemoviepilotconfig and openlist_available
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
                                                            "model": "openlist_token",
                                                            "label": "OpenList令牌",
                                                            "type": "password",
                                                            "placeholder": "在OpenList后台获取",
                                                            "hint": "在OpenList管理后台的'设置'-'全局'中获取令牌，如果使用MoviePilot配置则此项可留空",
                                                            "persistentHint": True,
                                                            "prependIcon": "mdi-key",
                                                            "disabled": self._usemoviepilotconfig and openlist_available
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VCard",
                        "props": {"variant": "outlined", "class": "mb-3", "style": "border-radius: 8px;"},
                        "content": [
                            {
                                "component": "VCardText",
                                "props": {"class": "pa-3"},
                                "content": [
                                    {
                                        "component": "div",
                                        "props": {"class": "d-flex align-center mb-3"},
                                        "content": [
                                            {
                                                "component": "VAvatar",
                                                "props": {"color": "primary", "size": "32", "class": "mr-2"},
                                                "content": [
                                                    {
                                                        "component": "VIcon",
                                                        "props": {"icon": "mdi-folder-multiple", "size": "20"},
                                                        "text": ""
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "div",
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-subtitle-1 font-weight-bold"},
                                                        "text": "目录配对设置"
                                                    },
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-caption text-grey-darken-1"},
                                                        "text": "配置源目录和目标目录的映射关系"
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        "component": "VRow",
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12},
                                                "content": [
                                                    {
                                                        "component": "VTextarea",
                                                        "props": {
                                                            "model": "directory_pairs",
                                                            "label": "目录配对",
                                                            "placeholder": "源目录1#目标目录1\n源目录2#目标目录2",
                                                            "rows": 3,
                                                            "hint": "每行一组配对，使用#分隔源目录和目标目录",
                                                            "persistentHint": True,
                                                            "prependIcon": "mdi-folder-network"
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VCard",
                        "props": {"variant": "outlined", "class": "mt-3", "style": "border-radius: 8px;"},
                        "content": [
                            {
                                "component": "VCardText",
                                "props": {"class": "pa-3"},
                                "content": [
                                    {
                                        "component": "div",
                                        "props": {"class": "d-flex align-center mb-3"},
                                        "content": [
                                            {
                                                "component": "VAvatar",
                                                "props": {"color": "info", "size": "32", "class": "mr-2"},
                                                "content": [
                                                    {
                                                        "component": "VIcon",
                                                        "props": {"icon": "mdi-information", "size": "20"},
                                                        "text": ""
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "div",
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-subtitle-1 font-weight-bold"},
                                                        "text": "说明信息"
                                                    },
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-caption text-grey-darken-1"},
                                                        "text": "插件使用说明和注意事项"
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        "component": "VRow",
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 6},
                                                "content": [
                                                    {
                                                        "component": "VAlert",
                                                        "props": {
                                                            "type": "info",
                                                            "text": True,
                                                            "variant": "tonal",
                                                            "class": "mb-0",
                                                            "density": "compact"
                                                        },
                                                        "content": [
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "font-weight-bold mb-1"},
                                                                "text": "文件尾缀说明："
                                                            },
                                                            {
                                                                "component": "div", 
                                                                "text": "• 默认：自动匹配常用视频格式（mp4, mkv, avi, mov等）"
                                                            },
                                                            {
                                                                "component": "div",
                                                                "text": "• 勾选复制字幕/元数据/封面图：额外匹配字幕(.srt,.ass)、元数据(.nfo)、封面图(.jpg,.png)"
                                                            }
                                                        ]
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 6},
                                                "content": [
                                                    {
                                                        "component": "VAlert",
                                                        "props": {
                                                            "type": "warning",
                                                            "text": True,
                                                            "variant": "tonal",
                                                            "class": "mb-0",
                                                            "density": "compact"
                                                        },
                                                        "content": [
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "font-weight-bold mb-1"},
                                                                "text": "清除缓存说明："
                                                            },
                                                            {
                                                                "component": "div",
                                                                "text": "• 勾选此选项后保存，将清空所有复制记录和任务状态"
                                                            },
                                                            {
                                                                "component": "div",
                                                                "text": "• 插件将重新开始记录复制历史"
                                                            },
                                                            {
                                                                "component": "div",
                                                                "text": "• 此操作不可逆，请谨慎使用"
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
                ]
            }
        ], {
            "enabled": self._enable,
            "onlyonce": self._onlyonce,
            "clear_cache": self._clearcache,
            "openlist_url": self._openlist_url,
            "openlist_token": self._openlist_token,
            "directory_pairs": self._directory_pairs,
            "enable_custom_suffix": self._enablecustomsuffix,
            "use_moviepilot_config": self._usemoviepilotconfig,
            "enable_wechat_notify": self._notify,
            "cron": self._cron or "0 2 * * *"
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

    def get_status(self):
        """
        获取任务状态
        """
        return self._task_status

    def run_task(self):
        """
        执行复制任务
        """
        if self._task_status.get("status") == "running":
            return {"status": "error", "message": "任务正在执行中"}
        
        import threading
        threading.Thread(target=self.execute_copy_task, daemon=True).start()
        return {"status": "success", "message": "任务已开始执行"}

    def execute_copy_task(self):
        """
        执行复制任务（简化版，完整实现请参考原插件）
        """
        logger.info(f"{self.plugin_name}: 开始执行复制任务")
        self._task_status["status"] = "running"
        self._task_status["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save_data("openlistmanager_task_status", self._task_status)
        
        # 这里只是简化实现，完整的文件复制逻辑请参考原插件
        try:
            # 模拟任务执行
            time.sleep(2)
            
            self._task_status["status"] = "idle"
            self._task_status["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._task_status["message"] = "任务执行完成"
            self.save_data("openlistmanager_task_status", self._task_status)
            
            logger.info(f"{self.plugin_name}: 复制任务执行完成")
        except Exception as e:
            logger.error(f"{self.plugin_name}: 复制任务执行失败: {str(e)}")
            self._task_status["status"] = "idle"
            self._task_status["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._task_status["message"] = f"任务执行失败: {str(e)}"
            self.save_data("openlistmanager_task_status", self._task_status)

    def _get_copying_media_files(self, limit=12):
        """
        获取正在复制的媒体文件（模拟实现）
        """
        return []

    def _get_recent_media_files(self, limit=12):
        """
        获取最近复制的媒体文件（模拟实现）
        """
        return []

    def get_page(self) -> List[dict]:
        """
        获取插件页面（使用远程Vue组件）
        """
        return []

    def get_render_mode(self) -> Tuple[str, str]:
        """
        获取插件渲染模式
        :return: 1、渲染模式，支持：vue/vuetify，默认vuetify
        :return: 2、组件路径，默认 dist/assets
        """
        return "vue", "dist/assets"
