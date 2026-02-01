# 标准库导入
from typing import Any, Dict, List, Optional, Tuple, Set
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

# 第三方库导入
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# 项目导入
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

# 缓存相关常量
FILE_LIST_CACHE_TTL = 300  # 文件列表缓存有效期（秒）
CONFIG_CACHE_TTL = 600  # 配置缓存有效期（秒）
STATUS_CACHE_TTL = 30  # 状态缓存有效期（秒）

# 缓存装饰器
def cached(cache_name, ttl):
    """缓存装饰器"""
    def decorator(func):
        async def wrapper(self, *args, **kwargs):
            # 构建缓存键
            cache_key = f"{cache_name}:{':'.join(map(str, args))}:{':'.join(map(str, kwargs.items()))}"
            cache_key = hashlib.md5(cache_key.encode()).hexdigest()
            
            # 检查缓存
            if hasattr(self, '_cache') and cache_key in self._cache:
                cached_data = self._cache[cache_key]
                if time.time() - cached_data['timestamp'] < ttl:
                    return cached_data['data']
            
            # 执行函数
            result = await func(self, *args, **kwargs)
            
            # 缓存结果
            if not hasattr(self, '_cache'):
                self._cache = {}
            self._cache[cache_key] = {
                'data': result,
                'timestamp': time.time()
            }
            
            return result
        return wrapper
    return decorator


class OpenListVueConfig(BaseModel):
    enable: bool = False
    openlist_url: str = ""
    openlist_token: str = ""
    directory_pairs: str = ""
    enable_custom_suffix: bool = False
    custom_suffix: str = ""
    cron: str = "30 3 * * *"
    use_moviepilot_config: bool = False
    enable_wechat_notify: bool = False
    onlyonce: bool = False
    clear_cache: bool = False


class OpenListVue(_PluginBase):
    """
    OpenList管理Vue插件 - 基于Vue框架的OpenList管理插件
    """
    # 插件基本信息
    plugin_name = "OpenList管理Vue"
    plugin_desc = "基于Vue框架的OpenList多元化管理插件。"
    plugin_icon = "Alist_B.png"
    plugin_version = "1.0"
    plugin_author = "LittlePigeno"
    author_url = "https://github.com/LittlePigeno217/MoviePilot-Plugins"
    plugin_config_prefix = "openlistvue_"
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
        self._usemoviepilotconfig = False
        self._notify = False

        # 实例属性
        self._openlist_instance: Any = None
        self._notification_helper: Any = None

        # 状态数据
        self._task_status: Dict[str, Any] = {}
        self._copied_files: Dict[str, Any] = {}
        self._target_files_count: int = 0
        # 文件标识统计数据
        self._file_identifier_stats: Dict[str, int] = {
            "total": 0,
            "completed": 0,
            "copying": 0
        }
        
        # 缓存
        self._cache: Dict[str, Dict[str, Any]] = {}
        
        # 批量保存相关
        self._last_save_time: float = 0
        self._save_interval: float = 5.0  # 保存间隔（秒）
        
        # JSON文件路径（保存在data子目录中）
        self._json_file_path: Path = self._plugin_dir / "data" / "openlistvue_stats.json"
        

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
    

    
    def _get_file_identifier(self, source_file: dict, source_dir: str, target_dir: str) -> str:
        """获取文件的唯一标识"""
        try:
            # 获取文件路径
            source_path = source_file.get("path")
            if not source_path:
                return self._generate_file_key(source_path or "", target_dir)
            
            # 生成基于路径的文件标识
            relative_path = self._get_relative_path(source_path, source_dir)
            target_path = os.path.join(target_dir, relative_path).replace('\\', '/')
            return self._generate_file_key(source_path, target_path)
        except Exception as e:
            logger.error(f"获取文件唯一标识失败: {str(e)}")
            # 回退到基本标识生成方法
            source_path = source_file.get("path", "")
            return self._generate_file_key(source_path, target_dir)
    
    def _migrate_file_identifiers(self) -> str:
        """迁移旧的文件标识格式到新格式"""
        try:
            migrated_count = 0
            new_copied_files = {}
            
            for old_key, file_info in self._copied_files.items():
                # 尝试从文件信息中重建标识
                source_path = file_info.get("source_path")
                target_path = file_info.get("target_path")
                if source_path and target_path:
                    try:
                        # 生成基于路径的文件标识
                        new_key = self._generate_file_key(source_path, target_path)
                        if new_key != old_key:
                            new_copied_files[new_key] = file_info
                            migrated_count += 1
                        else:
                            new_copied_files[old_key] = file_info
                    except Exception as e:
                        # 如果无法生成新标识，保留旧标识
                        logger.error(f"迁移文件标识失败: {str(e)}")
                        new_copied_files[old_key] = file_info
                else:
                    # 如果缺少必要信息，保留旧标识
                    new_copied_files[old_key] = file_info
            
            # 更新复制文件记录
            if migrated_count > 0:
                self._copied_files = new_copied_files
                self.save_data("openlistvue_copied_files", self._copied_files)
                return f"共迁移 {migrated_count} 个文件标识"
            else:
                return "无需迁移"
        except Exception as e:
            logger.error(f"文件标识迁移失败: {str(e)}")
            return "迁移失败"


    def init_plugin(self, config: dict = None):
        """初始化插件"""
        self.stop_service()

        if config:
            # 更新配置 - 同时处理 enable 和 enabled 字段
            self._enable = config.get('enabled', config.get('enable', False))
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
        migration_result = "无需迁移"
        incorrect_formats = []
        
        try:
            task_status_data = self.get_data("openlistvue_task_status")
            if isinstance(task_status_data, dict):
                self._task_status = task_status_data
            else:
                incorrect_formats.append("任务状态数据")
                self._task_status = self._get_default_task_status()
        except Exception as e:
            logger.error(f"加载任务状态失败: {str(e)}")
            self._task_status = self._get_default_task_status()
        
        try:
            copied_files_data = self.get_data("openlistvue_copied_files")
            if isinstance(copied_files_data, dict):
                self._copied_files = copied_files_data
                # 数据迁移：将旧的文件标识格式迁移到新格式
                migration_result = self._migrate_file_identifiers()
            else:
                incorrect_formats.append("复制文件记录")
                self._copied_files = {}
        except Exception as e:
            logger.error(f"加载复制文件记录失败: {str(e)}")
            self._copied_files = {}
        
        try:
            target_files_count_data = self.get_data("openlistvue_target_files_count")
            if isinstance(target_files_count_data, int):
                self._target_files_count = target_files_count_data
            else:
                incorrect_formats.append("目标文件数")
                self._target_files_count = 0
        except Exception as e:
            logger.error(f"加载目标文件数失败: {str(e)}")
            self._target_files_count = 0
        
        try:
            file_identifier_stats_data = self.get_data("openlistvue_file_identifier_stats")
            if isinstance(file_identifier_stats_data, dict):
                self._file_identifier_stats = file_identifier_stats_data
            else:
                incorrect_formats.append("文件标识统计数据")
                self._update_file_identifier_stats()
        except Exception as e:
            logger.error(f"加载文件标识统计数据失败: {str(e)}")
            self._update_file_identifier_stats()
        
        # 记录合并后的警告日志
        if incorrect_formats:
            logger.warning(f"以下数据格式不正确，已使用默认值: {', '.join(incorrect_formats)}")

        logger.info(f"插件状态数据恢复完成: 任务状态={self._task_status.get('status')}, " \
                   f"复制文件记录={len(self._copied_files)}个, 目标文件数={self._target_files_count}, "
                   f"文件标识迁移结果={migration_result}")
        
        # 将统计数据写入JSON文件
        self._write_stats_to_json()

        # 初始化调度器
        self._scheduler = BackgroundScheduler(timezone=settings.TZ)
        
        # 添加定时任务
        if self._enable and self._cron:
            try:
                self._scheduler.add_job(
                    func=self.execute_copy_task,
                    trigger=CronTrigger.from_crontab(self._cron),
                    name=self.plugin_name
                )
            except Exception as err:
                logger.error(f"定时任务配置错误: {err}")

        # 立即执行一次
        if self._onlyonce:
            logger.info("开始执行OpenList管理任务")
            import threading
            threading.Thread(target=self.execute_copy_task, daemon=True).start()
            self._onlyonce = False
            self._update_config()

        # 启动调度器
        if self._enable:
            if self._scheduler.get_jobs():
                self._scheduler.start()
                logger.info(f"已按 CRON '{self._cron}' 计划定时任务并启动调度器")
            else:
                logger.info("插件已启用，但未设置定时任务")
        else:
            logger.info("插件已禁用")

    def _init_moviepilot_openlist(self):
        """初始化MoviePilot OpenList实例"""
        if not ALIST_AVAILABLE:
            logger.warning("OpenList模块不可用，请确保安装了正确版本的MoviePilot")
            return
            
        try:
            self._openlist_instance = Alist()
            
            if self._usemoviepilotconfig:
                self._update_openlist_config_from_instance()
                
        except Exception as e:
            logger.error(f"初始化OpenList实例失败: {str(e)}")

    def _update_openlist_config_from_instance(self):
        """从MoviePilot OpenList实例更新配置"""
        if not self._openlist_instance:
            logger.warning("OpenList实例未初始化，无法从MoviePilot获取配置")
            return
            
        try:
            # 保存当前配置，作为后备
            original_url = self._openlist_url
            original_token = self._openlist_token
            
            # 尝试获取配置，使用 MoviePilot Alist 实例的方法
            base_url = None
            token = None
            
            # 方法2: 尝试访问可能的私有属性
            # 记录使用的属性名
            used_url_attr = None
            used_token_attr = None
            
            # 尝试不同的私有属性名获取地址
            private_url_attrs = ['_Alist__get_base_url', '_base_url', 'baseurl', 'url']
            for attr_name in private_url_attrs:
                if hasattr(self._openlist_instance, attr_name):
                    base_url = getattr(self._openlist_instance, attr_name)
                    if base_url:
                        self._openlist_url = base_url.rstrip('/')
                        used_url_attr = attr_name
                        break
            
            # 尝试不同的私有属性名获取Token
            private_token_attrs = ['_Alist__get_valuable_toke', '_token', 'token', 'authorization']
            for attr_name in private_token_attrs:
                if hasattr(self._openlist_instance, attr_name):
                    token = getattr(self._openlist_instance, attr_name)
                    if token:
                        self._openlist_token = token
                        used_token_attr = attr_name
                        break
            
            # 合并日志
            config_status = ""
            if base_url and token:
                config_status = f"Url: 已获取, Token: 已获取"
            elif base_url:
                config_status = f"Url: 已获取, Token: 未获取"
            elif token:
                config_status = f"Url: 未获取, Token: 已获取"
            
            # 如果无法从MoviePilot OpenList实例获取配置，使用用户配置的值
            if not base_url:
                logger.warning("无法从OpenList实例获取地址，使用用户配置的值")
                if not self._openlist_url:
                    self._openlist_url = original_url
            
            if not token:
                logger.warning("无法从OpenList实例获取Token，使用用户配置的值")
                if not self._openlist_token:
                    self._openlist_token = original_token
            
            # 成功获取地址和令牌后，立即验证连接
            auth_status = "未验证"
            if self._openlist_url and self._openlist_token:
                auth_status = "OpenList认证成功" if self._verify_openlist_connection() else "OpenList认证失败"
            
            # 只有在成功初始化和获取配置时才记录日志
            if config_status:
                logger.info(f"OpenList实例初始化成功，{config_status}，{auth_status}")
                
        except Exception as e:
            logger.error(f"从OpenList实例获取配置失败: {str(e)}")


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
        self._file_identifier_stats = {
            "total": 0,
            "completed": 0,
            "copying": 0
        }
        self._previous_completed_count = 0
        self._previous_completed_files = []
        
        self.save_data("openlistvue_task_status", self._task_status)
        self.save_data("openlistvue_copied_files", self._copied_files)
        self.save_data("openlistvue_target_files_count", self._target_files_count)
        self.save_data("openlistvue_file_identifier_stats", self._file_identifier_stats)

    def get_state(self) -> bool:
        """获取插件状态"""
        return self._enable

    # --- API 端点方法 ---
    def _get_config(self) -> Dict[str, Any]:
        """API 端点：返回当前插件配置"""
        # 构建缓存键
        cache_key = f"config:{self._enable}:{self._openlist_url}:{self._cron}"
        cache_key = hashlib.md5(cache_key.encode()).hexdigest()
        
        # 检查缓存
        if cache_key in self._cache:
            cached_data = self._cache[cache_key]
            if time.time() - cached_data['timestamp'] < CONFIG_CACHE_TTL:
                return cached_data['data']
        
        # 优化后的配置结构，移除冗余字段和敏感信息
        config_data = {
            "enabled": self._enable,
            "openlist_url": self._openlist_url,
            "directory_pairs": self._directory_pairs,
            "enable_custom_suffix": self._enablecustomsuffix,
            "use_moviepilot_config": self._usemoviepilotconfig,
            "enable_wechat_notify": self._notify,
            "cron": self._cron,
            "openlist_token_set": bool(self._openlist_token)  # 只返回令牌是否设置，不返回实际令牌
        }
        
        # 为了保持向后兼容性，添加旧字段
        config_data["enable"] = self._enable  # 保持 enable 字段
        
        # 缓存结果
        self._cache[cache_key] = {
            'data': config_data,
            'timestamp': time.time()
        }
        
        return config_data

    def _save_config(self, config_payload: dict) -> Dict[str, Any]:
        """API 端点：保存插件配置"""
        try:
            # 输入验证
            if not isinstance(config_payload, dict):
                logger.error("配置数据类型错误")
                return {"message": "配置数据类型错误", "error": True, "saved_config": self._get_config()}
            
            # 安全日志记录 - 不记录敏感信息
            sanitized_payload = config_payload.copy()
            if 'openlist_token' in sanitized_payload:
                sanitized_payload['openlist_token'] = '***'
            logger.info(f"收到配置保存请求: {sanitized_payload}")
            
            # 更新配置属性 - 同时处理 enable 和 enabled 字段
            self._enable = bool(config_payload.get('enabled', config_payload.get('enable', self._enable)))
            self._cron = str(config_payload.get('cron', self._cron))
            
            # 验证 URL 格式
            openlist_url = config_payload.get('openlist_url', self._openlist_url)
            if openlist_url:
                if not openlist_url.startswith(('http://', 'https://')):
                    logger.error("OpenList URL 格式错误")
                    return {"message": "OpenList URL 格式错误，必须以 http:// 或 https:// 开头", "error": True, "saved_config": self._get_config()}
                self._openlist_url = openlist_url
            else:
                self._openlist_url = openlist_url
            
            # 安全处理令牌
            self._openlist_token = str(config_payload.get('openlist_token', self._openlist_token))
            
            # 验证目录配对格式
            directory_pairs = config_payload.get('directory_pairs', self._directory_pairs)
            if directory_pairs:
                # 基本格式验证
                lines = directory_pairs.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if line:
                        if '#' not in line:
                            logger.error("目录配对格式错误，缺少 # 分隔符")
                            return {"message": "目录配对格式错误，请确保每行格式为 '源目录 # 目标目录'", "error": True, "saved_config": self._get_config()}
                        parts = line.split('#', 1)
                        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
                            logger.error("目录配对格式错误")
                            return {"message": "目录配对格式错误，请确保每行格式为 '源目录 # 目标目录'", "error": True, "saved_config": self._get_config()}
            self._directory_pairs = directory_pairs
            
            # 其他配置
            self._enablecustomsuffix = bool(config_payload.get('enable_custom_suffix', self._enablecustomsuffix))
            self._usemoviepilotconfig = bool(config_payload.get('use_moviepilot_config', self._usemoviepilotconfig))
            self._notify = bool(config_payload.get('enable_wechat_notify', self._notify))
            
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
            
            # 清除缓存
            self._cache.clear()
            
            # 重新初始化插件
            self.stop_service()
            self.init_plugin(config_to_save)
            
            return {"message": "配置已成功保存", "saved_config": self._get_config()}
        except Exception as e:
            error_msg = f"保存配置时发生错误: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"message": error_msg, "error": True, "saved_config": self._get_config()}

    def _get_status(self) -> Dict[str, Any]:
        """API 端点：返回当前插件状态和历史"""
        # 构建缓存键
        cache_key = f"status:{self._enable}:{self._cron}:{self._task_status.get('status')}:{len(self._copied_files)}"
        cache_key = hashlib.md5(cache_key.encode()).hexdigest()
        
        # 检查缓存
        if cache_key in self._cache:
            cached_data = self._cache[cache_key]
            if time.time() - cached_data['timestamp'] < STATUS_CACHE_TTL:
                return cached_data['data']
        
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

        # 获取文件标识统计信息
        file_identifier_stats = self._get_file_identifier_stats()
        
        status_data = {
            "enabled": self._enable,
            "cron": self._cron,
            "next_run_time": next_run_time,
            "task_status": self._task_status,
            "copied_files_count": len(self._copied_files),
            "target_files_count": self._target_files_count,
            "file_identifier_stats": file_identifier_stats
        }
        
        # 缓存结果
        self._cache[cache_key] = {
            'data': status_data,
            'timestamp': time.time()
        }
        
        return status_data

    def _run_task(self) -> Dict[str, Any]:
        """API 端点：触发手动复制任务"""
        logger.info(f"{self.plugin_name}: 收到手动执行任务请求")
        if not self._enable:
            logger.warning(f"{self.plugin_name}: 插件当前已禁用，无法执行任务")
            return {"message": "插件已禁用，无法执行任务", "error": True}
        
        try:
            import threading
            threading.Thread(target=self.execute_copy_task, daemon=True).start()
            
            # 清除状态缓存，确保下次获取状态时能获取到最新值
            self._cache.clear()
            
            return {"message": "任务已开始执行"}
        except Exception as e:
            logger.error(f"{self.plugin_name}: 启动任务失败: {e}")
            return {"message": f"启动任务失败: {e}", "error": True}

    def _clear_cache(self) -> Dict[str, Any]:
        """API 端点：清除插件缓存和文件标识"""
        logger.info(f"{self.plugin_name}: 收到清除缓存请求")
        try:
            # 调用 _clear_all_data 方法清除所有数据
            self._clear_all_data()
            
            # 清除内存缓存
            self._cache.clear()
            
            # 清空 data 文件夹内所有 JSON 文件
            try:
                # 获取 data 文件夹路径
                data_dir = self._plugin_dir / "data"
                if data_dir.exists() and data_dir.is_dir():
                    # 遍历 data 文件夹内的所有 JSON 文件
                    json_files = list(data_dir.glob("*.json"))
                    for json_file in json_files:
                        try:
                            with open(json_file, 'w', encoding='utf-8') as f:
                                json.dump({}, f)
                            logger.info(f"已清空 JSON 文件: {json_file}")
                        except Exception as file_error:
                            logger.error(f"清空 JSON 文件失败: {json_file}, 错误: {file_error}")
                else:
                    logger.info(f"data 文件夹不存在: {data_dir}")
            except Exception as json_error:
                logger.error(f"清空 JSON 文件失败: {json_error}")
            
            logger.info(f"{self.plugin_name}: 插件数据、缓存和文件标识已成功清除")
            return {"message": "缓存和文件标识已成功清除"}
        except Exception as e:
            logger.error(f"{self.plugin_name}: 清除缓存失败: {e}")
            return {"message": f"清除缓存失败: {e}", "error": True}



    def _get_combined_data(self) -> Dict[str, Any]:
        """API 端点：返回合并的配置、状态和认证信息"""
        # 获取配置
        config_data = self._get_config()
        
        # 获取状态
        status_data = self._get_status()
        
        # 获取认证状态
        auth_status = {
            "connected": False,
            "message": "未检查",
            "status": "未连接",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        try:
            if self._openlist_url and self._openlist_token:
                url = f"{self._openlist_url}/api/me"
                headers = {
                    "Authorization": self._openlist_token,
                    "Content-Type": "application/json"
                }
                
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                # 检查认证状态
                is_connected = data.get("code") == 200
                auth_status = {
                    "connected": is_connected,
                    "message": "连接成功" if is_connected else "连接失败",
                    "status": "通过" if is_connected else "未连接",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
        except Exception as e:
            auth_status = {
                "connected": False,
                "message": f"检查失败: {str(e)}",
                "status": "未连接",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        
        return {
            "config": config_data,
            "status": status_data,
            "auth": auth_status
        }

    def get_api(self) -> List[Dict[str, Any]]:
        """定义 API 端点"""
        return [
            {
                "path": "config",
                "endpoint": self._get_config,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取当前配置"
            },
            {
                "path": "config",
                "endpoint": self._save_config,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "保存配置"
            },
            {
                "path": "status",
                "endpoint": self._get_status,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取状态和任务信息"
            },
            {
                "path": "run",
                "endpoint": self._run_task,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "触发手动任务"
            },
            {
                "path": "combined",
                "endpoint": self._get_combined_data,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取合并的配置、状态和认证信息"
            },
            {
                "path": "clear_cache",
                "endpoint": self._clear_cache,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "清除插件缓存和文件标识"
            }
        ]

    # --- 基础方法实现 ---
    @staticmethod
    def get_render_mode() -> Tuple[str, Optional[str]]:
        """声明 Vue 渲染模式和资源路径"""
        return "vue", "dist/assets"

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

    def _update_file_status_and_counts(self, silent: bool = False):
        """更新媒体文件状态和数量统计（优化版）"""
        if not self._copied_files:
            return
            
        directory_pairs = self._parse_directory_pairs()
        if not directory_pairs:
            return
            
        if not silent:
            logger.info("更新媒体文件状态...")
        
        # 构建目标目录映射，避免重复遍历
        target_dir_map = {}
        for pair in directory_pairs:
            target_dir = self._normalize_path(pair["target"])
            if target_dir not in target_dir_map:
                target_dir_map[target_dir] = True
        
        # 为每个目标目录构建媒体文件索引（仅构建一次）
        target_dirs_index = {}
        for target_dir in target_dir_map:
            target_files = self._get_openlist_files(target_dir)
            if target_files:
                # 构建媒体文件名集合（使用集合提高查找效率）
                file_set = set()
                for file in target_files:
                    filename = file.get("name")
                    if filename and self._is_media_file(filename):
                        file_set.add(filename)
                target_dirs_index[target_dir] = file_set
            else:
                target_dirs_index[target_dir] = set()
        
        # 检查每个媒体文件的状态并更新
        updated_count = 0
        files_to_update = {}
        
        for file_key, record in self._copied_files.items():
            target_path = record.get("target_path", "")
            filename = record.get("filename", "")
            current_status = record.get("status", "copying")
            
            if not target_path or not filename:
                continue
                
            # 找到对应的目标目录（优化查找逻辑）
            target_dir = None
            normalized_target_path = self._normalize_path(target_path)
            
            for candidate_dir in target_dir_map:
                if normalized_target_path.startswith(candidate_dir):
                    target_dir = candidate_dir
                    break
            
            if not target_dir:
                continue
                
            # 检查媒体文件是否在目标目录中存在
            file_exists = target_dir in target_dirs_index and filename in target_dirs_index[target_dir]
            
            if file_exists and current_status != "completed":
                # 文件在目标目录中存在，更新状态为已完成
                files_to_update[file_key] = {
                    "status": "completed",
                    "completed_time": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                updated_count += 1
            elif not file_exists and current_status == "completed":
                # 文件不在目标目录中，更新状态为复制中
                logger.info(f"已完成文件 {filename} 不在目标目录中，状态更新为复制中")
                files_to_update[file_key] = {
                    "status": "copying"
                }
                updated_count += 1
        
        # 批量更新文件状态
        for file_key, updates in files_to_update.items():
            self._copied_files[file_key].update(updates)
            # 移除完成时间（如果状态变为复制中）
            if updates.get("status") == "copying" and "completed_time" in self._copied_files[file_key]:
                del self._copied_files[file_key]["completed_time"]
        
        if updated_count > 0:
            if not silent:
                logger.info(f"已更新 {updated_count} 个媒体文件的状态")
            # 保存更新后的复制文件记录
            self._save_copied_files()
        
        # 更新目标目录媒体文件数
        self._update_target_files_count(directory_pairs, silent=True)
    
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
    
    def _update_file_identifier_stats(self):
        """更新文件标识统计数据"""
        total_count = len(self._copied_files)
        completed_count = 0
        copying_count = 0
        
        for record in self._copied_files.values():
            status = record.get("status", "copying")
            if status == "completed":
                completed_count += 1
            else:
                copying_count += 1
        
        self._file_identifier_stats = {
            "total": total_count,
            "completed": completed_count,
            "copying": copying_count
        }
    
    def _get_file_identifier_stats(self) -> Dict[str, int]:
        """获取文件标识统计信息"""
        # 先更新统计数据
        self._update_file_identifier_stats()
        return self._file_identifier_stats
    
    def _write_stats_to_json(self):
        """将复制文件记录和目标文件数写入JSON文件"""
        try:
            # 确保data目录存在
            data_dir = self._plugin_dir / "data"
            if not data_dir.exists():
                data_dir.mkdir(exist_ok=True)
                logger.info(f"创建data目录: {data_dir}")
            
            # 清理旧的JSON文件（如果存在于插件根目录）
            old_json_path = self._plugin_dir / "openlistvue_stats.json"
            if old_json_path.exists():
                old_json_path.unlink()
                logger.info(f"清理旧的JSON文件: {old_json_path}")
            
            # 清理data目录中可能存在的其他JSON文件，只保留我们的主文件
            for json_file in data_dir.glob("*.json"):
                if json_file != self._json_file_path:
                    json_file.unlink()
                    logger.info(f"清理多余的JSON文件: {json_file}")
            
            # 更新统计数据
            self._update_file_identifier_stats()
            
            # 构建统计数据
            stats_data = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "copied_files_count": len(self._copied_files),
                "target_files_count": self._target_files_count,
                "file_identifier_stats": self._file_identifier_stats,
                "copied_files": self._copied_files
            }
            
            # 写入JSON文件
            with open(self._json_file_path, 'w', encoding='utf-8') as f:
                json.dump(stats_data, f, ensure_ascii=False, indent=2)
            
            logger.info("统计数据已记录")
        except Exception as e:
            logger.error(f"写入JSON文件失败: {str(e)}")
    

    
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
        logger.info("开始执行OpenList多目录复制任务")
        
        directory_pairs = []
        try:
            # 更新配置（如果使用MoviePilot配置）
            self._update_openlist_config_if_needed()
            
            # 验证配置和解析目录对
            directory_pairs = self._validate_and_parse_directory_pairs()
            if not directory_pairs:
                logger.info("未配置有效的目录配对，任务终止")
                return
            
            # 准备任务状态
            self._prepare_task_status()
            
            # 检查是否需要执行复制任务
            if not self._should_execute_copy_task(directory_pairs):
                self._handle_no_task_execution(directory_pairs)
                return
            
            # 初始化任务执行
            successfully_copied_files = []
            self._initialize_task_execution(directory_pairs)
            
            # 执行复制任务
            execution_result = self._execute_copy_operations(directory_pairs, successfully_copied_files)
            
            # 处理任务完成
            self._handle_task_completion(execution_result, successfully_copied_files, directory_pairs)
            
        except Exception as e:
            error_msg = f"复制任务执行失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self._complete_task("failed", error_msg)
        finally:
            # 处理任务结束后的清理工作
            self._handle_task_cleanup(directory_pairs)

    def _update_openlist_config_if_needed(self):
        """如果需要，从MoviePilot实例更新OpenList配置"""
        if self._usemoviepilotconfig and self._openlist_instance:
            self._update_openlist_config_from_instance()

    def _validate_and_parse_directory_pairs(self):
        """验证配置并解析目录对"""
        if not self._validate_config():
            directory_pairs = self._parse_directory_pairs()
            if directory_pairs:
                self._update_target_files_count(directory_pairs, silent=True)
            return []
            
        directory_pairs = self._parse_directory_pairs()
        if not directory_pairs:
            self._complete_task("failed", "未配置有效的目录配对")
            self._update_target_files_count(directory_pairs, silent=True)
        
        return directory_pairs

    def _prepare_task_status(self):
        """准备任务状态，记录当前已完成文件信息"""
        _, old_completed_count = self._get_file_status_counts()
        self._previous_completed_count = old_completed_count
        self._previous_completed_files = self._get_completed_files_list()

    def _handle_no_task_execution(self, directory_pairs):
        """处理无需执行复制任务的情况"""
        logger.info("无需执行复制任务")
        self._update_target_files_count(directory_pairs, silent=True)
        
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

    def _initialize_task_execution(self, directory_pairs):
        """初始化任务执行状态"""
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
        
        # 验证OpenList连接
        if not self._verify_openlist_connection():
            raise Exception("OpenList连接失败，请检查地址和令牌")

    def _execute_copy_operations(self, directory_pairs, successfully_copied_files):
        """执行复制操作并返回结果"""
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
        
        return {
            "total_copied": total_copied,
            "total_skipped": total_skipped,
            "total_files": total_files,
            "directory_pairs_count": len(directory_pairs)
        }

    def _handle_task_completion(self, execution_result, successfully_copied_files, directory_pairs):
        """处理任务完成"""
        # 更新文件状态和计数
        self._update_file_status_and_counts(silent=True)
        
        # 计算本次执行新增的完成文件数量
        _, new_completed_count = self._get_file_status_counts()
        increased_completed_count = new_completed_count - self._previous_completed_count
        
        newly_completed_files = self._get_newly_completed_files()
        
        # 发送通知（如果需要）
        should_send_notification = (
            self._notify and 
            (execution_result["total_copied"] > 0 or increased_completed_count > 0)
        )
        
        if should_send_notification:
            self._send_notification(execution_result["total_copied"], increased_completed_count, 
                                   successfully_copied_files, newly_completed_files)
        
        # 完成任务
        self._complete_task("success", 
                           f"复制完成！共处理 {execution_result['directory_pairs_count']} 组目录配对，" 
                           f"总计 {execution_result['total_files']} 个媒体文件，" 
                           f"复制 {execution_result['total_copied']} 个，" 
                           f"跳过 {execution_result['total_skipped']} 个，" 
                           f"新增完成 {increased_completed_count} 个")

    def _handle_task_cleanup(self, directory_pairs):
        """处理任务结束后的清理工作"""
        # 处理立即运行任务的清理
        if self._onlyonce:
            self._onlyonce = False
            self._update_config()
            logger.info("立即运行任务已完成")
        
        # 无论任务是否成功，都更新目标目录媒体文件数
        if directory_pairs:
            self._update_target_files_count(directory_pairs, silent=True)

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
        """判断是否需要执行复制任务"""
        # 检查是否有复制中的媒体文件
        copying_count, completed_count = self._get_file_status_counts()
        if copying_count > 0:
            logger.info(f"检测到 {copying_count} 个复制中的媒体文件，需要继续执行")
            return True
        
        # 检查是否有已完成但不存在于目标目录的文件
        if completed_count > 0:
            # 快速检查：如果有已完成文件，执行状态更新检查
            # 这会在状态更新时自动将不存在的文件标记为复制中
            self._update_file_status_and_counts(silent=True)
            # 重新获取状态，查看是否有新的复制中文件
            new_copying_count, _ = self._get_file_status_counts()
            if new_copying_count > 0:
                logger.info(f"检测到 {new_copying_count} 个需要重新复制的文件")
                return True
        
        # 检查源目录是否有新媒体文件需要复制
        
        
        current_suffixes = self._get_current_suffixes()
        
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
                target_index = self._build_target_index(target_files)
                
                # 检查源目录中是否有新媒体文件
                for source_file in source_files:
                    filename = source_file.get("name")
                    if not filename:
                        continue
                        
                    # 只处理媒体文件
                    if not any(filename.endswith(suffix) for suffix in current_suffixes):
                        continue
                    
                    # 检查媒体文件是否已经在目标目录中存在
                    if filename not in target_index:
                        logger.info(f"发现新媒体文件需要复制: {filename}")
                        return True
                        
            except Exception as e:
                logger.error(f"检查目录配对 {source_dir} → {target_dir} 时出错: {str(e)}")
                # 如果检查过程中出错，保守起见执行复制任务
                return True
        
        
        return False

    def _update_target_files_count(self, directory_pairs: List[Dict[str, str]], silent: bool = False):
        """更新目标目录媒体文件数统计（优化版）"""
        if not directory_pairs:
            self._target_files_count = 0
            self.save_data("openlistvue_target_files_count", self._target_files_count)
            return
            
        total_target_files = 0
        
        # 获取所有唯一的目标目录 - 使用标准化路径避免重复
        target_dirs = set()
        for pair in directory_pairs:
            # 标准化目标目录路径
            target_dir = self._normalize_path(pair["target"])
            target_dirs.add(target_dir)
        
        if not silent:
            logger.info(f"统计 {len(target_dirs)} 个目标目录的媒体文件数")
        
        # 批量处理：收集所有需要扫描的目录
        dirs_to_scan = []
        for target_dir in target_dirs:
            # 构建缓存键
            cache_key = f"file_count:{target_dir}"
            cache_key = hashlib.md5(cache_key.encode()).hexdigest()
            
            # 检查缓存
            if cache_key in self._cache:
                cached_data = self._cache[cache_key]
                if time.time() - cached_data['timestamp'] < FILE_LIST_CACHE_TTL:
                    total_target_files += cached_data['data']
                    continue
            
            dirs_to_scan.append(target_dir)
        
        # 扫描剩余目录
        for target_dir in dirs_to_scan:
            try:
                target_files = self._get_openlist_files(target_dir)
                if target_files:
                    # 只统计媒体文件（优化过滤逻辑）
                    file_count = 0
                    current_suffixes = self._get_current_suffixes()
                    for f in target_files:
                        filename = f.get("name", "")
                        if filename and any(filename.endswith(suffix) for suffix in current_suffixes):
                            file_count += 1
                else:
                    file_count = 0
                
                total_target_files += file_count
                
                # 缓存结果
                cache_key = f"file_count:{target_dir}"
                cache_key = hashlib.md5(cache_key.encode()).hexdigest()
                self._cache[cache_key] = {
                    'data': file_count,
                    'timestamp': time.time()
                }
                
            except Exception as e:
                logger.error(f"统计目标目录 {target_dir} 媒体文件数失败: {str(e)}")
        
        if not silent:
            logger.info(f"总计目标目录媒体文件数: {total_target_files}")
        
        # 只有当文件数发生变化时才保存
        if self._target_files_count != total_target_files:
            self._target_files_count = total_target_files
            self.save_data("openlistvue_target_files_count", self._target_files_count)

    def _execute_single_copy(self, source_dir: str, target_dir: str, pair_index: int, total_pairs: int, successfully_copied_files: List[str], global_processed_files: set) -> Optional[Dict[str, int]]:
        """执行单个目录配对复制（优化版）"""
        try:
            base_progress = int((pair_index) / total_pairs * 100)
            
            # 构建缓存键
            target_cache_key = f"file_list:{target_dir}"
            target_cache_key = hashlib.md5(target_cache_key.encode()).hexdigest()
            source_cache_key = f"file_list:{source_dir}"
            source_cache_key = hashlib.md5(source_cache_key.encode()).hexdigest()
            
            # 首先扫描目标目录，构建目标媒体文件索引
            self._update_status(f"正在扫描目标目录: {target_dir}", base_progress + 5)
            target_files = self._get_openlist_files(target_dir)
            target_index = self._build_target_index(target_files)
            
            # 然后扫描源目录
            self._update_status(f"正在扫描源目录: {source_dir}", base_progress + 15)
            source_files = self._get_openlist_files(source_dir)
            if not source_files:
                return {"copied": 0, "skipped": 0, "total": 0}
            
            # 过滤媒体文件（提前过滤，减少后续处理量）
            current_suffixes = self._get_current_suffixes()
            media_files = []
            for file in source_files:
                filename = file.get("name")
                if filename and any(filename.endswith(suffix) for suffix in current_suffixes):
                    media_files.append(file)
            
            if not media_files:
                return {"copied": 0, "skipped": 0, "total": 0}
            
            self._update_status(f"开始复制媒体文件: {source_dir} → {target_dir}", base_progress + 25)
            copy_result = self._copy_files(media_files, target_index, source_dir, target_dir, base_progress + 25, 70, successfully_copied_files, global_processed_files)
            
            return copy_result
            
        except Exception as e:
            logger.error(f"处理目录配对 {source_dir} → {target_dir} 时出错: {str(e)}")
            return {"copied": 0, "skipped": 0, "total": 0}

    def _build_target_index(self, target_files: List[dict]) -> set:
        """构建目标索引 - 使用完整媒体文件名"""
        index = set()
        
        if not target_files:
            return index
            
        current_suffixes = self._get_current_suffixes()
            
        for file in target_files:
            filename = file.get("name")
            if not filename:
                continue
                
            if any(filename.endswith(suffix) for suffix in current_suffixes):
                index.add(filename)  # 使用完整文件名
                
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
            
            # 检查认证状态
            is_connected = data.get("code") == 200
            
            # 添加日志记录
            if not is_connected:
                logger.warning(f"OpenList认证失败，返回码: {data.get('code')}")
            
            return is_connected
        except Exception as e:
            logger.error(f"OpenList连接验证失败: {str(e)}")
            return False

    async def _get_openlist_files_async(self, path: str) -> List[dict]:
        """异步获取OpenList目录文件列表"""
        try:
            # 构建缓存键
            cache_key = f"file_list:{path}"
            cache_key = hashlib.md5(cache_key.encode()).hexdigest()
            
            # 检查缓存
            if cache_key in self._cache:
                cached_data = self._cache[cache_key]
                if time.time() - cached_data['timestamp'] < FILE_LIST_CACHE_TTL:

                    return cached_data['data']
            
            # 验证OpenList配置
            if not self._openlist_url or not self._openlist_token:
                logger.error("OpenList配置不完整，无法获取文件列表")
                return []
            
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
                error_msg = f"获取目录 {path} 文件失败: {result.get('message')}"
                logger.error(error_msg)
                return []
                
            data_content = result.get("data", {})
            content = data_content.get("content") if data_content else None
            
            if content is None:

                return []
                
            if not isinstance(content, list):
                error_msg = f"目录 {path} 返回的content不是列表类型: {type(content)}"
                logger.error(error_msg)
                return []
                
            files = []
            
            for item in content:
                if not isinstance(item, dict):
                    continue
                    
                # 检查文件名是否为空
                item_name = item.get('name')
                if not item_name:
                    logger.warning(f"跳过空文件名: {item}")
                    continue
                    
                if item.get("is_dir"):
                    sub_path = f"{path.rstrip('/')}/{item_name}"
                    try:
                        sub_files = await self._get_openlist_files_async(sub_path)
                        files.extend(sub_files)
                    except Exception as sub_e:
                        logger.error(f"获取子目录 {sub_path} 文件失败: {str(sub_e)}")
                else:
                    files.append({
                        "name": item_name,
                        "path": f"{path.rstrip('/')}/{item_name}",
                        "size": item.get("size"),
                        "modified": item.get("modified")
                    })
            
            # 缓存结果
            self._cache[cache_key] = {
                'data': files,
                'timestamp': time.time()
            }

                    
            return files
            
        except requests.RequestException as e:
            error_msg = f"网络请求失败: {str(e)}"
            logger.error(error_msg)
            return []
        except json.JSONDecodeError as e:
            error_msg = f"JSON解析失败: {str(e)}"
            logger.error(error_msg)
            return []
        except Exception as e:
            error_msg = f"获取文件列表失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return []

    def _get_openlist_files(self, path: str) -> List[dict]:
        """获取OpenList目录文件列表（同步版本）"""
        return asyncio.run(self._get_openlist_files_async(path))

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
                
                # 生成文件唯一标识 - 使用统一的文件标识系统
                file_key = self._get_file_identifier(source_file, source_dir, target_dir)
                
                # 检查1: 媒体文件是否已经在本次任务执行中处理过
                if file_key in global_processed_files:
                    skipped += 1
                    continue
                
                # 检查2: 媒体文件是否在历史记录中已经复制过
                if file_key in self._copied_files:
                    # 检查文件记录状态
                    record_info = self._copied_files[file_key]
                    record_status = record_info.get("status", "copying")
                    
                    if record_status == "completed":
                        # 媒体文件已完成复制，跳过
                        skipped += 1
                        continue
                    else:
                        # 媒体文件状态为复制中，跳过复制但保留记录
                        skipped += 1
                        continue
                
                # 检查3: 目标目录是否已存在相同媒体文件（基于完整文件名比对）
                if filename in target_index:
                    skipped += 1
                    continue
                    
                # 执行复制操作
                if self._execute_openlist_copy_standard(source_path, target_path, filename):
                    copied += 1
                    self._task_status["copied_files"] += 1
                    
                    # 记录成功复制的媒体文件，默认状态为复制中
                    self._copied_files[file_key] = {
                        "source_path": source_path,
                        "target_path": target_path,
                        "filename": filename,
                        "copied_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "status": "copying"  # 默认状态为复制中
                    }
                    self._save_copied_files()  # 立即保存，避免重复复制
                    
                    # 添加到全局已处理媒体文件集合
                    global_processed_files.add(file_key)
                    
                    # 记录成功复制的媒体文件名
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

    def _directory_exists(self, directory: str) -> bool:
        """检查目录是否存在"""
        try:
            if not directory:
                logger.error("检查目录失败: 目录路径为空")
                return False
            
            # 构建请求获取目录信息
            url = f"{self._openlist_url}/api/fs/get"
            headers = {
                "Authorization": self._openlist_token,
                "Content-Type": "application/json"
            }
            data = {"path": directory}
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") == 200:
                # 检查返回的数据是否为目录
                data_info = result.get("data", {})
                is_dir = data_info.get("is_dir", False)
                return is_dir
            elif "path not found" in result.get("message", "").lower() or "not exist" in result.get("message", "").lower():
                # 目录不存在
                return False
            else:
                logger.error(f"检查目录失败: {result.get('message')}")
                return False
        except Exception as e:
            logger.error(f"检查目录存在性失败: {str(e)}")
            return False

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

    def _create_directory(self, directory: str) -> bool:
        """创建目录 - 基于 OpenList API"""
        try:
            if not directory:
                logger.error("创建目录失败: 目录路径为空")
                return False
            
            # 构建 API URL
            url = f"{self._openlist_url}/api/fs/mkdir"
            headers = {
                "Authorization": self._openlist_token,
                "Content-Type": "application/json"
            }
            
            # 构建请求体
            data = {"path": directory}
            
            # 发送请求
            response = requests.post(url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            # 解析响应
            result = response.json()
            
            # 处理响应
            if result.get("code") == 200:
                logger.info(f"目录创建成功: {directory}")
                return True
            else:
                error_message = result.get("message", "未知错误")
                logger.error(f"目录创建失败: {error_message}")
                return False
        except Exception as e:
            logger.error(f"创建目录失败: {str(e)}")
            return False

    def _copy_file_with_relative_dir(self, source_path: str, target_dir: str, relative_dir: str) -> bool:
        """复制文件到带相对目录的目标路径 - 基于 OpenList API"""
        try:
            # 检查参数
            if not source_path:
                logger.error("复制文件失败: 源路径为空")
                return False
            
            if not target_dir:
                logger.error("复制文件失败: 目标目录为空")
                return False
            
            # 获取文件名
            source_filename = source_path.split('/')[-1]
            if not source_filename:
                logger.error("复制文件失败: 源文件名为空")
                return False
            
            # 构建完整的目标路径
            if relative_dir:
                full_target_dir = os.path.join(target_dir, relative_dir).replace('\\', '/')
            else:
                full_target_dir = target_dir
            
            full_target_path = os.path.join(full_target_dir, source_filename).replace('\\', '/')
            
            # 确保相对目录存在
            if relative_dir:
                # 递归创建目录结构
                dir_parts = relative_dir.split('/')
                current_dir = target_dir
                for part in dir_parts:
                    if part:
                        current_dir = os.path.join(current_dir, part).replace('\\', '/')
                        # 检查并创建目录
                        self._create_directory(current_dir)
            
            # 构建 API URL
            url = f"{self._openlist_url}/api/fs/copy"
            headers = {
                "Authorization": self._openlist_token,
                "Content-Type": "application/json"
            }
            
            # 构建请求体 - 符合 Alist API 格式
            # 从源路径中提取源目录和文件名
            if '/' in source_path:
                src_dir = '/'.join(source_path.split('/')[:-1])
                if not src_dir:
                    src_dir = '/'
            else:
                src_dir = '/'
            
            data = {
                "src_dir": src_dir,
                "dst_dir": full_target_dir,
                "names": [source_filename]
            }
            

            
            # 发送请求
            response = requests.post(url, headers=headers, json=data, timeout=60)
            response.raise_for_status()
            
            # 解析响应
            result = response.json()
            
            # 处理响应
            if result.get("code") == 200:
                logger.info(f"文件复制成功: {source_path} → {full_target_path}")
                return True
            else:
                error_message = result.get("message", "未知错误")
                logger.error(f"文件复制失败: {error_message}")
                return False
        except Exception as e:
            logger.error(f"复制文件失败: {str(e)}")
            return False

    def _copy_file(self, source_path: str, target_path: str) -> bool:
        """复制文件 - 基于 OpenList API 重构"""
        try:
            # 检查源路径和目标路径
            if not source_path:
                logger.error("复制文件失败: 源路径为空")
                return False
            
            if not target_path:
                logger.error("复制文件失败: 目标路径为空")
                return False
            
            # 检查文件名
            # 使用字符串分割获取文件名，避免平台差异
            if '/' in source_path:
                source_filename = source_path.split('/')[-1]
            else:
                source_filename = source_path
            if not source_filename:
                logger.error("复制文件失败: 源文件名为空")
                return False
            
            # 提取目标目录和文件名
            try:
                if '/' in target_path:
                    target_parts = target_path.rsplit('/', 1)
                    if len(target_parts) != 2:
                        logger.error("复制文件失败: 目标路径格式错误")
                        return False
                    target_dir = target_parts[0]
                    target_filename = target_parts[1]
                    
                    if not target_dir:
                        logger.error("复制文件失败: 目标目录为空")
                        return False
                    
                    if not target_filename:
                        logger.error("复制文件失败: 目标文件名为空")
                        return False
                else:
                    logger.error("复制文件失败: 目标路径格式错误，缺少路径分隔符")
                    return False
            except IndexError:
                logger.error("复制文件失败: 目标路径格式错误")
                return False
            
            # 确保目标目录存在
            if not self._directory_exists(target_dir):
                logger.info(f"目标目录不存在，正在创建: {target_dir}")
                if not self._create_directory(target_dir):
                    logger.error(f"创建目标目录失败: {target_dir}")
                    return False
            
            # 构建相对目录路径
            relative_dir = ""
            
            # 调用带相对目录的复制方法
            return self._copy_file_with_relative_dir(source_path, target_dir, relative_dir)
                
        except Exception as e:
            logger.error(f"复制文件失败: {str(e)}")
            return False

    def _update_status(self, message: str, progress: int):
        """更新任务状态"""
        self._task_status["message"] = message
        self._task_status["progress"] = progress
        self._save_task_status()

    def _complete_task(self, status: str, message: str):
        """完成任务"""
        self._task_status.update({
            "status": status,
            "message": message,
            "end_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "last_run": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        self._save_task_status()

    def _save_task_status(self, force: bool = False):
        """保存任务状态（支持批量保存）"""
        if force or time.time() - self._last_save_time > self._save_interval:
            try:
                # 更新文件标识统计数据
                self._update_file_identifier_stats()
                # 保存数据
                self.save_data("openlistvue_task_status", self._task_status)
                self.save_data("openlistvue_copied_files", self._copied_files)
                self.save_data("openlistvue_target_files_count", self._target_files_count)
                self.save_data("openlistvue_file_identifier_stats", self._file_identifier_stats)
                self._last_save_time = time.time()
                
                # 将统计数据写入JSON文件
                self._write_stats_to_json()
            except Exception as e:
                logger.error(f"批量保存数据失败: {str(e)}")

    def _save_copied_files(self):
        """保存已复制文件记录"""
        try:
            self.save_data("openlistvue_copied_files", self._copied_files)
        except Exception as e:
            logger.error(f"保存复制文件记录失败: {str(e)}")



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