from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import requests
import time
import json
import os
import hashlib
import pytz

from app.plugins import _PluginBase
from app.core.config import settings
from app.log import logger
from app.schemas.types import EventType
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter

# 导入通知相关模块
try:
    from app.schemas import Notification, NotificationType, MessageChannel
    from app.helper.notification import NotificationHelper
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
    logger.warning("MoviePilot Alist模块不可用，将使用手动配置")

router = APIRouter()


class AlistCopyPlugin(_PluginBase):
    """
    OpenList自动复制插件 - 通过AList API实现多目录间文件复制
    """
    # 插件基本信息
    plugin_name = "OpenList自动复制"
    plugin_desc = "实现OpenList多目录间文件复制自动化"
    plugin_icon = "Alist_B.png"
    plugin_version = "1.1"
    plugin_author = "LittlePigeno"
    author_url = "https://github.com/LittlePigeno217/MoviePilot-Plugins"
    plugin_config_prefix = "alistcopy_"
    plugin_order = 1
    auth_level = 1

    # 默认视频文件尾缀
    DEFAULT_VIDEO_SUFFIXES = [
        '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', 
        '.m4v', '.3gp', '.ts', '.mts', '.m2ts', '.vob', '.ogv',
        '.mpg', '.mpeg', '.rm', '.rmvb', '.asf', '.divx'
    ]
    
    # 自定义文件尾缀（字幕、元数据、封面图）
    CUSTOM_SUFFIXES = ['.srt', '.ass', '.nfo', '.jpg', '.png']

    # 私有属性
    _enabled: bool = False
    _cron: str = ""
    _onlyonce: bool = False
    _clear_cache: bool = False
    _alist_url: str = ""
    _alist_token: str = ""
    _directory_pairs: str = ""
    _enable_custom_suffix: bool = False
    _use_moviepilot_config: bool = True
    _enable_wechat_notify: bool = False
    _notify_type: str = "default"

    # 任务状态
    _task_status: Dict[str, Any] = {}
    _copied_files: Dict[str, Any] = {}
    _target_files_count: int = 0

    # 调度器
    _scheduler: Optional[BackgroundScheduler] = None

    def init_plugin(self, config: dict = None):
        """
        初始化插件
        """
        # 停止现有服务
        self.stop_service()

        # 读取配置
        if config:
            self._enabled = config.get("enabled", False)
            self._cron = config.get("cron", "")
            self._onlyonce = config.get("onlyonce", False)
            self._clear_cache = config.get("clear_cache", False)
            self._alist_url = config.get("alist_url", "").rstrip('/')
            self._alist_token = config.get("alist_token", "")
            self._directory_pairs = config.get("directory_pairs", "")
            self._enable_custom_suffix = config.get("enable_custom_suffix", False)
            self._use_moviepilot_config = config.get("use_moviepilot_config", True)
            self._enable_wechat_notify = config.get("enable_wechat_notify", False)
            self._notify_type = config.get("notify_type", "default")

        # 如果启用了清除缓存，则清空所有数据
        if self._clear_cache:
            logger.info("检测到清除缓存选项，正在清空插件数据...")
            self._clear_all_data()
            # 重置清除缓存标志
            self._clear_cache = False
            self.__update_config()

        # 恢复任务状态
        saved_status = self.get_data("alistcopy_task_status")
        if saved_status:
            self._task_status = saved_status
        else:
            self._task_status = self._get_default_task_status()

        # 恢复复制记录
        saved_copied_files = self.get_data("alistcopy_copied_files")
        if saved_copied_files:
            self._copied_files = saved_copied_files
        else:
            self._copied_files = {}

        # 恢复目标目录文件数
        saved_target_count = self.get_data("alistcopy_target_files_count")
        if saved_target_count is not None:
            self._target_files_count = saved_target_count
        else:
            self._target_files_count = 0

        # 启动服务
        if self._enabled:
            # 初始化调度器
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)

            # 添加定时任务
            if self._cron:
                try:
                    self._scheduler.add_job(
                        func=self.execute_copy_task,
                        trigger=CronTrigger.from_crontab(self._cron),
                        name="OpenList自动复制任务"
                    )
                    logger.info(f"定时任务已设置：{self._cron}")
                except Exception as err:
                    logger.error(f"定时任务配置错误：{str(err)}")

            # 立即执行一次
            if self._onlyonce:
                logger.info("检测到立即运行一次，开始执行OpenList复制任务")
                self._scheduler.add_job(
                    func=self.execute_copy_task,
                    trigger='date',
                    run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                    name="立即执行OpenList复制"
                )
                # 关闭一次性开关
                self._onlyonce = False
                self.__update_config()

            # 启动任务
            if self._scheduler.get_jobs():
                self._scheduler.print_jobs()
                self._scheduler.start()

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

    def __update_config(self):
        """更新配置"""
        self.update_config({
            "enabled": self._enabled,
            "onlyonce": self._onlyonce,
            "clear_cache": self._clear_cache,
            "cron": self._cron,
            "alist_url": self._alist_url,
            "alist_token": self._alist_token,
            "directory_pairs": self._directory_pairs,
            "enable_custom_suffix": self._enable_custom_suffix,
            "use_moviepilot_config": self._use_moviepilot_config,
            "enable_wechat_notify": self._enable_wechat_notify,
            "notify_type": self._notify_type
        })

    def _clear_all_data(self):
        """清空所有插件数据"""
        # 清空任务状态
        self._task_status = self._get_default_task_status()
        self.save_data("alistcopy_task_status", self._task_status)
        
        # 清空复制记录
        self._copied_files = {}
        self.save_data("alistcopy_copied_files", self._copied_files)
        
        # 清空目标目录文件数
        self._target_files_count = 0
        self.save_data("alistcopy_target_files_count", self._target_files_count)
        
        logger.info("插件数据已全部清空，将重新开始记录")

    def get_state(self) -> bool:
        return self._enabled

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
                "summary": "执行任务"
            }
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        """
        获取定时服务 - 使用系统调度器
        """
        services = []
        if self._enabled and self._cron:
            services.append({
                "id": "AlistCopyTask",
                "name": "OpenList复制任务",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.execute_copy_task,
                "kwargs": {}
            })
        return services

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """获取配置表单"""
        # 检查MoviePilot Alist模块是否可用
        alist_available = ALIST_AVAILABLE
        
        # 通知类型选项
        notify_type_options = [
            {"title": "默认样式", "value": "default"},
            {"title": "卡片样式", "value": "card"}
        ]
        
        return [
            {
                "component": "VForm",
                "content": [
                    # 基本设置卡片
                    {
                        "component": "VCard",
                        "props": {"variant": "outlined", "class": "mb-4"},
                        "content": [
                            {
                                "component": "VCardText",
                                "content": [
                                    {
                                        'component': 'VRow',
                                        'content': [
                                            {
                                                'component': 'VCol',
                                                'props': {'cols': 12, 'md': 3},
                                                'content': [
                                                    {
                                                        'component': 'VSwitch',
                                                        'props': {
                                                            'model': 'enabled',
                                                            'label': '启用插件',
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                'component': 'VCol',
                                                'props': {'cols': 12, 'md': 3},
                                                'content': [
                                                    {
                                                        'component': 'VSwitch',
                                                        'props': {
                                                            'model': 'onlyonce',
                                                            'label': '立即运行一次',
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                'component': 'VCol',
                                                'props': {'cols': 12, 'md': 3},
                                                'content': [
                                                    {
                                                        'component': 'VSwitch',
                                                        'props': {
                                                            'model': 'clear_cache',
                                                            'label': '清除缓存',
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                'component': 'VCol',
                                                'props': {'cols': 12, 'md': 3},
                                                'content': [
                                                    {
                                                        'component': 'VSwitch',
                                                        'props': {
                                                            'model': 'enable_wechat_notify',
                                                            'label': '微信通知',
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        'component': 'VRow',
                                        'content': [
                                            {
                                                'component': 'VCol',
                                                'props': {'cols': 12, 'md': 4},
                                                'content': [
                                                    {
                                                        'component': 'VTextField',
                                                        'props': {
                                                            'model': 'cron',
                                                            'label': '执行周期',
                                                            'placeholder': '0 2 * * *'
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                'component': 'VCol',
                                                'props': {'cols': 12, 'md': 4},
                                                'content': [
                                                    {
                                                        'component': 'VSelect',
                                                        'props': {
                                                            'model': 'notify_type',
                                                            'label': '通知样式',
                                                            'items': notify_type_options
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                'component': 'VCol',
                                                'props': {'cols': 12, 'md': 4},
                                                'content': [
                                                    {
                                                        'component': 'VSwitch',
                                                        'props': {
                                                            'model': 'enable_custom_suffix',
                                                            'label': '复制字幕元数据',
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        'component': 'VRow',
                                        'content': [
                                            {
                                                'component': 'VCol',
                                                'props': {'cols': 12, 'md': 6},
                                                'content': [
                                                    {
                                                        'component': 'VSwitch',
                                                        'props': {
                                                            'model': 'use_moviepilot_config',
                                                            'label': '使用MoviePilot配置',
                                                            'disabled': not alist_available
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
                    
                    # 连接设置和目录配对（并排显示）
                    {
                        "component": "VRow",
                        "content": [
                            # Alist/OpenList连接设置
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VCard",
                                        "props": {"variant": "outlined", "class": "mb-4", "height": "100%"},
                                        "content": [
                                            {
                                                "component": "VCardText",
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "d-flex align-center mb-4"},
                                                        "content": [
                                                            {
                                                                "component": "VIcon",
                                                                "props": {"icon": "mdi-server-network", "color": "primary", "class": "mr-2"},
                                                                "text": ""
                                                            },
                                                            {
                                                                "component": "span",
                                                                "props": {"class": "text-h6"},
                                                                "text": "AList/OpenList连接设置"
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
                                                                        "component": "VTextField",
                                                                        "props": {
                                                                            "model": "alist_url",
                                                                            "label": "服务地址",
                                                                            "placeholder": "http://localhost:5244",
                                                                            "disabled": self._use_moviepilot_config and alist_available
                                                                        }
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
                                                                        "component": "VTextField",
                                                                        "props": {
                                                                            "model": "alist_token",
                                                                            "label": "访问令牌",
                                                                            "type": "password",
                                                                            "placeholder": "在AList后台获取",
                                                                            "disabled": self._use_moviepilot_config and alist_available
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
                            },
                            # 目录配对设置
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VCard",
                                        "props": {"variant": "outlined", "class": "mb-4", "height": "100%"},
                                        "content": [
                                            {
                                                "component": "VCardText",
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "d-flex align-center mb-4"},
                                                        "content": [
                                                            {
                                                                "component": "VIcon",
                                                                "props": {"icon": "mdi-folder-multiple", "color": "primary", "class": "mr-2"},
                                                                "text": ""
                                                            },
                                                            {
                                                                "component": "span",
                                                                "props": {"class": "text-h6"},
                                                                "text": "目录配对设置"
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
                                                                            "rows": 8,
                                                                            "hint": "每行一组配对，使用#分隔源目录和目标目录"
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
                        ]
                    },
                    
                    # 说明信息
                    {
                        "component": "VCard",
                        "props": {"variant": "outlined", "class": "mb-4"},
                        "content": [
                            {
                                "component": "VCardText",
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "text": True,
                                            "variant": "tonal"
                                        },
                                        "content": [
                                            {
                                                "component": "div",
                                                "props": {"class": "font-weight-bold mb-2"},
                                                "text": "文件尾缀说明："
                                            },
                                            {
                                                "component": "div", 
                                                "text": "• 默认：自动匹配常用视频格式（mp4, mkv, avi, mov等）"
                                            },
                                            {
                                                "component": "div",
                                                "text": "• 勾选复制字幕元数据：额外匹配字幕(.srt,.ass)、元数据(.nfo)、封面图(.jpg,.png)"
                                            }
                                        ]
                                    },
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "warning",
                                            "text": True,
                                            "variant": "tonal",
                                            "class": "mt-3"
                                        },
                                        "content": [
                                            {
                                                "component": "div",
                                                "props": {"class": "font-weight-bold mb-2"},
                                                "text": "清除缓存说明："
                                            },
                                            {
                                                "component": "div",
                                                "text": "• 勾选此选项后保存，将清空所有复制记录和任务状态"
                                            },
                                            {
                                                "component": "div",
                                                "text": "• 插件将重新开始记录复制历史"
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
            "enabled": self._enabled,
            "onlyonce": self._onlyonce,
            "clear_cache": self._clear_cache,
            "alist_url": self._alist_url,
            "alist_token": self._alist_token,
            "directory_pairs": self._directory_pairs,
            "enable_custom_suffix": self._enable_custom_suffix,
            "use_moviepilot_config": self._use_moviepilot_config,
            "enable_wechat_notify": self._enable_wechat_notify,
            "notify_type": self._notify_type,
            "cron": self._cron or "0 2 * * *"
        }

    def get_page(self) -> List[dict]:
        """获取插件页面"""
        # 获取状态信息
        status = self._task_status
        status_config = {
            "idle": {"color": "info", "text": "空闲", "icon": "mdi-play-circle-outline"},
            "running": {"color": "warning", "text": "运行中", "icon": "mdi-sync"},
            "success": {"color": "success", "text": "成功", "icon": "mdi-check-circle"},
            "failed": {"color": "error", "text": "失败", "icon": "mdi-alert-circle"}
        }
        config = status_config.get(status.get("status", "idle"), status_config["idle"])
        
        # 获取状态统计
        copying_count, completed_count = self._get_file_status_counts()
        
        # 获取最近完成的媒体文件
        recent_media_files = self._get_recent_media_files(50)
        copying_media_files = self._get_copying_media_files(50)
        
        return [
            {
                "component": "VCard",
                "content": [
                    {
                        "component": "VCardText",
                        "content": [
                            # 统计标题
                            {
                                "component": "div",
                                "props": {"class": "d-flex align-center mb-4"},
                                "content": [
                                    {
                                        "component": "VIcon",
                                        "props": {"icon": "mdi-chart-box", "color": "primary", "size": "large"},
                                        "text": ""
                                    },
                                    {
                                        "component": "span", 
                                        "props": {"class": "ml-2 text-h5"},
                                        "text": "OpenList媒体复制统计"
                                    }
                                ]
                            },
                            
                            # 统计卡片
                            {
                                "component": "VRow",
                                "content": [
                                    # 目标目录媒体文件数
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 12, "md": 4},
                                        "content": [
                                            {
                                                "component": "VCard",
                                                "props": {"color": "primary", "variant": "tonal", "height": "100%"},
                                                "content": [
                                                    {
                                                        "component": "VCardText",
                                                        "props": {"class": "text-center"},
                                                        "content": [
                                                            {
                                                                "component": "VIcon",
                                                                "props": {"icon": "mdi-folder-open", "size": "large", "color": "primary"},
                                                                "text": ""
                                                            },
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "text-h6 font-weight-bold mt-2"},
                                                                "text": "目标目录媒体文件数"
                                                            },
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "text-h4 font-weight-bold text-primary mt-2"},
                                                                "text": str(self._target_files_count)
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    # 当前复制媒体文件数量
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 12, "md": 4},
                                        "content": [
                                            {
                                                "component": "VCard",
                                                "props": {"color": "warning", "variant": "tonal", "height": "100%"},
                                                "content": [
                                                    {
                                                        "component": "VCardText",
                                                        "props": {"class": "text-center"},
                                                        "content": [
                                                            {
                                                                "component": "VIcon",
                                                                "props": {"icon": "mdi-progress-clock", "size": "large", "color": "warning"},
                                                                "text": ""
                                                            },
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "text-h6 font-weight-bold mt-2"},
                                                                "text": "当前复制媒体文件数量"
                                                            },
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "text-h4 font-weight-bold text-warning mt-2"},
                                                                "text": str(copying_count)
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    # 累计复制媒体文件数量
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 12, "md": 4},
                                        "content": [
                                            {
                                                "component": "VCard",
                                                "props": {"color": "info", "variant": "tonal", "height": "100%"},
                                                "content": [
                                                    {
                                                        "component": "VCardText",
                                                        "props": {"class": "text-center"},
                                                        "content": [
                                                            {
                                                                "component": "VIcon",
                                                                "props": {"icon": "mdi-history", "size": "large", "color": "info"},
                                                                "text": ""
                                                            },
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "text-h6 font-weight-bold mt-2"},
                                                                "text": "累计复制媒体文件数量"
                                                            },
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "text-h4 font-weight-bold text-info mt-2"},
                                                                "text": str(completed_count)
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            },
                            
                            # 正在复制的媒体文件
                            {
                                "component": "VRow",
                                "props": {"class": "mt-4"},
                                "content": [
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 12},
                                        "content": [
                                            {
                                                "component": "VCard",
                                                "props": {"color": "orange", "variant": "tonal"},
                                                "content": [
                                                    {
                                                        "component": "VCardText",
                                                        "content": [
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "d-flex align-center mb-3"},
                                                                "content": [
                                                                    {
                                                                        "component": "VIcon",
                                                                        "props": {"icon": "mdi-progress-upload", "color": "orange", "class": "mr-2"},
                                                                        "text": ""
                                                                    },
                                                                    {
                                                                        "component": "span",
                                                                        "props": {"class": "text-h6"},
                                                                        "text": f"正在复制的媒体文件（共{len(copying_media_files)}个）"
                                                                    }
                                                                ]
                                                            },
                                                            {
                                                                "component": "div",
                                                                "content": self._render_copying_media_files(copying_media_files)
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            },
                            
                            # 最近完成的媒体文件
                            {
                                "component": "VRow",
                                "props": {"class": "mt-4"},
                                "content": [
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 12},
                                        "content": [
                                            {
                                                "component": "VCard",
                                                "props": {"color": "deep-purple", "variant": "tonal"},
                                                "content": [
                                                    {
                                                        "component": "VCardText",
                                                        "content": [
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "d-flex align-center mb-3"},
                                                                "content": [
                                                                    {
                                                                        "component": "VIcon",
                                                                        "props": {"icon": "mdi-file-multiple", "color": "deep-purple", "class": "mr-2"},
                                                                        "text": ""
                                                                    },
                                                                    {
                                                                        "component": "span",
                                                                        "props": {"class": "text-h6"},
                                                                        "text": f"最近完成的媒体文件（共{len(recent_media_files)}个）"
                                                                    }
                                                                ]
                                                            },
                                                            {
                                                                "component": "div",
                                                                "content": self._render_recent_media_files(recent_media_files)
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            },
                            
                            # 任务状态
                            {
                                "component": "VRow",
                                "props": {"class": "mt-4"},
                                "content": [
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 12},
                                        "content": [
                                            {
                                                "component": "VAlert",
                                                "props": {
                                                    "type": config["color"],
                                                    "text": True,
                                                    "variant": "tonal"
                                                },
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "d-flex align-center"},
                                                        "content": [
                                                            {
                                                                "component": "VIcon",
                                                                "props": {"icon": config["icon"], "color": config["color"], "class": "mr-2"},
                                                                "text": ""
                                                            },
                                                            {
                                                                "component": "strong",
                                                                "text": f"当前状态: {config['text']}"
                                                            }
                                                        ]
                                                    },
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "mt-2"},
                                                        "text": status.get("message", "等待任务开始...")
                                                    },
                                                    {
                                                        "component": "VProgressLinear",
                                                        "props": {
                                                            "model-value": status.get("progress", 0),
                                                            "color": config["color"],
                                                            "height": "8",
                                                            "class": "mt-2"
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
        ]

    def execute_copy_task(self):
        """执行复制任务"""
        logger.info("开始执行OpenList多目录复制任务")
        
        # 验证配置
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
        
        # 任务执行前先更新媒体文件状态
        self._update_file_status_and_counts(silent=True)
        
        # 检查是否需要执行复制任务
        copying_count, completed_count = self._get_file_status_counts()
        if not self._should_execute_copy_task(directory_pairs, copying_count):
            logger.info("无需执行复制任务，所有媒体文件已处理完成")
            self._update_target_files_count(directory_pairs)
            self._complete_task("success", "无需执行复制任务，所有媒体文件已处理完成")
            return
            
        # 执行复制任务
        successfully_copied_files = []
        global_processed_files = set()
            
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
            if not self._verify_alist_connection():
                raise Exception("AList连接失败，请检查地址和令牌")
            
            total_copied = 0
            total_skipped = 0
            total_files = 0
            
            for i, pair in enumerate(directory_pairs):
                source_dir = pair["source"]
                target_dir = pair["target"]
                
                self._task_status["current_pair"] = f"{source_dir} → {target_dir}"
                self._update_status(f"正在处理第 {i+1}/{len(directory_pairs)} 组目录配对: {source_dir} → {target_dir}", 
                                  int((i) / len(directory_pairs) * 100))
                
                pair_result = self._execute_single_copy(source_dir, target_dir, i, len(directory_pairs), 
                                                      successfully_copied_files, global_processed_files)
                if pair_result:
                    total_copied += pair_result["copied"]
                    total_skipped += pair_result["skipped"]
                    total_files += pair_result["total"]
                
                self._task_status["completed_pairs"] = i + 1
                self._save_task_status()
            
            # 任务完成后更新媒体文件状态
            self._update_file_status_and_counts(silent=False)
            
            # 发送通知
            if self._enable_wechat_notify and successfully_copied_files:
                self._send_wechat_notification(total_copied, successfully_copied_files)
            
            self._complete_task("success", 
                               f"复制完成！共处理 {len(directory_pairs)} 组目录配对，"
                               f"总计 {total_files} 个媒体文件，"
                               f"复制 {total_copied} 个，"
                               f"跳过 {total_skipped} 个")
                               
        except Exception as e:
            logger.error(f"复制任务执行失败: {str(e)}")
            self._complete_task("failed", f"任务执行失败: {str(e)}")
        finally:
            # 更新目标目录媒体文件数
            self._update_target_files_count(directory_pairs)

    # 以下为辅助方法，保持原有逻辑不变
    def _parse_directory_pairs(self) -> List[Dict[str, str]]:
        """解析目录配对"""
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

    def _get_current_suffixes(self) -> List[str]:
        """获取当前文件尾缀列表"""
        all_suffixes = self.DEFAULT_VIDEO_SUFFIXES.copy()
        
        if self._enable_custom_suffix:
            for suffix in self.CUSTOM_SUFFIXES:
                if suffix not in all_suffixes:
                    all_suffixes.append(suffix)
        
        return all_suffixes

    def _validate_config(self) -> bool:
        """验证配置"""
        if not self._alist_url or not self._alist_token:
            self._complete_task("failed", "AList地址或令牌未配置")
            return False
            
        directory_pairs = self._parse_directory_pairs()
        if not directory_pairs:
            self._complete_task("failed", "未配置有效的目录配对")
            return False
            
        return True

    def _verify_alist_connection(self) -> bool:
        """验证AList连接"""
        try:
            url = f"{self._alist_url}/api/me"
            headers = {
                "Authorization": self._alist_token,
                "Content-Type": "application/json"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            return data.get("code") == 200
        except Exception as e:
            logger.error(f"AList连接验证失败: {str(e)}")
            return False

    def _should_execute_copy_task(self, directory_pairs: List[Dict[str, str]], copying_count: int) -> bool:
        """判断是否需要执行复制任务"""
        if copying_count > 0:
            return True
            
        logger.info("检查源目录是否有新媒体文件需要复制...")
        
        for pair in directory_pairs:
            source_dir = pair["source"]
            target_dir = pair["target"]
            
            try:
                source_files = self._get_alist_files(source_dir)
                if not source_files:
                    continue
                
                target_files = self._get_alist_files(target_dir)
                target_index = self._build_target_index(target_files)
                
                current_suffixes = self._get_current_suffixes()
                
                for source_file in source_files:
                    filename = source_file.get("name")
                    if not filename:
                        continue
                        
                    if not any(filename.endswith(suffix) for suffix in current_suffixes):
                        continue
                    
                    if filename not in target_index:
                        logger.info(f"发现新媒体文件需要复制: {filename}")
                        return True
                        
            except Exception as e:
                logger.error(f"检查目录配对 {source_dir} → {target_dir} 时出错: {str(e)}")
                return True
        
        logger.info("所有源目录媒体文件已在目标目录中存在，无需执行复制任务")
        return False

    def _execute_single_copy(self, source_dir: str, target_dir: str, pair_index: int, total_pairs: int, 
                           successfully_copied_files: List[str], global_processed_files: set) -> Optional[Dict[str, int]]:
        """执行单个目录配对复制"""
        try:
            base_progress = int((pair_index) / total_pairs * 100)
            
            self._update_status(f"正在扫描目标目录: {target_dir}", base_progress + 5)
            target_files = self._get_alist_files(target_dir)
            target_index = self._build_target_index(target_files)
            
            self._update_status(f"正在扫描源目录: {source_dir}", base_progress + 15)
            source_files = self._get_alist_files(source_dir)
            if not source_files:
                return {"copied": 0, "skipped": 0, "total": 0}
            
            self._update_status(f"开始复制媒体文件: {source_dir} → {target_dir}", base_progress + 25)
            copy_result = self._copy_files(source_files, target_index, source_dir, target_dir, 
                                         base_progress + 25, 70, successfully_copied_files, global_processed_files)
            
            return copy_result
            
        except Exception as e:
            logger.error(f"处理目录配对 {source_dir} → {target_dir} 时出错: {str(e)}")
            return {"copied": 0, "skipped": 0, "total": 0}

    def _get_alist_files(self, path: str) -> List[dict]:
        """获取AList文件列表"""
        try:
            url = f"{self._alist_url}/api/fs/list"
            headers = {
                "Authorization": self._alist_token,
                "Content-Type": "application/json"
            }
            data = {"path": path, "password": ""}
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") != 200:
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
                    sub_files = self._get_alist_files(sub_path)
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

    def _build_target_index(self, target_files: List[dict]) -> set:
        """构建目标索引"""
        index = set()
        
        if not target_files:
            return index
            
        current_suffixes = self._get_current_suffixes()
            
        for file in target_files:
            filename = file.get("name")
            if not filename:
                continue
                
            if any(filename.endswith(suffix) for suffix in current_suffixes):
                index.add(filename)
                
        return index

    def _copy_files(self, source_files: List[dict], target_index: set, source_dir: str, target_dir: str, 
                   base_progress: int, progress_range: int, successfully_copied_files: List[str], global_processed_files: set) -> Dict[str, int]:
        """复制文件"""
        if not source_files:
            logger.warning("源文件列表为空，跳过复制")
            return {"copied": 0, "skipped": 0, "total": 0}
            
        current_suffixes = self._get_current_suffixes()
        
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
                
                relative_path = self._get_relative_path(source_path, source_dir)
                target_path = os.path.join(target_dir, relative_path).replace('\\', '/')
                file_key = self._generate_file_key(source_path, target_path)
                
                if file_key in global_processed_files:
                    skipped += 1
                    logger.debug(f"跳过本次任务已处理媒体文件: {filename}")
                    self._update_status(f"跳过已处理媒体文件: {filename}", progress)
                    continue
                
                if file_key in self._copied_files:
                    record_info = self._copied_files[file_key]
                    record_status = record_info.get("status", "copying")
                    
                    if record_status == "completed":
                        skipped += 1
                        completed_time = record_info.get("completed_time", "未知时间")
                        logger.debug(f"跳过已完成媒体文件: {filename} (完成于: {completed_time})")
                        self._update_status(f"跳过已完成媒体文件: {filename}", progress)
                        continue
                    else:
                        skipped += 1
                        copied_time = record_info.get("copied_time", "未知时间")
                        logger.debug(f"跳过复制中媒体文件: {filename} (记录于: {copied_time})")
                        self._update_status(f"跳过复制中媒体文件: {filename}", progress)
                        continue
                
                if filename in target_index:
                    skipped += 1
                    logger.debug(f"跳过目标目录已存在媒体文件: {filename}")
                    self._update_status(f"跳过目标目录已存在媒体文件: {filename}", progress)
                    continue
                    
                if self._execute_alist_copy_standard(source_path, target_path, filename):
                    copied += 1
                    self._task_status["copied_files"] += 1
                    
                    self._copied_files[file_key] = {
                        "source_path": source_path,
                        "target_path": target_path,
                        "filename": filename,
                        "copied_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "status": "copying"
                    }
                    self._save_copied_files()
                    
                    global_processed_files.add(file_key)
                    successfully_copied_files.append(filename)
                    
                    self._update_status(f"创建复制任务: {filename}", progress)
                else:
                    logger.error(f"复制失败: {filename}")
                    
            except Exception as e:
                logger.error(f"处理媒体文件 {source_file.get('name', '未知文件')} 时出错: {str(e)}")
                continue
        
        self._task_status["skipped_files"] += skipped
        self._task_status["total_files"] += total
        self._save_task_status()
                
        return {"copied": copied, "skipped": skipped, "total": total}

    def _get_relative_path(self, file_path: str, base_dir: str) -> str:
        """获取相对路径"""
        if not base_dir.endswith('/'):
            base_dir += '/'
        
        if file_path.startswith(base_dir):
            return file_path[len(base_dir):]
        
        try:
            return os.path.relpath(file_path, base_dir)
        except:
            return os.path.basename(file_path)

    def _generate_file_key(self, source_path: str, target_path: str) -> str:
        """生成文件唯一标识"""
        key_string = f"{source_path}->{target_path}"
        return hashlib.md5(key_string.encode()).hexdigest()

    def _execute_alist_copy_standard(self, source_path: str, target_path: str, filename: str) -> bool:
        """执行AList复制"""
        try:
            target_dir = os.path.dirname(target_path)
            
            if not self._ensure_directory_exists(target_dir):
                logger.error(f"无法确保目标目录存在: {target_dir}")
                return False
            
            url = f"{self._alist_url}/api/fs/copy"
            headers = {
                "Authorization": self._alist_token,
                "Content-Type": "application/json"
            }
            
            data = {
                "src_dir": os.path.dirname(source_path),
                "dst_dir": target_dir,
                "names": [filename]
            }
            
            logger.debug(f"复制参数: {data}")
            response = requests.post(url, headers=headers, json=data, timeout=60)
            
            if response.status_code != 200:
                logger.error(f"复制请求失败，状态码: {response.status_code}")
                return False
                
            result = response.json()
            
            if result.get("code") == 200:
                logger.info(f"复制成功: {filename} -> {target_path}")
                return True
            else:
                error_msg = result.get('message', '未知错误')
                logger.error(f"复制失败: {error_msg}")
                return False
                
        except Exception as e:
            logger.error(f"复制媒体文件异常: {filename}, 错误: {str(e)}")
            return False

    def _ensure_directory_exists(self, path: str) -> bool:
        """确保目录存在"""
        try:
            url = f"{self._alist_url}/api/fs/get"
            headers = {
                "Authorization": self._alist_token,
                "Content-Type": "application/json"
            }
            params = {"path": path}
            
            response = requests.post(url, headers=headers, json=params, timeout=10)
            if response.status_code == 200:
                result = response.json()
                if result.get("code") == 200:
                    return True
            
            url = f"{self._alist_url}/api/fs/mkdir"
            data = {"path": path}
            
            response = requests.post(url, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                result = response.json()
                if result.get("code") == 200:
                    logger.info(f"创建目录成功: {path}")
                    return True
                else:
                    logger.warning(f"创建目录失败: {result.get('message')}")
            
            return False
            
        except Exception as e:
            logger.error(f"确保目录存在失败: {path}, 错误: {str(e)}")
            return False

    def _update_target_files_count(self, directory_pairs: List[Dict[str, str]]):
        """更新目标目录媒体文件数统计"""
        if not directory_pairs:
            self._target_files_count = 0
            self.save_data("alistcopy_target_files_count", self._target_files_count)
            return
            
        total_target_files = 0
        target_dirs = set()
        
        for pair in directory_pairs:
            target_dir = self._normalize_path(pair["target"])
            target_dirs.add(target_dir)
        
        logger.info(f"开始统计 {len(target_dirs)} 个唯一目标目录的媒体文件数")
        
        scanned_dirs = {}
        
        for target_dir in target_dirs:
            try:
                if target_dir in scanned_dirs:
                    file_count = scanned_dirs[target_dir]
                    logger.info(f"使用缓存结果: 目标目录 {target_dir} 有 {file_count} 个媒体文件")
                else:
                    logger.info(f"正在统计目标目录媒体文件数: {target_dir}")
                    target_files = self._get_alist_files(target_dir)
                    if target_files:
                        media_files = [f for f in target_files if self._is_media_file(f.get("name", ""))]
                        file_count = len(media_files)
                        scanned_dirs[target_dir] = file_count
                        logger.info(f"目标目录 {target_dir} 有 {file_count} 个媒体文件")
                    else:
                        file_count = 0
                        scanned_dirs[target_dir] = file_count
                        logger.info(f"目标目录 {target_dir} 为空或无法访问")
                
                total_target_files += file_count
            except Exception as e:
                logger.error(f"统计目标目录 {target_dir} 媒体文件数失败: {str(e)}")
        
        logger.info(f"总计目标目录媒体文件数: {total_target_files}")
        self._target_files_count = total_target_files
        self.save_data("alistcopy_target_files_count", self._target_files_count)

    def _normalize_path(self, path: str) -> str:
        """标准化路径"""
        return path.rstrip('/')

    def _is_media_file(self, filename: str) -> bool:
        """判断文件是否为媒体文件"""
        current_suffixes = self._get_current_suffixes()
        return any(filename.endswith(suffix) for suffix in current_suffixes)

    def _update_file_status_and_counts(self, silent: bool = False):
        """更新媒体文件状态和数量统计"""
        if not self._copied_files:
            return
            
        directory_pairs = self._parse_directory_pairs()
        if not directory_pairs:
            return
            
        if not silent:
            logger.info("正在更新媒体文件状态和数量统计...")
        
        target_dirs_index = {}
        for pair in directory_pairs:
            target_dir = self._normalize_path(pair["target"])
            if target_dir not in target_dirs_index:
                if not silent:
                    logger.info(f"扫描目标目录以更新媒体文件状态: {target_dir}")
                target_files = self._get_alist_files(target_dir)
                if target_files:
                    file_index = {}
                    for file in target_files:
                        filename = file.get("name")
                        if filename and self._is_media_file(filename):
                            file_index[filename] = file.get("path", "")
                    target_dirs_index[target_dir] = file_index
                    if not silent:
                        logger.info(f"目标目录 {target_dir} 有 {len(file_index)} 个媒体文件")
                else:
                    target_dirs_index[target_dir] = {}
                    if not silent:
                        logger.info(f"目标目录 {target_dir} 为空")
        
        updated_count = 0
        for file_key, record in self._copied_files.items():
            target_path = record.get("target_path", "")
            filename = record.get("filename", "")
            current_status = record.get("status", "copying")
            
            if not target_path or not filename:
                continue
                
            target_dir = None
            for pair in directory_pairs:
                normalized_target = self._normalize_path(pair["target"])
                if self._normalize_path(target_path).startswith(normalized_target):
                    target_dir = normalized_target
                    break
            
            if not target_dir:
                continue
                
            if target_dir in target_dirs_index and filename in target_dirs_index[target_dir]:
                if current_status != "completed":
                    self._copied_files[file_key]["status"] = "completed"
                    self._copied_files[file_key]["completed_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    updated_count += 1
        
        if updated_count > 0 and not silent:
            logger.info(f"已更新 {updated_count} 个媒体文件的状态")

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
        """获取最近完成的媒体文件列表"""
        completed_files = []
        
        for record in self._copied_files.values():
            if record.get("status") == "completed":
                completed_files.append(record)
        
        completed_files.sort(key=lambda x: x.get("completed_time", ""), reverse=True)
        return completed_files[:count]

    def _get_copying_media_files(self, count: int = 50) -> List[Dict]:
        """获取正在复制的媒体文件列表"""
        copying_files = []
        
        for record in self._copied_files.values():
            if record.get("status") == "copying":
                copying_files.append(record)
        
        copying_files.sort(key=lambda x: x.get("copied_time", ""), reverse=True)
        return copying_files[:count]

    def _render_recent_media_files(self, media_files: List[Dict]) -> List[Dict]:
        """渲染最近完成的媒体文件列表"""
        if not media_files:
            return [
                {
                    "component": "div",
                    "props": {"class": "text-center text-grey py-4"},
                    "text": "暂无完成的媒体文件记录"
                }
            ]
        
        content = []
        
        for i, media_file in enumerate(media_files):
            filename = media_file.get("filename", "未知文件")
            completed_time = media_file.get("completed_time", "未知时间")
            
            content.append({
                "component": "div",
                "props": {"class": "d-flex align-center justify-space-between mb-2 py-1", "style": "border-bottom: 1px solid #eee;"},
                "content": [
                    {
                        "component": "div",
                        "props": {"class": "d-flex align-center", "style": "flex: 1;"},
                        "content": [
                            {
                                "component": "VIcon",
                                "props": {"icon": "mdi-file", "size": "small", "class": "mr-2 text-grey"},
                                "text": ""
                            },
                            {
                                "component": "span",
                                "props": {"class": "text-caption text-truncate"},
                                "text": filename
                            }
                        ]
                    },
                    {
                        "component": "span",
                        "props": {"class": "text-caption text-grey ml-2"},
                        "text": completed_time
                    }
                ]
            })
        
        return content

    def _render_copying_media_files(self, media_files: List[Dict]) -> List[Dict]:
        """渲染正在复制的媒体文件列表"""
        if not media_files:
            return [
                {
                    "component": "div",
                    "props": {"class": "text-center text-grey py-4"},
                    "text": "暂无正在复制的媒体文件"
                }
            ]
        
        content = []
        
        for i, media_file in enumerate(media_files):
            filename = media_file.get("filename", "未知文件")
            copied_time = media_file.get("copied_time", "未知时间")
            
            content.append({
                "component": "div",
                "props": {"class": "d-flex align-center justify-space-between mb-2 py-1", "style": "border-bottom: 1px solid #eee;"},
                "content": [
                    {
                        "component": "div",
                        "props": {"class": "d-flex align-center", "style": "flex: 1;"},
                        "content": [
                            {
                                "component": "VIcon",
                                "props": {"icon": "mdi-progress-upload", "size": "small", "class": "mr-2 text-orange"},
                                "text": ""
                            },
                            {
                                "component": "span",
                                "props": {"class": "text-caption text-truncate"},
                                "text": filename
                            }
                        ]
                    },
                    {
                        "component": "span",
                        "props": {"class": "text-caption text-grey ml-2"},
                        "text": copied_time
                    }
                ]
            })
        
        return content

    def _send_wechat_notification(self, total_copied: int, successfully_copied_files: List[str]):
        """发送企业微信通知"""
        try:
            title = "🎬 OpenList复制任务完成"
            
            file_list_text = ""
            if len(successfully_copied_files) <= 10:
                file_list_text = "\n".join([f"• {filename}" for filename in successfully_copied_files])
            else:
                file_list_text = "\n".join([f"• {filename}" for filename in successfully_copied_files[:10]])
                file_list_text += f"\n• ...等 {len(successfully_copied_files)} 个文件"
            
            message = f"**本次运行复制任务统计**\n\n" \
                    f"📊 建立复制任务：{total_copied} 个\n" \
                    f"✅ 完成复制任务：{total_copied} 个\n\n" \
                    f"**本次复制文件列表：**\n{file_list_text}"
            
            # 使用新的通知方式
            if NOTIFICATION_AVAILABLE:
                if self._notify_type == "card":
                    # 创建卡片通知 - 使用正确的参数
                    try:
                        # 方法1: 使用Notification对象
                        notification = Notification(
                            mtype=NotificationType.Manual,
                            title=title,
                            text=message
                            # 移除 image 和 channel 参数，因为它们可能不是必需的
                        )
                        self.post_message(notification)
                    except Exception as e:
                        logger.warning(f"卡片通知发送失败，尝试简化方式: {str(e)}")
                        # 方法2: 简化方式
                        self.post_message(
                            title=title,
                            text=message,
                            mtype=NotificationType.Manual
                        )
                else:
                    # 默认通知方式
                    self.post_message(
                        title=title,
                        text=message,
                        mtype=NotificationType.Manual
                    )
            else:
                # 使用基础通知方式
                self.post_message(
                    title=title,
                    text=message
                )
            
            logger.info("企业微信通知发送成功")
            
        except Exception as e:
            logger.error(f"发送企业微信通知失败: {str(e)}")

    def _update_status(self, message: str, progress: int = None):
        """更新任务状态"""
        self._task_status["message"] = message
        if progress is not None:
            self._task_status["progress"] = progress
        self._save_task_status()
        
    def _complete_task(self, status: str, message: str):
        """完成任务"""
        self._task_status.update({
            "status": status,
            "message": message,
            "progress": 100,
            "end_time": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        self._save_task_status()

    def _save_task_status(self):
        """保存任务状态"""
        self.save_data("alistcopy_task_status", self._task_status)
        
    def _save_copied_files(self):
        """保存复制文件记录"""
        self.save_data("alistcopy_copied_files", self._copied_files)

    def get_status(self):
        """获取任务状态API"""
        self._update_file_status_and_counts()
        
        current_suffixes = self._get_current_suffixes()
        directory_pairs = self._parse_directory_pairs()
        copying_count, completed_count = self._get_file_status_counts()
        
        return {
            "success": True,
            "data": {
                **self._task_status,
                "config": {
                    "enabled": self._enabled,
                    "alist_url": self._alist_url,
                    "alist_token": self._alist_token,
                    "directory_pairs": self._directory_pairs,
                    "enable_custom_suffix": self._enable_custom_suffix,
                    "cron": self._cron,
                    "use_moviepilot_config": self._use_moviepilot_config,
                    "enable_wechat_notify": self._enable_wechat_notify,
                    "notify_type": self._notify_type,
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
        """运行任务API"""
        if self._task_status.get("status") == "running":
            return {"success": False, "message": "任务正在运行中，请等待完成"}
        
        self._onlyonce = True
        self.__update_config()
        
        import threading
        threading.Thread(target=self.execute_copy_task, daemon=True).start()
        return {"success": True, "message": "复制任务已开始执行"}

    def stop_service(self):
        """停止服务"""
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.error(f"停止插件服务失败：{str(e)}")