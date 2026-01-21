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
    openlist_source_dir: str = ""
    openlist_target_dir: str = ""
    openlist_source_dirs: list = []
    openlist_target_dirs: list = []
    enable_custom_suffix: bool = False
    custom_suffix: str = ""
    cron: str = "0 */30 * * *"
    use_moviepilot_config: bool = True
    enable_wechat_notify: bool = False
    onlyonce: bool = False
    clear_cache: bool = False


class OpenListManagerVue(_PluginBase):
    """
    OpenList管理器Vue插件 - 实现OpenList多目录间文件复制与管理
    """
    # 插件基本信息
    plugin_name = "OpenList管理器Vue"
    plugin_desc = "OpenList多元化的管理插件。"
    plugin_icon = "https://raw.githubusercontent.com/LittlePigeno217/MoviePilot-Plugins/main/icons/Alist_B.png"
    plugin_version = "1.0"
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

        # 配置属性
        self._enable = False
        self._cron = "30 3 * * *"
        self._onlyonce = False
        self._clearcache = False
        self._openlist_url = ""
        self._openlist_token = ""
        self._openlist_source_dir = ""
        self._openlist_target_dir = ""
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
        self._media_counts: List[Dict[str, Any]] = []
        
        self._default_card_image = "https://raw.githubusercontent.com/LittlePigeno217/MoviePilot-Plugins/main/icons/Alist_B.png"
        
        self._previous_completed_count: int = 0
        self._previous_completed_files: List[str] = []
        
        # 全局任务执行锁 - 使用类变量确保所有实例共享同一把锁
        import threading
        if not hasattr(OpenListManagerVue, '_global_task_lock'):
            OpenListManagerVue._global_task_lock = threading.Lock()
        if not hasattr(OpenListManagerVue, '_global_is_running'):
            OpenListManagerVue._global_is_running = False

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
            self._openlist_source_dir = config.get('openlist_source_dir', '')
            self._openlist_target_dir = config.get('openlist_target_dir', '')
            # 处理多选目录配置
            self._openlist_source_dirs = config.get('openlist_source_dirs', [])
            self._openlist_target_dirs = config.get('openlist_target_dirs', [])
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
            
            # 清除缓存后立即更新目标文件数
            if self._enable:
                logger.info("清除缓存后，立即更新目标文件数")
                import threading
                threading.Thread(target=self._update_target_files_count, daemon=True).start()

        # 恢复插件状态数据
        logger.info("正在恢复插件状态数据...")
        self._task_status = self.get_data("openlistmanagervue_task_status") or self._get_default_task_status()
        self._copied_files = self.get_data("openlistmanagervue_copied_files") or {}
        self._target_files_count = self.get_data("openlistmanagervue_target_files_count") or 0
        self._media_counts = self.get_data("openlistmanagervue_media_counts") or []

        logger.info(f"恢复数据完成: 任务状态={self._task_status.get('status')}, " \
                   f"复制文件记录={len(self._copied_files)}个, "
                   f"目标文件数={self._target_files_count}")
        
        # 当插件启用后，验证复制历史文件加载情况
        if self._enable:
            # 从文件加载复制历史，确保文件存在并能正常加载
            copy_history = self._load_copy_history()
            logger.info(f"插件已启用，从文件加载复制历史，共 {len(copy_history)} 条记录")

        # 初始化调度器
        self._scheduler = BackgroundScheduler(timezone=settings.TZ)
        
        # 添加定时任务
        if self._enable and self._cron:
            try:
                self._scheduler.add_job(func=self._run_async_task,
                                       trigger=CronTrigger.from_crontab(self._cron),
                                       name=self.plugin_name)
                logger.info(f"已按 CRON '{self._cron}' 计划定时任务。")
            except Exception as err:
                logger.error(f"定时任务配置错误: {err}")


        

        # 立即执行一次
        if self._onlyonce:
            logger.info("开始执行OpenList管理任务")
            import threading
            threading.Thread(target=self._run_async_task, daemon=True).start()
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
            "openlist_source_dir": self._openlist_source_dir,
            "openlist_target_dir": self._openlist_target_dir,
            "enable_custom_suffix": self._enablecustomsuffix,
            "use_moviepilot_config": self._usemoviepilotconfig,
            "enable_wechat_notify": self._notify
        })

    def _clear_all_data(self):
        """清空所有插件数据"""
        logger.info("开始执行清除数据操作...")
        
        # 1. 重置所有内存中的数据
        self._task_status = self._get_default_task_status()
        self._copied_files = {}  # 已完成数量归0
        self._target_files_count = 0  # 目标文件数归0
        self._previous_completed_count = 0
        self._previous_completed_files = []
        
        # 2. 保存重置后的数据到数据库
        logger.info("清空数据库存储的数据...")
        self.save_data("openlistmanagervue_task_status", self._task_status)
        self.save_data("openlistmanagervue_copied_files", self._copied_files)
        self.save_data("openlistmanagervue_target_files_count", self._target_files_count)
        
        # 3. 删除复制历史记录文件
        logger.info("删除复制历史记录文件...")
        copy_history_file = self._plugin_dir / "copy_history.json"
        if copy_history_file.exists():
            try:
                copy_history_file.unlink()
                logger.info("复制历史记录文件已成功删除")
            except Exception as e:
                logger.error(f"删除复制历史记录文件失败: {e}")
        else:
            logger.info("复制历史记录文件不存在，跳过删除")
        
        logger.info("清除数据操作完成：")
        logger.info("- 复制历史记录文件已删除")
        logger.info("- 目标文件数已归零")
        logger.info("- 已完成数量已归零")

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
            "openlist_source_dir": self._openlist_source_dir,
            "openlist_target_dir": self._openlist_target_dir,
            "openlist_source_dirs": self._openlist_source_dirs,
            "openlist_target_dirs": self._openlist_target_dirs,
            "enable_custom_suffix": self._enablecustomsuffix,
            "use_moviepilot_config": self._usemoviepilotconfig,
            "enable_wechat_notify": self._notify,
            "cron": self._cron,
            "onlyonce": False
        }

    def _save_config(self, config_payload: dict) -> Dict[str, Any]:
        """API 端点：保存插件配置"""
        logger.info(f"收到配置保存请求: {config_payload}")
        try:
            # 更新配置属性
            self._enable = config_payload.get('enable', self._enable)
            self._cron = config_payload.get('cron', self._cron)
            self._openlist_url = config_payload.get('openlist_url', self._openlist_url)
            self._openlist_token = config_payload.get('openlist_token', self._openlist_token)
            self._openlist_source_dir = config_payload.get('openlist_source_dir', self._openlist_source_dir)
            self._openlist_target_dir = config_payload.get('openlist_target_dir', self._openlist_target_dir)
            # 处理多选目录配置
            self._openlist_source_dirs = config_payload.get('openlist_source_dirs', self._openlist_source_dirs)
            self._openlist_target_dirs = config_payload.get('openlist_target_dirs', self._openlist_target_dirs)
            self._enablecustomsuffix = config_payload.get('enable_custom_suffix', self._enablecustomsuffix)
            self._usemoviepilotconfig = config_payload.get('use_moviepilot_config', self._usemoviepilotconfig)
            self._notify = config_payload.get('enable_wechat_notify', self._notify)
            
            # 准备保存的配置
            config_to_save = {
                "enable": self._enable,
                "cron": self._cron,
                "openlist_url": self._openlist_url,
                "openlist_token": self._openlist_token,
                "openlist_source_dir": self._openlist_source_dir,
                "openlist_target_dir": self._openlist_target_dir,
                "openlist_source_dirs": self._openlist_source_dirs,
                "openlist_target_dirs": self._openlist_target_dirs,
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
            
            # 配置保存后更新目标文件数
            if self._enable:
                import threading
                threading.Thread(target=self._update_target_files_count, daemon=True).start()
            
            return {"message": "配置已成功保存", "saved_config": self._get_config()}
        except Exception as e:
            logger.error(f"保存配置时发生错误: {e}")
            return {"message": f"保存配置失败: {e}", "error": True, "saved_config": self._get_config()}

    def _save_copy_history(self, copy_history: List[Dict[str, Any]]):
        """保存复制历史到文件"""
        copy_history_file = self._plugin_dir / "copy_history.json"
        try:
            with open(copy_history_file, 'w', encoding='utf-8') as f:
                json.dump(copy_history, f, ensure_ascii=False, indent=2)
            logger.info(f"复制历史已保存到文件，共 {len(copy_history)} 条记录")
        except Exception as e:
            logger.error(f"保存复制历史到文件失败: {e}")
    
    def _load_copy_history(self) -> List[Dict[str, Any]]:
        """从文件加载复制历史"""
        copy_history_file = self._plugin_dir / "copy_history.json"
        if not copy_history_file.exists():
            return []
        
        try:
            with open(copy_history_file, 'r', encoding='utf-8') as f:
                copy_history = json.load(f)
            logger.info(f"从文件加载复制历史成功，共 {len(copy_history)} 条记录")
            return copy_history
        except Exception as e:
            logger.error(f"从文件加载复制历史失败: {e}")
            return []
    
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

        # 从文件获取复制历史
        copy_history = self._load_copy_history()

        return {
            "enabled": self._enable,
            "cron": self._cron,
            "next_run_time": next_run_time,
            "task_status": self._task_status,
            "copied_files_count": len(self._copied_files),
            "target_files_count": self._target_files_count,
            "copy_history": copy_history,
            "media_counts": self._media_counts
        }

    def _run_task(self) -> Dict[str, Any]:
        """API 端点：触发手动复制任务"""
        logger.info("收到手动执行任务请求")
        if not self._enable:
            logger.warning("插件当前已禁用，无法执行任务")
            return {"message": "插件已禁用，无法执行任务", "error": True}
        
        try:
            import threading
            threading.Thread(target=self._run_async_task, daemon=True).start()
            return {"message": "任务已开始执行"}
        except Exception as e:
            logger.error(f"启动任务失败: {e}")
            return {"message": f"启动任务失败: {e}", "error": True}

    def _get_directory_structure(self, path: str, headers: dict, depth: int = 0, max_depth: int = 4) -> Dict[str, Any]:
        """
        递归获取目录结构
        :param path: 当前目录路径
        :param headers: 请求头
        :param depth: 当前递归深度
        :param max_depth: 最大递归深度
        :return: 目录结构字典
        """
        dir_info = {
            "path": path,
            "name": path.split("/")[-1] if path != "/" else "/",
            "children": []
        }
        
        # 达到最大深度，不再递归
        if depth >= max_depth:
            return dir_info
        
        try:
            # API URL
            list_url = f"{self._openlist_url}/api/fs/list"
            
            # 请求体
            list_payload = {
                "path": path,
                "password": "",
                "page": 1,
                "per_page": 0
            }
            
            # 发送请求
            list_response = requests.post(list_url, json=list_payload, headers=headers, timeout=30)
            
            if list_response.status_code == 200:
                list_result = list_response.json()
                
                if list_result.get("code") == 200:
                    # 确保contents始终是可迭代对象
                    contents = list_result.get("data", {}).get("content") or []
                    
                    # 处理目录项，递归获取子目录
                    for item in contents:
                        if item.get("is_dir", False):
                            item_name = item.get("name")
                            sub_path = f"{path}/{item_name}" if path != "/" else f"/{item_name}"
                            # 递归获取子目录结构
                            sub_dir = self._get_directory_structure(sub_path, headers, depth + 1, max_depth)
                            dir_info["children"].append(sub_dir)
                
        except Exception as e:
            logger.error(f"获取目录 {path} 结构失败: {e}")
        
        return dir_info
    
    def _get_directories(self) -> Dict[str, Any]:
        """API 端点：获取OpenList中的目录列表，支持多级目录"""
        logger.info("获取OpenList目录列表请求")
        
        try:
            # 构造 API 请求头
            headers = {
                "Authorization": self._openlist_token,
                "Content-Type": "application/json"
            }
            
            # 递归获取目录结构，最大深度为4级
            directory_structure = self._get_directory_structure("/", headers, max_depth=4)
            
            logger.info("成功获取OpenList目录结构")
            return {
                "directory_structure": directory_structure,
                "error": False
            }
        except Exception as e:
            logger.error(f"获取目录列表失败: {e}")
            return {
                "message": f"获取目录列表失败: {str(e)}",
                "error": True
            }
    
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
            },
            {
                "path": "/directories",
                "endpoint": self._get_directories,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取OpenList目录列表"
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

    def _run_async_task(self):
        """同步包装器，用于执行异步任务"""
        import asyncio
        asyncio.run(self.execute_copy_task())
    
    def stop_service(self):
        """停止服务"""
        if self._scheduler:
            try:
                self._scheduler.shutdown(wait=False)
                self._scheduler = None
                logger.info("定时任务已停止")
            except Exception as e:
                logger.error(f"停止定时任务失败: {e}")

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        """获取表单配置"""
        return None, self._get_config()

    def get_page(self) -> Optional[List[dict]]:
        """获取页面配置"""
        return None

    def _update_target_files_count(self):
        """更新目标目录的媒体文件总数"""
        logger.info("开始统计目标目录的媒体文件总数")
        
        try:
            # 解析目录对配置
            directory_pairs = self._parse_directory_pairs()
            if not directory_pairs:
                logger.warning("没有配置有效的目录对，无法统计目标文件数")
                self._target_files_count = 0
                self.save_data("openlistmanagervue_target_files_count", self._target_files_count)
                return
            
            # 构造 API 请求头
            headers = {
                "Authorization": self._openlist_token,
                "Content-Type": "application/json"
            }
            
            total_media_files = 0
            media_counts = []
            
            # 遍历所有目录对，统计每个目标目录的媒体文件数和大小
            for _, target_dir in directory_pairs:
                logger.info(f"正在扫描目标目录 {target_dir}")
                
                # 获取目标目录下的所有文件
                all_files = self._get_all_files(target_dir, headers)
                
                # 统计媒体文件数量和大小
                media_files = [file for file in all_files if self._is_media_file(file["name"])]
                media_count = len(media_files)
                total_media_files += media_count
                
                # 计算目标目录大小（仅媒体文件大小）
                dir_size = sum(file["size"] for file in media_files)
                
                # 提取目录名称
                dir_name = target_dir.split("/")[-1] if target_dir != "/" else "/"
                
                logger.info(f"目标目录 {target_dir} 下有 {media_count} 个媒体文件，大小 {dir_size} 字节")
                
                # 添加到media_counts列表
                media_counts.append({
                    "dir_name": dir_name,
                    "dir_path": target_dir,
                    "count": media_count,
                    "size": dir_size
                })
            
            # 更新目标文件数
            self._target_files_count = total_media_files
            self.save_data("openlistmanagervue_target_files_count", self._target_files_count)
            
            # 更新媒体数量统计
            self._media_counts = media_counts
            self.save_data("openlistmanagervue_media_counts", self._media_counts)
            
            logger.info(f"所有目标目录的媒体文件总数为 {total_media_files}")
            
        except Exception as e:
            logger.error(f"统计目标目录媒体文件数失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
    
    def _get_all_files(self, dir_path: str, headers: dict) -> list:
        """
        递归获取目录及其子目录下的所有文件
        :param dir_path: 目录路径
        :param headers: 请求头
        :return: 文件列表，每个元素包含path, name, size等信息
        """
        all_files = []
        list_url = f"{self._openlist_url}/api/fs/list"
        
        try:
            list_payload = {
                "path": dir_path,
                "password": "",
                "page": 1,
                "per_page": 0
            }
            
            # 发送列表请求
            list_response = requests.post(list_url, json=list_payload, headers=headers, timeout=30)
            
            if list_response.status_code == 200:
                list_result = list_response.json()
                
                if list_result.get("code") == 200:
                    # 确保contents始终是可迭代对象，处理content为None的情况
                    contents = list_result.get("data", {}).get("content") or []
                    
                    for item in contents:
                        item_name = item.get("name")
                        is_dir = item.get("is_dir", False)
                        
                        if is_dir:
                            # 是目录，递归获取
                            sub_dir = f"{dir_path}/{item_name}" if dir_path != "/" else f"/{item_name}"
                            # 递归调用获取子目录文件，不输出日志
                            sub_files = self._get_all_files(sub_dir, headers)
                            all_files.extend(sub_files)
                        else:
                            # 是文件，添加到列表，包含完整信息
                            all_files.append({
                                "path": dir_path,
                                "name": item_name,
                                "size": item.get("size", 0),
                                "type": item.get("type", 0),
                                "modified": item.get("modified", 0)
                            })
                else:
                    logger.error(f"获取目录 {dir_path} 列表失败: API返回错误码 {list_result.get('code')}")
            else:
                logger.error(f"获取目录 {dir_path} 列表失败: HTTP状态码 {list_response.status_code}")
        except Exception as e:
            logger.error(f"获取目录 {dir_path} 列表失败: {e}")
        
        return all_files
    
    def _parse_directory_pairs(self) -> List[Tuple[str, str]]:
        """获取目录对配置，支持多选目录"""
        pairs = []
        
        # 获取源目录列表
        source_dirs = self._openlist_source_dirs if hasattr(self, '_openlist_source_dirs') and self._openlist_source_dirs else []
        # 获取目标目录列表
        target_dirs = self._openlist_target_dirs if hasattr(self, '_openlist_target_dirs') and self._openlist_target_dirs else []
        
        # 向后兼容：如果没有多选目录配置，使用旧的单目录配置
        if not source_dirs:
            source_dir = self._openlist_source_dir.strip()
            if source_dir:
                source_dirs = [source_dir]
        
        if not target_dirs:
            target_dir = self._openlist_target_dir.strip()
            if target_dir:
                target_dirs = [target_dir]
        
        # 创建所有源目录和目标目录的组合对
        for source_dir in source_dirs:
            for target_dir in target_dirs:
                source_dir = source_dir.strip()
                target_dir = target_dir.strip()
                if source_dir and target_dir:
                    pairs.append((source_dir, target_dir))
        
        return pairs

    def _initialize_task(self, total_pairs: int):
        """
        初始化任务状态
        :param total_pairs: 目录对总数
        """
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self._update_task_status(
            status="running",
            progress=0,
            message="正在初始化任务...",
            last_run=now,
            start_time=now,
            end_time=None,
            total_files=0,
            copied_files=0,
            skipped_files=0,
            current_pair="",
            total_pairs=total_pairs,
            completed_pairs=0
        )
    
    def _finish_task(self, success: bool = True, message: str = None):
        """
        完成任务并更新状态
        :param success: 是否成功
        :param message: 完成消息
        """
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        status = "idle"
        
        if success:
            msg = message or "所有目录对处理完成"
            self._update_task_status(
                status=status,
                message=msg,
                end_time=now,
                progress=100
            )
        else:
            msg = message or "任务执行失败"
            self._update_task_status(
                status=status,
                message=msg,
                end_time=now
            )
        
        logger.info(f"{msg}")
    
    def _update_task_status(self, **kwargs):
        """
        更新任务状态并保存
        :param kwargs: 要更新的状态字段
        """
        for key, value in kwargs.items():
            self._task_status[key] = value
        self.save_data("openlistmanagervue_task_status", self._task_status)
    
    async def execute_copy_task(self):
        """执行复制任务"""
        # 检查插件是否已启用
        if not self._enable:
            logger.warning("插件已禁用，跳过任务执行")
            return
        
        # 检查任务是否已经在运行 - 使用全局标志
        if OpenListManagerVue._global_is_running:
            logger.info("任务正在执行中，跳过重复触发")
            return
        
        # 获取全局任务锁
        with OpenListManagerVue._global_task_lock:
            # 再次检查任务状态，防止在获取锁期间有其他线程启动了任务
            if OpenListManagerVue._global_is_running:
                logger.info("任务正在执行中，跳过重复触发")
                return
            
            # 设置全局任务运行状态
            OpenListManagerVue._global_is_running = True
            
            total_copied = 0
            total_media = 0
            total_scraper = 0
            copied_files_list = []
            all_files_to_copy = []
            total_files_to_copy = 0
            
            try:
                logger.info("开始执行复制任务")
                
                # 更新目标文件数（任务开始前）
                self._update_task_status(
                    status="running",
                    progress=0,
                    message="正在更新目标文件数...",
                    last_run=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    start_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                )
                
                self._update_target_files_count()
                
                # 解析目录对配置
                directory_pairs = self._parse_directory_pairs()
                total_pairs = len(directory_pairs)
                
                if not directory_pairs:
                    logger.warning("没有配置有效的目录对")
                    self._finish_task(success=True, message="没有配置有效的目录对")
                    return
                
                # 构造 API 请求头
                headers = {
                    "Authorization": self._openlist_token,
                    "Content-Type": "application/json"
                }
                
                # 收集所有需要复制的文件
                logger.info("正在收集所有需要复制的文件...")
                for source_dir, target_dir in directory_pairs:
                    # 获取源目录下的所有文件
                    source_files = self._get_all_files(source_dir, headers)
                    logger.info(f"源目录 {source_dir} 下有 {len(source_files)} 个文件")
                    
                    # 过滤出有效的文件
                    for file_item in source_files:
                        # 检查文件名是否为空，跳过空文件名的文件
                        file_name = file_item.get('name', '')
                        if not file_name:
                            logger.warning(f"跳过空文件名的文件，路径: {file_item['path']}")
                            continue
                            
                        source_file_path = f"{file_item['path']}/{file_name}"
                        target_file_path = source_file_path.replace(source_dir, target_dir, 1)
                        
                        # 判断文件类型
                        is_media = self._is_media_file(file_name)
                        
                        # 添加到待复制文件列表
                        all_files_to_copy.append({
                            "file_item": file_item,
                            "source_file_path": source_file_path,
                            "target_file_path": target_file_path,
                            "is_media": is_media,
                            "source_dir": source_dir,
                            "target_dir": target_dir
                        })
                
                total_files_to_copy = len(all_files_to_copy)
                if total_files_to_copy == 0:
                    logger.info("没有需要复制的文件")
                    self._finish_task(success=True, message="没有需要复制的文件")
                    return
                
                # 初始化任务状态，使用实际文件数量计算进度
                self._initialize_task(total_pairs)
                self._update_task_status(
                    total_files=total_files_to_copy,
                    copied_files=0,
                    progress=0,
                    message=f"准备复制 {total_files_to_copy} 个文件..."
                )
                
                logger.info(f"开始复制 {total_files_to_copy} 个文件")
                
                # 执行并行复制，使用线程池提高效率
                from concurrent.futures import ThreadPoolExecutor, as_completed
                
                # 设置最大线程数，避免服务器压力过大
                max_workers = min(10, os.cpu_count() * 2 + 1)
                logger.info(f"使用 {max_workers} 个线程进行并行复制")
                
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    # 提交所有复制任务
                    future_to_file = {}
                    for file_info in all_files_to_copy:
                        future = executor.submit(
                            self._copy_single_file,
                            file_info,
                            headers
                        )
                        future_to_file[future] = file_info
                    
                    # 处理复制结果
                    for future in as_completed(future_to_file):
                        file_info = future_to_file[future]
                        try:
                            result = future.result()
                            if result:
                                # 记录复制的文件信息
                                copied_files_list.append(result)
                                
                                # 只有成功复制的文件才计入统计
                                if result["status"] == "success":
                                    total_copied += 1
                                    if file_info["is_media"]:
                                        total_media += 1
                                    else:
                                        total_scraper += 1
                            
                            # 每处理10个文件更新一次状态，减少状态更新频率
                            if (len(copied_files_list) % 10 == 0 or len(copied_files_list) == total_files_to_copy):
                                # 计算精确进度，基于已处理的文件数
                                progress = int((len(copied_files_list) / total_files_to_copy) * 100)
                                self._update_task_status(
                                    copied_files=total_copied,
                                    progress=progress,
                                    message=f"已处理 {len(copied_files_list)}/{total_files_to_copy} 个文件，成功复制 {total_copied} 个..."
                                )
                        except Exception as e:
                            logger.error(f"处理文件复制结果时发生错误: {e}")
                
                # 所有文件复制完成
                logger.info(f"所有文件复制完成，共成功复制 {total_copied} 个文件（媒体文件: {total_media}，刮削文件: {total_scraper}）")
                self._finish_task(
                    success=True,
                    message=f"所有文件复制完成，共成功复制 {total_copied} 个文件（媒体文件: {total_media}，刮削文件: {total_scraper}）"
                )
                
                # 只有当成功复制的文件数大于0时，才记录到复制历史和发送通知
                if total_copied > 0:
                    # 获取现有复制历史（从文件）
                    copy_history = self._load_copy_history()
                    
                    # 添加新的历史记录，包含详细的文件信息
                    new_history_item = {
                        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        "total": total_copied,
                        "media": total_media,
                        "scraper": total_scraper,
                        "directory_pairs": total_pairs,
                        "total_files": total_files_to_copy,
                        "files": copied_files_list
                    }
                    
                    # 添加到历史记录开头
                    copy_history.insert(0, new_history_item)
                    
                    # 只保留最近10条记录
                    if len(copy_history) > 10:
                        copy_history = copy_history[:10]
                    
                    # 保存更新后的历史记录到文件
                    self._save_copy_history(copy_history)
                    logger.info(f"复制历史已更新，共 {len(copy_history)} 条记录")
                    
                    # 发送企业微信通知
                    if self._notify and NOTIFICATION_AVAILABLE:
                        try:
                            # 准备通知内容
                            notification_title = "OpenList 复制任务完成"
                            notification_message = f"✅ 复制任务已完成\n\n" \
                                                 f"📊 共成功复制 {total_copied} 个文件\n" \
                                                 f"🎬 媒体文件: {total_media} 个\n" \
                                                 f"📝 刮削文件: {total_scraper} 个\n" \
                                                 f"⏰ 执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                            
                            # 调用通知助手发送企业微信通知
                            if hasattr(self, '_notification_helper') and self._notification_helper:
                                try:
                                    # 尝试使用直接的方式获取通知模块实例
                                    from app.core.module import ModuleManager
                                    from app.schemas.types import ModuleType
                                    module_manager = ModuleManager()
                                    notification_modules = module_manager.get_running_type_modules(ModuleType.Notification)
                                    
                                    # 遍历所有通知模块
                                    wechat_found = False
                                    for module in notification_modules:
                                        if not module:
                                            continue
                                        
                                        # 获取模块实例
                                        instances = module.get_instances()
                                        if not isinstance(instances, dict):
                                            continue
                                        
                                        for name, instance in instances.items():
                                            if not instance:
                                                continue
                                                
                                            try:
                                                # 直接调用send方法发送通知，不依赖于配置
                                                await instance.send(
                                                    title=notification_title,
                                                    text=notification_message,
                                                    userid="@all"
                                                )
                                                logger.info(f"企业微信通知发送成功: {name}")
                                                wechat_found = True
                                            except Exception as e:
                                                logger.error(f"发送企业微信通知失败 {name}: {e}")
                                    
                                    if not wechat_found:
                                        logger.warning("未找到可用的企业微信通知服务或发送失败")
                                except Exception as e:
                                    logger.error(f"获取通知服务失败: {e}")
                        except Exception as e:
                            logger.error(f"发送企业微信通知失败: {e}")
                    
            except Exception as e:
                logger.error(f"执行复制任务时发生错误: {e}")
                import traceback
                logger.error(f"错误详情: {traceback.format_exc()}")
                self._finish_task(success=False, message=f"任务执行失败: {str(e)}")
            finally:
                # 无论任务成功还是失败，都要重置全局任务运行状态
                OpenListManagerVue._global_is_running = False
                
                # 更新目标文件数（任务结束后）
                self._update_task_status(
                    message="正在更新目标文件数..."
                )
                self._update_target_files_count()
                
                logger.info("任务执行锁已释放")
                
    def _copy_single_file(self, file_info, headers):
        """复制单个文件的辅助方法，用于并行复制"""
        file_item = file_info["file_item"]
        source_file_path = file_info["source_file_path"]
        target_file_path = file_info["target_file_path"]
        is_media = file_info["is_media"]
        file_name = file_item.get('name', '')
        
        # 执行复制操作
        try:
            # 调用OpenList API执行复制，使用标准的OpenList API格式
            copy_url = f"{self._openlist_url}/api/fs/copy"
            
            # 解析源文件路径和目标文件路径
            import os
            src_dir = os.path.dirname(source_file_path)
            dst_dir = os.path.dirname(target_file_path)
            
            copy_payload = {
                "src_dir": src_dir,
                "dst_dir": dst_dir,
                "names": [file_name]
                # 移除force参数，不强制覆盖
            }
            
            logger.debug(f"调用OpenList API复制文件: {source_file_path} -> {target_file_path}")
            logger.debug(f"API参数: {copy_payload}")
            
            copy_response = requests.post(copy_url, json=copy_payload, headers=headers, timeout=60)
            
            if copy_response.status_code == 200:
                copy_result = copy_response.json()
                if copy_result.get("code") == 200:
                    # 复制成功，只记录关键日志
                    logger.debug(f"成功复制文件: {source_file_path} -> {target_file_path}")
                    return {
                        "name": file_name,
                        "size": file_item['size'],
                        "path": target_file_path,
                        "source_path": source_file_path,
                        "is_media": is_media,
                        "status": "success"
                    }
                else:
                    # 复制失败，处理不同的错误情况
                    error_msg = copy_result.get("message", "复制失败")
                    if "exists" in error_msg.lower() or "already" in error_msg.lower():
                        # 文件已存在，跳过该文件
                        logger.debug(f"跳过已存在的文件: {target_file_path}")
                        return {
                            "name": file_name,
                            "size": file_item['size'],
                            "path": target_file_path,
                            "source_path": source_file_path,
                            "is_media": is_media,
                            "status": "skipped",
                            "error": "文件已存在"
                        }
                    else:
                        # 其他错误，记录失败
                        logger.error(f"复制文件失败: {source_file_path} -> {target_file_path}，错误: {error_msg}")
                        return {
                            "name": file_name,
                            "size": file_item['size'],
                            "path": target_file_path,
                            "source_path": source_file_path,
                            "is_media": is_media,
                            "status": "failed",
                            "error": error_msg
                        }
            else:
                # HTTP错误
                error_msg = f"HTTP错误 {copy_response.status_code}"
                logger.error(f"复制文件失败: {source_file_path} -> {target_file_path}，HTTP状态码: {copy_response.status_code}")
                return {
                    "name": file_name,
                    "size": file_item['size'],
                    "path": target_file_path,
                    "source_path": source_file_path,
                    "is_media": is_media,
                    "status": "failed",
                    "error": error_msg
                }
        except Exception as e:
            # 异常错误
            error_msg = str(e)
            logger.error(f"复制文件失败: {source_file_path} -> {target_file_path}，异常: {error_msg}")
            import traceback
            logger.debug(f"异常详情: {traceback.format_exc()}")
            return {
                "name": file_name,
                "size": file_item['size'],
                "path": target_file_path,
                "source_path": source_file_path,
                "is_media": is_media,
                "status": "failed",
                "error": error_msg
            }

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
