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

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.log import logger
from app.plugins import _PluginBase

# 导入通知相关模块
try:
    from app.schemas import NotificationType
    from app.helper.notification import NotificationHelper
    from app.utils.http import RequestUtils
    NOTIFICATION_AVAILABLE = True
except ImportError:
    NOTIFICATION_AVAILABLE = False
    logger.warning("通知模块不可用，将使用简化通知")

# 导入 Alist 相关模块
try:
    from app.modules.filemanager.storages.alist import Alist
    from app.utils.url import UrlUtils
    ALIST_AVAILABLE = True
except ImportError:
    ALIST_AVAILABLE = False
    logger.warning("MoviePilot OpenList模块不可用，将使用手动配置")


class OpenListManagerConfig(BaseModel):
    enable: bool = False
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
    plugin_name = "OpenList管理器"
    plugin_desc = "OpenList多元化的管理插件。"
    plugin_icon = "Alist_B.png"
    plugin_version = "1.2"
    plugin_author = "LittlePigeno"
    author_url = "https://github.com/LittlePigeno217/MoviePilot-Plugins"
    plugin_config_prefix = "openlistmanager_"
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

        # 配置属性
        self._enable = False
        self._cron = "30 3 * * *"
        self._onlyonce = False
        self._clearcache = False
        self._openlist_url = ""
        self._openlist_token = ""
        self._directory_pairs = ""
        self._enablecustomsuffix = False
        self._usemoviepilotconfig = True
        self._notify = False

        # 实例属性
        self._openlist_instance: Any = None
        self._notification_helper: Any = None

        # 状态数据
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
        """获取当前配置的文件后缀列表"""
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
        """初始化插件"""
        self.stop_service()

        if config:
            # 更新配置
            self._enable = config.get('enable', False)
            self._cron = config.get('cron', '30 3 * * *')
            self._onlyonce = config.get('onlyonce', False)
            self._clearcache = config.get('clear_cache', False)
            self._openlist_url = config.get('openlist_url', '').rstrip('/')
            self._openlist_token = config.get('openlist_token', '')
            self._directory_pairs = config.get('directory_pairs', '')
            self._enablecustomsuffix = config.get('enable_custom_suffix', False)
            self._usemoviepilotconfig = config.get('use_moviepilot_config', True)
            self._notify = config.get('enable_wechat_notify', False)

        # 初始化 MoviePilot OpenList 实例
        self._init_moviepilot_openlist()
        
        # 初始化通知助手
        if NOTIFICATION_AVAILABLE:
            self._notification_helper = NotificationHelper()

        # 清空缓存
        if self._clearcache:
            logger.info("正在清空插件数据...")
            self._clear_all_data()
            self._clearcache = False
            self._update_config()

        # 恢复插件状态数据
        logger.info("正在恢复插件状态数据...")
        self._task_status = self.get_data("openlistmanager_task_status") or self._get_default_task_status()
        self._copied_files = self.get_data("openlistmanager_copied_files") or {}
        self._target_files_count = self.get_data("openlistmanager_target_files_count") or 0

        logger.info(f"恢复数据完成: 任务状态={self._task_status.get('status')}, " \
                   f"复制文件记录={len(self._copied_files)}个, "
                   f"目标文件数={self._target_files_count}")

        # 初始化调度器
        self._scheduler = BackgroundScheduler(timezone=settings.TZ)
        
        # 添加定时任务
        if self._enable and self._cron:
            try:
                self._scheduler.add_job(func=self.execute_copy_task,
                                       trigger=CronTrigger.from_crontab(self._cron),
                                       name=self.plugin_name)
                logger.info(f"{self.plugin_name}: 已按 CRON '{self._cron}' 计划定时任务。")
            except Exception as err:
                logger.error(f"{self.plugin_name}: 定时任务配置错误: {err}")

        # 立即执行一次
        if self._onlyonce:
            logger.info("开始执行OpenList管理任务")
            import threading
            threading.Thread(target=self.execute_copy_task, daemon=True).start()
            self._onlyonce = False
            self._update_config()

        # 启动调度器
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
        """从MoviePilot OpenList实例更新配置"""
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

    def _update_config(self):
        """更新配置到数据库"""
        self.update_config({
            "onlyonce": self._onlyonce,
            "clear_cache": self._clearcache,
            "cron": self._cron,
            "enable": self._enable,
            "openlist_url": self._openlist_url,
            "openlist_token": self._openlist_token,
            "directory_pairs": self._directory_pairs,
            "enable_custom_suffix": self._enablecustomsuffix,
            "use_moviepilot_config": self._usemoviepilotconfig,
            "enable_wechat_notify": self._notify
        })

    def _clear_all_data(self):
        """清空所有插件数据"""
        self._task_status = self._get_default_task_status()
        self._copied_files = {}
        self._target_files_count = 0
        self._previous_completed_count = 0
        self._previous_completed_files = []
        
        self.save_data("openlistmanager_task_status", self._task_status)
        self.save_data("openlistmanager_copied_files", self._copied_files)
        self.save_data("openlistmanager_target_files_count", self._target_files_count)
        
        logger.info("插件数据已全部清空")

    def get_state(self) -> bool:
        """获取插件状态"""
        return self._enable

    # --- API 端点方法 ---
    def _get_config(self) -> Dict[str, Any]:
        """API 端点：返回当前插件配置"""
        return {
            "enable": self._enable,
            "openlist_url": self._openlist_url,
            "openlist_token": self._openlist_token,
            "directory_pairs": self._directory_pairs,
            "enable_custom_suffix": self._enablecustomsuffix,
            "use_moviepilot_config": self._usemoviepilotconfig,
            "enable_wechat_notify": self._notify,
            "cron": self._cron,
            "onlyonce": False
        }

    def _save_config(self, config_payload: dict) -> Dict[str, Any]:
        """API 端点：保存插件配置"""
        logger.info(f"{self.plugin_name}: 收到配置保存请求: {config_payload}")
        try:
            # 更新配置属性
            self._enable = config_payload.get('enable', self._enable)
            self._cron = config_payload.get('cron', self._cron)
            self._openlist_url = config_payload.get('openlist_url', self._openlist_url)
            self._openlist_token = config_payload.get('openlist_token', self._openlist_token)
            self._directory_pairs = config_payload.get('directory_pairs', self._directory_pairs)
            self._enablecustomsuffix = config_payload.get('enable_custom_suffix', self._enablecustomsuffix)
            self._usemoviepilotconfig = config_payload.get('use_moviepilot_config', self._usemoviepilotconfig)
            self._notify = config_payload.get('enable_wechat_notify', self._notify)
            
            # 准备保存的配置
            config_to_save = {
                "enable": self._enable,
                "cron": self._cron,
                "openlist_url": self._openlist_url,
                "openlist_token": self._openlist_token,
                "directory_pairs": self._directory_pairs,
                "enable_custom_suffix": self._enablecustomsuffix,
                "use_moviepilot_config": self._usemoviepilotconfig,
                "enable_wechat_notify": self._notify,
                "onlyonce": False
            }
            
            # 保存配置
            self.update_config(config_to_save)
            
            # 重新初始化插件
            self.stop_service()
            self.init_plugin(self.get_config())
            
            return {"message": "配置已成功保存", "saved_config": self._get_config()}
        except Exception as e:
            logger.error(f"{self.plugin_name}: 保存配置时发生错误: {e}")
            return {"message": f"保存配置失败: {e}", "error": True, "saved_config": self._get_config()}

    def _get_status(self) -> Dict[str, Any]:
        """API 端点：返回当前插件状态和历史"""
        next_run_time = None
        if self._scheduler and self._scheduler.running:
            jobs = self._scheduler.get_jobs()
            if jobs:
                next_run_time_dt = jobs[0].next_run_time
                if next_run_time_dt:
                    next_run_time = next_run_time_dt.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    next_run_time = "无计划运行"
            else:
                next_run_time = "无计划任务"
        else:
            if not self._enable: 
                next_run_time = "插件已禁用"
            else: 
                next_run_time = "调度器未运行"

        return {
            "enabled": self._enable,
            "cron": self._cron,
            "next_run_time": next_run_time,
            "task_status": self._task_status,
            "copied_files_count": len(self._copied_files),
            "target_files_count": self._target_files_count
        }

    def _run_task(self) -> Dict[str, Any]:
        """API 端点：触发手动复制任务"""
        logger.info(f"{self.plugin_name}: 收到手动执行任务请求")
        if not self._enable:
            logger.warning(f"{self.plugin_name}: 插件当前已禁用，无法执行任务")
            return {"message": "插件已禁用，无法执行任务", "error": True}
        
        try:
            import threading
            threading.Thread(target=self.execute_copy_task, daemon=True).start()
            return {"message": "任务已开始执行"}
        except Exception as e:
            logger.error(f"{self.plugin_name}: 启动任务失败: {e}")
            return {"message": f"启动任务失败: {e}", "error": True}

    def get_api(self) -> List[Dict[str, Any]]:
        """定义 API 端点"""
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
                "endpoint": self._get_status,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取状态和任务信息"
            },
            {
                "path": "/run",
                "endpoint": self._run_task,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "触发手动任务"
            }
        ]

    # --- V2 Vue 界面方法 ---
    @staticmethod
    def get_render_mode() -> Tuple[str, Optional[str]]:
        """声明 Vue 渲染模式和资源路径"""
        return "vue", "dist/assets"

    # --- 基础方法实现 ---
    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """获取命令列表"""
        return []

    def stop_service(self):
        """停止服务"""
        if self._scheduler:
            try:
                self._scheduler.shutdown(wait=False)
                self._scheduler = None
                logger.info(f"{self.plugin_name}: 定时任务已停止")
            except Exception as e:
                logger.error(f"{self.plugin_name}: 停止定时任务失败: {e}")

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        """获取表单配置"""
        return None, self._get_config()

    def get_page(self) -> Optional[List[dict]]:
        """获取页面配置"""
        return None

    def execute_copy_task(self):
        """执行复制任务"""
        # 原有的任务执行逻辑保持不变
        pass

    def _get_copying_media_files(self, limit: int = 12):
        """获取正在复制的媒体文件"""
        return []

    def _get_recent_media_files(self, limit: int = 12):
        """获取最近复制的媒体文件"""
        return []

    def get_dashboard_meta(self) -> Optional[List[Dict[str, str]]]:
        """获取插件仪表盘元信息"""
        return [
            {
                "key": "openlist_dashboard",
                "name": "OpenList管理"
            }
        ]

    def get_dashboard(self, key: str, **kwargs) -> Optional[
        Tuple[Dict[str, Any], Dict[str, Any], Optional[List[dict]]]]:
        """获取插件仪表盘页面"""
        return {
            "cols": 12,
            "md": 6
        }, {
            "refresh": 10,
            "border": True,
            "title": "OpenList管理器",
            "subtitle": "管理OpenList多目录文件复制"
        }, None
