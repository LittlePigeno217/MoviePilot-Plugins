from typing import Any, Dict, List, Optional, Tuple

from apscheduler.triggers.cron import CronTrigger

from app.plugins import _PluginBase
from app.core.config import settings
from app.log import logger
from app.scheduler import Scheduler

from .client import U115Client
from .store import Store
from .api import Api


class P115StrmHelper(_PluginBase):
    plugin_name = "115 STRM 助手"
    plugin_desc = "扫描 115 网盘目录生成 STRM，经 302 重定向流式播放，支持定时/增量/刮削同步与多目录映射。"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/cloud.png"
    plugin_version = "1.0.0"
    plugin_author = "LittlePigeno"
    author_url = "https://github.com/LittlePigeno217"
    plugin_config_prefix = "p115strmhelper_"
    plugin_order = 52
    auth_level = 1

    def __init__(self):
        super().__init__()
        self._store = Store(self)
        self._client: Optional[U115Client] = None
        self._api = Api(self._get_client, self._store, self._get_api_token)

    def init_plugin(self, config: dict = None):
        # MoviePilot 标准配置流：保存面板提交的 config 到 Store，保持单一数据源
        if config:
            merged = self._store.get_config()
            merged.update(config)
            self._store.save_config(merged)
        # 每次初始化重建客户端，读取最新配置
        self._client = None
        self._get_client()

    def _get_client(self) -> U115Client:
        if self._client is None:
            cfg = self._store.get_config()
            app_id = cfg.get("app_id") or getattr(settings, "U115_APP_ID", "")
            auth_server = cfg.get("auth_server") or getattr(settings, "U115_AUTH_SERVER", "")
            self._client = U115Client(
                cookie=cfg.get("cookie", ""),
                tokens=cfg.get("tokens", {}),
                app_id=app_id,
                auth_server=auth_server,
                logger=logger,
            )
        return self._client

    @staticmethod
    def _get_api_token() -> str:
        return settings.API_TOKEN

    def get_state(self) -> bool:
        return bool(self._store.get_config().get("mappings"))

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_render_mode(self) -> Tuple[str, Optional[str]]:
        return "vue", "dist/assets"

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        cfg = self._store.get_config()
        cfg.pop("tokens", None)  # 初始数据不外泄 token
        return None, cfg

    def get_page(self) -> Optional[List[dict]]:
        return None

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {"path": "/qrcode", "endpoint": self._api.qrcode, "methods": ["POST"], "auth": "bear", "summary": "生成二维码"},
            {"path": "/check_login", "endpoint": self._api.check_login, "methods": ["GET"], "auth": "bear", "summary": "检查登录"},
            {"path": "/browse_115", "endpoint": self._api.browse_115, "methods": ["GET"], "auth": "bear", "summary": "浏览115目录"},
            {"path": "/browse_local", "endpoint": self._api.browse_local, "methods": ["GET"], "auth": "bear", "summary": "浏览本地目录"},
            {"path": "/config", "endpoint": self._api.get_config, "methods": ["GET"], "auth": "bear", "summary": "读配置"},
            {"path": "/config", "endpoint": self._api.save_config, "methods": ["POST"], "auth": "bear", "summary": "写配置"},
            {"path": "/sync", "endpoint": self._api.trigger_sync, "methods": ["POST"], "auth": "bear", "summary": "触发同步"},
            {"path": "/history", "endpoint": self._api.history, "methods": ["GET"], "auth": "bear", "summary": "同步历史"},
            {"path": "/redirect", "endpoint": self._api.redirect, "methods": ["GET"], "auth": "apikey", "summary": "302重定向"},
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        cron = (self._store.get_config().get("schedule_cron") or "").strip()
        if not cron:
            return []
        try:
            return [{
                "id": self.__class__.__name__.lower(),
                "name": "115 STRM 定时同步",
                "trigger": CronTrigger.from_crontab(cron),
                "func": self._api.run_sync,
                "kwargs": {},
            }]
        except Exception as err:  # noqa: BLE001
            logger.error(f"{self.plugin_name}: 注册定时任务失败: {err}")
            return []

    def stop_service(self):
        try:
            Scheduler().remove_plugin_job(self.__class__.__name__.lower())
        except Exception as err:  # noqa: BLE001
            logger.warning(f"{self.plugin_name}: 移除定时任务失败: {err}")
        self._client = None
