#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import re
import shutil
import string
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional, Set, Union

from pydantic import BaseModel
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Windows平台支持
if os.name == 'nt':
    from ctypes import windll

from app.core.config import settings
from app.core.event import eventmanager
from app.db.systemconfig_oper import SystemConfigOper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import NotificationType
from app.schemas.types import SystemConfigKey
from app.utils.string import StringUtils
from app.helper.plugin import PluginHelper
from app.helper.module import ModuleHelper
from app.helper.downloader import DownloaderHelper
from app.schemas import ServiceInfo
from app.modules.qbittorrent import Qbittorrent
from app.modules.transmission import Transmission


# --- 配置模型 ---
class TrashCleanConfig(BaseModel):
    """垃圾文件清理插件配置"""
    enable: bool = False  # 是否启用
    notify: bool = True   # 是否发送通知
    cron: str = '0 4 * * *'  # 执行时间
    only_when_no_download: bool = True  # 仅当下载器无任务时执行
    monitor_paths: List[str] = []  # 监控的路径
    empty_dir_cleanup: bool = True  # 清理空目录
    small_dir_cleanup: bool = False  # 清理小体积目录
    small_dir_max_size: int = 10  # 小体积目录最大体积(MB)
    size_reduction_cleanup: bool = False  # 清理体积减少的目录
    size_reduction_threshold: int = 80  # 体积减少阈值(%)
    scan_interval: int = 24  # 监控间隔(小时)
    exclude_dirs: List[str] = []  # 排除的目录
    onlyonce: bool = False  # 仅执行一次


# --- 插件类 ---
class TrashClean(_PluginBase):
    # 插件信息
    plugin_name = "垃圾文件清理"
    plugin_desc = "自动清理下载文件夹中的垃圾文件"
    plugin_icon = "https://raw.githubusercontent.com/madrays/MoviePilot-Plugins/main/icons/clean1.png"
    plugin_version = "1.1"
    plugin_author = "madrays"
    author_url = "https://github.com/madrays"
    plugin_config_prefix = "trashclean_"
    plugin_order = 75
    auth_level = 1

    # 私有变量
    _enable = False
    _notify = True
    _cron = '0 4 * * *'
    _only_when_no_download = True
    _monitor_paths = []
    _empty_dir_cleanup = True
    _small_dir_cleanup = False
    _small_dir_max_size = 10
    _size_reduction_cleanup = False
    _size_reduction_threshold = 80
    _scan_interval = 24
    _exclude_dirs = []

    _scheduler: Optional[BackgroundScheduler] = None
    _plugin_dir: Path = Path(__file__).parent
    
    # 目录监控数据
    _dir_size_history: Dict[str, Dict[str, Any]] = {}
    # 目录统计数据
    _dir_stats_cache: Dict[str, Any] = {}
    # 清理任务进度
    _clean_progress: Dict[str, Any] = {
        "running": False,
        "total_dirs": 0,
        "processed_dirs": 0,
        "current_dir": "",
        "removed_dirs": [],
        "start_time": None,
        "status": "idle",
        "message": "",
        "percent": 0
    }

    def init_plugin(self, config: dict = None):
        """初始化插件"""
        self.stop_service()

        if config:
            # 更新配置
            self._enable = config.get('enable', False)
            self._notify = config.get('notify', True)
            self._cron = config.get('cron', '0 4 * * *')
            self._only_when_no_download = config.get('only_when_no_download', True)
            self._monitor_paths = config.get('monitor_paths', [])
            self._empty_dir_cleanup = config.get('empty_dir_cleanup', True)
            self._small_dir_cleanup = config.get('small_dir_cleanup', False)
            self._small_dir_max_size = config.get('small_dir_max_size', 10)
            self._size_reduction_cleanup = config.get('size_reduction_cleanup', False)
            self._size_reduction_threshold = config.get('size_reduction_threshold', 80)
            self._scan_interval = config.get('scan_interval', 24)
            
            # 确保排除目录正确初始化
            exclude_dirs = config.get('exclude_dirs', [])
            self._exclude_dirs = [dir.strip() for dir in exclude_dirs if dir and dir.strip()]
            logger.info(f"{self.plugin_name}: 已配置排除目录: {self._exclude_dirs}")
        
        # 加载历史数据
        self._load_history_data()
        
        # 初始化定时服务
        self._scheduler = BackgroundScheduler(timezone=settings.TZ)
        
        # 添加定时任务
        if self._enable and self._cron:
            try:
                self._scheduler.add_job(func=self._task,
                                      trigger=CronTrigger.from_crontab(self._cron),
                                      name=self.plugin_name)
                logger.info(f"{self.plugin_name}: 已按 CRON '{self._cron}' 计划定时任务")
            except Exception as err:
                logger.error(f"{self.plugin_name}: 定时任务配置错误: {err}")
        
        # 启动任务
        if self._scheduler.get_jobs():
            self._scheduler.print_jobs()
            self._scheduler.start()
            logger.info(f"{self.plugin_name}: 服务启动")
        else:
            logger.info(f"{self.plugin_name}: 没有计划任务需要启动")

    def _task(self, manual_run: bool = False):
        """定时任务"""
        log_prefix = f"{self.plugin_name}{' (手动)' if manual_run else ''}"
        logger.info(f"{log_prefix}: 开始执行清理任务...")
        
        # 检查下载器状态
        if self._only_when_no_download and not manual_run:
            has_downloads = self._check_downloaders_running()
            if has_downloads:
                logger.info(f"{log_prefix}: 下载器正在执行任务，跳过清理")
                return {"status": "skipped", "message": "下载器正在执行任务，跳过清理"}
        
        result = self._clean_trash_files(manual_run)
        
        # 修复可能的对象引用问题：确保返回的是深拷贝数据
        if result and isinstance(result, dict) and "removed_dirs" in result:
            # 创建结果的深拷贝
            import copy
            result_copy = copy.deepcopy(result)
            return result_copy
        
        return result

    def _clean_trash_files(self, manual_run: bool = False) -> Dict[str, Any]:
        """清理垃圾文件"""
        log_prefix = f"{self.plugin_name}{' (手动)' if manual_run else ''}"
        
        if not self._monitor_paths:
            logger.warning(f"{log_prefix}: 未设置监控路径，跳过清理")
            self._update_clean_progress(status="error", message="未设置监控路径", percent=100)
            return {"status": "error", "message": "未设置监控路径"}
        
        # 初始化进度数据
        self._clean_progress = {
            "running": True,
            "total_dirs": 0,
            "processed_dirs": 0,
            "current_dir": "",
            "removed_dirs": [],
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "running",
            "message": "开始清理任务...",
            "percent": 0
        }
        
        # 初始化结果
        result = {
            "status": "success",
            "removed_dirs": [],
            "removed_empty_dirs_count": 0,
            "removed_small_dirs_count": 0,
            "removed_size_reduction_dirs_count": 0,
            "total_freed_space": 0
        }
        
        try:
            # 确保我们首先加载历史数据
            self._load_history_data()
            
            # 更新目录大小历史
            logger.info(f"{log_prefix}: 开始更新目录大小历史数据")
            self._update_clean_progress(message="更新目录大小历史数据...", percent=5)
            self._update_dir_size_history()
            
            # 计算总目录数
            self._update_clean_progress(message="扫描目录结构...", percent=10)
            total_dirs = 0
            for monitor_path in self._monitor_paths:
                if not os.path.exists(monitor_path):
                    continue
                for _ in os.walk(monitor_path):
                    total_dirs += 1
            
            self._clean_progress["total_dirs"] = total_dirs
            
            # 处理每个监控路径
            processed_dirs = 0
            for monitor_path in self._monitor_paths:
                if not monitor_path or not os.path.exists(monitor_path):
                    logger.warning(f"{log_prefix}: 监控路径不存在: {monitor_path}")
                    continue
                
                logger.info(f"{log_prefix}: 开始处理监控路径: {monitor_path}")
                self._update_clean_progress(
                    message=f"处理监控路径: {monitor_path}",
                    current_dir=monitor_path,
                    percent=10 + (processed_dirs / (total_dirs or 1)) * 80
                )
                
                # 遍历目录处理垃圾文件
                for root, dirs, files in os.walk(monitor_path, topdown=False):
                    processed_dirs += 1
                    
                    # 更新进度
                    self._update_clean_progress(
                        processed_dirs=processed_dirs,
                        current_dir=root,
                        percent=10 + (processed_dirs / (total_dirs or 1)) * 80
                    )
                    
                    # 跳过排除目录
                    if self._is_excluded_dir(root):
                        continue
                    
                    # 处理空目录
                    if self._empty_dir_cleanup and not files and not dirs:
                        # 主目录不删除
                        if root != monitor_path:
                            if self._remove_directory(root):
                                dir_info = {"path": root, "type": "empty", "size": 0}
                                result["removed_dirs"].append(dir_info)
                                self._clean_progress["removed_dirs"].append(dir_info)
                                result["removed_empty_dirs_count"] += 1
                        continue
                    
                    # 计算目录大小
                    dir_size_bytes = self._get_directory_size(root)
                    dir_size_mb = dir_size_bytes / (1024 * 1024)
                    
                    # 处理小体积目录
                    if self._small_dir_cleanup and dir_size_mb <= self._small_dir_max_size and root != monitor_path:
                        if self._remove_directory(root):
                            dir_info = {"path": root, "type": "small", "size": dir_size_mb}
                            result["removed_dirs"].append(dir_info)
                            self._clean_progress["removed_dirs"].append(dir_info)
                            result["removed_small_dirs_count"] += 1
                            result["total_freed_space"] += dir_size_mb
                        continue
                    
                    # 处理体积减少的目录
                    if self._size_reduction_cleanup and root in self._dir_size_history:
                        logger.debug(f"{log_prefix}: 检查目录是否体积减少: {root}")
                        previous_size = self._dir_size_history[root].get("size", 0)
                        
                        # 只处理有历史记录的目录
                        if previous_size > 0 and dir_size_bytes > 0:
                            # 计算体积减少百分比
                            reduction_percent = ((previous_size - dir_size_bytes) / previous_size) * 100
                            
                            logger.debug(f"{log_prefix}: 目录 {root} 体积变化: 从 {previous_size/(1024*1024):.2f}MB 变为 {dir_size_mb:.2f}MB, 变化率: {reduction_percent:.2f}%")
                            
                            if previous_size > dir_size_bytes and reduction_percent >= self._size_reduction_threshold:
                                logger.info(f"{log_prefix}: 目录 {root} 体积减少 {reduction_percent:.2f}%, 超过阈值 {self._size_reduction_threshold}%, 将被清理")
                                
                                if root != monitor_path and self._remove_directory(root):
                                    dir_info = {
                                        "path": root, 
                                        "type": "size_reduction", 
                                        "size": dir_size_mb,
                                        "reduction_percent": reduction_percent
                                    }
                                    result["removed_dirs"].append(dir_info)
                                    self._clean_progress["removed_dirs"].append(dir_info)
                                    result["removed_size_reduction_dirs_count"] += 1
                                    result["total_freed_space"] += dir_size_mb
                                    
                                    # 从历史记录中移除已删除的目录
                                    if root in self._dir_size_history:
                                        logger.debug(f"{log_prefix}: 从历史记录中移除已删除的目录: {root}")
                                        del self._dir_size_history[root]
                                    
                                    continue
            
            # 保存更新后的历史数据
            self._update_clean_progress(message="保存历史数据...", percent=90)
            self._save_history_data()
            
            # 发送通知
            if self._notify and (result["removed_empty_dirs_count"] > 0 or 
                                result["removed_small_dirs_count"] > 0 or 
                                result["removed_size_reduction_dirs_count"] > 0):
                self._update_clean_progress(message="发送通知...", percent=95)
                self._send_notify(result)
            
            # 记录结果到历史记录
            self._update_clean_progress(message="保存清理结果...", percent=98)
            self._save_clean_result(result)
            
            # 更新目录统计并保存
            self._update_clean_progress(message="更新目录统计...", percent=99)
            self._update_and_save_dir_stats()
            
            # 标记清理完成
            self._update_clean_progress(
                running=False,
                status="success",
                message=f"清理任务完成！共清理 {len(result['removed_dirs'])} 个目录，释放 {result['total_freed_space']:.2f}MB 空间",
                percent=100
            )
            
            logger.info(f"{log_prefix}: 清理任务完成，共清理 {len(result['removed_dirs'])} 个目录，释放 {result['total_freed_space']:.2f}MB 空间")
            return result
            
        except Exception as e:
            logger.error(f"{log_prefix}: 清理过程发生错误: {str(e)}", exc_info=True)
            self._update_clean_progress(
                running=False,
                status="error",
                message=f"清理过程发生错误: {str(e)}",
                percent=100
            )
            return {"status": "error", "message": f"清理过程发生错误: {str(e)}"}

    def _check_downloaders_running(self) -> bool:
        """检查下载器是否正在执行任务"""
        try:
            # 获取下载器状态
            has_active_tasks = False
            
            # 获取所有下载器
            downloader_helper = DownloaderHelper()
            downloader_configs = downloader_helper.get_configs()
            
            if not downloader_configs:
                logger.warning(f"{self.plugin_name}: 未找到下载器配置")
                return False
                
            # 遍历下载器插件检查是否有活动任务
            for name, config in downloader_configs.items():
                try:
                    # 获取下载器服务信息
                    service = downloader_helper.get_service(name=name)
                    if not service or not service.instance:
                        logger.warning(f"{self.plugin_name}: 获取下载器 {name} 实例失败")
                        continue
                    
                    if service.instance.is_inactive():
                        logger.warning(f"{self.plugin_name}: 下载器 {name} 未连接")
                        continue
                    
                    # 获取下载器实例
                    downloader = service.instance
                    
                    # 获取下载中的种子
                    if service.type == "qbittorrent":
                        torrents = downloader.get_downloading_torrents()
                    else:
                        torrents = downloader.get_downloading_torrents()
                    
                    # 检查是否有活动的下载任务
                    if torrents and len(torrents) > 0:
                        logger.info(f"{self.plugin_name}: 下载器 {name} 有活动任务，数量: {len(torrents)}")
                        has_active_tasks = True
                        break
                        
                except Exception as e:
                    logger.error(f"{self.plugin_name}: 检查下载器 {name} 状态出错: {str(e)}")
                    continue
            
            # 未发现活动任务
            if not has_active_tasks:
                logger.info(f"{self.plugin_name}: 未发现下载器活动任务")
            
            return has_active_tasks
            
        except Exception as e:
            logger.error(f"{self.plugin_name}: 检查下载器状态失败: {str(e)}")
            # 出错时返回False，允许清理
            return False
    
    def _is_excluded_dir(self, dir_path: str) -> bool:
        """检查是否是排除的目录"""
        dir_path = os.path.normpath(dir_path).replace('\\', '/')
        
        for exclude_dir in self._exclude_dirs:
            exclude_dir = os.path.normpath(exclude_dir).replace('\\', '/')
            
            # 完全匹配
            if dir_path == exclude_dir:
                return True
            
            # 子目录匹配
            if dir_path.startswith(f"{exclude_dir}/") or dir_path.startswith(f"{exclude_dir}\\"):
                return True
                
        return False
    
    def _get_directory_size(self, path: str) -> int:
        """获取目录大小(字节)"""
        total_size = 0
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.exists(fp):
                    total_size += os.path.getsize(fp)
        return total_size
    
    def _remove_directory(self, dir_path: str) -> bool:
        """删除目录"""
        try:
            if os.path.exists(dir_path):
                shutil.rmtree(dir_path)
                logger.info(f"{self.plugin_name}: 已删除目录: {dir_path}")
                return True
        except Exception as e:
            logger.error(f"{self.plugin_name}: 删除目录 {dir_path} 失败: {str(e)}")
        return False
    
    def _update_dir_size_history(self):
        """更新目录大小历史数据"""
        now = datetime.now()
        
        # 遍历监控路径下的所有子目录
        for monitor_path in self._monitor_paths:
            if not os.path.exists(monitor_path):
                continue
                
            for root, _, _ in os.walk(monitor_path):
                # 跳过排除目录
                if self._is_excluded_dir(root):
                    continue
                
                # 计算目录大小
                dir_size = self._get_directory_size(root)
                
                if root not in self._dir_size_history:
                    # 新增目录记录
                    self._dir_size_history[root] = {
                        "size": dir_size,
                        "last_update": now.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    logger.debug(f"{self.plugin_name}: 新增目录记录: {root}, 大小: {dir_size/(1024*1024):.2f}MB")
                else:
                    # 根据扫描间隔更新
                    last_update = datetime.strptime(
                        self._dir_size_history[root]["last_update"], 
                        "%Y-%m-%d %H:%M:%S"
                    )
                    
                    # 如果超过扫描间隔，更新记录
                    if (now - last_update).total_seconds() / 3600 >= self._scan_interval:
                        # 记录旧值和新值
                        old_size = self._dir_size_history[root]["size"]
                        if old_size > 0 and dir_size > 0 and old_size > dir_size:
                            reduction_percent = ((old_size - dir_size) / old_size) * 100
                            logger.debug(f"{self.plugin_name}: 目录 {root} 体积减少: 从 {old_size/(1024*1024):.2f}MB 减少到 {dir_size/(1024*1024):.2f}MB, 减少了 {reduction_percent:.2f}%")
                        
                        self._dir_size_history[root] = {
                            "size": dir_size,
                            "last_update": now.strftime("%Y-%m-%d %H:%M:%S")
                        }
    
    def _load_history_data(self):
        """加载历史数据"""
        try:
            history_file = self._plugin_dir / "history_data.json"
            if history_file.exists():
                import json
                with open(history_file, "r", encoding="utf-8") as f:
                    self._dir_size_history = json.load(f)
                logger.info(f"{self.plugin_name}: 成功加载历史数据，共 {len(self._dir_size_history)} 条记录")
        except Exception as e:
            logger.error(f"{self.plugin_name}: 加载历史数据失败: {str(e)}")
            self._dir_size_history = {}
    
    def _save_history_data(self):
        """保存历史数据"""
        try:
            history_file = self._plugin_dir / "history_data.json"
            
            # 清理历史数据：只保留当前监控路径下的目录数据
            if self._dir_size_history:
                logger.info(f"{self.plugin_name}: 开始清理历史数据，当前共 {len(self._dir_size_history)} 条记录")
                
                # 获取当前所有监控路径
                current_monitored_paths = []
                for monitor_path in self._monitor_paths:
                    if os.path.exists(monitor_path):
                        current_monitored_paths.append(os.path.normpath(monitor_path))
                        # 遍历该监控路径下的所有子目录
                        for root, _, _ in os.walk(monitor_path):
                            current_monitored_paths.append(os.path.normpath(root))
                
                # 标准化路径格式
                current_monitored_paths = [path.replace('\\', '/') for path in current_monitored_paths]
                
                # 仅保留当前监控路径下的目录数据
                new_history = {}
                for path, data in self._dir_size_history.items():
                    norm_path = os.path.normpath(path).replace('\\', '/')
                    if any(norm_path.startswith(monitored_path) for monitored_path in current_monitored_paths):
                        new_history[path] = data
                
                # 更新历史数据
                removed_count = len(self._dir_size_history) - len(new_history)
                self._dir_size_history = new_history
                logger.info(f"{self.plugin_name}: 历史数据清理完成，共移除 {removed_count} 条不再监控的路径数据，保留 {len(self._dir_size_history)} 条记录")
            
            import json
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(self._dir_size_history, f, ensure_ascii=False, indent=2)
            logger.info(f"{self.plugin_name}: 成功保存历史数据，共 {len(self._dir_size_history)} 条记录")
        except Exception as e:
            logger.error(f"{self.plugin_name}: 保存历史数据失败: {str(e)}")
    
    def _send_notify(self, result: Dict[str, Any]):
        """发送通知"""
        if not self._notify:
            return
            
        log_prefix = f"{self.plugin_name}"
        
        try:
            # 构建通知消息
            title = "✅ 垃圾文件清理完成"
            msg_text = (
                f"🧹 清理任务已完成！\n"
                f"--------------------\n"
                f"⏱️ 时间: {datetime.now(tz=pytz.timezone(settings.TZ)).strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"📁 清理目录: {len(result['removed_dirs'])} 个\n"
                f"📊 释放空间: {result['total_freed_space']:.2f}MB\n"
            )
            
            if result["removed_empty_dirs_count"] > 0:
                msg_text += f"🗑️ 空目录: {result['removed_empty_dirs_count']} 个\n"
            
            if result["removed_small_dirs_count"] > 0:
                msg_text += f"📦 小体积目录(<={self._small_dir_max_size}MB): {result['removed_small_dirs_count']} 个\n"
            
            if result["removed_size_reduction_dirs_count"] > 0:
                msg_text += f"📉 体积减少目录(>={self._size_reduction_threshold}%): {result['removed_size_reduction_dirs_count']} 个\n"
                
            msg_text += f"--------------------"
            
            # 发送通知
            self.post_message(
                mtype=NotificationType.SiteMessage,
                title=title,
                text=msg_text
            )
            logger.info(f"{log_prefix}: 已发送清理完成通知")
        except Exception as e:
            logger.error(f"{log_prefix}: 发送清理通知失败: {e}", exc_info=True)
    
    def get_state(self) -> bool:
        """获取插件状态"""
        return self._enable

    def _get_config(self) -> Dict[str, Any]:
        """获取配置"""
        return {
            "enable": self._enable,
            "notify": self._notify,
            "cron": self._cron,
            "only_when_no_download": self._only_when_no_download,
            "monitor_paths": self._monitor_paths,
            "empty_dir_cleanup": self._empty_dir_cleanup,
            "small_dir_cleanup": self._small_dir_cleanup,
            "small_dir_max_size": self._small_dir_max_size,
            "size_reduction_cleanup": self._size_reduction_cleanup,
            "size_reduction_threshold": self._size_reduction_threshold,
            "scan_interval": self._scan_interval,
            "exclude_dirs": self._exclude_dirs
        }

    def _save_config(self, config_payload: dict) -> Dict[str, Any]:
        """保存配置"""
        try:
            logger.info(f"{self.plugin_name}: 开始保存配置: {config_payload}")
            
            # 验证必要的字段
            if "monitor_paths" not in config_payload or not isinstance(config_payload["monitor_paths"], list):
                logger.error(f"{self.plugin_name}: 配置保存失败，监控路径必须为列表")
                return {"status": "error", "message": "监控路径必须为列表"}
                
            if "exclude_dirs" not in config_payload or not isinstance(config_payload["exclude_dirs"], list):
                logger.error(f"{self.plugin_name}: 配置保存失败，排除目录必须为列表")
                return {"status": "error", "message": "排除目录必须为列表"}
            
            # 更新配置
            self._enable = config_payload.get('enable', False)
            self._notify = config_payload.get('notify', True)
            self._cron = config_payload.get('cron', '0 4 * * *')
            self._only_when_no_download = config_payload.get('only_when_no_download', True)
            self._monitor_paths = config_payload.get('monitor_paths', [])
            self._empty_dir_cleanup = config_payload.get('empty_dir_cleanup', True)
            self._small_dir_cleanup = config_payload.get('small_dir_cleanup', False)
            self._small_dir_max_size = config_payload.get('small_dir_max_size', 10)
            self._size_reduction_cleanup = config_payload.get('size_reduction_cleanup', False)
            self._size_reduction_threshold = config_payload.get('size_reduction_threshold', 80)
            self._scan_interval = config_payload.get('scan_interval', 24)
            self._exclude_dirs = config_payload.get('exclude_dirs', [])
            
            # 保存配置
            self.update_config(config_payload)
            
            # 如果启用了插件，重新启动任务
            if self._enable:
                self.stop_service()
                
                # 初始化定时服务
                self._scheduler = BackgroundScheduler(timezone=settings.TZ)
                
                # 添加定时任务
                if self._cron:
                    try:
                        self._scheduler.add_job(func=self._task,
                                            trigger=CronTrigger.from_crontab(self._cron),
                                            name=self.plugin_name)
                        logger.info(f"{self.plugin_name}: 已按 CRON '{self._cron}' 计划定时任务")
                    except Exception as err:
                        logger.error(f"{self.plugin_name}: 定时任务配置错误: {err}")
                
                # 启动任务
                if self._scheduler.get_jobs():
                    self._scheduler.print_jobs()
                    self._scheduler.start()
                    logger.info(f"{self.plugin_name}: 服务启动")
            
            logger.info(f"{self.plugin_name}: 配置保存成功")
            return {"status": "success"}
        except Exception as e:
            logger.error(f"{self.plugin_name}: 配置保存异常: {str(e)}")
            return {"status": "error", "message": f"配置保存失败: {str(e)}"}
    
    def _trigger_manual_clean(self) -> Dict[str, Any]:
        """手动触发清理"""
        return self._task(manual_run=True)
    
    def _get_status(self) -> Dict[str, Any]:
        """获取状态"""
        # 检查目录是否存在
        valid_paths = []
        invalid_paths = []
        for path in self._monitor_paths:
            if os.path.exists(path):
                valid_paths.append(path)
            else:
                invalid_paths.append(path)
        
        next_run_time = None
        if self._scheduler:
            for job in self._scheduler.get_jobs():
                if job.name == self.plugin_name:
                    if job.next_run_time:
                        next_run_time = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
                    break
        
        # 获取清理历史记录
        cleaning_history = []
        try:
            history_file = self._plugin_dir / "clean_history.json"
            if history_file.exists():
                import json
                with open(history_file, "r", encoding="utf-8") as f:
                    cleaning_history = json.load(f)
                # 限制传递的历史记录数量
                cleaning_history = cleaning_history[:5]
        except Exception as e:
            logger.error(f"{self.plugin_name}: 读取清理历史记录失败: {str(e)}")
        
        return {
            "enabled": self._enable,
            "cron": self._cron,
            "next_run_time": next_run_time,
            "monitor_paths": self._monitor_paths,
            "exclude_dirs": self._exclude_dirs,
            "only_when_no_download": self._only_when_no_download,
            "valid_paths_count": len(valid_paths),
            "invalid_paths_count": len(invalid_paths),
            "invalid_paths": invalid_paths,
            "dir_history_count": len(self._dir_size_history),
            "cleaning_history": cleaning_history,
            "cleanup_rules": {
                "empty_dir": self._empty_dir_cleanup,
                "small_dir": {
                    "enabled": self._small_dir_cleanup,
                    "max_size": self._small_dir_max_size
                },
                "size_reduction": {
                    "enabled": self._size_reduction_cleanup,
                    "threshold": self._size_reduction_threshold
                }
            }
        }
    
    def _get_monitor_path_stats(self, use_cache: bool = True) -> List[Dict[str, Any]]:
        """获取监控路径统计"""
        # 如果使用缓存且有缓存数据，则返回缓存
        if use_cache and self._dir_stats_cache and "stats" in self._dir_stats_cache:
            return self._dir_stats_cache["stats"]
            
        result = []
        for path in self._monitor_paths:
            if not os.path.exists(path):
                result.append({
                    "path": path,
                    "exists": False,
                    "status": "invalid"
                })
                continue
            
            # 统计目录信息
            try:
                total_size = self._get_directory_size(path)
                file_count = sum(len(files) for _, _, files in os.walk(path))
                dir_count = sum(len(dirs) for _, dirs, _ in os.walk(path))
                
                result.append({
                    "path": path,
                    "exists": True,
                    "status": "valid",
                    "total_size_bytes": total_size,
                    "total_size_mb": total_size / (1024 * 1024),
                    "file_count": file_count,
                    "dir_count": dir_count
                })
            except Exception as e:
                result.append({
                    "path": path,
                    "exists": True,
                    "status": "error",
                    "error": str(e)
                })
        
        return result
    
    def _get_browse(self, path: str = None) -> Dict[str, Any]:
        """浏览目录"""
        if not path:
            if os.name == 'nt':
                # Windows系统获取所有盘符
                drives = []
                try:
                    bitmask = windll.kernel32.GetLogicalDrives()
                    for letter in string.ascii_uppercase:
                        if bitmask & 1:
                            drives.append({
                                "name": f"{letter}:",
                                "path": f"{letter}:\\",
                                "type": "drive"
                            })
                        bitmask >>= 1
                    return {
                        "status": "success",
                        "path": "",
                        "items": drives
                    }
                except Exception as e:
                    # 使用备用方法
                    for letter in string.ascii_uppercase:
                        drive_path = f"{letter}:\\"
                        if os.path.exists(drive_path):
                            drives.append({
                                "name": f"{letter}:",
                                "path": drive_path,
                                "type": "drive"
                            })
                    return {
                        "status": "success",
                        "path": "",
                        "items": drives
                    }
            else:
                # Linux/Unix系统从根目录开始
                path = "/"
        
        # 标准化路径
        try:
            path = os.path.abspath(path)
            
            # 检查路径是否存在
            if not os.path.exists(path):
                return {
                    "status": "error",
                    "message": f"路径不存在: {path}"
                }
            
            # 如果不是目录
            if not os.path.isdir(path):
                return {
                    "status": "error",
                    "message": f"不是有效目录: {path}"
                }
            
            # 列出目录内容
            items = []
            
            # 添加上级目录（如果不是根目录）
            parent_path = os.path.dirname(path)
            if parent_path != path:  # 不是根目录
                items.append({
                    "name": "..",
                    "path": parent_path,
                    "type": "parent"
                })
            
            # 列出目录和文件
            try:
                entries = os.listdir(path)
                
                # 首先添加目录
                for entry in sorted(entries):
                    full_path = os.path.join(path, entry)
                    if os.path.isdir(full_path):
                        items.append({
                            "name": entry,
                            "path": full_path,
                            "type": "dir"
                        })
                
                # 目录排序
                items.sort(key=lambda x: x["name"].lower())
                
                return {
                    "status": "success",
                    "path": path,
                    "items": items
                }
            except PermissionError:
                return {
                    "status": "error",
                    "message": f"没有权限访问: {path}"
                }
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"列出目录失败: {str(e)}"
                }
        except Exception as e:
            return {
                "status": "error",
                "message": f"浏览目录失败: {str(e)}"
            }
    
    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        """Returns None for Vue form, but provides initial config data."""
        # This dict is passed as initialConfig to Config.vue by the host
        return None, self._get_config()

    def get_page(self) -> Optional[List[dict]]:
        """Vue mode doesn't use Vuetify page definitions."""
        return None

    # --- V2 Vue Interface Method ---
    @staticmethod
    def get_render_mode() -> Tuple[str, Optional[str]]:
        """Declare Vue rendering mode and assets path."""
        return "vue", "dist/assets"
        
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
        return [
            {
                "key": "dashboard1",
                "name": "垃圾文件清理"
            }
        ]

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
        return {
            "cols": 12,
            "md": 6
        }, {
            "refresh": 10,
            "border": True,
            "title": "垃圾文件清理",
            "subtitle": "定时清理文件目录中的垃圾文件"
        }, None

    def stop_service(self):
        """停止服务"""
        if self._scheduler:
            self._scheduler.remove_all_jobs()
            if self._scheduler.running:
                self._scheduler.shutdown()
            self._scheduler = None
            logger.info(f"{self.plugin_name}: 服务已停止")

    def _get_downloader_status(self) -> List[Dict[str, Any]]:
        """获取所有下载器状态"""
        result = []
        
        try:
            # 创建下载器帮助类实例
            downloader_helper = DownloaderHelper()
            downloader_configs = downloader_helper.get_configs()
            
            if not downloader_configs:
                logger.warning(f"{self.plugin_name}: 未找到下载器配置")
                return result
            
            # 遍历下载器插件检查是否有活动任务
            for name, config in downloader_configs.items():
                try:
                    # 获取下载器服务信息
                    service = downloader_helper.get_service(name=name)
                    if not service or not service.instance:
                        result.append({
                            "name": name,
                            "hasActiveTasks": False,
                            "error": "下载器服务未连接"
                        })
                        continue
                    
                    if service.instance.is_inactive():
                        result.append({
                            "name": name,
                            "hasActiveTasks": False,
                            "error": "下载器未连接"
                        })
                        continue
                    
                    # 下载器实例
                    downloader = service.instance
                    
                    # 获取活动的下载任务
                    if service.type == "qbittorrent":
                        torrents = downloader.get_downloading_torrents()
                        
                        active_tasks = []
                        if torrents:
                            for torrent in torrents:
                                task = {
                                    "hash": torrent.get("hash", ""),
                                    "name": torrent.get("name", "未知"),
                                    "state": torrent.get("state", ""),
                                    "size": torrent.get("total_size", 0),
                                    "progress": torrent.get("progress", 0) * 100,
                                    "dlspeed": torrent.get("dlspeed", 0),
                                    "eta": torrent.get("eta", 0)
                                }
                                active_tasks.append(task)
                                
                    else:  # transmission
                        torrents = downloader.get_downloading_torrents()
                        
                        active_tasks = []
                        if torrents:
                            for torrent in torrents:
                                task = {
                                    "hash": torrent.hashString,
                                    "name": torrent.name,
                                    "state": torrent.status,
                                    "size": torrent.total_size,
                                    "progress": torrent.percent_done * 100 if hasattr(torrent, 'percent_done') else 0,
                                    "dlspeed": torrent.rate_download if hasattr(torrent, 'rate_download') else torrent.rateDownload,
                                    "eta": torrent.eta if hasattr(torrent, 'eta') else 0
                                }
                                active_tasks.append(task)
                    
                    # 添加到结果
                    result.append({
                        "name": name,
                        "type": service.type,
                        "hasActiveTasks": len(active_tasks) > 0,
                        "count": len(active_tasks),
                        "activeTasks": active_tasks
                    })
                    
                except Exception as e:
                    logger.error(f"{self.plugin_name}: 检查下载器 {name} 状态出错: {str(e)}")
                    # 添加出错的下载器信息
                    result.append({
                        "name": name,
                        "hasActiveTasks": False,
                        "error": str(e)
                    })
            
            return result
            
        except Exception as e:
            logger.error(f"{self.plugin_name}: 获取下载器状态失败: {str(e)}")
            return []
    
    def _get_history(self) -> List[Dict[str, Any]]:
        """获取清理历史记录"""
        try:
            # 从文件读取历史记录
            history_file = self._plugin_dir / "clean_history.json"
            clean_history = []
            
            if history_file.exists():
                try:
                    import json
                    with open(history_file, "r", encoding="utf-8") as f:
                        clean_history = json.load(f)
                except Exception as e:
                    logger.error(f"{self.plugin_name}: 读取清理历史记录失败: {str(e)}")
                    clean_history = []
            
            return clean_history
            
        except Exception as e:
            logger.error(f"{self.plugin_name}: 获取清理历史记录失败: {str(e)}")
            return []

    def get_api(self) -> List[Dict[str, Any]]:
        """Defines API endpoints accessible via props.api in Vue components."""
        return [
            {
                "path": "/config",
                "endpoint": self._get_config,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取配置"
            },
            {
                "path": "/config",
                "endpoint": self._save_config,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "保存配置"
            },
            {
                "path": "/clean",
                "endpoint": self._trigger_manual_clean,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "手动清理"
            },
            {
                "path": "/status",
                "endpoint": self._get_status,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取状态"
            },
            {
                "path": "/stats",
                "endpoint": self._get_monitor_path_stats,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取监控路径统计"
            },
            {
                "path": "/stats_cache",
                "endpoint": self._get_dir_stats_cache,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取统计缓存信息"
            },
            {
                "path": "/update_stats",
                "endpoint": self._update_and_save_dir_stats,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "更新目录统计数据"
            },
            {
                "path": "/browse",
                "endpoint": self._get_browse,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "浏览目录"
            },
            {
                "path": "/downloaders",
                "endpoint": self._get_downloader_status,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取下载器状态"
            },
            {
                "path": "/history",
                "endpoint": self._get_history,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取历史记录"
            },
            {
                "path": "/clean_progress",
                "endpoint": self._get_clean_progress,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取清理进度"
            },
            {
                "path": "/latest_clean_result",
                "endpoint": self._get_latest_clean_result,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取最新清理结果"
            }
        ]

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """No commands defined for this plugin"""
        return []

    def _save_clean_result(self, result: Dict[str, Any]):
        """保存清理结果到历史记录"""
        try:
            # 确保result包含必要的字段
            if not result or result.get("status") != "success":
                return
                
            # 构造历史记录条目
            now = datetime.now(tz=pytz.timezone(settings.TZ))
            formatted_time = now.strftime("%Y-%m-%d %H:%M:%S")
            
            # 不对路径长度进行截断，保留完整路径信息
            clean_record = {
                "timestamp": formatted_time,
                "removed_dirs": result.get("removed_dirs", []),
                "removed_empty_dirs_count": result.get("removed_empty_dirs_count", 0),
                "removed_small_dirs_count": result.get("removed_small_dirs_count", 0),
                "removed_size_reduction_dirs_count": result.get("removed_size_reduction_dirs_count", 0),
                "total_freed_space": result.get("total_freed_space", 0),
                "last_update": formatted_time
            }
            
            # 从文件读取历史记录
            history_file = self._plugin_dir / "clean_history.json"
            clean_history = []
            
            if history_file.exists():
                try:
                    import json
                    with open(history_file, "r", encoding="utf-8") as f:
                        clean_history = json.load(f)
                except Exception as e:
                    logger.error(f"{self.plugin_name}: 读取清理历史记录失败: {str(e)}")
                    clean_history = []
            
            # 添加新记录到历史
            clean_history.insert(0, clean_record)
            
            # 限制历史记录数量，保留最近的30条
            max_history_records = 30
            if len(clean_history) > max_history_records:
                logger.info(f"{self.plugin_name}: 清理历史记录超过{max_history_records}条，进行精简")
                clean_history = clean_history[:max_history_records]
            
            # 保存历史记录
            try:
                import json
                with open(history_file, "w", encoding="utf-8") as f:
                    json.dump(clean_history, f, ensure_ascii=False, indent=2)
                logger.info(f"{self.plugin_name}: 成功保存清理历史记录，时间: {formatted_time}")
                
                # 同时将最新的清理结果单独保存，便于持久化显示
                # 确保result中包含timestamp字段
                result_with_timestamp = result.copy()
                result_with_timestamp["timestamp"] = formatted_time
                
                latest_result_file = self._plugin_dir / "latest_clean_result.json"
                with open(latest_result_file, "w", encoding="utf-8") as f:
                    json.dump(result_with_timestamp, f, ensure_ascii=False, indent=2)
                logger.info(f"{self.plugin_name}: 成功保存最新清理结果")
                
            except Exception as e:
                logger.error(f"{self.plugin_name}: 保存清理历史记录失败: {str(e)}")
                
        except Exception as e:
            logger.error(f"{self.plugin_name}: 保存清理结果到历史记录失败: {str(e)}")

    def _update_clean_progress(self, running=None, total_dirs=None, processed_dirs=None, 
                             current_dir=None, removed_dirs=None, status=None, 
                             message=None, percent=None):
        """更新清理进度信息"""
        if running is not None:
            self._clean_progress["running"] = running
        if total_dirs is not None:
            self._clean_progress["total_dirs"] = total_dirs
        if processed_dirs is not None:
            self._clean_progress["processed_dirs"] = processed_dirs
        if current_dir is not None:
            self._clean_progress["current_dir"] = current_dir
        if removed_dirs is not None:
            self._clean_progress["removed_dirs"] = removed_dirs
        if status is not None:
            self._clean_progress["status"] = status
        if message is not None:
            self._clean_progress["message"] = message
        if percent is not None:
            self._clean_progress["percent"] = percent
    
    def _get_clean_progress(self) -> Dict[str, Any]:
        """获取清理进度"""
        return self._clean_progress
        
    def _update_and_save_dir_stats(self):
        """更新并保存目录统计"""
        try:
            # 获取当前时间
            now = datetime.now(tz=pytz.timezone(settings.TZ))
            formatted_time = now.strftime("%Y-%m-%d %H:%M:%S")
            
            # 初始化进度数据
            progress_data = {
                "status": "running",
                "message": "开始扫描目录...",
                "progress": 0,
                "last_update": formatted_time
            }
            
            # 记录开始时间
            start_time = time.time()
            
            # 获取所有需要扫描的目录
            total_dirs = 0
            valid_paths = []
            
            # 先检查哪些路径存在
            for monitor_path in self._monitor_paths:
                if os.path.exists(monitor_path):
                    valid_paths.append(monitor_path)
            
            if not valid_paths:
                logger.warning(f"{self.plugin_name}: 没有有效的监控路径")
                return {
                    "stats": [],
                    "last_update": formatted_time,
                    "status": "error",
                    "message": "没有有效的监控路径"
                }
            
            # 统计总目录数，用于进度计算
            logger.info(f"{self.plugin_name}: 开始统计目录总数...")
            progress_data["message"] = "统计目录总数..."
            progress_data["progress"] = 5
            self._dir_stats_cache = progress_data.copy()
            
            for path in valid_paths:
                for _ in os.walk(path):
                    total_dirs += 1
                    
            logger.info(f"{self.plugin_name}: 共发现 {total_dirs} 个目录")
            
            # 初始化结果数组
            result = []
            processed_dirs = 0
            
            # 处理每个监控路径
            for path in valid_paths:
                # 更新进度
                processed_percentage = 10 + (processed_dirs / (total_dirs or 1)) * 80
                progress_data["message"] = f"扫描路径: {path}"
                progress_data["progress"] = int(processed_percentage)
                self._dir_stats_cache = progress_data.copy()
                
                logger.info(f"{self.plugin_name}: 开始处理监控路径: {path}")
                
                # 统计目录信息
                try:
                    # 计算总大小
                    total_size = self._get_directory_size(path)
                    
                    # 统计文件和目录数量
                    file_count = 0
                    dir_count = 0
                    
                    for root, dirs, files in os.walk(path):
                        processed_dirs += 1
                        dir_count += len(dirs)
                        file_count += len(files)
                        
                        # 定期更新进度
                        if processed_dirs % 10 == 0:
                            processed_percentage = 10 + (processed_dirs / (total_dirs or 1)) * 80
                            progress_data["message"] = f"扫描目录: {root}"
                            progress_data["progress"] = int(processed_percentage)
                            self._dir_stats_cache = progress_data.copy()
                    
                    # 添加到结果
                    result.append({
                        "path": path,
                        "exists": True,
                        "status": "valid",
                        "total_size_bytes": total_size,
                        "total_size_mb": total_size / (1024 * 1024),
                        "file_count": file_count,
                        "dir_count": dir_count
                    })
                    
                except Exception as e:
                    result.append({
                        "path": path,
                        "exists": True,
                        "status": "error",
                        "error": str(e)
                    })
                    logger.error(f"{self.plugin_name}: 统计目录 {path} 时出错: {str(e)}")
            
            # 统计完成，更新进度
            progress_data["message"] = "保存统计数据..."
            progress_data["progress"] = 90
            self._dir_stats_cache = progress_data.copy()
            
            # 更新最终结果
            elapsed_time = time.time() - start_time
            logger.info(f"{self.plugin_name}: 目录统计完成，耗时 {elapsed_time:.2f} 秒")
            
            # 更新缓存对象
            self._dir_stats_cache = {
                "stats": result,
                "last_update": formatted_time,
                "status": "success",
                "message": f"统计完成，共 {len(result)} 个路径，耗时 {elapsed_time:.2f} 秒",
                "progress": 100
            }
            
            # 保存到文件
            stats_file = self._plugin_dir / "dir_stats_cache.json"
            try:
                import json
                with open(stats_file, "w", encoding="utf-8") as f:
                    json.dump(self._dir_stats_cache, f, ensure_ascii=False, indent=2)
                logger.info(f"{self.plugin_name}: 目录统计数据已保存，更新时间: {formatted_time}")
            except Exception as e:
                logger.error(f"{self.plugin_name}: 保存目录统计数据失败: {str(e)}")
            
            # 返回统计数据
            return self._dir_stats_cache
                
        except Exception as e:
            logger.error(f"{self.plugin_name}: 更新目录统计数据失败: {str(e)}")
            return {
                "stats": [], 
                "last_update": "",
                "status": "error",
                "message": f"更新目录统计数据失败: {str(e)}",
                "progress": 0
            }
    
    def _load_dir_stats_cache(self):
        """加载目录统计缓存"""
        try:
            stats_file = self._plugin_dir / "dir_stats_cache.json"
            if stats_file.exists():
                import json
                with open(stats_file, "r", encoding="utf-8") as f:
                    self._dir_stats_cache = json.load(f)
                logger.info(f"{self.plugin_name}: 已加载目录统计缓存数据")
        except Exception as e:
            logger.error(f"{self.plugin_name}: 加载目录统计缓存失败: {str(e)}")
            self._dir_stats_cache = {
                "stats": [],
                "last_update": ""
            } 

    def _get_latest_clean_result(self) -> Dict[str, Any]:
        """获取最新清理结果"""
        try:
            # 尝试读取最新清理结果文件
            latest_result_file = self._plugin_dir / "latest_clean_result.json"
            if latest_result_file.exists():
                import json
                with open(latest_result_file, "r", encoding="utf-8") as f:
                    result = json.load(f)
                logger.debug(f"{self.plugin_name}: 成功读取最新清理结果")
                return result
            else:
                logger.debug(f"{self.plugin_name}: 未找到最新清理结果文件")
                # 返回空结果而不是None，确保格式一致
                return {
                    "status": "success",
                    "removed_dirs": [],
                    "removed_empty_dirs_count": 0,
                    "removed_small_dirs_count": 0,
                    "removed_size_reduction_dirs_count": 0,
                    "total_freed_space": 0
                }
        except Exception as e:
            logger.error(f"{self.plugin_name}: 获取最新清理结果失败: {str(e)}")
            # 出错时也返回空结果而不是None
            return {
                "status": "error",
                "message": f"获取清理结果失败: {str(e)}",
                "removed_dirs": [],
                "removed_empty_dirs_count": 0,
                "removed_small_dirs_count": 0,
                "removed_size_reduction_dirs_count": 0,
                "total_freed_space": 0
            } 

    def _get_dir_stats_cache(self) -> Dict[str, Any]:
        """获取目录统计缓存信息"""
        try:
            # 如果未加载缓存，尝试从文件加载
            if not self._dir_stats_cache:
                self._load_dir_stats_cache()
                
            # 返回缓存数据
            return self._dir_stats_cache or {"stats": [], "last_update": ""}
        except Exception as e:
            logger.error(f"{self.plugin_name}: 获取目录统计缓存失败: {str(e)}")
            return {"stats": [], "last_update": ""} 