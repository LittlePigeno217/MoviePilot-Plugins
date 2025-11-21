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
    logger.warning("MoviePilot Alist模块不可用，将使用手动配置")


class AlistCopyPlugin(_PluginBase):
    """
    AList复制插件 - 通过AList API实现多目录间文件复制
    """
    # 插件基本信息
    plugin_name = "OpenList自动复制"
    plugin_desc = "实现OpenList多目录间文件复制自动化"
    plugin_icon = "Alist_B.png"
    plugin_version = "1.4"
    plugin_author = "LittlePigeno"
    author_url = "https://github.com/LittlePigeno217/MoviePilot-Plugins"
    plugin_config_prefix = "alistcopy_"
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
        # 初始化配置项
        self._enabled: bool = False
        self._cron: str = ""
        self._onlyonce: bool = False
        self._clear_cache: bool = False
        self._alist_url: str = ""
        self._alist_token: str = ""
        self._directory_pairs: str = ""
        self._enable_custom_suffix: bool = False
        self._use_moviepilot_config: bool = True
        self._enable_wechat_notify: bool = False

        # 实例变量
        self._alist_instance: Any = None
        self._notification_helper: Any = None

        # 状态数据 - 在init_plugin中从持久化存储恢复
        self._task_status: Dict[str, Any] = {}
        self._copied_files: Dict[str, Any] = {}
        self._target_files_count: int = 0

        # 固定的卡片样式图片URL
        self._default_card_image = "https://raw.githubusercontent.com/LittlePigeno217/MoviePilot-Plugins/main/icons/Alist_B.png"
        
        # 用于记录本次执行前的已完成文件数量
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
        """获取当前启用的文件后缀列表"""
        all_suffixes = self.DEFAULT_VIDEO_SUFFIXES.copy()
        if self._enable_custom_suffix:
            for suffix in self.CUSTOM_SUFFIXES:
                if suffix not in all_suffixes:
                    all_suffixes.append(suffix)
        return all_suffixes

    def _is_media_file(self, filename: str) -> bool:
        """判断文件是否为媒体文件"""
        current_suffixes = self._get_current_suffixes()
        return any(filename.endswith(suffix) for suffix in current_suffixes)

    def _normalize_path(self, path: str) -> str:
        """标准化路径"""
        return path.rstrip('/')

    def _get_relative_path(self, file_path: str, base_dir: str) -> str:
        """获取文件相对于基础目录的相对路径"""
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

    def init_plugin(self, config: dict = None):
        """初始化插件 - 确保数据持久化"""
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

        # 初始化实例
        self._init_moviepilot_alist()
        if NOTIFICATION_AVAILABLE:
            self._notification_helper = NotificationHelper()

        # 处理清除缓存
        if self._clear_cache:
            logger.info("正在清空插件数据...")
            self._clear_all_data()
            self._clear_cache = False
            self.__update_config()

        # 恢复状态数据 - 确保插件更新或重新安装时数据不丢失
        logger.info("正在恢复插件状态数据...")
        self._task_status = self.get_data("alistcopy_task_status") or self._get_default_task_status()
        self._copied_files = self.get_data("alistcopy_copied_files") or {}
        self._target_files_count = self.get_data("alistcopy_target_files_count") or 0
        
        logger.info(f"恢复数据完成: 任务状态={self._task_status.get('status')}, " 
                   f"复制文件记录={len(self._copied_files)}个, "
                   f"目标文件数={self._target_files_count}")

        # 启动服务
        if self._enabled:
            if self._onlyonce:
                logger.info("开始执行AList复制任务")
                import threading
                threading.Thread(target=self.execute_copy_task, daemon=True).start()
                self._onlyonce = False
                self.__update_config()

    def _create_notification(self, title: str, text: str) -> Notification:
        """
        创建通知对象 - 固定使用卡片样式
        """
        return Notification(
            mtype=NotificationType.Manual,
            title=title,
            text=text,
            image=self._default_card_image,
            channel=MessageChannel.Wechat
        )

    def _get_wechat_instance(self) -> Any:
        """
        获取可用的企业微信实例
        返回: 企业微信实例或None
        """
        if not self._notification_helper:
            return None
            
        service_names = self._notification_helper.get_services()
        for service_name in service_names:
            service = self._notification_helper.get_service(name=service_name)
            if service and service.config.enabled:
                return service.instance
        return None

    def _send_wecom_card(self, title: str, text: str, picurl: str = None, wechat_instance=None) -> bool:
        """
        发送企业微信卡片消息（支持指定实例）
        """
        try:
            # 允许外部传入实例，优先用传入的
            if wechat_instance is None:
                wechat_instance = self._get_wechat_instance()
            if not wechat_instance:
                logger.error("未找到企业微信服务实例")
                return False

            # 获取access_token
            if not wechat_instance._WeChat__get_access_token():
                logger.error("获取微信access_token失败，请检查参数配置")
                return False

            # 构建卡片消息（news类型，支持图片）
            article = {
                "title": title,
                "description": text,
                "picurl": picurl or self._default_card_image
            }

            req_json = {
                "touser": "@all",
                "msgtype": "news",
                "agentid": wechat_instance._appid,
                "news": {
                    "articles": [article]
                },
                "safe": 0,
                "enable_id_trans": 0,
                "enable_duplicate_check": 0
            }

            # 拼接代理地址
            base_url = "https://qyapi.weixin.qq.com"
            if getattr(wechat_instance, '_proxy', None):
                base_url = wechat_instance._proxy
            message_url = f"{base_url}/cgi-bin/message/send?access_token={wechat_instance._access_token}"

            res = RequestUtils().post(message_url, json=req_json)
            if res is None:
                logger.error("发送请求失败，未获取到返回信息")
                return False
            if res.status_code != 200:
                logger.error(f"发送请求失败，错误码：{res.status_code}，错误原因：{res.reason}")
                return False

            ret_json = res.json()
            if ret_json.get("errcode") == 0:
                return True
            else:
                logger.error(f"企业微信消息发送失败: {ret_json.get('errmsg')}")
                return False
        except Exception as e:
            logger.error(f"企业微信文本卡片消息发送异常: {str(e)}")
            return False

    def _send_wechat_message(self, service: Any, title: str, text: str) -> bool:
        """
        发送企业微信消息的通用方法 - 固定使用卡片样式
        """
        if not service or not service.instance:
            return False

        wechat_instance = service.instance
        
        # 固定使用卡片样式
        return self._send_wecom_card(title, text, picurl=self._default_card_image, wechat_instance=wechat_instance)

    def post_message(self, message: Notification):
        """
        兼容主程序类型分发逻辑，支持企业微信card推送。
        """
        try:
            # 获取消息属性
            mtype = getattr(message, "mtype", None)
            mtype_value = mtype.value if mtype else None
            channel = getattr(message, "channel", None)
            text = getattr(message, "text", "")
            title = getattr(message, "title", "")
            
            # 获取所有通知服务名称
            if not self._notification_helper:
                logger.warning("通知助手未初始化，无法发送通知")
                return
                
            service_names = self._notification_helper.get_services()
            for service_name in service_names:
                service = self._notification_helper.get_service(name=service_name)
                if not service or not service.config.enabled:
                    continue

                # 检查消息类型开关
                switchs = getattr(service.config, 'switchs', []) or []
                if mtype_value and mtype_value not in switchs:
                    continue

                # 处理企业微信消息
                if channel == MessageChannel.Wechat:
                    try:
                        self._send_wechat_message(service, title, text)
                        logger.info(f"企业微信通知发送成功: {title}")
                    except Exception as e:
                        logger.error(f"发送企业微信消息失败: {str(e)}")

        except Exception as e:
            logger.error(f"插件post_message分发异常: {str(e)}")

    def _init_moviepilot_alist(self):
        """初始化MoviePilot Alist实例"""
        if not ALIST_AVAILABLE:
            logger.warning("MoviePilot Alist模块不可用，请确保安装了正确版本的MoviePilot")
            return
            
        try:
            self._alist_instance = Alist()
            logger.info("MoviePilot Alist实例初始化成功")
            
            if self._use_moviepilot_config:
                self._update_alist_config_from_instance()
                
        except Exception as e:
            logger.error(f"初始化MoviePilot Alist实例失败: {str(e)}")

    def _update_alist_config_from_instance(self):
        """从MoviePilot Alist实例更新配置"""
        if not self._alist_instance:
            return
            
        try:
            # 获取基础URL
            if hasattr(self._alist_instance, '_Alist__get_base_url'):
                base_url = self._alist_instance._Alist__get_base_url
                if base_url:
                    self._alist_url = base_url.rstrip('/')
                    logger.info(f"从MoviePilot Alist实例获取地址: {self._alist_url}")
            
            # 获取Token
            if hasattr(self._alist_instance, '_Alist__get_valuable_toke'):
                token = self._alist_instance._Alist__get_valuable_toke
                if token:
                    self._alist_token = token
                    logger.info("从MoviePilot Alist实例获取Token成功")
                    
        except Exception as e:
            logger.error(f"从MoviePilot Alist实例获取配置失败: {str(e)}")

    def get_state(self) -> bool:
        return self._enabled

    def __update_config(self):
        """统一更新配置"""
        self.update_config({
            "onlyonce": self._onlyonce,
            "clear_cache": self._clear_cache,
            "cron": self._cron,
            "enabled": self._enabled,
            "alist_url": self._alist_url,
            "alist_token": self._alist_token,
            "directory_pairs": self._directory_pairs,
            "enable_custom_suffix": self._enable_custom_suffix,
            "use_moviepilot_config": self._use_moviepilot_config,
            "enable_wechat_notify": self._enable_wechat_notify
        })

    def _clear_all_data(self):
        """清空所有插件数据"""
        self._task_status = self._get_default_task_status()
        self._copied_files = {}
        self._target_files_count = 0
        self._previous_completed_count = 0
        self._previous_completed_files = []
        
        self.save_data("alistcopy_task_status", self._task_status)
        self.save_data("alistcopy_copied_files", self._copied_files)
        self.save_data("alistcopy_target_files_count", self._target_files_count)
        
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
                "summary": "执行任务"
            }
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        """获取定时服务"""
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
        # 检查MoviePilot Alist模块是否可用
        alist_available = ALIST_AVAILABLE
        
        return [
            {
                "component": "VForm",
                "content": [
                    # 第一块：基本设置
                    {
                        "component": "VCard",
                        "props": {"variant": "outlined", "class": "mb-4"},
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
                                                "props": {"icon": "mdi-cog", "color": "primary", "class": "mr-2"},
                                                "text": ""
                                            },
                                            {
                                                "component": "span",
                                                "props": {"class": "text-h6"},
                                                "text": "基本设置"
                                            }
                                        ]
                                    },
                                    # 第一行：启动插件，刮削文件，立即运行，清除缓存，执行周期
                                    {
                                        "component": "VRow",
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 3},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "enabled",
                                                            "label": "启动插件",
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 3},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "enable_custom_suffix",
                                                            "label": "刮削文件",
                                                            "hint": "额外复制字幕(.srt,.ass)、元数据(.nfo)、封面图(.jpg,.png)文件"
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 3},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "onlyonce",
                                                            "label": "立即运行",
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 3},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "clear_cache",
                                                            "label": "清理统计",
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    # 第二行：发送通知，使用MoviePilot的内置Alist/OpenList，执行周期
                                    {
                                        "component": "VRow",
                                        "props": {"class": "mt-4"},
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 4},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "enable_wechat_notify",
                                                            "label": "发送通知",
                                                            "hint": "当有复制任务时发送企业微信卡片通知"
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
                                                            "model": "use_moviepilot_config",
                                                            "label": "使用MoviePilot的内置Alist/OpenList",
                                                            "hint": "使用MoviePilot中已配置的Alist/OpenList实例",
                                                            "disabled": not alist_available
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 4},
                                                "content": [
                                                    {
                                                        "component": "VTextField",
                                                        "props": {
                                                            "model": "cron",
                                                            "label": "执行周期",
                                                            "placeholder": "0 2 * * *",
                                                            "hint": "Cron表达式，默认每天凌晨2点执行"
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    # 第三行：如果没有勾选读取内置配置，显示地址和令牌
                                    {
                                        "component": "VRow",
                                        "props": {"class": "mt-4"},
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 6},
                                                "content": [
                                                    {
                                                        "component": "VTextField",
                                                        "props": {
                                                            "model": "alist_url",
                                                            "label": "AList/OpenList地址",
                                                            "placeholder": "http://localhost:5244",
                                                            "hint": "请输入完整的AList或OpenList服务地址，如果使用MoviePilot配置则此项可留空",
                                                            "disabled": self._use_moviepilot_config and alist_available
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
                                                            "model": "alist_token",
                                                            "label": "AList/OpenList令牌",
                                                            "type": "password",
                                                            "placeholder": "在AList/OpenList后台获取",
                                                            "hint": "在AList/OpenList管理后台的'设置'-'全局'中获取令牌，如果使用MoviePilot配置则此项可留空",
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
                    },
                    
                    # 第二块：目录配对设置
                    {
                        "component": "VCard",
                        "props": {"variant": "outlined", "class": "mb-4"},
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
                                    # 目录配对设置
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
                    },
                    
                    # 第三块：说明信息
                    {
                        "component": "VCard",
                        "props": {"variant": "outlined", "class": "mt-4"},
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
                                                "props": {"icon": "mdi-information", "color": "info", "class": "mr-2"},
                                                "text": ""
                                            },
                                            {
                                                "component": "span",
                                                "props": {"class": "text-h6"},
                                                "text": "说明信息"
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
                                                            "variant": "tonal"
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
            "enabled": self._enabled,
            "onlyonce": self._onlyonce,
            "clear_cache": self._clear_cache,
            "alist_url": self._alist_url,
            "alist_token": self._alist_token,
            "directory_pairs": self._directory_pairs,
            "enable_custom_suffix": self._enable_custom_suffix,
            "use_moviepilot_config": self._use_moviepilot_config,
            "enable_wechat_notify": self._enable_wechat_notify,
            "cron": self._cron or "0 2 * * *"
        }

    def get_page(self) -> List[dict]:
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
        
        # 获取最近完成的媒体文件 - 上限50个
        recent_media_files = self._get_recent_media_files(50)
        
        # 获取正在复制的媒体文件 - 上限50个
        copying_media_files = self._get_copying_media_files(50)
        
        return [
            {
                "component": "VCard",
                "content": [
                    {
                        "component": "VCardText",
                        "content": [
                            # 第一行：三个状态框（每行4列，共12列） - 缩小高度
                            {
                                "component": "VRow",
                                "content": [
                                    # 状态框1：目标目录媒体文件数
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 12, "md": 4},
                                        "content": [
                                            {
                                                "component": "VCard",
                                                "props": {"color": "primary", "variant": "tonal", "style": "min-height: 80px; height: 100%;"},
                                                "content": [
                                                    {
                                                        "component": "VCardText",
                                                        "props": {"class": "text-center pa-2"},
                                                        "content": [
                                                            {
                                                                "component": "VIcon",
                                                                "props": {"icon": "mdi-folder-open", "size": "small", "color": "primary"},
                                                                "text": ""
                                                            },
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "text-h6 font-weight-bold mt-1"},
                                                                "text": "目标目录媒体文件数"
                                                            },
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "text-h5 font-weight-bold text-primary mt-1"},
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
                                        "props": {"cols": 12, "md": 4},
                                        "content": [
                                            {
                                                "component": "VCard",
                                                "props": {"color": "warning", "variant": "tonal", "style": "min-height: 80px; height: 100%;"},
                                                "content": [
                                                    {
                                                        "component": "VCardText",
                                                        "props": {"class": "text-center pa-2"},
                                                        "content": [
                                                            {
                                                                "component": "VIcon",
                                                                "props": {"icon": "mdi-progress-clock", "size": "small", "color": "warning"},
                                                                "text": ""
                                                            },
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "text-h6 font-weight-bold mt-1"},
                                                                "text": "当前复制媒体文件数量"
                                                            },
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "text-h5 font-weight-bold text-warning mt-1"},
                                                                "text": str(copying_count)
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
                                        "props": {"cols": 12, "md": 4},
                                        "content": [
                                            {
                                                "component": "VCard",
                                                "props": {"color": "info", "variant": "tonal", "style": "min-height: 80px; height: 100%;"},
                                                "content": [
                                                    {
                                                        "component": "VCardText",
                                                        "props": {"class": "text-center pa-2"},
                                                        "content": [
                                                            {
                                                                "component": "VIcon",
                                                                "props": {"icon": "mdi-history", "size": "small", "color": "info"},
                                                                "text": ""
                                                            },
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "text-h6 font-weight-bold mt-1"},
                                                                "text": "累计复制媒体文件数量"
                                                            },
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "text-h5 font-weight-bold text-info mt-1"},
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
                            
                            # 第二行：正在复制的媒体文件记录状态框
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
                                                                        "text": f"正在复制的媒体文件（共{len(copying_media_files)}个，显示最近50个）"
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
                            
                            # 第三行：最近完成的媒体文件记录状态框
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
                                                                        "text": f"最近完成的媒体文件（共{len(recent_media_files)}个，显示最近50个）"
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
                            }
                        ]
                    }
                ]
            }
        ]

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
                target_files = self._get_alist_files(target_dir)
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
        
        # 更新目标目录媒体文件数
        self._update_target_files_count(directory_pairs)
    
    def _normalize_path(self, path: str) -> str:
        """标准化路径"""
        return path.rstrip('/')
    
    def _is_media_file(self, filename: str) -> bool:
        """判断文件是否为媒体文件"""
        current_suffixes = self._get_current_suffixes()
        return any(filename.endswith(suffix) for suffix in current_suffixes)
    
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
                    "props": {"class": "text-center text-grey py-2"},
                    "text": "暂无完成的媒体文件记录"
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
                
                row_content.append({
                    "component": "VCol",
                    "props": {"cols": 12, "sm": 3, "md": 3, "lg": 3, "class": "pa-0"},
                    "content": [
                        {
                            "component": "VCard",
                            "props": {
                                "color": "deep-purple-lighten-5", 
                                "variant": "flat", 
                                "class": "text-center compact-file-card",
                                "style": "min-height: 28px; height: 100%;"
                            },
                            "content": [
                                {
                                    "component": "VCardText",
                                    "props": {
                                        "class": "pa-0 d-flex align-center justify-center", 
                                        "style": "min-height: 28px; padding: 2px 4px !important;"
                                    },
                                    "content": [
                                        {
                                            "component": "div",
                                            "props": {"class": "d-flex align-center justify-center w-100"},
                                            "content": [
                                                {
                                                    "component": "VIcon",
                                                    "props": {
                                                        "icon": "mdi-check-circle", 
                                                        "size": "x-small", 
                                                        "class": "text-success mr-1",
                                                        "style": "min-width: 16px;"
                                                    },
                                                    "text": ""
                                                },
                                                {
                                                    "component": "span",
                                                    "props": {
                                                        "class": "text-caption text-left compact-filename", 
                                                        "style": "word-break: break-all; line-height: 1.0; max-height: 2.0em; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; font-size: 0.65rem; flex: 1;"
                                                    },
                                                    "text": filename
                                                }
                                            ]
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
                    "props": {"cols": 12, "sm": 3, "md": 3, "lg": 3, "class": "pa-0"},
                    "content": []
                })
            
            content.append({
                "component": "VRow",
                "props": {"class": "mb-0", "dense": True, "align": "stretch"},
                "content": row_content
            })
        
        return content
    
    def _render_copying_media_files(self, media_files: List[Dict]) -> List[Dict]:
        """渲染正在复制的媒体文件列表 - 更紧凑的样式"""
        if not media_files:
            return [
                {
                    "component": "div",
                    "props": {"class": "text-center text-grey py-2"},
                    "text": "暂无正在复制的媒体文件"
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
                
                row_content.append({
                    "component": "VCol",
                    "props": {"cols": 12, "sm": 3, "md": 3, "lg": 3, "class": "pa-0"},
                    "content": [
                        {
                            "component": "VCard",
                            "props": {
                                "color": "orange-lighten-5", 
                                "variant": "flat", 
                                "class": "text-center compact-file-card",
                                "style": "min-height: 28px; height: 100%;"
                            },
                            "content": [
                                {
                                    "component": "VCardText",
                                    "props": {
                                        "class": "pa-0 d-flex align-center justify-center", 
                                        "style": "min-height: 28px; padding: 2px 4px !important;"
                                    },
                                    "content": [
                                        {
                                            "component": "div",
                                            "props": {"class": "d-flex align-center justify-center w-100"},
                                            "content": [
                                                {
                                                    "component": "VIcon",
                                                    "props": {
                                                        "icon": "mdi-progress-upload", 
                                                        "size": "x-small", 
                                                        "class": "text-orange mr-1",
                                                        "style": "min-width: 16px;"
                                                    },
                                                    "text": ""
                                                },
                                                {
                                                    "component": "span",
                                                    "props": {
                                                        "class": "text-caption text-left compact-filename", 
                                                        "style": "word-break: break-all; line-height: 1.0; max-height: 2.0em; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; font-size: 0.65rem; flex: 1;"
                                                    },
                                                    "text": filename
                                                }
                                            ]
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
                    "props": {"cols": 12, "sm": 3, "md": 3, "lg": 3, "class": "pa-0"},
                    "content": []
                })
            
            content.append({
                "component": "VRow",
                "props": {"class": "mb-0", "dense": True, "align": "stretch"},
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
        """
        停止服务
        """
        # 由于使用系统调度器，不需要手动停止
        pass

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
        logger.info("开始执行AList多目录复制任务")
        
        # 如果使用MoviePilot配置，更新Alist配置
        if self._use_moviepilot_config and self._alist_instance:
            self._update_alist_config_from_instance()
        
        if not self._validate_config():
            # 即使验证失败也要更新目标目录媒体文件数
            directory_pairs = self._parse_directory_pairs()
            if directory_pairs:
                self._update_target_files_count(directory_pairs)
            return
            
        directory_pairs = self._parse_directory_pairs()
        if not directory_pairs:
            self._complete_task("failed", "未配置有效的目录配对")
            # 即使配对失败也要更新目标目录媒体文件数
            self._update_target_files_count(directory_pairs)
            return
        
        # 记录执行前的已完成文件数量和列表
        _, old_completed_count = self._get_file_status_counts()
        self._previous_completed_count = old_completed_count
        self._previous_completed_files = self._get_completed_files_list()
        
        # 检查是否需要执行复制任务
        if not self._should_execute_copy_task(directory_pairs):
            logger.info("无需执行复制任务")
            # 即使跳过任务也要更新目标目录媒体文件数
            self._update_target_files_count(directory_pairs)
            
            # 检查是否有文件状态发生变化（从复制中变为已完成）
            self._update_file_status_and_counts(silent=True)
            _, new_completed_count = self._get_file_status_counts()
            increased_completed_count = new_completed_count - self._previous_completed_count
            
            # 即使没有复制任务，如果累计完成数量有增加，也发送通知
            if self._enable_wechat_notify and increased_completed_count > 0:
                newly_completed_files = self._get_newly_completed_files()
                self._send_wechat_notification(0, increased_completed_count, [], newly_completed_files)
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
            if not self._verify_alist_connection():
                raise Exception("AList连接失败，请检查地址和令牌")
            
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
            
            # 获取本次执行任务中新完成的文件列表
            newly_completed_files = self._get_newly_completed_files()
            
            # 发送企业微信通知的条件：当有产生复制任务或本次任务的累计复制媒体文件数量有增加时发送
            should_send_notification = (
                self._enable_wechat_notify and 
                (total_copied > 0 or increased_completed_count > 0)
            )
            
            if should_send_notification:
                self._send_wechat_notification(total_copied, increased_completed_count, 
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
            # 确保立即运行标志被重置 - 无论任务是否成功执行
            if self._onlyonce:
                self._onlyonce = False
                self.__update_config()
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

    def _send_wechat_notification(self, total_copied: int, increased_completed_count: int, 
                                successfully_copied_files: List[str], newly_completed_files: List[str]):
        """发送企业微信通知 - 使用固定的卡片样式"""
        try:
            # 构建通知内容
            title = "🏆 OpenList复制任务统计"
            
            # 构建本次复制文件列表，最多显示3个文件
            copied_files_text = ""
            if successfully_copied_files:
                if len(successfully_copied_files) <= 3:
                    copied_files_text = "\n".join([f"• {filename}" for filename in successfully_copied_files])
                else:
                    copied_files_text = "\n".join([f"• {filename}" for filename in successfully_copied_files[:3]])
                    copied_files_text += f"\n• ...等 {len(successfully_copied_files)} 个文件"
            else:
                copied_files_text = "• 无新增复制文件"
            
            # 构建完成复制任务的文件列表，最多显示3个文件
            completed_files_text = ""
            if newly_completed_files:
                if len(newly_completed_files) <= 3:
                    completed_files_text = "\n".join([f"• {filename}" for filename in newly_completed_files])
                else:
                    completed_files_text = "\n".join([f"• {filename}" for filename in newly_completed_files[:3]])
                    completed_files_text += f"\n• ...等 {len(newly_completed_files)} 个文件"
            else:
                completed_files_text = "• 无新增完成文件"
            
            # 美化通知内容
            message = f"\n" \
                    f"📊 **建立复制任务：** {total_copied} 个\n" \
                    f"✅ **完成复制任务：** {increased_completed_count} 个\n\n" \
                    f"📁 **本次复制文件列表：**\n{copied_files_text}\n\n" \
                    f"🎯 **本次完成复制任务的文件列表：**\n{completed_files_text}"
            
            # 创建通知对象 - 固定使用卡片样式
            notification = self._create_notification(title, message)
            
            # 发送通知
            self.post_message(notification)
            
            logger.info(f"企业微信卡片通知发送成功，本次新增完成数量: {increased_completed_count}")
            
        except Exception as e:
            logger.error(f"发送企业微信通知失败: {str(e)}")
        
    def _should_execute_copy_task(self, directory_pairs: List[Dict[str, str]]) -> bool:
        """
        判断是否需要执行复制任务 - 优化版本
        """
        # 检查是否有复制中的媒体文件
        copying_count, _ = self._get_file_status_counts()
        if copying_count > 0:
            logger.info(f"检测到 {copying_count} 个复制中的媒体文件，需要继续执行")
            return True
            
        # 检查源目录是否有新媒体文件需要复制
        logger.info("检查源目录是否有新媒体文件...")
        
        for pair in directory_pairs:
            source_dir = pair["source"]
            target_dir = pair["target"]
            
            try:
                # 扫描源目录
                source_files = self._get_alist_files(source_dir)
                if not source_files:
                    continue
                
                # 扫描目标目录，构建目标媒体文件索引
                target_files = self._get_alist_files(target_dir)
                target_index = self._build_target_index(target_files)
                
                # 检查源目录中是否有新媒体文件
                current_suffixes = self._get_current_suffixes()
                
                for source_file in source_files:
                    filename = source_file.get("name")
                    if not filename:
                        continue
                        
                    # 只处理媒体文件
                    if not any(filename.endswith(suffix) for suffix in current_suffixes):
                        continue
                    
                    # 检查媒体文件是否已经在目标目录中存在 - 使用完整文件名判断
                    if filename not in target_index:
                        logger.info(f"发现新媒体文件需要复制: {filename}")
                        return True
                        
            except Exception as e:
                logger.error(f"检查目录配对 {source_dir} → {target_dir} 时出错: {str(e)}")
                # 如果检查过程中出错，保守起见执行复制任务
                return True
        
        logger.info("所有源目录媒体文件已在目标目录中存在，无需执行复制任务")
        return False

    def _update_target_files_count(self, directory_pairs: List[Dict[str, str]]):
        """更新目标目录媒体文件数统计"""
        if not directory_pairs:
            self._target_files_count = 0
            self.save_data("alistcopy_target_files_count", self._target_files_count)
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
                    target_files = self._get_alist_files(target_dir)
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
        self.save_data("alistcopy_target_files_count", self._target_files_count)

    def _execute_single_copy(self, source_dir: str, target_dir: str, pair_index: int, total_pairs: int, successfully_copied_files: List[str], global_processed_files: set) -> Optional[Dict[str, int]]:
        try:
            base_progress = int((pair_index) / total_pairs * 100)
            
            # 首先扫描目标目录，构建目标媒体文件索引
            self._update_status(f"正在扫描目标目录: {target_dir}", base_progress + 5)
            target_files = self._get_alist_files(target_dir)
            target_index = self._build_target_index(target_files)
            
            # 然后扫描源目录
            self._update_status(f"正在扫描源目录: {source_dir}", base_progress + 15)
            source_files = self._get_alist_files(source_dir)
            if not source_files:
                return {"copied": 0, "skipped": 0, "total": 0}
            
            self._update_status(f"开始复制媒体文件: {source_dir} → {target_dir}", base_progress + 25)
            copy_result = self._copy_files(source_files, target_index, source_dir, target_dir, base_progress + 25, 70, successfully_copied_files, global_processed_files)
            
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
                "authorization": self._alist_token,
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
                
                # 生成文件唯一标识 - 使用源路径和目标路径的组合
                file_key = self._generate_file_key(source_path, target_path)
                
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
                if self._execute_alist_copy_standard(source_path, target_path, filename):
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
                "authorization": self._alist_token,
                "content-type": "application/json"
            }
            
            # 根据AList官方API文档，复制API需要以下参数
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

    def _ensure_directory_exists(self, path: str) -> bool:
        """确保目录存在"""
        try:
            url = f"{self._alist_url}/api/fs/get"
            headers = {
                "authorization": self._alist_token,
                "content-type": "application/json"
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
                    "enabled": self._enabled,
                    "alist_url": self._alist_url,
                    "alist_token": self._alist_token,
                    "directory_pairs": self._directory_pairs,
                    "enable_custom_suffix": self._enable_custom_suffix,
                    "cron": self._cron,
                    "use_moviepilot_config": self._use_moviepilot_config,
                    "enable_wechat_notify": self._enable_wechat_notify,
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