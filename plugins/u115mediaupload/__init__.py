from __future__ import annotations

import threading
import uuid
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

try:
    from apscheduler.triggers.cron import CronTrigger
except Exception:  # pragma: no cover
    CronTrigger = None

try:
    from app.core.config import settings
    from app.core.event import eventmanager
    from app.log import logger
    from app.plugins import _PluginBase
    from app.schemas.types import EventType
except Exception:  # pragma: no cover
    settings = type("Settings", (), {"U115_APP_ID": "", "U115_AUTH_SERVER": ""})()
    logger = type(
        "Logger",
        (),
        {
            "info": staticmethod(lambda *args, **kwargs: None),
            "warning": staticmethod(lambda *args, **kwargs: None),
            "warn": staticmethod(lambda *args, **kwargs: None),
            "error": staticmethod(lambda *args, **kwargs: None),
        },
    )()

    class _PluginBase:  # type: ignore
        pass

    class EventType:  # type: ignore
        TransferComplete = "transfer.complete"

    class _EventManager:
        @staticmethod
        def register(*args, **kwargs):
            def decorator(func):
                return func

            return decorator

    eventmanager = _EventManager()

from .client import U115AuthError, U115Client
from .records import IncrementalRecordStore, TaskHistory
from .scanner import MediaScanner, UploadPlanItem
from .scraper import MetadataScraper


DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "auth_mode": "cookie",
    "cookie": "",
    "tokens": {},
    "path_mappings": [],
    "media_extensions": [
        ".mkv",
        ".mp4",
        ".avi",
        ".mov",
        ".ts",
        ".iso",
        ".m2ts",
        ".rmvb",
        ".wmv",
    ],
    "sidecar_extensions": [
        ".nfo",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".srt",
        ".ass",
        ".ssa",
        ".sup",
    ],
    "upload_existing_sidecars": True,
    "scrape_before_upload": False,
    "scrape_overwrite": False,
    "event_incremental": True,
    "cron": "",
    "concurrency": 1,
}


class U115MediaUpload(_PluginBase):
    plugin_name = "115媒体上传"
    plugin_desc = "上传本地媒体和刮削文件到 115，支持全量、增量和秒传。"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/cloud.png"
    plugin_version = "1.0.0"
    plugin_author = "LittlePigeno"
    author_url = "https://github.com/LittlePigeno"
    plugin_config_prefix = "u115mediaupload_"
    plugin_order = 51
    auth_level = 1

    def __init__(self):
        super().__init__()
        self._config: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self._task_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._task_thread: Optional[threading.Thread] = None
        self._status: Dict[str, Any] = self._default_status()

    def init_plugin(self, config: dict = None):
        self._config = self._merge_config(config or self.get_config() or {})
        self._status = self.get_data("last_status") or self._default_status()
        self._stop_event.clear()

    def get_state(self) -> bool:
        return bool(self._config.get("enabled"))

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_render_mode(self) -> Tuple[str, Optional[str]]:
        return "vue", "dist/assets"

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        return None, self._public_config()

    def get_page(self) -> List[dict]:
        return []

    @staticmethod
    def get_sidebar_nav() -> List[Dict[str, Any]]:
        return [
            {
                "nav_key": "main",
                "title": "115媒体上传",
                "icon": "mdi-cloud-upload-outline",
                "section": "organize",
                "permission": "manage",
                "order": 60,
            }
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        if not self.get_state() or not self._config.get("cron") or CronTrigger is None:
            return []
        return [
            {
                "id": "U115MediaUpload_incremental",
                "name": "115媒体上传定时增量",
                "trigger": CronTrigger.from_crontab(self._config["cron"]),
                "func": self.run_incremental_task,
                "kwargs": {},
            }
        ]

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {"path": "/config", "endpoint": self._get_config_api, "methods": ["GET"], "auth": "bear", "summary": "获取配置"},
            {"path": "/config", "endpoint": self._save_config_api, "methods": ["POST"], "auth": "bear", "summary": "保存配置"},
            {"path": "/status", "endpoint": self._get_status_api, "methods": ["GET"], "auth": "bear", "summary": "获取状态"},
            {"path": "/run_full", "endpoint": self._run_full_api, "methods": ["POST"], "auth": "bear", "summary": "执行全量上传"},
            {"path": "/run_incremental", "endpoint": self._run_incremental_api, "methods": ["POST"], "auth": "bear", "summary": "执行增量上传"},
            {"path": "/stop", "endpoint": self._stop_api, "methods": ["POST"], "auth": "bear", "summary": "停止任务"},
            {"path": "/qrcode", "endpoint": self._qrcode_api, "methods": ["POST"], "auth": "bear", "summary": "生成 115 登录二维码"},
            {"path": "/check_login", "endpoint": self._check_login_api, "methods": ["GET"], "auth": "bear", "summary": "检查 115 登录状态"},
            {"path": "/history", "endpoint": self._history_api, "methods": ["GET"], "auth": "bear", "summary": "获取历史"},
            {"path": "/clear_records", "endpoint": self._clear_records_api, "methods": ["POST"], "auth": "bear", "summary": "清理增量记录"},
        ]

    def stop_service(self):
        self._stop_event.set()

    @eventmanager.register(EventType.TransferComplete)
    def transfer_complete(self, event):
        if not self.get_state() or not self._config.get("event_incremental"):
            return
        event_data = getattr(event, "event_data", None) or {}
        transferinfo = event_data.get("transferinfo")
        target_diritem = getattr(transferinfo, "target_diritem", None) if transferinfo else None
        scope = getattr(target_diritem, "path", None)
        self._start_task("incremental", scope_source=scope)

    def run_incremental_task(self):
        self._start_task("incremental")

    def _get_config_api(self) -> Dict[str, Any]:
        return self._public_config()

    def _save_config_api(self, config_payload: dict = None) -> Dict[str, Any]:
        self._config = self._merge_config(config_payload or {})
        self.update_config(self._config)
        self.init_plugin(self._config)
        return {"success": True, "message": "配置已保存", "data": self._public_config()}

    def _get_status_api(self) -> Dict[str, Any]:
        return {"success": True, "data": self._status_payload()}

    def _run_full_api(self) -> Dict[str, Any]:
        return self._start_task("full")

    def _run_incremental_api(self) -> Dict[str, Any]:
        return self._start_task("incremental")

    def _stop_api(self) -> Dict[str, Any]:
        self._stop_event.set()
        return {"success": True, "message": "已请求停止任务", "data": self._status_payload()}

    def _qrcode_api(self) -> Dict[str, Any]:
        client = self._make_client(require_cookie=False)
        return client.generate_qrcode()

    def _check_login_api(self) -> Dict[str, Any]:
        client = self._make_client(require_cookie=False)
        result = client.check_login()
        if result.get("success") and (result.get("data") or {}).get("status") == 2:
            self._config["tokens"] = client.export_tokens()
            self._config["auth_mode"] = "qrcode"
            self.update_config(self._config)
        return result

    def _history_api(self) -> Dict[str, Any]:
        return {
            "success": True,
            "data": {
                "history": self.get_data("history") or [],
                "failures": self.get_data("failures") or [],
                "records": self.get_data("records") or {},
            },
        }

    def _clear_records_api(self) -> Dict[str, Any]:
        self.save_data("records", {})
        return {"success": True, "message": "增量记录已清理"}

    def _start_task(self, mode: str, scope_source: Optional[str] = None) -> Dict[str, Any]:
        with self._task_lock:
            if self._task_thread and self._task_thread.is_alive():
                return {"success": False, "message": "已有任务正在运行", "data": self._status_payload()}
            self._stop_event.clear()
            task_id = uuid.uuid4().hex[:12]
            self._task_thread = threading.Thread(
                target=self._run_task,
                kwargs={"task_id": task_id, "mode": mode, "scope_source": scope_source},
                daemon=True,
            )
            self._task_thread.start()
        return {"success": True, "message": "任务已启动", "data": self._status_payload()}

    def _run_task(self, task_id: str, mode: str, scope_source: Optional[str] = None) -> None:
        started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        records = IncrementalRecordStore(self.get_data("records") or {})
        history = TaskHistory(self.get_data("history") or [])
        failures: List[Dict[str, Any]] = []
        counts = {
            "scanned": 0,
            "planned": 0,
            "reused": 0,
            "uploaded": 0,
            "failed": 0,
        }

        self._set_status(task_id, mode, "scanning", counts, "开始扫描")
        try:
            mappings = self._scoped_mappings(scope_source)
            scanner = MediaScanner(
                media_extensions=self._config.get("media_extensions"),
                sidecar_extensions=self._config.get("sidecar_extensions"),
            )
            plan, scan_failures = scanner.scan_mappings(
                mappings,
                include_sidecars=bool(self._config.get("upload_existing_sidecars")),
                records=records,
                incremental=mode == "incremental",
            )
            failures.extend(scan_failures)
            counts["scanned"] = len(plan)

            if self._config.get("scrape_before_upload"):
                self._set_status(task_id, mode, "scraping", counts, "开始刮削")
                plan.extend(self._scrape_generated_items(scanner, plan, records, mode))

            counts["planned"] = len(plan)
            self._set_status(task_id, mode, "uploading", counts, "开始上传")
            client = self._make_client()

            for item in plan:
                if self._stop_event.is_set():
                    self._set_status(task_id, mode, "stopped", counts, "任务已停止")
                    break
                result = self._upload_item(client, item)
                if result.get("success"):
                    if result.get("reused"):
                        counts["reused"] += 1
                    else:
                        counts["uploaded"] += 1
                    records.mark_uploaded(item.path, item.target_path)
                    self._set_status(task_id, mode, "uploading", counts, f"已上传 {item.path.name}")
                else:
                    counts["failed"] += 1
                    failures.append(result)
                    self._set_status(task_id, mode, "uploading", counts, f"上传失败 {item.path.name}")

            final_phase = "stopped" if self._stop_event.is_set() else "completed"
            message = "任务已停止" if final_phase == "stopped" else "任务完成"
        except Exception as err:
            counts["failed"] += 1
            failures.append({"reason": str(err)})
            final_phase = "failed"
            message = str(err)
            logger.error(f"【115媒体上传】任务失败: {err}")

        ended_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        summary = {
            "id": task_id,
            "mode": mode,
            "status": final_phase,
            "message": message,
            "counts": counts,
            "started_at": started_at,
            "ended_at": ended_at,
        }
        history.add(summary)
        self.save_data("records", records.to_dict())
        self.save_data("history", history.to_list())
        self.save_data("failures", failures[:100])
        self._set_status(task_id, mode, final_phase, counts, message, last_result=summary)

    def _scrape_generated_items(
        self,
        scanner: MediaScanner,
        plan: List[UploadPlanItem],
        records: IncrementalRecordStore,
        mode: str,
    ) -> List[UploadPlanItem]:
        scraper = MetadataScraper(self._config.get("sidecar_extensions"), logger=logger)
        generated: List[UploadPlanItem] = []
        for item in [entry for entry in plan if entry.kind == "media"]:
            if self._stop_event.is_set():
                break
            result = scraper.scrape_and_collect(
                item.path, overwrite=bool(self._config.get("scrape_overwrite"))
            )
            paths = result.get("paths") or []
            if not result.get("success"):
                continue
            generated.extend(
                scanner.plan_for_paths(
                    paths,
                    source_root=Path(item.source_root),
                    target_root=item.target_root,
                    records=records,
                    incremental=mode == "incremental",
                )
            )
        known = {entry.target_path for entry in plan}
        return [item for item in generated if item.target_path not in known]

    def _upload_item(self, client: U115Client, item: UploadPlanItem) -> Dict[str, Any]:
        parent_path = PurePosixPath(item.target_path).parent.as_posix()
        target_dir = client.get_folder(parent_path)
        if not target_dir:
            return {
                "success": False,
                "local_path": str(item.path),
                "target_path": item.target_path,
                "reason": "115 目录创建失败",
            }
        try:
            result = client.upload_file(target_dir, item.path, new_name=Path(item.target_path).name)
        except U115AuthError as err:
            raise err
        except Exception as err:
            return {
                "success": False,
                "local_path": str(item.path),
                "target_path": item.target_path,
                "reason": str(err),
            }
        return {
            "success": bool(result.success),
            "reused": bool(result.reused),
            "local_path": str(item.path),
            "target_path": item.target_path,
            "reason": result.message,
        }

    def _make_client(self, require_cookie: bool = True) -> U115Client:
        cookie = self._config.get("cookie") or ""
        tokens = self._config.get("tokens") or {}
        app_id = getattr(settings, "U115_APP_ID", "")
        auth_server = getattr(settings, "U115_AUTH_SERVER", "")
        client = U115Client(
            cookie=cookie,
            tokens=tokens,
            app_id=app_id,
            auth_server=auth_server,
            logger=logger,
        )
        if require_cookie and not client.is_authenticated():
            raise U115AuthError("115 未授权")
        return client

    def _scoped_mappings(self, scope_source: Optional[str]) -> List[Dict[str, Any]]:
        mappings = list(self._config.get("path_mappings") or [])
        if not scope_source:
            return mappings
        scope = Path(scope_source)
        result = []
        for mapping in mappings:
            source = Path(str(mapping.get("source") or ""))
            try:
                if scope.is_relative_to(source) or source.is_relative_to(scope):
                    result.append(mapping)
            except ValueError:
                continue
        return result or mappings

    def _set_status(
        self,
        task_id: str,
        mode: str,
        phase: str,
        counts: Dict[str, int],
        message: str,
        last_result: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._status = {
            "task_id": task_id,
            "mode": mode,
            "phase": phase,
            "running": phase in {"scanning", "scraping", "uploading"},
            "message": message,
            "counts": dict(counts),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_result": last_result or self._status.get("last_result"),
        }
        self.save_data("last_status", self._status)

    def _status_payload(self) -> Dict[str, Any]:
        return {
            **self._status,
            "enabled": self.get_state(),
            "auth_mode": self._config.get("auth_mode"),
            "authorized": bool(self._config.get("cookie") or (self._config.get("tokens") or {}).get("access_token")),
            "mapping_count": len(self._config.get("path_mappings") or []),
        }

    @staticmethod
    def _default_status() -> Dict[str, Any]:
        return {
            "task_id": "",
            "mode": "",
            "phase": "idle",
            "running": False,
            "message": "未执行",
            "counts": {"scanned": 0, "planned": 0, "reused": 0, "uploaded": 0, "failed": 0},
            "updated_at": "",
            "last_result": None,
        }

    def _public_config(self) -> Dict[str, Any]:
        return dict(self._config)

    @staticmethod
    def _merge_config(config: Dict[str, Any]) -> Dict[str, Any]:
        merged = {**DEFAULT_CONFIG, **(config or {})}
        merged["path_mappings"] = [
            {
                "enabled": bool(item.get("enabled", True)),
                "source": str(item.get("source") or ""),
                "target": str(item.get("target") or "/"),
            }
            for item in merged.get("path_mappings") or []
            if item
        ]
        merged["concurrency"] = max(1, int(merged.get("concurrency") or 1))
        return merged
