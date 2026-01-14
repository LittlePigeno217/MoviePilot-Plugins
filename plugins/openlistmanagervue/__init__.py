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


class OpenListManager(_PluginBase):
    """
    OpenList管理器插件 - 实现OpenList多目录间文件复制与管理
    """
    # 插件基本信息
    plugin_name = "OpenList管理Vue"
    plugin_desc = "OpenList多元化的管理插件。"
    plugin_icon = "Alist_B.png"
    plugin_version = "1.1"
    plugin_author = "LittlePigeno"
    author_url = "https://github.com/LittlePigeno217/MoviePilot-Plugins"
    plugin_config_prefix = "openlistmanagervue_"
    plugin_order = 1
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
        self._task_status = self.get_data("openlistmanagervue_task_status") or self._get_default_task_status()
        self._copied_files = self.get_data("openlistmanagervue_copied_files") or {}
        self._target_files_count = self.get_data("openlistmanagervue_target_files_count") or 0

        logger.info(f"恢复数据完成: 任务状态={self._task_status.get('status')}, " \
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
        
        self.save_data("openlistmanagervue_task_status", self._task_status)
        self.save_data("openlistmanagervue_copied_files", self._copied_files)
        self.save_data("openlistmanagervue_target_files_count", self._target_files_count)
        
        logger.info("插件数据已全部清空")

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/config",
                "endpoint": self._get_config,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取当前配置"
            },
            {
                "path": "/config",
                "endpoint": self._save_config,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "保存配置"
            },
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
                    "id": "OpenListManagerTask",
                    "name": "OpenList管理任务",
                    "trigger": CronTrigger.from_crontab(self._cron),
                    "func": self.execute_copy_task,
                    "kwargs": {}
                }
            ]
        return []

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        """Returns None for Vue form, but provides initial config data."""
        # This dict is passed as initialConfig to Config.vue by the host
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

    # --- V2 Vue Interface Method ---
    @staticmethod
    def get_render_mode() -> Tuple[str, Optional[str]]:
        """Declare Vue rendering mode and assets path."""
        return "vue", "dist/assets"

    def _save_task_status(self):
        """保存任务状态"""
        self.save_data("openlistmanagervue_task_status", self._task_status)

    def _complete_task(self, status: str, message: str):
        """完成任务并更新状态"""
        self._task_status.update({
            "status": status,
            "end_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "message": message
        })
        self._save_task_status()

    def _get_completed_files_list(self) -> List[str]:
        """获取已完成文件列表"""
        completed_files = []
        for record in self._copied_files.values():
            if record.get("status") == "completed":
                filename = record.get("filename", "")
                if filename:
                    completed_files.append(filename)
        return completed_files

    def _send_notification(self, copied_count: int, completed_count: int, 
                          copied_files: List[str], completed_files: List[str]):
        """发送通知"""
        # 实现通知发送逻辑
        pass

    def _get_config(self) -> Dict[str, Any]:
        """API Endpoint: Returns current plugin configuration."""
        return {
            "enabled": self._enable,
            "notify": self._notify,
            "cron": self._cron,
            "openlist_url": self._openlist_url,
            "openlist_token": self._openlist_token,
            "directory_pairs": self._directory_pairs,
            "enable_custom_suffix": self._enablecustomsuffix,
            "use_moviepilot_config": self._usemoviepilotconfig,
            "enable_wechat_notify": self._notify,
            "onlyonce": False  # 始终返回False
        }

    def _save_config(self, config_payload: dict) -> Dict[str, Any]:
        """API Endpoint: Saves plugin configuration. Expects a dict payload."""
        logger.info(f"{self.plugin_name}: 收到配置保存请求: {config_payload}")
        try:
            # Update instance variables directly from payload, defaulting to current values if key is missing
            self._enable = config_payload.get('enabled', self._enable)
            self._notify = config_payload.get('enable_wechat_notify', self._notify)
            self._cron = config_payload.get('cron', self._cron)
            self._openlist_url = config_payload.get('openlist_url', self._openlist_url)
            self._openlist_token = config_payload.get('openlist_token', self._openlist_token)
            self._directory_pairs = config_payload.get('directory_pairs', self._directory_pairs)
            self._enablecustomsuffix = config_payload.get('enable_custom_suffix', self._enablecustomsuffix)
            self._usemoviepilotconfig = config_payload.get('use_moviepilot_config', self._usemoviepilotconfig)
            self._notify = config_payload.get('enable_wechat_notify', self._notify)
            
            # 忽略onlyonce参数

            # Prepare config to save
            config_to_save = {
                "enabled": self._enable,
                "onlyonce": False,
                "clear_cache": False,
                "cron": self._cron,
                "openlist_url": self._openlist_url,
                "openlist_token": self._openlist_token,
                "directory_pairs": self._directory_pairs,
                "enable_custom_suffix": self._enablecustomsuffix,
                "use_moviepilot_config": self._usemoviepilotconfig,
                "enable_wechat_notify": self._notify
            }
            
            # 保存配置
            self.update_config(config_to_save)
            
            # 重新初始化插件
            self.stop_service()
            self.init_plugin(self.get_config())
            
            logger.info(f"{self.plugin_name}: 配置已保存并通过 init_plugin 重新初始化。当前内存状态: enable={self._enable}")
            
            # 返回最终状态
            return {"message": "配置已成功保存", "saved_config": self._get_config()}

        except Exception as e:
            logger.error(f"{self.plugin_name}: 保存配置时发生错误: {e}", exc_info=True)
            # Return current in-memory config on error
            return {"message": f"保存配置失败: {e}", "error": True, "saved_config": self._get_config()}

    def get_status(self) -> Dict[str, Any]:
        """获取任务状态"""
        return {
            "task_status": self._task_status,
            "copied_files": self._copied_files,
            "target_files_count": self._target_files_count
        }

    def run_task(self, payload: dict = None) -> Dict[str, Any]:
        """执行复制任务"""
        # 实现任务执行逻辑
        pass

    def execute_copy_task(self):
        """执行复制任务"""
        # 实现复制任务逻辑
        pass

    def _update_file_status_and_counts(self, silent: bool = False):
        """更新媒体文件状态和数量统计"""
        # 实现更新逻辑
        pass

    def _normalize_path(self, path: str) -> str:
        """标准化路径"""
        return path.rstrip('/')
    
    def _get_file_status_counts(self) -> Tuple[int, int]:
        """获取媒体文件状态统计数量"""
        # 实现获取统计逻辑
        pass
    
    def _get_recent_media_files(self, count: int = 50) -> List[Dict]:
        """获取最近完成的媒体文件列表"""
        # 实现获取逻辑
        pass
    
    def _get_copying_media_files(self, count: int = 50) -> List[Dict]:
        """获取正在复制的媒体文件列表"""
        # 实现获取逻辑
        pass
    
    def _render_recent_media_files(self, media_files: List[Dict]) -> List[Dict]:
        """渲染最近完成的媒体文件列表"""
        # 实现渲染逻辑
        pass
    
    def _render_copying_media_files(self, media_files: List[Dict]) -> List[Dict]:
        """渲染正在复制的媒体文件列表"""
        # 实现渲染逻辑
        pass

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
        if self._scheduler:
            try:
                self._scheduler.shutdown(wait=False)
                self._scheduler = None
                logger.info(f"{self.plugin_name}: 定时任务已停止")
            except Exception as e:
                logger.error(f"{self.plugin_name}: 停止定时任务失败: {e}")

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

    def _validate_config(self) -> bool:
        """验证配置是否有效"""
        # 实现配置验证逻辑
        return True

    def _should_execute_copy_task(self, directory_pairs: List[Dict[str, str]]) -> bool:
        """判断是否应该执行复制任务"""
        # 实现判断逻辑
        return True

    def _verify_openlist_connection(self) -> bool:
        """验证OpenList连接"""
        # 实现连接验证逻辑
        return True

    def _update_target_files_count(self, directory_pairs: List[Dict[str, str]], silent: bool = False):
        """更新目标目录媒体文件数"""
        # 实现更新逻辑
        pass

    def _get_openlist_files(self, path: str) -> List[Dict]:
        """获取OpenList文件列表"""
        # 实现获取文件列表逻辑
        return []

    def get_command(self) -> List[Dict[str, Any]]:
        return []

    def get_dashboard_meta(self) -> Optional[List[Dict[str, str]]]:
        """
        获取插件仪表盘元信息
        """
        return None

    def get_dashboard(self, key: str, **kwargs) -> Optional[
        Tuple[Dict[str, Any], Dict[str, Any], Optional[List[dict]]]]:
        """
        获取插件仪表盘页面
        """
        return None, None, None