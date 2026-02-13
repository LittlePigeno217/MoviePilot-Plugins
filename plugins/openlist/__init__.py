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
import threading
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


class OpenListConfig(BaseModel):
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


class OpenList(_PluginBase):
    """
    OpenList管理器插件 - 实现OpenList多目录间文件复制与管理
    """
    # 插件基本信息
    plugin_name = "OpenList管理器"
    plugin_desc = "OpenList多元化的管理插件。"
    plugin_icon = "Alist_B.png"
    plugin_version = "1.0"
    plugin_author = "LittlePigeno"
    author_url = "https://github.com/LittlePigeno217/MoviePilot-Plugins"
    plugin_config_prefix = "openlist_"
    plugin_order = 1
    auth_level = 1

    # 文件状态枚举
    FILE_STATUS_PENDING = "未复制"
    FILE_STATUS_COPYING = "复制中"
    FILE_STATUS_COMPLETED = "已完成"
    FILE_STATUS_ERROR = "复制失败"

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
        self._file_status: Dict[str, str] = {}  # 文件状态存储，key为文件唯一标识，value为状态
        self._lock = threading.RLock()  # 线程锁，用于并发控制
        
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
    
    def _generate_file_key(self, relative_path: str) -> str:
        """生成文件唯一标识（基于相对路径）"""
        # 使用相对路径生成唯一标识，确保源目录和目标目录下相对路径相同的文件被识别为同一标识
        return hashlib.md5(relative_path.encode()).hexdigest()

    def init_plugin(self, config: dict = None):
        self.stop_service()

        # 检查 MoviePilot 版本
        if hasattr(settings, 'VERSION_FLAG'):
            version = settings.VERSION_FLAG  # V2
        else:
            version = "v1"

        if config:
            self._config = OpenListConfig(**config)
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
        self._task_status = self.get_data("openlist_task_status") or self._get_default_task_status()
        self._copied_files = self.get_data("openlist_copied_files") or {}
        self._target_files_count = self.get_data("openlist_target_files_count") or 0
        self._file_status = self.get_data("openlist_file_status") or {}  # 加载文件状态数据

        logger.info(f"恢复数据完成: 任务状态={self._task_status.get('status')}, " 
                   f"复制文件记录={len(self._copied_files)}个, "
                   f"目标文件数={self._target_files_count}, "
                   f"文件状态记录={len(self._file_status)}条")

        if self._onlyonce:
            logger.info("开始执行OpenList管理任务")
            import threading
            threading.Thread(target=self.execute_copy_task, daemon=True).start()
            self._onlyonce = False
            self._update_config()

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
        with self._lock:
            self._task_status = self._get_default_task_status()
            self._copied_files = {}
            self._target_files_count = 0
            self._file_status = {}  # 清空文件状态数据
            self._previous_completed_count = 0
            self._previous_completed_files = []
            
            self.save_data("openlist_task_status", self._task_status)
            self.save_data("openlist_copied_files", self._copied_files)
            self.save_data("openlist_target_files_count", self._target_files_count)
            self.save_data("openlist_file_status", self._file_status)  # 保存清空后的文件状态
        
        logger.info("插件数据已全部清空")

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/status",
                "endpoint": self.get_status,
                "methods": ["GET"],
                "summary": "获取任务状态"
            },
            {
                "path": "/run",
                "endpoint": self.run_task,
                "methods": ["POST"],
                "summary": "执行复制任务"
            }
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        if self._enable and self._cron:
            return [
                {
                    "id": "OpenListManagerTask",
                    "name": "OpenList管理任务",
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
                                                                "text": "• 勾选此选项后保存，将清空所有复制记录、任务状态和文件状态"
                                                            },
                                                            {
                                                                "component": "div",
                                                                "text": "• 插件将重新开始记录复制历史和文件状态"
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

    def get_page(self) -> List[dict]:
        copying_media_files = self._get_copying_media_files(12)
        completed_media_files = self._get_recent_media_files(12)
        
        return [
            {
                "component": "VCard",
                "props": {"variant": "outlined", "class": "status-card", "style": "height: 100vh; max-height: 100vh; overflow-y: auto;"},
                "content": [
                    {
                        "component": "VCardText",
                        "props": {"class": "pa-3"},
                        "content": [
                            # 页面标题
                            {
                                "component": "div",
                                "props": {"class": "d-flex align-center justify-space-between mb-3"},
                                "content": [
                                    {
                                        "component": "div",
                                        "props": {"class": "d-flex align-center"},
                                        "content": [
                                            {
                                                "component": "VIcon",
                                                "props": {"icon": "mdi-view-dashboard", "color": "primary", "size": "medium", "class": "mr-2"},
                                                "text": ""
                                            },
                                            {
                                                "component": "div",
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-h6 font-weight-bold"},
                                                        "text": "OpenList管理器"
                                                    },
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-caption text-grey-darken-1"},
                                                        "text": "文件复制与管理状态监控"
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            },
                            
                            # 第一行：三个状态框
                            {
                                "component": "VRow",
                                "props": {"class": "mb-3"},
                                "content": [
                                    # 状态框1：目标目录媒体文件数
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 12, "sm": 4},
                                        "content": [
                                            {
                                                "component": "VCard",
                                                "props": {
                                                    "color": "primary", 
                                                    "variant": "tonal", 
                                                    "class": "status-card-item",
                                                    "style": "min-height: 80px; height: 100%; border-radius: 8px; transition: all 0.3s ease;"
                                                },
                                                "content": [
                                                    {
                                                        "component": "VCardText",
                                                        "props": {"class": "text-center pa-2"},
                                                        "content": [
                                                            {
                                                                "component": "VAvatar",
                                                                "props": {
                                                                    "color": "primary",
                                                                    "size": "36",
                                                                    "class": "mb-1"
                                                                },
                                                                "content": [
                                                                    {
                                                                        "component": "VIcon",
                                                                        "props": {"icon": "mdi-folder-open", "size": "20"},
                                                                        "text": ""
                                                                    }
                                                                ]
                                                            },
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "text-caption font-weight-medium text-primary-darken-1 mb-1"},
                                                                "text": "目标目录媒体文件数"
                                                            },
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "text-h5 font-weight-bold text-primary-darken-2"},
                                                                "text": str(self._target_files_count)
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    # 状态框2：当前复制媒体文件数量
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 12, "sm": 4},
                                        "content": [
                                            {
                                                "component": "VCard",
                                                "props": {
                                                    "color": "warning", 
                                                    "variant": "tonal", 
                                                    "class": "status-card-item",
                                                    "style": "min-height: 80px; height: 100%; border-radius: 8px; transition: all 0.3s ease;"
                                                },
                                                "content": [
                                                    {
                                                        "component": "VCardText",
                                                        "props": {"class": "text-center pa-2"},
                                                        "content": [
                                                            {
                                                                "component": "VAvatar",
                                                                "props": {
                                                                    "color": "warning",
                                                                    "size": "36",
                                                                    "class": "mb-1"
                                                                },
                                                                "content": [
                                                                    {
                                                                        "component": "VIcon",
                                                                        "props": {"icon": "mdi-progress-clock", "size": "20"},
                                                                        "text": ""
                                                                    }
                                                                ]
                                                            },
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "text-caption font-weight-medium text-warning-darken-1 mb-1"},
                                                                "text": "正在复制媒体文件"
                                                            },
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "text-h5 font-weight-bold text-warning-darken-2"},
                                                                "text": str(len(copying_media_files))
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    # 状态框3：累计复制媒体文件数量
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 12, "sm": 4},
                                        "content": [
                                            {
                                                "component": "VCard",
                                                "props": {
                                                    "color": "success", 
                                                    "variant": "tonal", 
                                                    "class": "status-card-item",
                                                    "style": "min-height: 80px; height: 100%; border-radius: 8px; transition: all 0.3s ease;"
                                                },
                                                "content": [
                                                    {
                                                        "component": "VCardText",
                                                        "props": {"class": "text-center pa-2"},
                                                        "content": [
                                                            {
                                                                "component": "VAvatar",
                                                                "props": {
                                                                    "color": "success",
                                                                    "size": "36",
                                                                    "class": "mb-1"
                                                                },
                                                                "content": [
                                                                    {
                                                                        "component": "VIcon",
                                                                        "props": {"icon": "mdi-check-circle-outline", "size": "20"},
                                                                        "text": ""
                                                                    }
                                                                ]
                                                            },
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "text-caption font-weight-medium text-success-darken-1 mb-1"},
                                                                "text": "累计复制媒体文件"
                                                            },
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "text-h5 font-weight-bold text-success-darken-2"},
                                                                "text": str(len(completed_media_files))
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            },
                            
                            # 第二行：正在复制的媒体文件列表
                            {
                                "component": "VRow",
                                "props": {"class": "mb-3"},
                                "content": [
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 12},
                                        "content": [
                                            {
                                                "component": "VCard",
                                                "props": {
                                                    "variant": "outlined", 
                                                    "class": "file-list-card",
                                                    "style": "border-radius: 8px;"
                                                },
                                                "content": [
                                                    {
                                                        "component": "VCardTitle",
                                                        "props": {"class": "d-flex align-center pa-2 bg-orange-lighten-5"},
                                                        "content": [
                                                            {
                                                                "component": "VAvatar",
                                                                "props": {
                                                                    "color": "orange",
                                                                    "size": "28",
                                                                    "class": "mr-2"
                                                                },
                                                                "content": [
                                                                    {
                                                                        "component": "VIcon",
                                                                        "props": {"icon": "mdi-progress-upload", "size": "16"},
                                                                        "text": ""
                                                                    }
                                                                ]
                                                            },
                                                            {
                                                                "component": "div",
                                                                "content": [
                                                                    {
                                                                        "component": "div",
                                                                        "props": {"class": "text-subtitle-2 font-weight-bold text-orange-darken-2"},
                                                                        "text": "正在复制的媒体文件"
                                                                    },
                                                                    {
                                                                        "component": "div",
                                                                        "props": {"class": "text-caption text-grey-darken-1"},
                                                                        "text": f"共 {len(copying_media_files)} 个文件"
                                                                    }
                                                                ]
                                                            }
                                                        ]
                                                    },
                                                    {
                                                        "component": "VCardText",
                                                        "props": {"class": "pa-2"},
                                                        "content": self._render_copying_media_files(copying_media_files)
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            },
                            
                            # 第三行：最近完成的媒体文件列表
                            {
                                "component": "VRow",
                                "content": [
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 12},
                                        "content": [
                                            {
                                                "component": "VCard",
                                                "props": {
                                                    "variant": "outlined", 
                                                    "class": "file-list-card",
                                                    "style": "border-radius: 8px;"
                                                },
                                                "content": [
                                                    {
                                                        "component": "VCardTitle",
                                                        "props": {"class": "d-flex align-center pa-2 bg-green-lighten-5"},
                                                        "content": [
                                                            {
                                                                "component": "VAvatar",
                                                                "props": {
                                                                    "color": "success",
                                                                    "size": "28",
                                                                    "class": "mr-2"
                                                                },
                                                                "content": [
                                                                    {
                                                                        "component": "VIcon",
                                                                        "props": {"icon": "mdi-check-circle", "size": "16"},
                                                                        "text": ""
                                                                    }
                                                                ]
                                                            },
                                                            {
                                                                "component": "div",
                                                                "content": [
                                                                    {
                                                                        "component": "div",
                                                                        "props": {"class": "text-subtitle-2 font-weight-bold text-green-darken-2"},
                                                                        "text": "最近完成的媒体文件"
                                                                    },
                                                                    {
                                                                        "component": "div",
                                                                        "props": {"class": "text-caption text-grey-darken-1"},
                                                                        "text": f"共 {len(completed_media_files)} 个文件"
                                                                    }
                                                                ]
                                                            }
                                                        ]
                                                    },
                                                    {
                                                        "component": "VCardText",
                                                        "props": {"class": "pa-2"},
                                                        "content": self._render_recent_media_files(completed_media_files)
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

    # 以下是原有的复制任务相关方法
    def _update_file_status_and_counts(self, silent: bool = False):
        """更新媒体文件状态和数量统计"""
        if not self._copied_files:
            return
            
        directory_pairs = self._parse_directory_pairs()
        if not directory_pairs:
            return
            
        if not silent:
            logger.info("更新媒体文件状态...")
        
        # 为每个目标目录构建媒体文件索引
        target_dirs_index = {}
        for pair in directory_pairs:
            target_dir = self._normalize_path(pair["target"])
            if target_dir not in target_dirs_index:
                target_files = self._get_openlist_files(target_dir)
                if target_files:
                    # 构建媒体文件名索引
                    file_index = {}
                    for file in target_files:
                        filename = file.get("name")
                        if filename and self._is_media_file(filename):
                            file_index[filename] = file.get("path", "")
                    target_dirs_index[target_dir] = file_index
                else:
                    target_dirs_index[target_dir] = {}
        
        # 检查每个媒体文件的状态并更新
        updated_count = 0
        for file_key, record in self._copied_files.items():
            target_path = record.get("target_path", "")
            filename = record.get("filename", "")
            current_status = record.get("status", "copying")
            
            if not target_path or not filename:
                continue
                
            # 找到对应的目标目录
            target_dir = None
            for pair in directory_pairs:
                normalized_target = self._normalize_path(pair["target"])
                if self._normalize_path(target_path).startswith(normalized_target):
                    target_dir = normalized_target
                    break
            
            if not target_dir:
                continue
                
            # 检查媒体文件是否在目标目录中存在
            if target_dir in target_dirs_index and filename in target_dirs_index[target_dir]:
                # 文件在目标目录中存在，更新状态为已完成
                if current_status != "completed":
                    self._copied_files[file_key]["status"] = "completed"
                    self._copied_files[file_key]["completed_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    updated_count += 1
        
        if updated_count > 0 and not silent:
            logger.info(f"已更新 {updated_count} 个媒体文件的状态")
    
    def _normalize_path(self, path: str) -> str:
        """标准化路径"""
        return path.rstrip('/')
    
    def _get_file_status_counts(self) -> Tuple[int, int]:
        """获取媒体文件状态统计数量"""
        copying_count = 0
        completed_count = 0
        
        for record in self._copied_files.values():
            status = record.get("status", "copying")
            if status == "completed":
                completed_count += 1
            else:
                copying_count += 1
                
        return copying_count, completed_count
    
    def _get_recent_media_files(self, count: int = 50) -> List[Dict]:
        """获取最近完成的媒体文件列表 - 按时间倒序，文件名倒序排序"""
        completed_files = []
        
        for record in self._copied_files.values():
            if record.get("status") == "completed":
                completed_files.append(record)
        
        # 按完成时间倒序，文件名倒序排序
        completed_files.sort(key=lambda x: (
            x.get("completed_time", ""), 
            x.get("filename", "")
        ), reverse=True)
        
        # 返回指定数量的文件
        return completed_files[:count]
    
    def _get_copying_media_files(self, count: int = 50) -> List[Dict]:
        """获取正在复制的媒体文件列表 - 按时间倒序，文件名倒序排序"""
        copying_files = []
        
        for record in self._copied_files.values():
            if record.get("status") == "copying":
                copying_files.append(record)
        
        # 按复制时间倒序，文件名倒序排序
        copying_files.sort(key=lambda x: (
            x.get("copied_time", ""), 
            x.get("filename", "")
        ), reverse=True)
        
        # 返回指定数量的文件
        return copying_files[:count]
    
    def _render_recent_media_files(self, media_files: List[Dict]) -> List[Dict]:
        """渲染最近完成的媒体文件列表 - 更紧凑的样式"""
        if not media_files:
            return [
                {
                    "component": "div",
                    "props": {"class": "text-center text-grey py-8"},
                    "content": [
                        {
                            "component": "VIcon",
                            "props": {"icon": "mdi-file-question", "size": "48", "color": "grey-lighten-1", "class": "mb-2"},
                            "text": ""
                        },
                        {
                            "component": "div",
                            "props": {"class": "text-body-2 text-grey-darken-1"},
                            "text": "暂无完成的媒体文件记录"
                        }
                    ]
                }
            ]
        
        content = []
        
        # 将文件列表按每行6个分组
        rows = []
        for i in range(0, len(media_files), 6):
            rows.append(media_files[i:i+6])
        
        # 渲染每一行
        for row in rows:
            row_content = []
            for media_file in row:
                filename = media_file.get("filename", "未知文件")
                completed_time = media_file.get("completed_time", "")
                
                row_content.append({
                    "component": "VCol",
                    "props": {"cols": 12, "sm": 2, "md": 2, "lg": 2, "class": "pa-1"},
                    "content": [
                        {
                            "component": "VCard",
                            "props": {
                                "color": "green-lighten-5", 
                                "variant": "flat", 
                                "class": "text-center compact-file-card",
                                "style": "min-height: 50px; height: 100%; border-radius: 6px; transition: all 0.2s ease;"
                            },
                            "content": [
                                {
                                    "component": "VCardText",
                                    "props": {
                                        "class": "pa-1 d-flex flex-column align-center justify-center", 
                                        "style": "min-height: 50px;"
                                    },
                                    "content": [
                                        {
                                            "component": "div",
                                            "props": {"class": "d-flex align-center justify-center w-100 mb-1"},
                                            "content": [
                                                {
                                                    "component": "VIcon",
                                                    "props": {
                                                        "icon": "mdi-check-circle", 
                                                        "size": "x-small", 
                                                        "class": "text-success mr-1",
                                                        "style": "min-width: 14px;"
                                                    },
                                                    "text": ""
                                                },
                                                {
                                                    "component": "span",
                                                    "props": {
                                                        "class": "text-caption text-left compact-filename", 
                                                        "style": "word-break: break-all; line-height: 1.1; max-height: 2.2em; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; font-size: 0.7rem; flex: 1;"
                                                    },
                                                    "text": filename
                                                }
                                            ]
                                        },
                                        {
                                            "component": "div",
                                            "props": {
                                                "class": "text-caption text-grey-darken-1 mt-1",
                                                "style": "font-size: 0.6rem;"
                                            },
                                            "text": completed_time
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                })
            
            # 如果一行不足4个，用空列填充以保持对称
            while len(row_content) < 4:
                row_content.append({
                    "component": "VCol",
                    "props": {"cols": 12, "sm": 3, "md": 3, "lg": 3, "class": "pa-1"},
                    "content": []
                })
            
            content.append({
                "component": "VRow",
                "props": {"class": "mb-1", "dense": True, "align": "stretch"},
                "content": row_content
            })
        
        return content
    
    def _render_copying_media_files(self, media_files: List[Dict]) -> List[Dict]:
        """渲染正在复制的媒体文件列表 - 更紧凑的样式"""
        if not media_files:
            return [
                {
                    "component": "div",
                    "props": {"class": "text-center text-grey py-8"},
                    "content": [
                        {
                            "component": "VIcon",
                            "props": {"icon": "mdi-file-sync-outline", "size": "48", "color": "grey-lighten-1", "class": "mb-2"},
                            "text": ""
                        },
                        {
                            "component": "div",
                            "props": {"class": "text-body-2 text-grey-darken-1"},
                            "text": "暂无正在复制的媒体文件"
                        }
                    ]
                }
            ]
        
        content = []
        
        # 将文件列表按每行4个分组
        rows = []
        for i in range(0, len(media_files), 4):
            rows.append(media_files[i:i+4])
        
        # 渲染每一行
        for row in rows:
            row_content = []
            for media_file in row:
                filename = media_file.get("filename", "未知文件")
                copied_time = media_file.get("copied_time", "")
                
                row_content.append({
                    "component": "VCol",
                    "props": {"cols": 12, "sm": 3, "md": 3, "lg": 3, "class": "pa-1"},
                    "content": [
                        {
                            "component": "VCard",
                            "props": {
                                "color": "orange-lighten-5", 
                                "variant": "flat", 
                                "class": "text-center compact-file-card",
                                "style": "min-height: 60px; height: 100%; border-radius: 8px; transition: all 0.2s ease;"
                            },
                            "content": [
                                {
                                    "component": "VCardText",
                                    "props": {
                                        "class": "pa-2 d-flex flex-column align-center justify-center", 
                                        "style": "min-height: 60px;"
                                    },
                                    "content": [
                                        {
                                            "component": "div",
                                            "props": {"class": "d-flex align-center justify-center w-100 mb-1"},
                                            "content": [
                                                {
                                                    "component": "VIcon",
                                                    "props": {
                                                        "icon": "mdi-progress-upload", 
                                                        "size": "small", 
                                                        "class": "text-orange mr-1",
                                                        "style": "min-width: 18px;"
                                                    },
                                                    "text": ""
                                                },
                                                {
                                                    "component": "span",
                                                    "props": {
                                                        "class": "text-caption text-left compact-filename", 
                                                        "style": "word-break: break-all; line-height: 1.2; max-height: 2.4em; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; font-size: 0.75rem; flex: 1;"
                                                    },
                                                    "text": filename
                                                }
                                            ]
                                        },
                                        {
                                            "component": "div",
                                            "props": {
                                                "class": "text-caption text-grey-darken-1 mt-1",
                                                "style": "font-size: 0.65rem;"
                                            },
                                            "text": copied_time
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                })
            
            # 如果一行不足4个，用空列填充以保持对称
            while len(row_content) < 4:
                row_content.append({
                    "component": "VCol",
                    "props": {"cols": 12, "sm": 3, "md": 3, "lg": 3, "class": "pa-1"},
                    "content": []
                })
            
            content.append({
                "component": "VRow",
                "props": {"class": "mb-1", "dense": True, "align": "stretch"},
                "content": row_content
            })
        
        return content

    def _parse_directory_pairs(self) -> List[Dict[str, str]]:
        """解析目录配对字符串"""
        pairs = []
        if not self._directory_pairs:
            return pairs
            
        lines = self._directory_pairs.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if '#' in line:
                parts = line.split('#', 1)
                if len(parts) == 2:
                    source = parts[0].strip()
                    target = parts[1].strip()
                    if source and target:
                        pairs.append({
                            "source": source,
                            "target": target
                        })
        return pairs

    def stop_service(self):
        """停止服务"""
        # 停止服务，确保不会有重复的任务执行
        if hasattr(self, '_scheduler') and self._scheduler:
            try:
                self._scheduler.shutdown()
                logger.info(f"{self.plugin_name}: 定时任务已停止")
            except Exception as err:
                logger.error(f"{self.plugin_name}: 停止定时任务失败: {err}")

    def _get_newly_completed_files(self) -> List[str]:
        """获取本次执行任务中新完成的文件列表"""
        newly_completed_files = []
        
        # 获取当前所有已完成文件
        current_completed_files = []
        for record in self._copied_files.values():
            if record.get("status") == "completed":
                filename = record.get("filename", "")
                if filename:
                    current_completed_files.append(filename)
        
        # 找出本次执行任务中新完成的文件
        for filename in current_completed_files:
            if filename not in self._previous_completed_files:
                newly_completed_files.append(filename)
        
        return newly_completed_files

    def execute_copy_task(self):
        """执行复制任务 - 优化版本，避免重复执行"""
        # 检查任务状态，如果正在运行则跳过
        if self._task_status.get("status") == "running":
            logger.info("任务正在运行中，跳过执行")
            return
        
        logger.info("开始执行OpenList多目录复制任务")
        
        if self._usemoviepilotconfig and self._openlist_instance:
            self._update_openlist_config_from_instance()
        
        if not self._validate_config():
            directory_pairs = self._parse_directory_pairs()
            if directory_pairs:
                self._update_target_files_count(directory_pairs)
            return
            
        directory_pairs = self._parse_directory_pairs()
        if not directory_pairs:
            self._complete_task("failed", "未配置有效的目录配对")
            self._update_target_files_count(directory_pairs)
            return
        
        _, old_completed_count = self._get_file_status_counts()
        self._previous_completed_count = old_completed_count
        self._previous_completed_files = self._get_completed_files_list()
        
        if not self._should_execute_copy_task(directory_pairs):
            logger.info("无需执行复制任务")
            
            # 检查是否有文件状态发生变化（从复制中变为已完成）
            self._update_file_status_and_counts(silent=True)
            _, new_completed_count = self._get_file_status_counts()
            increased_completed_count = new_completed_count - self._previous_completed_count
            
            if self._notify and increased_completed_count > 0:
                newly_completed_files = self._get_newly_completed_files()
                self._send_notification(0, increased_completed_count, [], newly_completed_files)
                self._complete_task("success", f"无需执行复制任务，但检测到 {increased_completed_count} 个文件已完成复制")
            else:
                self._complete_task("success", "无需执行复制任务")
            return
            
        # 用于记录本次执行成功复制的媒体文件
        successfully_copied_files = []
            
        self._task_status.update({
            "status": "running",
            "progress": 0,
            "message": f"开始准备复制任务，共 {len(directory_pairs)} 组目录配对...",
            "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": None,
            "total_files": 0,
            "copied_files": 0,
            "skipped_files": 0,
            "current_pair": "",
            "total_pairs": len(directory_pairs),
            "completed_pairs": 0
        })
        self._save_task_status()
        
        try:
            if not self._verify_openlist_connection():
                raise Exception("OpenList连接失败，请检查地址和令牌")
            
            total_copied = 0
            total_skipped = 0
            total_files = 0
            
            # 创建全局已处理媒体文件集合，确保在整个任务执行期间文件只被处理一次
            global_processed_files = set()
            
            for i, pair in enumerate(directory_pairs):
                source_dir = pair["source"]
                target_dir = pair["target"]
                
                self._task_status["current_pair"] = f"{source_dir} → {target_dir}"
                self._update_status(f"正在处理第 {i+1}/{len(directory_pairs)} 组目录配对: {source_dir} → {target_dir}", 
                                  int((i) / len(directory_pairs) * 100))
                
                pair_result = self._execute_single_copy(source_dir, target_dir, i, len(directory_pairs), successfully_copied_files, global_processed_files)
                if pair_result:
                    total_copied += pair_result["copied"]
                    total_skipped += pair_result["skipped"]
                    total_files += pair_result["total"]
                
                self._task_status["completed_pairs"] = i + 1
                self._save_task_status()
            
            # 任务完成后更新媒体文件状态
            self._update_file_status_and_counts(silent=True)
            
            # 计算本次执行新增的完成文件数量
            _, new_completed_count = self._get_file_status_counts()
            increased_completed_count = new_completed_count - self._previous_completed_count
            
            newly_completed_files = self._get_newly_completed_files()
            
            should_send_notification = (
                self._notify and 
                (total_copied > 0 or increased_completed_count > 0)
            )
            
            if should_send_notification:
                self._send_notification(total_copied, increased_completed_count, 
                                       successfully_copied_files, newly_completed_files)
            
            self._complete_task("success", 
                               f"复制完成！共处理 {len(directory_pairs)} 组目录配对，" 
                               f"总计 {total_files} 个媒体文件，" 
                               f"复制 {total_copied} 个，" 
                               f"跳过 {total_skipped} 个，" 
                               f"新增完成 {increased_completed_count} 个")
                               
        except Exception as e:
            logger.error(f"复制任务执行失败: {str(e)}")
            self._complete_task("failed", f"任务执行失败: {str(e)}")
        finally:
            if self._onlyonce:
                self._onlyonce = False
                self._update_config()
                logger.info("立即运行任务已完成")
            
            # 无论任务是否成功，都更新目标目录媒体文件数
            self._update_target_files_count(directory_pairs)

    def _get_completed_files_list(self) -> List[str]:
        """获取当前所有已完成文件的列表"""
        completed_files = []
        for record in self._copied_files.values():
            if record.get("status") == "completed":
                filename = record.get("filename", "")
                if filename:
                    completed_files.append(filename)
        return completed_files

    def _send_notification(self, total_copied: int, increased_completed_count: int, 
                          successfully_copied_files: List[str], newly_completed_files: List[str]):
        """发送任务完成通知"""
        if not self._notify:
            return
            
        try:
            title = "🏆 OpenList管理任务统计"
            
            copied_files_text = ""
            if successfully_copied_files:
                if len(successfully_copied_files) <= 3:
                    copied_files_text = "\n".join([f"• {filename}" for filename in successfully_copied_files])
                else:
                    copied_files_text = "\n".join([f"• {filename}" for filename in successfully_copied_files[:3]])
                    copied_files_text += f"\n• ...等 {len(successfully_copied_files)} 个文件"
            else:
                copied_files_text = "• 无新增复制文件"
            
            completed_files_text = ""
            if newly_completed_files:
                if len(newly_completed_files) <= 3:
                    completed_files_text = "\n".join([f"• {filename}" for filename in newly_completed_files])
                else:
                    completed_files_text = "\n".join([f"• {filename}" for filename in newly_completed_files[:3]])
                    completed_files_text += f"\n• ...等 {len(newly_completed_files)} 个文件"
            else:
                completed_files_text = "• 无新增完成文件"
            
            message = f"\n" \
                    f"📊 **建立复制任务：** {total_copied} 个\n" \
                    f"✅ **完成复制任务：** {increased_completed_count} 个\n\n" \
                    f"📁 **本次复制文件列表：**\n{copied_files_text}\n\n" \
                    f"🎯 **本次完成复制任务的文件列表：**\n{completed_files_text}"
            
            self.post_message(
                mtype=NotificationType.SiteMessage,
                title=title,
                text=message
            )
            
            logger.info(f"通知发送成功，本次新增完成数量: {increased_completed_count}")
            
        except Exception as e:
            logger.error(f"发送通知失败: {str(e)}")
        
    def _should_execute_copy_task(self, directory_pairs: List[Dict[str, str]]) -> bool:
        """判断是否需要执行复制任务 - 优化版本"""
        # 检查是否有复制中的媒体文件
        copying_count, _ = self._get_file_status_counts()
        if copying_count > 0:
            logger.info(f"检测到 {copying_count} 个复制中的媒体文件，需要继续执行")
            return True
            
        # 检查源目录是否有新媒体文件需要复制
        logger.info("检查源目录是否有新媒体文件...")
        
        new_media_files = []
        
        for pair in directory_pairs:
            source_dir = pair["source"]
            target_dir = pair["target"]
            
            try:
                # 扫描源目录
                source_files = self._get_openlist_files(source_dir)
                if not source_files:
                    continue
                
                # 扫描目标目录，构建目标媒体文件索引
                target_files = self._get_openlist_files(target_dir)
                target_index = self._build_target_index(target_files, target_dir)
                
                # 检查源目录中是否有新媒体文件
                current_suffixes = self._get_current_suffixes()
                
                for source_file in source_files:
                    filename = source_file.get("name")
                    source_path = source_file.get("path")
                    if not filename or not source_path:
                        continue
                        
                    # 只处理媒体文件
                    if not any(filename.endswith(suffix) for suffix in current_suffixes):
                        continue
                    
                    # 计算相对路径
                    relative_path = self._get_relative_path(source_path, source_dir)
                    
                    # 生成文件唯一标识 - 使用相对路径
                    file_key = self._generate_file_key(relative_path)
                    
                    # 检查媒体文件是否已经在目标目录中存在 - 使用相对路径判断
                    # 或者检查文件状态是否为已完成
                    if relative_path not in target_index:
                        # 检查文件状态，如果状态为已完成，则不视为新媒体文件
                        current_status = self._file_status.get(file_key, self.FILE_STATUS_PENDING)
                        if current_status != self.FILE_STATUS_COMPLETED:
                            new_media_files.append(filename)
                            
            except Exception as e:
                logger.error(f"检查目录配对 {source_dir} → {target_dir} 时出错: {str(e)}")
                # 如果检查过程中出错，保守起见执行复制任务
                return True
        
        if new_media_files:
            # 合并成一条日志信息
            if len(new_media_files) <= 5:
                logger.info(f"发现新媒体文件需要复制: {', '.join(new_media_files)}")
            else:
                logger.info(f"发现 {len(new_media_files)} 个新媒体文件需要复制，前5个: {', '.join(new_media_files[:5])}...")
            return True
        else:
            logger.info("所有源目录媒体文件已在目标目录中存在，无需执行复制任务")
            return False

    def _update_target_files_count(self, directory_pairs: List[Dict[str, str]]):
        """更新目标目录媒体文件数统计"""
        if not directory_pairs:
            self._target_files_count = 0
            self.save_data("openlist_target_files_count", self._target_files_count)
            return
            
        total_target_files = 0
        
        # 获取所有唯一的目标目录 - 使用标准化路径避免重复
        target_dirs = set()
        for pair in directory_pairs:
            # 标准化目标目录路径
            target_dir = self._normalize_path(pair["target"])
            target_dirs.add(target_dir)
        
        logger.info(f"统计 {len(target_dirs)} 个目标目录的媒体文件数")
        
        # 创建一个字典来缓存已经扫描过的目录结果
        scanned_dirs = {}
        
        # 统计每个目标目录的媒体文件数
        for target_dir in target_dirs:
            try:
                # 如果已经扫描过这个目录，直接使用缓存结果
                if target_dir in scanned_dirs:
                    file_count = scanned_dirs[target_dir]
                else:
                    target_files = self._get_openlist_files(target_dir)
                    if target_files:
                        # 只统计媒体文件
                        media_files = [f for f in target_files if self._is_media_file(f.get("name", ""))]
                        file_count = len(media_files)
                        scanned_dirs[target_dir] = file_count  # 缓存结果
                    else:
                        file_count = 0
                        scanned_dirs[target_dir] = file_count  # 缓存结果
                
                total_target_files += file_count
            except Exception as e:
                logger.error(f"统计目标目录 {target_dir} 媒体文件数失败: {str(e)}")
        
        logger.info(f"总计目标目录媒体文件数: {total_target_files}")
        self._target_files_count = total_target_files
        self.save_data("openlist_target_files_count", self._target_files_count)

    def _execute_single_copy(self, source_dir: str, target_dir: str, pair_index: int, total_pairs: int, successfully_copied_files: List[str], global_processed_files: set) -> Optional[Dict[str, int]]:
        """执行单个目录配对复制"""
        try:
            base_progress = int((pair_index) / total_pairs * 100)
            
            # 首先扫描目标目录，构建目标媒体文件索引
            self._update_status(f"正在扫描目标目录: {target_dir}", base_progress + 5)
            target_files = self._get_openlist_files(target_dir)
            target_index = self._build_target_index(target_files, target_dir)
            
            # 然后扫描源目录
            self._update_status(f"正在扫描源目录: {source_dir}", base_progress + 15)
            source_files = self._get_openlist_files(source_dir)
            if not source_files:
                return {"copied": 0, "skipped": 0, "total": 0}
            
            self._update_status(f"开始复制媒体文件: {source_dir} → {target_dir}", base_progress + 25)
            copy_result = self._copy_files(source_files, target_index, source_dir, target_dir, base_progress + 25, 70, successfully_copied_files, global_processed_files)
            
            return copy_result
            
        except Exception as e:
            logger.error(f"处理目录配对 {source_dir} → {target_dir} 时出错: {str(e)}")
            return {"copied": 0, "skipped": 0, "total": 0}

    def _build_target_index(self, target_files: List[dict], base_dir: str = "") -> set:
        """构建目标索引 - 使用相对路径"""
        index = set()
        
        if not target_files:
            return index
            
        current_suffixes = self._get_current_suffixes()
            
        for file in target_files:
            filename = file.get("name")
            file_path = file.get("path")
            if not filename or not file_path:
                continue
                
            if any(filename.endswith(suffix) for suffix in current_suffixes):
                if base_dir:
                    # 使用相对路径作为索引
                    relative_path = self._get_relative_path(file_path, base_dir)
                    index.add(relative_path)
                else:
                    # 向后兼容，使用文件名作为索引
                    index.add(filename)
                
        return index

    def _validate_config(self) -> bool:
        """验证配置是否有效"""
        if not self._openlist_url or not self._openlist_token:
            self._complete_task("failed", "OpenList地址或令牌未配置")
            return False
            
        directory_pairs = self._parse_directory_pairs()
        if not directory_pairs:
            self._complete_task("failed", "未配置有效的目录配对")
            return False
            
        return True

    def _verify_openlist_connection(self) -> bool:
        """验证OpenList连接"""
        try:
            url = f"{self._openlist_url}/api/me"
            headers = {
                "Authorization": self._openlist_token,
                "Content-Type": "application/json"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            return data.get("code") == 200
        except Exception as e:
            logger.error(f"OpenList连接验证失败: {str(e)}")
            return False

    def _get_openlist_files(self, path: str) -> List[dict]:
        """获取OpenList目录文件列表"""
        try:
            url = f"{self._openlist_url}/api/fs/list"
            headers = {
                "authorization": self._openlist_token,
                "content-type": "application/json"
            }
            data = {"path": path, "password": ""}
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") != 200:
                # 对于目标目录为空的情况，不记录错误日志
                if "path not found" in result.get("message", "").lower() or "not exist" in result.get("message", "").lower():
                    return []
                logger.error(f"获取目录 {path} 文件失败: {result.get('message')}")
                return []
                
            data_content = result.get("data", {})
            content = data_content.get("content") if data_content else None
            
            if content is None:
                return []
                
            if not isinstance(content, list):
                logger.error(f"目录 {path} 返回的content不是列表类型: {type(content)}")
                return []
                
            files = []
            
            for item in content:
                if not isinstance(item, dict):
                    continue
                    
                if item.get("is_dir"):
                    sub_path = f"{path.rstrip('/')}/{item.get('name')}"
                    sub_files = self._get_openlist_files(sub_path)
                    files.extend(sub_files)
                else:
                    files.append({
                        "name": item.get("name"),
                        "path": f"{path.rstrip('/')}/{item.get('name')}",
                        "size": item.get("size"),
                        "modified": item.get("modified")
                    })
                    
            return files
            
        except Exception as e:
            logger.error(f"获取文件列表失败: {str(e)}")
            return []

    def _copy_files(self, source_files: List[dict], target_index: set, source_dir: str, target_dir: str, 
                   base_progress: int, progress_range: int, successfully_copied_files: List[str], global_processed_files: set) -> Dict[str, int]:
        """复制文件到目标目录"""
        if not source_files:
            return {"copied": 0, "skipped": 0, "total": 0}
            
        current_suffixes = self._get_current_suffixes()
        
        # 只过滤媒体文件
        media_files = []
        for file in source_files:
            filename = file.get("name")
            if filename and any(filename.endswith(suffix) for suffix in current_suffixes):
                media_files.append(file)
        
        total = len(media_files)
        copied = 0
        skipped = 0
        
        logger.info(f"目录 {source_dir} → {target_dir} 需要处理的媒体文件数量: {total}")
        
        for i, source_file in enumerate(media_files):
            try:
                filename = source_file.get("name")
                if not filename:
                    continue
                    
                source_path = source_file.get("path")
                if not source_path:
                    continue
                
                progress = base_progress + int((i + 1) / total * progress_range)
                
                # 计算相对路径
                relative_path = self._get_relative_path(source_path, source_dir)
                
                # 构建完整的目标路径（保留目录结构）
                target_path = os.path.join(target_dir, relative_path).replace('\\', '/')
                
                # 生成文件唯一标识 - 使用相对路径
                file_key = self._generate_file_key(relative_path)
                
                # 检查1: 媒体文件是否已经在本次任务执行中处理过
                if file_key in global_processed_files:
                    skipped += 1
                    continue
                
                # 检查2: 目标目录是否已存在相同相对路径的文件
                if relative_path in target_index:
                    # 直接将状态更新为已完成并跳过复制操作
                    self._file_status[file_key] = self.FILE_STATUS_COMPLETED
                    self._save_file_status()
                    skipped += 1
                    continue
                
                # 检查3: 检查文件标识当前状态
                current_status = self._file_status.get(file_key, self.FILE_STATUS_PENDING)
                
                if current_status == self.FILE_STATUS_COPYING:
                    # 状态为复制中，跳过该文件复制
                    skipped += 1
                    continue
                
                if current_status == self.FILE_STATUS_COMPLETED:
                    # 状态为已完成，跳过该文件复制
                    skipped += 1
                    continue
                
                # 执行复制操作
                try:
                    # 将状态更新为复制中
                    self._file_status[file_key] = self.FILE_STATUS_COPYING
                    self._save_file_status()
                    
                    if self._execute_openlist_copy_standard(source_path, target_path, filename):
                        copied += 1
                        self._task_status["copied_files"] += 1
                        
                        # 记录成功复制的媒体文件
                        self._copied_files[file_key] = {
                            "source_path": source_path,
                            "target_path": target_path,
                            "filename": filename,
                            "copied_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "status": "completed"
                        }
                        self._save_copied_files()  # 立即保存，避免重复复制
                        
                        # 将状态更新为已完成
                        self._file_status[file_key] = self.FILE_STATUS_COMPLETED
                        self._save_file_status()
                        
                        # 添加到全局已处理媒体文件集合
                        global_processed_files.add(file_key)
                        
                        # 记录成功复制的媒体文件名
                        successfully_copied_files.append(filename)
                        
                        self._update_status(f"创建复制任务: {filename}", progress)
                    else:
                        # 复制失败，将状态更新为复制失败
                        self._file_status[file_key] = self.FILE_STATUS_ERROR
                        self._save_file_status()
                        logger.error(f"复制失败: {filename}")
                except Exception as e:
                    # 处理复制过程中的异常
                    self._file_status[file_key] = self.FILE_STATUS_ERROR
                    self._save_file_status()
                    logger.error(f"复制文件 {filename} 时出错: {str(e)}")
                    
            except Exception as e:
                logger.error(f"处理媒体文件 {source_file.get('name', '未知文件')} 时出错: {str(e)}")
                continue
        
        self._task_status["skipped_files"] += skipped
        self._task_status["total_files"] += total
        self._save_task_status()
        
        # 生成复制成功的汇总日志
        if copied > 0:
            if len(successfully_copied_files) <= 5:
                logger.info(f"复制成功: {', '.join(successfully_copied_files)}")
            else:
                logger.info(f"成功复制 {len(successfully_copied_files)} 个文件，前5个: {', '.join(successfully_copied_files[:5])}...")
                
        return {"copied": copied, "skipped": skipped, "total": total}

    def _get_relative_path(self, file_path: str, base_dir: str) -> str:
        """获取文件相对于基础目录的相对路径"""
        # 确保基础目录以/结尾
        if not base_dir.endswith('/'):
            base_dir += '/'
        
        # 如果文件路径以基础目录开头，则提取相对路径
        if file_path.startswith(base_dir):
            return file_path[len(base_dir):]
        
        # 否则，尝试使用os.path.relpath
        try:
            return os.path.relpath(file_path, base_dir)
        except:
            # 如果失败，返回文件名
            return os.path.basename(file_path)

    def _execute_openlist_copy_standard(self, source_path: str, target_path: str, filename: str) -> bool:
        """使用标准OpenList API复制方式，保留目录结构"""
        try:
            # 提取目标目录（不包含文件名）
            target_dir = os.path.dirname(target_path)
            
            # 确保目标目录存在
            if not self._ensure_directory_exists(target_dir):
                logger.error(f"无法确保目标目录存在: {target_dir}")
                return False
            
            url = f"{self._openlist_url}/api/fs/copy"
            headers = {
                "authorization": self._openlist_token,
                "content-type": "application/json"
            }
            
            # 根据OpenList官方API文档，复制API需要以下参数
            data = {
                "src_dir": os.path.dirname(source_path),
                "dst_dir": target_dir,
                "names": [filename]
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=60)
            
            if response.status_code != 200:
                logger.error(f"复制请求失败，状态码: {response.status_code}")
                if response.status_code == 401:
                    logger.error("权限错误: 可能是OpenList令牌无效或已过期")
                elif response.status_code == 403:
                    logger.error("权限错误: 没有足够的权限执行复制操作")
                elif response.status_code == 404:
                    logger.error("路径错误: 源文件或目标目录不存在")
                elif response.status_code == 500:
                    logger.error("服务器错误: OpenList服务器内部错误")
                elif response.status_code == 507:
                    logger.error("存储错误: 目标目录磁盘空间不足")
                return False
                
            result = response.json()
            
            if result.get("code") == 200:
                return True
            else:
                error_msg = result.get('message', '未知错误')
                error_code = result.get('code', '未知代码')
                logger.error(f"复制失败: 代码={error_code}, 消息={error_msg}")
                if error_code == 401:
                    logger.error("权限错误: 可能是OpenList令牌无效或已过期")
                elif error_code == 403:
                    logger.error("权限错误: 没有足够的权限执行复制操作")
                elif error_code == 404:
                    logger.error("路径错误: 源文件或目标目录不存在")
                elif error_code == 500:
                    logger.error("服务器错误: OpenList服务器内部错误")
                elif error_code == 507:
                    logger.error("存储错误: 目标目录磁盘空间不足")
                return False
                
        except requests.exceptions.Timeout:
            logger.error(f"复制超时: {filename}，请求超过60秒未响应")
            return False
        except requests.exceptions.ConnectionError:
            logger.error(f"连接错误: {filename}，无法连接到OpenList服务器")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"网络错误: {filename}，请求失败: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"复制媒体文件异常: {filename}, 错误: {str(e)}")
            return False

    def _ensure_directory_exists(self, path: str) -> bool:
        """确保目录存在"""
        try:
            url = f"{self._openlist_url}/api/fs/get"
            headers = {
                "authorization": self._openlist_token,
                "content-type": "application/json"
            }
            params = {"path": path}
            
            response = requests.post(url, headers=headers, json=params, timeout=10)
            if response.status_code == 200:
                result = response.json()
                if result.get("code") == 200:
                    return True
            
            # 目录不存在，创建它
            url = f"{self._openlist_url}/api/fs/mkdir"
            data = {"path": path}
            
            response = requests.post(url, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                result = response.json()
                if result.get("code") == 200:
                    return True
                else:
                    logger.warning(f"创建目录失败: {result.get('message')}")
            
            return False
            
        except Exception as e:
            logger.error(f"确保目录存在失败: {path}, 错误: {str(e)}")
            return False

    def _update_status(self, message: str, progress: int = None):
        """更新任务状态"""
        self._task_status["message"] = message
        if progress is not None:
            self._task_status["progress"] = progress
        self._save_task_status()
        
    def _complete_task(self, status: str, message: str):
        """完成任务状态更新"""
        self._task_status.update({
            "status": status,
            "message": message,
            "progress": 100,
            "end_time": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        self._save_task_status()

    def _save_task_status(self):
        """保存任务状态"""
        with self._lock:
            self.save_data("openlist_task_status", self._task_status)
        
    def _save_copied_files(self):
        """保存已复制文件记录"""
        with self._lock:
            self.save_data("openlist_copied_files", self._copied_files)
    
    def _save_file_status(self):
        """保存文件状态"""
        with self._lock:
            self.save_data("openlist_file_status", self._file_status)

    def get_status(self):
        """获取任务状态API"""
        # 只在空闲状态下更新媒体文件状态，避免重复执行
        if self._task_status.get("status") == "idle":
            self._update_file_status_and_counts()
        
        current_suffixes = self._get_current_suffixes()
        directory_pairs = self._parse_directory_pairs()
        copying_count, completed_count = self._get_file_status_counts()
        
        return {
            "success": True,
            "data": {
                **self._task_status,
                "config": {
                    "enabled": self._enable,
                    "openlist_url": self._openlist_url,
                    "openlist_token": self._openlist_token,
                    "directory_pairs": self._directory_pairs,
                    "enable_custom_suffix": self._enablecustomsuffix,
                    "cron": self._cron,
                    "use_moviepilot_config": self._usemoviepilotconfig,
                    "enable_wechat_notify": self._notify,
                    "current_suffixes": current_suffixes,
                    "parsed_pairs": directory_pairs
                },
                "copied_files_count": len(self._copied_files),
                "copying_count": copying_count,
                "completed_count": completed_count,
                "target_files_count": self._target_files_count
            }
        }

    def run_task(self):
        """手动运行任务API"""
        if self._task_status.get("status") == "running":
            return {"success": False, "message": "任务正在运行中，请等待完成"}
        
        self._onlyonce = True
        self._update_config()
        
        import threading
        threading.Thread(target=self.execute_copy_task, daemon=True).start()
        return {"success": True, "message": "复制任务已开始执行"}