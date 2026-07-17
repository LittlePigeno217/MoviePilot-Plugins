from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from apscheduler.triggers.cron import CronTrigger
from app.core.config import settings
from app.log import logger
from app.plugins import _PluginBase
from app.scheduler import Scheduler

from .api import Api
from .client import U115Client
from .store import Store


class P115LiteAssistant(_PluginBase):
    plugin_name = "115 轻量助手"
    plugin_desc = "独立提供 115 登录、目录选择、STRM/302、目录上传秒传和签到。"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/cloud.png"
    plugin_version = "1.1.1"
    plugin_author = "LittlePigeno"
    author_url = "https://github.com/LittlePigeno217"
    plugin_config_prefix = "p115liteassistant_"
    plugin_order = 52
    auth_level = 1

    def __init__(self):
        super().__init__()
        self._store = Store(self)
        self._client: Optional[U115Client] = None
        self._client_signature: Optional[Tuple[str, ...]] = None
        self._api = Api(self._get_client, self._store, self._get_api_token)

    def init_plugin(self, config: dict | None = None) -> None:
        if config:
            self._store.update_config(config)
        self._client = None

    def _get_client(self) -> U115Client:
        config = self._store.get_config()
        client_type = str(config.get("login_client_type") or "")
        signature = (str(config.get("cookie") or ""), client_type)
        if self._client is None or self._client_signature != signature:
            self._client = U115Client(
                cookie=signature[0],
                tokens=config.get("tokens") or {},
                client_type=signature[1],
                token_saver=self._save_client_tokens,
            )
            self._client_signature = signature
        return self._client

    def _save_client_tokens(self, tokens: Dict[str, Any]) -> None:
        self._store.update_config({"tokens": dict(tokens)})

    @staticmethod
    def _get_api_token() -> str:
        return str(settings.API_TOKEN)

    def get_state(self) -> bool:
        return bool(self._store.get_config().get("enabled"))

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_render_mode(self) -> Tuple[str, Optional[str]]:
        return "vue", "dist/assets"

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        config = self._store.get_config()
        config.pop("tokens", None)
        return None, config

    def get_page(self) -> Optional[List[dict]]:
        return None

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {"path": "/config", "endpoint": self._api.get_config, "methods": ["GET"], "auth": "bear", "summary": "读取配置"},
            {"path": "/config", "endpoint": self._api.save_config, "methods": ["POST"], "auth": "bear", "summary": "保存配置"},
            {"path": "/qrcode", "endpoint": self._api.qrcode, "methods": ["POST"], "auth": "bear", "summary": "获取 115 登录二维码"},
            {"path": "/check-login", "endpoint": self._api.check_login, "methods": ["GET"], "auth": "bear", "summary": "检查 115 扫码状态"},
            {"path": "/browse-115", "endpoint": self._api.browse_115, "methods": ["GET"], "auth": "bear", "summary": "浏览 115 目录"},
            {"path": "/browse-local", "endpoint": self._api.browse_local, "methods": ["GET"], "auth": "bear", "summary": "浏览本地媒体库目录"},
            {"path": "/status", "endpoint": self._api.status, "methods": ["GET"], "auth": "bear", "summary": "获取运行状态"},
            {"path": "/strm/sync", "endpoint": self._api.trigger_strm, "methods": ["POST"], "auth": "bear", "summary": "开始 STRM 同步"},
            {"path": "/upload", "endpoint": self._api.trigger_upload, "methods": ["POST"], "auth": "bear", "summary": "开始目录上传"},
            {"path": "/checkin", "endpoint": self._api.run_checkin, "methods": ["POST"], "auth": "bear", "summary": "执行 115 签到"},
            {"path": "/history", "endpoint": self._api.history, "methods": ["GET"], "auth": "bear", "summary": "读取执行历史"},
            {"path": "/redirect", "endpoint": self._api.redirect, "methods": ["GET"], "auth": "apikey", "summary": "115 302 跳转"},
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        config = self._store.get_config()
        if not config.get("enabled") or not config.get("checkin_enabled"):
            return []
        try:
            return [
                {
                    "id": "p115liteassistant_checkin",
                    "name": "115 轻量助手随机每日签到",
                    "trigger": CronTrigger.from_crontab("*/5 * * * *"),
                    "func": self._api.run_scheduled_checkin,
                    "kwargs": {},
                }
            ]
        except Exception as err:  # noqa: BLE001
            logger.error(f"{self.plugin_name}: 签到定时任务注册失败: {err}")
            return []

    def stop_service(self) -> None:
        try:
            Scheduler().remove_plugin_job("p115liteassistant_checkin")
        except Exception:  # noqa: BLE001
            pass
        self._client = None
        self._client_signature = None
