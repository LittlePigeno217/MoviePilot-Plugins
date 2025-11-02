from app.plugins import _PluginBase
from typing import Any, Dict, List, Optional, Tuple
import requests
import time
import json
import os
import hashlib
from app.core.config import settings
from app.log import logger
from app.schemas.types import EventType
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger


class AlistCopyPlugin(_PluginBase):
    """
    AList复制插件 - 通过AList API实现多目录间文件复制
    """
    # 插件基本信息
    plugin_name = "OpenList自动复制"
    plugin_desc = "实现OpenList多目录间文件复制自动化"
    plugin_icon = "Alist_B.png"
    plugin_version = "1.8"
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

    # 可配置项
    _enabled: bool = False
    _cron: str = ""
    _onlyonce: bool = False
    _clear_cache: bool = False
    _alist_url: str = ""
    _alist_token: str = ""
    _directory_pairs: str = ""
    _enable_custom_suffix: bool = False

    # 任务状态
    _task_status: Dict[str, Any] = {}
    
    # 复制记录 - 记录已成功复制的文件，现在包含状态字段
    _copied_files: Dict[str, Any] = {}
    
    # 执行历史记录 - 独立存储，避免冲突
    _execution_history: List[Dict[str, Any]] = []
    
    # 目标目录文件数统计
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
            self._task_status = {
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

        # 恢复复制记录
        saved_copied_files = self.get_data("alistcopy_copied_files")
        if saved_copied_files:
            self._copied_files = saved_copied_files
        else:
            self._copied_files = {}

        # 恢复执行历史记录 - 使用独立键名避免冲突
        saved_history = self.get_data("alistcopy_execution_history")
        if saved_history:
            self._execution_history = saved_history
        else:
            self._execution_history = []

        # 恢复目标目录文件数
        saved_target_count = self.get_data("alistcopy_target_files_count")
        if saved_target_count is not None:
            self._target_files_count = saved_target_count
        else:
            self._target_files_count = 0

        # 启动服务
        if self._enabled:
            # 启动定时服务
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            
            if self._cron:
                try:
                    self._scheduler.add_job(
                        func=self.execute_copy_task,
                        trigger=CronTrigger.from_crontab(self._cron),
                        id="alist_copy_task",
                        name="AList复制任务"
                    )
                    logger.info(f"定时任务已设置，周期: {self._cron}")
                except Exception as e:
                    logger.error(f"定时任务配置错误：{str(e)}")

            # 立即执行一次
            if self._onlyonce:
                logger.info("检测到立即运行一次，开始执行AList复制任务")
                import threading
                threading.Thread(target=self.execute_copy_task, daemon=True).start()

            # 启动调度器
            if self._scheduler.get_jobs():
                if not self._scheduler.running:
                    self._scheduler.start()
                    logger.info("AList复制管理器服务启动成功")

    def get_state(self) -> bool:
        return self._enabled

    def __update_config(self):
        self.update_config({
            "onlyonce": self._onlyonce,
            "clear_cache": self._clear_cache,
            "cron": self._cron,
            "enabled": self._enabled,
            "alist_url": self._alist_url,
            "alist_token": self._alist_token,
            "directory_pairs": self._directory_pairs,
            "enable_custom_suffix": self._enable_custom_suffix
        })

    def _clear_all_data(self):
        """清空所有插件数据"""
        # 清空任务状态
        self._task_status = {
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
        self.save_data("alistcopy_task_status", self._task_status)
        
        # 清空复制记录
        self._copied_files = {}
        self.save_data("alistcopy_copied_files", self._copied_files)
        
        # 清空执行历史记录
        self._execution_history = []
        self.save_data("alistcopy_execution_history", self._execution_history)
        
        # 清空目标目录文件数
        self._target_files_count = 0
        self.save_data("alistcopy_target_files_count", self._target_files_count)
        
        logger.info("插件数据已全部清空，将重新开始记录")

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
        if self._enabled and self._cron:
            return [{
                "id": "AlistCopyTask",
                "name": "OpenList复制任务",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.execute_copy_task,
                "kwargs": {}
            }]
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "onlyonce",
                                            "label": "立即运行一次",
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "clear_cache",
                                            "label": "清除缓存后运行",
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
                                            "model": "alist_url",
                                            "label": "AList/OpenList地址",
                                            "placeholder": "http://localhost:5244"
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
                                            "label": "AList/OpenList令牌",
                                            "type": "password",
                                            "placeholder": "在AList/OpenList后台获取"
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
                                        "component": "VTextarea",
                                        "props": {
                                            "model": "directory_pairs",
                                            "label": "目录配对",
                                            "placeholder": "源目录1#目标目录1\n源目录2#目标目录2",
                                            "rows": 4
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
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enable_custom_suffix",
                                            "label": "复制字幕/元数据/封面图文件",
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "cron",
                                            "label": "执行周期",
                                            "placeholder": "0 2 * * *"
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
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "text": True,
                                            "variant": "tonal"
                                        },
                                        "content": [
                                            {
                                                "component": "div",
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
                                        "component": "VAlert",
                                        "props": {
                                            "type": "warning",
                                            "text": True,
                                            "variant": "tonal"
                                        },
                                        "content": [
                                            {
                                                "component": "div",
                                                "props": {"class": "font-weight-bold"},
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
        ], {
            "enabled": self._enabled,
            "onlyonce": self._onlyonce,
            "clear_cache": self._clear_cache,
            "alist_url": self._alist_url,
            "alist_token": self._alist_token,
            "directory_pairs": self._directory_pairs,
            "enable_custom_suffix": self._enable_custom_suffix,
            "cron": self._cron or "0 2 * * *"
        }

    def get_page(self) -> List[dict]:
        # 不再每次打开页面时自动更新文件状态和数量统计
        # 直接使用已保存的数据显示页面
        
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
        
        # 获取最近一次有复制文件的记录
        latest_copied_record = self._get_latest_copied_record()
        
        return [
            {
                "component": "VCard",
                "content": [
                    {
                        "component": "VCardText",
                        "content": [
                            # 第一行：OpenList媒体复制统计
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
                            
                            # 第二行：三个状态框（每行4列，共12列）
                            {
                                "component": "VRow",
                                "content": [
                                    # 状态框1：目标目录文件数
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
                                                                "text": "目标目录文件数"
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
                                    # 状态框2：当前复制数量
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
                                                                "text": "当前复制数量"
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
                                    # 状态框3：累计复制数量
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
                                                                "text": "累计复制数量"
                                                            },
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "text-h4 font-weight-bold text-info mt-2"},
                                                                "text": str(completed_count)
                                                            },
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "text-body-2 text-grey mt-1"},
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            },
                            
                            # 第三行：最近复制文件记录状态框
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
                                                                        "text": "最近复制文件记录"
                                                                    }
                                                                ]
                                                            },
                                                            {
                                                                "component": "div",
                                                                "content": self._render_latest_copied_record(latest_copied_record)
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            },
                            
                            # 任务状态信息
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
      
    def _update_file_status_and_counts(self):
        """更新文件状态和数量统计"""
        if not self._copied_files:
            return
            
        directory_pairs = self._parse_directory_pairs()
        if not directory_pairs:
            return
            
        logger.info("正在更新文件状态和数量统计...")
        
        # 为每个目标目录构建文件索引
        target_dirs_index = {}
        for pair in directory_pairs:
            target_dir = pair["target"]
            if target_dir not in target_dirs_index:
                logger.info(f"扫描目标目录以更新文件状态: {target_dir}")
                target_files = self._get_alist_files(target_dir)
                if target_files:
                    # 构建文件名索引（不包含路径）
                    file_index = {}
                    for file in target_files:
                        filename = file.get("name")
                        if filename:
                            file_index[filename] = file.get("path", "")
                    target_dirs_index[target_dir] = file_index
                    logger.info(f"目标目录 {target_dir} 有 {len(file_index)} 个文件")
                else:
                    target_dirs_index[target_dir] = {}
                    logger.info(f"目标目录 {target_dir} 为空")
        
        # 检查每个文件的状态并更新
        updated_count = 0
        for file_key, record in self._copied_files.items():
            target_path = record.get("target_path", "")
            filename = record.get("filename", "")
            current_status = record.get("status", "copying")  # 默认为复制中
            
            if not target_path or not filename:
                continue
                
            # 找到对应的目标目录
            target_dir = None
            for pair in directory_pairs:
                if target_path.startswith(pair["target"]):
                    target_dir = pair["target"]
                    break
            
            if not target_dir:
                continue
                
            # 检查文件是否在目标目录中存在
            if target_dir in target_dirs_index and filename in target_dirs_index[target_dir]:
                # 文件在目标目录中存在，更新状态为已完成
                if current_status != "completed":
                    self._copied_files[file_key]["status"] = "completed"
                    self._copied_files[file_key]["completed_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    updated_count += 1
            else:
                # 文件在目标目录中不存在，保持状态为复制中
                if current_status != "copying":
                    self._copied_files[file_key]["status"] = "copying"
                    updated_count += 1
        
        if updated_count > 0:
            self._save_copied_files()
            logger.info(f"已更新 {updated_count} 个文件的状态")
        
        # 更新目标目录文件数
        self._update_target_files_count(directory_pairs)
    
    def _get_file_status_counts(self) -> Tuple[int, int]:
        """获取文件状态统计数量"""
        copying_count = 0
        completed_count = 0
        
        for record in self._copied_files.values():
            status = record.get("status", "copying")
            if status == "completed":
                completed_count += 1
            else:
                copying_count += 1
                
        return copying_count, completed_count
    
    def _get_recent_executions(self) -> List[Dict]:
        """获取最近5次执行记录（过滤掉没有复制文件的记录）"""
        # 过滤掉复制文件数为0的记录，然后取前5条
        filtered_executions = [execution for execution in self._execution_history if execution.get("copied_count", 0) > 0]
        return filtered_executions[:5]
    
    def _get_latest_copied_record(self) -> Optional[Dict]:
        """获取最近一次有复制文件的记录"""
        if not self._execution_history:
            return None
        
        # 过滤掉复制文件数为0的记录，然后取第一条
        filtered_executions = [execution for execution in self._execution_history if execution.get("copied_count", 0) > 0]
        return filtered_executions[0] if filtered_executions else None
    
    def _add_execution_record(self, copied_count: int, files: List[str]):
        """添加执行记录（只有复制文件数大于0时才记录）"""
        if copied_count <= 0:
            return  # 不记录没有复制文件的执行
            
        record = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "copied_count": copied_count,
            "files": files  # 不再限制文件数量，保留所有文件
        }
        
        # 添加到历史记录开头
        self._execution_history.insert(0, record)
        
        # 限制历史记录数量，最多保留20条
        if len(self._execution_history) > 20:
            self._execution_history = self._execution_history[:20]
        
        # 保存历史记录
        self.save_data("alistcopy_execution_history", self._execution_history)
    
    def _render_latest_copied_record(self, execution: Optional[Dict]) -> List[Dict]:
        """渲染最近一次复制文件记录"""
        if not execution:
            return [
                {
                    "component": "div",
                    "props": {"class": "text-center text-grey py-4"},
                    "text": "暂无复制文件记录"
                }
            ]
        
        # 对文件列表进行正序排序
        sorted_files = sorted(execution.get("files", []))
        
        content = [
            {
                "component": "div",
                "props": {"class": "d-flex justify-space-between align-center mb-3"},
                "content": [
                    {
                        "component": "VChip",
                        "props": {
                            "color": "deep-purple",
                            "size": "small"
                        },
                        "text": f"复制 {execution.get('copied_count', 0)} 个文件"
                    }
                ]
            }
        ]
        
        # 添加文件列表
        if sorted_files:
            content.append({
                "component": "div",
                "props": {"class": "mt-2"},
                "content": self._render_multi_line_file_list(sorted_files)
            })
        else:
            content.append({
                "component": "div",
                "props": {"class": "text-caption text-grey"},
                "text": "本次执行没有复制文件"
            })
        
        return content
    
    def _render_multi_line_file_list(self, files: List[str]) -> List[Dict]:
        """渲染多行文件列表，每行最多五个文件名"""
        if not files:
            return []
        
        content = []
        
        # 将文件列表按每5个一组进行分组
        file_groups = [files[i:i+5] for i in range(0, len(files), 5)]
        
        for group in file_groups:
            row_content = []
            for file in group:
                row_content.append({
                    "component": "div",
                    "props": {"class": "d-flex align-center mb-1", "style": "flex: 1 0 20%;"},
                    "content": [
                        {
                            "component": "VIcon",
                            "props": {"icon": "mdi-file", "size": "x-small", "class": "mr-2"},
                            "text": ""
                        },
                        {
                            "component": "span",
                            "props": {"class": "text-caption text-truncate"},
                            "text": file
                        }
                    ]
                })
            
            content.append({
                "component": "div",
                "props": {"class": "d-flex justify-space-between"},
                "content": row_content
            })
        
        return content

    def _parse_directory_pairs(self) -> List[Dict[str, str]]:
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
        all_suffixes = self.DEFAULT_VIDEO_SUFFIXES.copy()
        
        if self._enable_custom_suffix:
            for suffix in self.CUSTOM_SUFFIXES:
                if suffix not in all_suffixes:
                    all_suffixes.append(suffix)
        
        return all_suffixes

    def stop_service(self):
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.error(f"停止插件服务失败：{str(e)}")

    def execute_copy_task(self):
        logger.info("开始执行AList多目录复制任务")
        
        if not self._validate_config():
            return
            
        directory_pairs = self._parse_directory_pairs()
        if not directory_pairs:
            self._complete_task("failed", "未配置有效的目录配对")
            return
        
        # 任务执行前先更新文件状态
        logger.info("开始更新文件状态...")
        self._update_file_status_and_counts()
        
        # 检查复制中和已完成的文件数量
        copying_count, completed_count = self._get_file_status_counts()
        
        # 如果检测到复制中的文件，先检查目标目录是否存在这些文件
        if copying_count > 0:
            logger.info(f"检测到 {copying_count} 个复制中的文件，正在检查目标目录是否存在这些文件...")
            updated_count = self._check_and_update_copying_files(directory_pairs)
            if updated_count > 0:
                logger.info(f"已将 {updated_count} 个复制中的文件更新为已完成状态")
            
            # 重新获取状态统计
            copying_count, completed_count = self._get_file_status_counts()
        
        # 检查是否需要执行复制任务
        if not self._should_execute_copy_task(directory_pairs, copying_count):
            logger.info("无需执行复制任务，所有文件已处理完成")
            self._complete_task("success", "无需执行复制任务，所有文件已处理完成")
            return
            
        # 用于记录本次执行成功复制的文件
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
            if not self._verify_alist_connection():
                raise Exception("AList连接失败，请检查地址和令牌")
            
            total_copied = 0
            total_skipped = 0
            total_files = 0
            
            # 创建全局已处理文件集合，确保在整个任务执行期间文件只被处理一次
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
            
            # 添加执行记录（只有复制文件数大于0时才记录）
            self._add_execution_record(total_copied, successfully_copied_files)
            
            # 任务完成后更新文件状态
            self._update_file_status_and_counts()
            
            self._complete_task("success", 
                               f"复制完成！共处理 {len(directory_pairs)} 组目录配对，"
                               f"总计 {total_files} 个文件，"
                               f"复制 {total_copied} 个，"
                               f"跳过 {total_skipped} 个")
                               
        except Exception as e:
            logger.error(f"复制任务执行失败: {str(e)}")
            # 即使失败也记录执行记录（只有复制文件数大于0时才记录）
            self._add_execution_record(len(successfully_copied_files), successfully_copied_files)
            self._complete_task("failed", f"任务执行失败: {str(e)}")
        finally:
            # 确保立即运行标志被重置
            if self._onlyonce:
                self._onlyonce = False
                self.__update_config()
                logger.info("立即运行任务已完成，重置立即运行标志")

    def _should_execute_copy_task(self, directory_pairs: List[Dict[str, str]], copying_count: int) -> bool:
        """
        判断是否需要执行复制任务
        
        返回:
            bool: True表示需要执行复制任务，False表示跳过
        """
        # 如果还有复制中的文件，需要执行任务
        if copying_count > 0:
            return True
            
        # 检查源目录是否有新文件需要复制
        logger.info("检查源目录是否有新文件需要复制...")
        
        for pair in directory_pairs:
            source_dir = pair["source"]
            target_dir = pair["target"]
            
            try:
                # 扫描源目录
                source_files = self._get_alist_files(source_dir)
                if not source_files:
                    continue
                
                # 扫描目标目录，构建目标文件索引
                target_files = self._get_alist_files(target_dir)
                target_index = self._build_target_index(target_files)
                
                # 检查源目录中是否有新文件
                current_suffixes = self._get_current_suffixes()
                
                for source_file in source_files:
                    filename = source_file.get("name")
                    if not filename:
                        continue
                        
                    # 只处理指定后缀的文件
                    if not any(filename.endswith(suffix) for suffix in current_suffixes):
                        continue
                    
                    # 检查文件是否已经在目标目录中存在 - 使用完整文件名判断
                    if filename not in target_index:
                        logger.info(f"发现新文件需要复制: {filename}")
                        return True
                        
            except Exception as e:
                logger.error(f"检查目录配对 {source_dir} → {target_dir} 时出错: {str(e)}")
                # 如果检查过程中出错，保守起见执行复制任务
                return True
        
        logger.info("所有源目录文件已在目标目录中存在，无需执行复制任务")
        return False

    def _check_and_update_copying_files(self, directory_pairs: List[Dict[str, str]]) -> int:
        """检查并更新复制中的文件状态"""
        updated_count = 0
        
        # 为每个目标目录构建文件索引
        target_dirs_index = {}
        for pair in directory_pairs:
            target_dir = pair["target"]
            if target_dir not in target_dirs_index:
                logger.info(f"扫描目标目录以检查复制中文件: {target_dir}")
                target_files = self._get_alist_files(target_dir)
                if target_files:
                    # 构建文件名索引（不包含路径）
                    file_index = {}
                    for file in target_files:
                        filename = file.get("name")
                        if filename:
                            file_index[filename] = file.get("path", "")
                    target_dirs_index[target_dir] = file_index
                    logger.info(f"目标目录 {target_dir} 有 {len(file_index)} 个文件")
                else:
                    target_dirs_index[target_dir] = {}
                    logger.info(f"目标目录 {target_dir} 为空")
        
        # 检查每个复制中的文件
        for file_key, record in self._copied_files.items():
            if record.get("status") != "copying":
                continue
                
            target_path = record.get("target_path", "")
            filename = record.get("filename", "")
            
            if not target_path or not filename:
                continue
                
            # 找到对应的目标目录
            target_dir = None
            for pair in directory_pairs:
                if target_path.startswith(pair["target"]):
                    target_dir = pair["target"]
                    break
            
            if not target_dir:
                continue
                
            # 检查文件是否在目标目录中存在
            if target_dir in target_dirs_index and filename in target_dirs_index[target_dir]:
                # 文件在目标目录中存在，更新状态为已完成
                self._copied_files[file_key]["status"] = "completed"
                self._copied_files[file_key]["completed_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
                updated_count += 1
                logger.info(f"复制中文件 {filename} 已在目标目录中存在，状态已更新为已完成")
        
        if updated_count > 0:
            self._save_copied_files()
        
        return updated_count

    def _update_target_files_count(self, directory_pairs: List[Dict[str, str]]):
        """更新目标目录文件数统计"""
        total_target_files = 0
        
        # 获取所有唯一的目标目录
        target_dirs = set()
        for pair in directory_pairs:
            target_dirs.add(pair["target"])
        
        # 统计每个目标目录的文件数
        for target_dir in target_dirs:
            try:
                target_files = self._get_alist_files(target_dir)
                if target_files:
                    total_target_files += len(target_files)
            except Exception as e:
                logger.error(f"统计目标目录 {target_dir} 文件数失败: {str(e)}")
        
        self._target_files_count = total_target_files
        self.save_data("alistcopy_target_files_count", self._target_files_count)

    def _execute_single_copy(self, source_dir: str, target_dir: str, pair_index: int, total_pairs: int, successfully_copied_files: List[str], global_processed_files: set) -> Optional[Dict[str, int]]:
        try:
            base_progress = int((pair_index) / total_pairs * 100)
            
            # 首先扫描目标目录，构建目标文件索引
            self._update_status(f"正在扫描目标目录: {target_dir}", base_progress + 5)
            target_files = self._get_alist_files(target_dir)
            target_index = self._build_target_index(target_files)
            
            # 然后扫描源目录
            self._update_status(f"正在扫描源目录: {source_dir}", base_progress + 15)
            source_files = self._get_alist_files(source_dir)
            if not source_files:
                return {"copied": 0, "skipped": 0, "total": 0}
            
            self._update_status(f"开始复制文件: {source_dir} → {target_dir}", base_progress + 25)
            copy_result = self._copy_files(source_files, target_index, source_dir, target_dir, base_progress + 25, 70, successfully_copied_files, global_processed_files)
            
            return copy_result
            
        except Exception as e:
            logger.error(f"处理目录配对 {source_dir} → {target_dir} 时出错: {str(e)}")
            return {"copied": 0, "skipped": 0, "total": 0}

    def _build_target_index(self, target_files: List[dict]) -> set:
        """构建目标索引 - 使用完整文件名"""
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
        if not self._alist_url or not self._alist_token:
            self._complete_task("failed", "AList地址或令牌未配置")
            return False
            
        directory_pairs = self._parse_directory_pairs()
        if not directory_pairs:
            self._complete_task("failed", "未配置有效的目录配对")
            return False
            
        return True

    def _verify_alist_connection(self) -> bool:
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

    def _get_alist_files(self, path: str) -> List[dict]:
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

    def _copy_files(self, source_files: List[dict], target_index: set, source_dir: str, target_dir: str, 
                   base_progress: int, progress_range: int, successfully_copied_files: List[str], global_processed_files: set) -> Dict[str, int]:
        if not source_files:
            logger.warning("源文件列表为空，跳过复制")
            return {"copied": 0, "skipped": 0, "total": 0}
            
        current_suffixes = self._get_current_suffixes()
        
        filtered_files = []
        for file in source_files:
            filename = file.get("name")
            if filename and any(filename.endswith(suffix) for suffix in current_suffixes):
                filtered_files.append(file)
        
        total = len(filtered_files)
        copied = 0
        skipped = 0
        
        logger.info(f"目录 {source_dir} → {target_dir} 过滤后需要处理的文件数量: {total}")
        
        for i, source_file in enumerate(filtered_files):
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
                
                # 生成文件唯一标识 - 使用源路径和目标路径的组合
                file_key = self._generate_file_key(source_path, target_path)
                
                # 检查1: 文件是否已经在本次任务执行中处理过
                if file_key in global_processed_files:
                    skipped += 1
                    logger.debug(f"跳过本次任务已处理文件: {filename}")
                    self._update_status(f"跳过已处理文件: {filename}", progress)
                    continue
                
                # 检查2: 文件是否在历史记录中已经复制过
                if file_key in self._copied_files:
                    # 检查文件记录状态
                    record_info = self._copied_files[file_key]
                    record_status = record_info.get("status", "copying")
                    
                    if record_status == "completed":
                        # 文件已完成复制，跳过
                        skipped += 1
                        completed_time = record_info.get("completed_time", "未知时间")
                        logger.debug(f"跳过已完成文件: {filename} (完成于: {completed_time})")
                        self._update_status(f"跳过已完成文件: {filename}", progress)
                        continue
                    else:
                        # 文件状态为复制中，跳过复制但保留记录
                        skipped += 1
                        copied_time = record_info.get("copied_time", "未知时间")
                        logger.debug(f"跳过复制中文件: {filename} (记录于: {copied_time})")
                        self._update_status(f"跳过复制中文件: {filename}", progress)
                        continue
                
                # 检查3: 目标目录是否已存在相同文件（基于完整文件名比对）
                if filename in target_index:
                    skipped += 1
                    logger.debug(f"跳过目标目录已存在文件: {filename}")
                    self._update_status(f"跳过目标目录已存在文件: {filename}", progress)
                    continue
                    
                # 执行复制操作
                if self._execute_alist_copy_standard(source_path, target_path, filename):
                    copied += 1
                    self._task_status["copied_files"] += 1
                    
                    # 记录成功复制的文件，默认状态为复制中
                    self._copied_files[file_key] = {
                        "source_path": source_path,
                        "target_path": target_path,
                        "filename": filename,
                        "copied_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "status": "copying"  # 默认状态为复制中
                    }
                    self._save_copied_files()  # 立即保存，避免重复复制
                    
                    # 添加到全局已处理文件集合
                    global_processed_files.add(file_key)
                    
                    # 记录成功复制的文件名
                    successfully_copied_files.append(filename)
                    
                    self._update_status(f"创建任务: {filename}", progress)
                else:
                    logger.error(f"复制失败: {filename}")
                    
            except Exception as e:
                logger.error(f"处理文件 {source_file.get('name', '未知文件')} 时出错: {str(e)}")
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

    def _generate_file_key(self, source_path: str, target_path: str) -> str:
        """生成文件唯一标识"""
        # 使用源文件路径和目标文件路径的组合作为唯一标识
        key_string = f"{source_path}->{target_path}"
        return hashlib.md5(key_string.encode()).hexdigest()

    def _execute_alist_copy_standard(self, source_path: str, target_path: str, filename: str) -> bool:
        """
        使用标准AList API复制方式，保留目录结构
        """
        try:
            # 提取目标目录（不包含文件名）
            target_dir = os.path.dirname(target_path)
            
            # 确保目标目录存在
            if not self._ensure_directory_exists(target_dir):
                logger.error(f"无法确保目标目录存在: {target_dir}")
                return False
            
            url = f"{self._alist_url}/api/fs/copy"
            headers = {
                "Authorization": self._alist_token,
                "Content-Type": "application/json"
            }
            
            # 根据AList官方API文档，复制API需要以下参数
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
            logger.error(f"复制文件异常: {filename}, 错误: {str(e)}")
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
            
            # 目录不存在，创建它
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

    def _update_status(self, message: str, progress: int = None):
        self._task_status["message"] = message
        if progress is not None:
            self._task_status["progress"] = progress
        self._save_task_status()
        
    def _complete_task(self, status: str, message: str):
        self._task_status.update({
            "status": status,
            "message": message,
            "progress": 100,
            "end_time": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        self._save_task_status()

    def _save_task_status(self):
        self.save_data("alistcopy_task_status", self._task_status)
        
    def _save_copied_files(self):
        self.save_data("alistcopy_copied_files", self._copied_files)

    def get_status(self):
        # 更新文件状态和数量统计
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
                    "directory_pairs": self._directory_pairs,
                    "enable_custom_suffix": self._enable_custom_suffix,
                    "cron": self._cron,
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
        if self._task_status.get("status") == "running":
            return {"success": False, "message": "任务正在运行中，请等待完成"}
        
        self._onlyonce = True
        self.__update_config()
        
        import threading
        threading.Thread(target=self.execute_copy_task, daemon=True).start()
        return {"success": True, "message": "复制任务已开始执行"}