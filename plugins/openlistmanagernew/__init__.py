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


class OpenListManagerNewConfig(BaseModel):
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


class OpenListManagerNew(_PluginBase):
    """
    OpenList管理器插件 - 实现OpenList多目录间文件复制与管理（新）
    支持实时任务进度显示，递归目录创建，以及更完整的文件状态管理。
    """
    # 插件基本信息
    plugin_name = "OpenList管理器新"
    plugin_desc = "OpenList多元化的管理插件，支持实时进度显示和递归目录创建。"
    plugin_icon = "Alist_B.png"
    plugin_version = "1.1"
    plugin_author = "LittlePigeno"
    author_url = "https://github.com/LittlePigeno217/MoviePilot-Plugins"
    plugin_config_prefix = "openlist_new_"
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
            self._config = OpenListManagerNewConfig(**config)
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
            }
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        if self._enable and self._cron:
            return [
                {
                    "id": "OpenListManagerNewTask",
                    "name": "OpenList管理任务新",
                    "trigger": CronTrigger.from_crontab(self._cron),
                    "func": self.execute_copy_task,
                    "kwargs": {}
                }
            ]
        return []
    
    def get_render_mode(self) -> Tuple[str, str]:
        """
        获取插件渲染模式
        :return: 1、渲染模式，支持：vue/vuetify，默认vuetify
        :return: 2、组件路径，默认 dist/assets
        """
        return "vue", "dist/assets"

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        """Returns None for Vue form, but provides initial config data."""
        return None, {
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

    def get_page(self) -> Optional[List[dict]]:
        """Vue mode doesn't use Vuetify page definitions."""
        return None

    def get_dashboard_meta(self) -> Optional[List[Dict[str, str]]]:
        """
        获取插件仪表盘元信息
        返回示例：
            [{
                "key": "dashboard1", // 仪表盘的key，在当前插件范围唯一
                "name": "仪表盘1" // 仪表盘的名称
            }, {
                "key": "dashboard2",
                "name": "仪表盘2"
            }]
        """
        return []

    def get_dashboard(self, key: str, **kwargs) -> Optional[
        Tuple[Dict[str, Any], Dict[str, Any], Optional[List[dict]]]]:
        """
        获取插件仪表盘页面，需要返回：1、仪表板col配置字典；2、全局配置（布局、自动刷新等）；3、仪表板页面元素配置含数据json（vuetify）或 None（vue模式）
        1、col配置参考：
        {
            "cols": 12, "md": 6
        }
        2、全局配置参考：
        {
            "refresh": 10, // 自动刷新时间，单位秒
            "border": True, // 是否显示边框，默认True，为False时取消组件边框和边距，由插件自行控制
            "title": "组件标题", // 组件标题，如有将显示该标题，否则显示插件名称
            "subtitle": "组件子标题", // 组件子标题，缺省时不展示子标题
        }
        3、vuetify模式页面配置使用Vuetify组件拼装，参考：https://vuetifyjs.com/；vue模式为None

        kwargs参数可获取的值：1、user_agent：浏览器UA

        :param key: 仪表盘key，根据指定的key返回相应的仪表盘数据，缺省时返回一个固定的仪表盘数据（兼容旧版）
        """
        return None

    def get_command(self) -> List[Dict[str, Any]]:
        return []

    def stop_service(self):
        if self._scheduler:
            try:
                self._scheduler.shutdown(wait=False)
                self._scheduler = None
                logger.info(f"{self.plugin_name}: 定时任务已停止")
            except Exception as e:
                logger.error(f"{self.plugin_name}: 停止定时任务失败: {e}")

    def get_status(self):
        """获取任务状态"""
        return {
            "status": self._task_status,
            "copied_files": self._copied_files,
            "target_files_count": self._target_files_count
        }

    def run_task(self):
        """执行复制任务"""
        if self._task_status.get("status") == "running":
            return {"status": "error", "message": "任务正在运行中"}
        
        logger.info("开始执行OpenList管理任务")
        import threading
        threading.Thread(target=self.execute_copy_task, daemon=True).start()
        return {"status": "success", "message": "任务已启动"}

    def execute_copy_task(self):
        """执行复制任务的实际逻辑"""
        # 这里是执行复制任务的实际逻辑，保持不变
        pass

    def _get_copying_media_files(self, limit: int = 12) -> List[str]:
        """获取正在复制的媒体文件"""
        return []

    def _get_recent_media_files(self, limit: int = 12) -> List[str]:
        """获取最近复制的媒体文件"""
        return []