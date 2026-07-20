from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from apscheduler.triggers.cron import CronTrigger
from app.core.event import Event, eventmanager
from app.log import logger
from app.plugins import _PluginBase
from app.scheduler import Scheduler
from app.schemas.types import EventType

from .api import Api
from .client import U115Client
from .life_monitor import LifeMonitor
from .store import Store


class P115LiteAssistant(_PluginBase):
    plugin_name = "115 轻量助手"
    plugin_desc = "独立提供 115 登录、生活事件监控、STRM/302、目录上传秒传和签到。"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/cloud.png"
    plugin_version = "1.1.7"
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
        self._api = Api(
            self._get_client,
            self._store,
            on_config_saved=self._on_config_saved,
            life_monitor_status=self._is_life_monitor_running,
        )
        self._life_monitor = LifeMonitor(
            self._get_client,
            self._store,
            self._api.cloud_task_lock,
            self._moviepilot_url,
        )

    def init_plugin(self, config: dict | None = None) -> None:
        if config:
            self._store.update_config(config)
        self._client = None
        self._client_signature = None
        self._sync_life_monitor()

    def _moviepilot_url(self) -> str:
        return str(self._store.get_config().get("moviepilot_address") or "").strip().rstrip("/")

    def _is_life_monitor_running(self) -> bool:
        monitor = getattr(self, "_life_monitor", None)
        return bool(monitor and monitor.is_running)

    def _on_config_saved(self) -> None:
        self._client = None
        self._client_signature = None
        self._sync_life_monitor()

    def _sync_life_monitor(self) -> None:
        config = self._store.get_config()
        mappings = [
            mapping
            for mapping in config.get("strm_mappings") or []
            if isinstance(mapping, dict) and mapping.get("enabled", True)
        ]
        if config.get("enabled") and config.get("life_monitor_enabled") and mappings:
            self._life_monitor.start()
        else:
            self._life_monitor.stop()

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

    def get_state(self) -> bool:
        return bool(self._store.get_config().get("enabled"))

    @eventmanager.register(EventType.TransferComplete)
    def upload_after_transfer_complete(self, event: Event) -> None:
        """媒体整理完成后触发一次增量上传。"""
        if not event.event_data:
            return
        config = self._store.get_config()
        if not config.get("enabled"):
            return
        if not any(
            isinstance(mapping, dict) and mapping.get("enabled", True)
            for mapping in config.get("upload_mappings") or []
        ):
            return
        logger.info("【目录上传】媒体整理完成，触发增量上传")
        self._api.trigger_upload(True)

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
            {
                "path": "/redirect",
                "endpoint": self._api.redirect,
                "methods": ["GET", "POST", "HEAD"],
                "allow_anonymous": True,
                "summary": "115 302 跳转",
            },
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
        self._life_monitor.stop()
        try:
            Scheduler().remove_plugin_job("p115liteassistant_checkin")
        except Exception:  # noqa: BLE001
            pass
        self._client = None
        self._client_signature = None
