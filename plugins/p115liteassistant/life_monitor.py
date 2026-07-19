from __future__ import annotations

from datetime import datetime
from pathlib import Path, PurePosixPath
from threading import Event, Lock, RLock, Thread, current_thread
from time import monotonic, time
from typing import Any, Callable, Dict, Iterable, Optional

import httpx

from app.log import logger

from .client import U115ApiError, U115AuthError, U115Client
from .file_types import DEFAULT_MEDIA_EXTENSIONS, DEFAULT_SIDECAR_EXTENSIONS, parse_extensions
from .strm import (
    STRM_URL_FORMAT_VERSION,
    build_strm_content,
    build_strm_record,
    mapping_cloud_path,
    normalize_cloud_path,
    normalize_pickcode,
    strm_output_path,
    write_strm_file,
)


CREATE_EVENT_TYPES = frozenset({1, 2, 14, 18, 23})
MOVE_EVENT_TYPES = frozenset({5, 6})
RENAME_EVENT_TYPES = frozenset({20, 24})
DELETE_EVENT_TYPES = frozenset({22})
SUPPORTED_EVENT_TYPES = (
    CREATE_EVENT_TYPES
    | MOVE_EVENT_TYPES
    | RENAME_EVENT_TYPES
    | DELETE_EVENT_TYPES
    | {17}
)


class LifeEventRetryError(U115ApiError):
    """事件的本地状态未可靠落地，必须保留游标等待下一轮重试。"""


EVENT_TYPE_NAMES = {
    1: "上传图片",
    2: "上传文件",
    5: "移动图片",
    6: "移动文件或目录",
    14: "接收文件",
    17: "新建目录",
    18: "复制目录",
    20: "重命名目录",
    22: "删除文件或目录",
    23: "复制文件",
    24: "重命名文件",
}
EVENT_NAME_TYPES = {
    "upload_image_file": 1,
    "upload_file": 2,
    "move_image_file": 5,
    "move_file": 6,
    "receive_files": 14,
    "new_folder": 17,
    "copy_folder": 18,
    "folder_rename": 20,
    "delete_file": 22,
    "copy_file": 23,
    "file_rename": 24,
}


class LifeMonitor:
    """轮询 115 生活事件，并将事件转换为局部 STRM 状态变更。"""

    POLL_INTERVAL = 15.0
    ERROR_RETRY_INTERVAL = 30.0
    WEB_FALLBACK_DURATION = 24 * 60 * 60
    EVENT_PAGE_SIZE = 1000
    FIRST_EVENT_PAGE_SIZE = 64
    EVENT_PAGE_COOLDOWN = 2.0

    def __init__(
        self,
        client_provider: Callable[[], U115Client],
        store,
        cloud_task_lock: Optional[Lock] = None,
        moviepilot_url_provider: Optional[Callable[[], str]] = None,
    ):
        self._client_provider = client_provider
        self._store = store
        self._cloud_task_lock = cloud_task_lock or Lock()
        self._moviepilot_url_provider = moviepilot_url_provider or (lambda: "")
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        self._thread_lock = Lock()
        self._state_lock = RLock()
        self._desired_running = False

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive())

    def start(self) -> None:
        """启动生活事件监控线程。"""

        with self._thread_lock:
            self._desired_running = True
            if self.is_running:
                return
            self._stop_event = Event()
            self._thread = Thread(
                target=self._thread_main,
                name="p115liteassistant-life",
                daemon=True,
            )
            self._thread.start()
        logger.info("【115生活监控】监控线程已启动")

    def stop(self, timeout: float = 5.0) -> None:
        """请求停止生活事件监控线程，并等待其退出。"""

        with self._thread_lock:
            self._desired_running = False
            thread = self._thread
            stop_event = self._stop_event
        if not thread:
            return
        stop_event.set()
        if thread and thread.is_alive() and thread is not current_thread():
            thread.join(timeout=max(0.0, float(timeout)))
        with self._thread_lock:
            if self._thread is thread and not thread.is_alive():
                self._thread = None
        logger.info("【115生活监控】监控线程已停止")

    def run_once(self) -> int:
        """执行一轮拉取与处理，返回成功处理的事件数量。"""

        with self._state_lock:
            self._migrate_legacy_records()
            cursor = self._load_cursor()
            events = self._fetch_events(cursor["from_time"], cursor["from_id"])
            processed = 0
            for event in events:
                self._process_event(event)
                event_time, event_id = self._event_cursor(event)
                self._save_cursor(event_time, event_id)
                processed += 1
            return processed

    def process_events(self, events: Iterable[Dict[str, Any]]) -> int:
        """供测试和宿主调用的逐事件处理入口，不负责拉取。"""

        with self._state_lock:
            processed = 0
            cursor = self._load_cursor()
            for event in self._sorted_events(events, cursor["from_time"], cursor["from_id"]):
                self._process_event(event)
                event_time, event_id = self._event_cursor(event)
                self._save_cursor(event_time, event_id)
                processed += 1
            return processed

    def _thread_main(self) -> None:
        """运行监控循环，并在短暂重启竞争中恢复线程。"""

        try:
            self._run()
        finally:
            with self._thread_lock:
                if self._thread is not current_thread():
                    return
                self._thread = None
                should_restart = self._desired_running and self._is_configured()
                if should_restart:
                    self._stop_event = Event()
                    self._thread = Thread(
                        target=self._thread_main,
                        name="p115liteassistant-life",
                        daemon=True,
                    )
                    self._thread.start()
            if should_restart:
                logger.info("【115生活监控】监控线程已重新启动")

    def _is_configured(self) -> bool:
        """判断当前配置是否仍满足监控启动条件。"""

        config = self._store.get_config()
        mappings = config.get("strm_mappings") or []
        return bool(
            config.get("enabled")
            and config.get("life_monitor_enabled")
            and any(
                isinstance(mapping, dict) and mapping.get("enabled", True)
                for mapping in mappings
            )
        )

    def _run(self) -> None:
        life_enabled = False
        while not self._stop_event.is_set():
            try:
                config = self._store.get_config()
                if not config.get("enabled") or not config.get("life_monitor_enabled"):
                    return
                client = self._client_provider()
                if not life_enabled:
                    client.enable_life_events()
                    life_enabled = True
                if self._cloud_task_lock.acquire(blocking=False):
                    try:
                        self.run_once()
                    finally:
                        self._cloud_task_lock.release()
                else:
                    logger.debug("【115生活监控】115 数据任务正在运行，本轮延后")
                self._stop_event.wait(self.POLL_INTERVAL)
            except (U115AuthError, U115ApiError, httpx.HTTPError) as err:
                logger.error(f"【115生活监控】本轮处理失败：{err}")
                self._stop_event.wait(self.ERROR_RETRY_INTERVAL)
            except Exception as err:  # noqa: BLE001
                logger.error(f"【115生活监控】线程异常：{err}")
                self._stop_event.wait(self.ERROR_RETRY_INTERVAL)

    @staticmethod
    def _is_405(err: BaseException) -> bool:
        if isinstance(err, httpx.HTTPStatusError):
            return err.response.status_code == 405
        text = str(err)
        return "405" in text or "Method Not Allowed" in text

    def _api_state(self) -> Dict[str, Any]:
        getter = getattr(self._store, "get_life_api_state", None)
        state = getter() if callable(getter) else {}
        return dict(state) if isinstance(state, dict) else {}

    def _save_api_state(self, state: Dict[str, Any]) -> None:
        saver = getattr(self._store, "save_life_api_state", None)
        if callable(saver):
            saver(state)

    def _selected_app(self) -> str:
        state = self._api_state()
        try:
            fallback_until = float(state.get("web_fallback_until") or 0)
        except (TypeError, ValueError):
            fallback_until = 0
        if fallback_until > time():
            return "web"
        if fallback_until:
            state.pop("web_fallback_until", None)
            self._save_api_state(state)
        return "ios"

    def _record_ios_405(self) -> None:
        state = self._api_state()
        try:
            count = int(state.get("ios_405_count") or 0) + 1
        except (TypeError, ValueError):
            count = 1
        if count >= 3:
            state = {
                "ios_405_count": 0,
                "web_fallback_until": int(time()) + self.WEB_FALLBACK_DURATION,
            }
            logger.warning("【115生活监控】proapi 连续 3 次 405，24 小时内切换 webapi")
        else:
            state["ios_405_count"] = count
        self._save_api_state(state)

    def _reset_ios_405(self) -> None:
        state = self._api_state()
        if state.get("ios_405_count"):
            state["ios_405_count"] = 0
            self._save_api_state(state)

    def _fetch_events(self, from_time: int, from_id: int) -> list[Dict[str, Any]]:
        client = self._client_provider()
        app = self._selected_app()
        try:
            pages = self._fetch_pages(client, app, from_time, from_id)
            if app == "ios":
                self._reset_ios_405()
        except Exception as err:
            if not self._is_405(err):
                raise
            if app == "web":
                state = self._api_state()
                state.pop("web_fallback_until", None)
                self._save_api_state(state)
                pages = self._fetch_pages(client, "ios", from_time, from_id)
                self._reset_ios_405()
            else:
                logger.warning("【115生活监控】proapi 返回 405，切换 webapi 重试")
                pages = self._fetch_pages(client, "web", from_time, from_id)
                self._record_ios_405()
        events: list[Dict[str, Any]] = []
        for page in pages:
            events.extend(page)
        return self._sorted_events(events, from_time, from_id)

    def _fetch_pages(
        self,
        client: U115Client,
        app: str,
        from_time: int = 0,
        from_id: int = 0,
    ) -> list[list[Dict[str, Any]]]:
        pages: list[list[Dict[str, Any]]] = []
        offset = 0
        limit = self.FIRST_EVENT_PAGE_SIZE if (from_time or from_id) else self.EVENT_PAGE_SIZE
        date = self._event_date(from_time)
        last_request_at = 0.0
        seen_page_signatures: set[tuple[tuple[int, int], ...]] = set()
        while True:
            if last_request_at:
                delay = self.EVENT_PAGE_COOLDOWN - (monotonic() - last_request_at)
                if delay > 0 and self._stop_event.wait(delay):
                    raise LifeEventRetryError("115 生活监控已停止")
            result = client.get_life_events_page(
                app=app,
                offset=offset,
                limit=limit,
                date=date,
            )
            last_request_at = monotonic()
            events = list(result.get("events") or [])
            pages.append(events)
            if not events:
                break
            signature = tuple(
                cursor
                for event in events
                if isinstance(event, dict)
                and (cursor := self._event_cursor_or_none(event)) is not None
            )
            if signature in seen_page_signatures:
                raise LifeEventRetryError(
                    "115 生活事件分页未前进，保留游标等待下一轮重试"
                )
            seen_page_signatures.add(signature)
            total = int(result.get("count") or 0)
            offset += len(events)
            if self._page_reaches_cursor(events, from_time, from_id):
                break
            if len(events) < limit or (total and offset >= total):
                break
            limit = self.EVENT_PAGE_SIZE
        return pages

    @classmethod
    def _event_cursor_or_none(cls, event: Dict[str, Any]) -> Optional[tuple[int, int]]:
        """读取事件游标，无法读取时返回空值。"""

        try:
            return cls._event_cursor(event)
        except ValueError:
            return None

    @staticmethod
    def _event_date(from_time: int) -> str:
        if not from_time:
            return ""
        try:
            event_date = datetime.fromtimestamp(from_time).date()
        except (OverflowError, OSError, ValueError):
            return ""
        return event_date.isoformat() if event_date == datetime.now().date() else ""

    @classmethod
    def _page_reaches_cursor(
        cls,
        events: Iterable[Dict[str, Any]],
        from_time: int,
        from_id: int,
    ) -> bool:
        if not (from_time or from_id):
            return False
        for event in events:
            try:
                event_time, event_id = cls._event_cursor(event)
            except ValueError:
                continue
            if event_time < from_time or (event_time == from_time and event_id <= from_id):
                return True
        return False

    @classmethod
    def _event_type(cls, event: Dict[str, Any]) -> int:
        raw = event.get("type")
        if raw in (None, ""):
            raw = event.get("behavior_type")
        if isinstance(raw, str):
            raw = raw.strip()
            if raw in EVENT_NAME_TYPES:
                return EVENT_NAME_TYPES[raw]
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _event_cursor(event: Dict[str, Any]) -> tuple[int, int]:
        try:
            event_time = int(float(event.get("update_time") or event.get("utime") or 0))
        except (TypeError, ValueError):
            event_time = 0
        try:
            event_id = int(event.get("id") or event.get("event_id") or 0)
        except (TypeError, ValueError):
            event_id = 0
        if event_time <= 0 or event_id <= 0:
            raise ValueError(f"115 生活事件缺少有效游标: {event}")
        return event_time, event_id

    @classmethod
    def _sorted_events(
        cls,
        events: Iterable[Dict[str, Any]],
        from_time: int,
        from_id: int,
    ) -> list[Dict[str, Any]]:
        selected: list[tuple[int, int, Dict[str, Any]]] = []
        seen: set[tuple[int, int]] = set()
        for event in events:
            if not isinstance(event, dict):
                continue
            event_time, event_id = cls._event_cursor(event)
            if event_time < from_time:
                continue
            if event_time == from_time and event_id <= from_id:
                continue
            cursor = (event_time, event_id)
            if cursor in seen:
                continue
            seen.add(cursor)
            selected.append((event_time, event_id, event))
        selected.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in selected]

    def _load_cursor(self) -> Dict[str, int]:
        getter = getattr(self._store, "get_life_cursor", None)
        state = getter() if callable(getter) else {}
        try:
            from_time = int(float((state or {}).get("from_time") or 0))
        except (TypeError, ValueError):
            from_time = 0
        try:
            from_id = int((state or {}).get("from_id") or 0)
        except (TypeError, ValueError):
            from_id = 0
        if from_time <= 0 and from_id <= 0:
            from_time = int(time())
            self._save_cursor(from_time, 0)
        return {"from_time": max(0, from_time), "from_id": max(0, from_id)}

    def _save_cursor(self, from_time: int, from_id: int) -> None:
        saver = getattr(self._store, "save_life_cursor", None)
        if callable(saver):
            saver(from_time, from_id)

    def _config_mappings(self) -> list[Dict[str, Any]]:
        config = self._store.get_config()
        return [
            mapping
            for mapping in config.get("strm_mappings") or []
            if isinstance(mapping, dict)
            and mapping.get("enabled", True)
            and str(mapping.get("source_path") or "").strip()
            and str(mapping.get("target_dir") or "").strip()
        ]

    @staticmethod
    def _mapping_id(mapping: Dict[str, Any]) -> str:
        return str(mapping.get("id") or mapping.get("source_cid") or "default")

    @staticmethod
    def _path_matches(root: str, path: str) -> bool:
        root = normalize_cloud_path(root)
        path = normalize_cloud_path(path)
        return path == root or path.startswith(f"{root.rstrip('/')}/")

    @staticmethod
    def _event_path(value: str) -> str:
        path = normalize_cloud_path(value)
        if ".." in PurePosixPath(path).parts:
            raise LifeEventRetryError(f"115 生活事件路径包含非法片段: {value}")
        return path

    def _matching_mappings(self, cloud_path: str) -> list[Dict[str, Any]]:
        return [
            mapping
            for mapping in self._config_mappings()
            if self._path_matches(str(mapping.get("source_path") or "/"), cloud_path)
        ]

    def _life_paths(self) -> Dict[str, Dict[str, Any]]:
        getter = getattr(self._store, "get_life_paths", None)
        state = getter() if callable(getter) else {}
        return dict(state) if isinstance(state, dict) else {}

    def _save_life_paths(self, paths: Dict[str, Dict[str, Any]]) -> None:
        saver = getattr(self._store, "save_life_paths", None)
        if callable(saver):
            saver(paths)

    def _remember_path(self, item_id: str, cloud_path: str, item_type: str = "file") -> None:
        if not item_id:
            return
        paths = self._life_paths()
        paths[str(item_id)] = {"path": self._event_path(cloud_path), "type": item_type}
        self._save_life_paths(paths)

    def _forget_paths(self, prefix: str) -> None:
        prefix = normalize_cloud_path(prefix)
        paths = self._life_paths()
        changed = False
        for item_id, value in list(paths.items()):
            if not isinstance(value, dict):
                continue
            path = str(value.get("path") or "")
            if self._path_matches(prefix, path):
                paths.pop(item_id, None)
                changed = True
        if changed:
            self._save_life_paths(paths)

    def _migrate_legacy_records(self) -> None:
        records = self._store.get_strm_records()
        changed = False
        for mapping in self._config_mappings():
            mapping_id = self._mapping_id(mapping)
            prefix = f"{mapping_id}:"
            for key, record in records.items():
                if not str(key).startswith(prefix) or not isinstance(record, dict):
                    continue
                if record.get("cloud_path"):
                    continue
                key_text = str(key)
                is_sidecar = key_text.startswith(f"{prefix}sidecar:")
                rel_offset = len(prefix) + (len("sidecar:") if is_sidecar else 0)
                rel_path = key_text[rel_offset:]
                try:
                    record["cloud_path"] = mapping_cloud_path(mapping, rel_path)
                except ValueError:
                    continue
                record.setdefault("kind", "sidecar" if is_sidecar else "strm")
                record.setdefault("mapping_id", mapping_id)
                changed = True
        if changed:
            self._store.save_strm_records(records)

    def _event_file_id(self, event: Dict[str, Any]) -> str:
        return str(
            event.get("file_id")
            or event.get("fid")
            or ""
        ).strip()

    def _event_parent_id(self, event: Dict[str, Any]) -> str:
        return str(event.get("parent_id") or event.get("pid") or "0").strip()

    @staticmethod
    def _event_name(event: Dict[str, Any]) -> str:
        return str(
            event.get("file_name")
            or event.get("name")
            or event.get("fn")
            or ""
        ).strip()

    def _resolve_event_item(self, event: Dict[str, Any]) -> Dict[str, Any]:
        client = self._client_provider()
        file_id = self._event_file_id(event)
        item: Optional[Dict[str, Any]] = None
        if file_id:
            item = client.get_item_by_id(file_id)
        if item:
            return item

        explicit_path = str(event.get("path") or event.get("file_path") or "").strip()
        if explicit_path:
            cloud_path = self._event_path(explicit_path)
        else:
            name = self._event_name(event)
            if not name:
                raise U115ApiError(f"115 生活事件缺少文件名: {event}")
            parent = client.get_item_by_id(self._event_parent_id(event))
            if not parent or parent.get("type") != "dir":
                raise U115ApiError(f"无法解析 115 生活事件父目录: {event}")
            cloud_path = self._event_path(f"{parent['path'].rstrip('/')}/{name}")
        category = str(event.get("file_category") or event.get("fc") or "1")
        return {
            "fileid": file_id,
            "parent_id": self._event_parent_id(event),
            "path": cloud_path,
            "type": "dir" if category == "0" else "file",
            "name": self._event_name(event) or PurePosixPath(cloud_path).name,
            "pickcode": event.get("pick_code") or event.get("pickcode") or event.get("pc") or "",
            "size": event.get("file_size") or event.get("size") or 0,
            "mtime": event.get("update_time") or 0,
        }

    def _process_event(self, event: Dict[str, Any]) -> None:
        event_type = self._event_type(event)
        if event_type not in SUPPORTED_EVENT_TYPES:
            return
        label = EVENT_TYPE_NAMES.get(event_type, str(event_type))
        logger.debug(f"【115生活监控】处理事件：{label}，id={event.get('id')}")
        if event_type in DELETE_EVENT_TYPES:
            self._handle_delete(event)
            return
        item = self._resolve_event_item(event)
        item_id = str(item.get("fileid") or self._event_file_id(event)).strip()
        cloud_path = self._event_path(str(item.get("path") or ""))
        if not cloud_path or cloud_path == "/":
            raise U115ApiError(f"115 生活事件路径无效: {event}")
        item_type = str(item.get("type") or "file")
        old_paths = (
            self._find_old_paths(item_id, event)
            if event_type in MOVE_EVENT_TYPES | RENAME_EVENT_TYPES
            else []
        )
        if event_type == 17:
            self._remember_path(item_id, cloud_path, item_type)
            return
        if item_type == "dir":
            self._sync_directory(item, cloud_path, old_paths)
        else:
            self._sync_file(item, cloud_path, old_paths if old_paths else [])
        if event_type in MOVE_EVENT_TYPES | RENAME_EVENT_TYPES and old_paths:
            for old_path in old_paths:
                if old_path != cloud_path:
                    self._remove_records_under(old_path, keep_ids={item_id})
                self._forget_paths(old_path)
        self._remember_path(item_id, cloud_path, item_type)

    def _find_old_paths(self, item_id: str, event: Dict[str, Any]) -> list[str]:
        paths: list[str] = []
        life_path = self._life_paths().get(item_id)
        if isinstance(life_path, dict) and life_path.get("path"):
            paths.append(self._event_path(str(life_path["path"])))
        for key in ("old_path", "previous_path", "from_path"):
            value = str(event.get(key) or "").strip()
            if value:
                paths.append(self._event_path(value))
        old_name = str(
            event.get("old_file_name")
            or event.get("old_name")
            or event.get("previous_name")
            or ""
        ).strip()
        if old_name:
            parent_id = self._event_parent_id(event)
            try:
                parent = self._client_provider().get_item_by_id(parent_id)
            except Exception as err:  # noqa: BLE001
                logger.warning(f"【115生活监控】旧路径父目录解析失败：{err}")
                parent = None
            if parent and parent.get("path"):
                paths.append(
                    self._event_path(f"{parent['path'].rstrip('/')}/{old_name}")
                )
        records = self._store.get_strm_records()
        for record in records.values():
            if not isinstance(record, dict) or str(record.get("file_id") or "") != item_id:
                continue
            value = str(record.get("cloud_path") or "").strip()
            if value:
                paths.append(self._event_path(value))
        return list(dict.fromkeys(paths))

    def _sync_directory(
        self,
        item: Dict[str, Any],
        cloud_path: str,
        old_paths: list[str],
    ) -> None:
        file_id = str(item.get("fileid") or "").strip()
        if not file_id:
            raise LifeEventRetryError(f"目录事件缺少 file_id，暂不消费事件：{cloud_path}")
        client = self._client_provider()
        records = self._store.get_strm_records()
        resolved_old_paths = list(old_paths)
        seen_ids: set[str] = set()
        for child in client.iter_files(file_id):
            name = str(child.get("name") or "").strip()
            rel_path = str(child.get("rel_path") or name).replace("\\", "/")
            if not name or not rel_path:
                continue
            child_path = self._event_path(f"{cloud_path.rstrip('/')}/{rel_path}")
            child_item = {**child, "fileid": child.get("fileid") or child.get("file_id")}
            child_id = str(child_item.get("fileid") or "").strip()
            if child_id:
                seen_ids.add(child_id)
                inferred_path = self._infer_directory_old_path(
                    child_id,
                    rel_path,
                    records,
                )
                if (
                    inferred_path
                    and inferred_path != cloud_path
                    and inferred_path not in resolved_old_paths
                ):
                    resolved_old_paths.append(inferred_path)
            self._sync_file(child_item, child_path, resolved_old_paths)
            if child_id:
                self._remember_path(child_id, child_path, "file")
        for old_path in resolved_old_paths:
            self._remove_records_under(old_path, keep_ids=seen_ids, exclude_prefix=cloud_path)

    def _infer_directory_old_path(
        self,
        child_id: str,
        rel_path: str,
        records: Dict[str, Dict[str, Any]],
    ) -> str:
        relative = PurePosixPath(rel_path)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            return ""
        candidates: list[str] = []
        stored = self._life_paths().get(child_id)
        if isinstance(stored, dict) and stored.get("path"):
            candidates.append(str(stored["path"]))
        for record in records.values():
            if not isinstance(record, dict) or str(record.get("file_id") or "") != child_id:
                continue
            cloud_path = str(record.get("cloud_path") or "").strip()
            if cloud_path:
                candidates.append(cloud_path)
        relative_parts = relative.parts
        for candidate in candidates:
            candidate_path = PurePosixPath(self._event_path(candidate))
            if len(candidate_path.parts) <= len(relative_parts):
                continue
            if candidate_path.parts[-len(relative_parts):] != relative_parts:
                continue
            return PurePosixPath(*candidate_path.parts[:-len(relative_parts)]).as_posix()
        return ""

    def _sync_file(
        self,
        item: Dict[str, Any],
        cloud_path: str,
        old_paths: list[str],
    ) -> None:
        records = self._store.get_strm_records()
        item_id = str(item.get("fileid") or item.get("file_id") or "").strip()
        suffix = PurePosixPath(str(item.get("name") or cloud_path)).suffix.lower()
        if suffix not in DEFAULT_MEDIA_EXTENSIONS:
            media_keys = self._record_keys_for_item(
                records,
                item_id,
                [cloud_path, *old_paths],
                kind="strm",
            )
            for key in media_keys:
                self._remove_record(key, records)
            self._sync_sidecar(item, cloud_path, old_paths, records, item_id, suffix)
            if media_keys:
                self._store.save_strm_records(records)
            return
        old_keys = self._record_keys_for_item(
            records,
            item_id,
            [cloud_path, *old_paths],
            kind="strm",
        )
        mappings = self._matching_mappings(cloud_path)
        if not mappings:
            for key in old_keys:
                self._remove_record(key, records)
            if old_keys:
                self._store.save_strm_records(records)
            return
        try:
            pickcode = normalize_pickcode(str(item.get("pickcode") or item.get("pick_code") or ""))
        except ValueError as err:
            raise U115ApiError(f"115 生活事件文件 Pickcode 无效: {cloud_path}") from err
        new_keys: set[str] = set()
        for mapping in mappings:
            new_key = self._upsert_file(
                mapping,
                item,
                cloud_path,
                pickcode,
                records,
                old_keys,
            )
            if new_key:
                new_keys.add(new_key)
        if old_keys:
            for key in old_keys - new_keys:
                self._remove_record(key, records)
        self._store.save_strm_records(records)

    def _sync_sidecar(
        self,
        item: Dict[str, Any],
        cloud_path: str,
        old_paths: list[str],
        records: Dict[str, Dict[str, Any]],
        item_id: str,
        suffix: str,
    ) -> None:
        config = self._store.get_config()
        extensions = parse_extensions(
            str(config.get("upload_sidecar_extensions") or ""),
            DEFAULT_SIDECAR_EXTENSIONS,
        )
        old_keys = self._record_keys_for_item(
            records,
            item_id,
            [cloud_path, *old_paths],
            kind="sidecar",
        )
        if not config.get("strm_download_sidecars") or suffix not in extensions:
            for key in old_keys:
                self._remove_record(key, records)
            if old_keys:
                self._store.save_strm_records(records)
            return
        try:
            pickcode = normalize_pickcode(str(item.get("pickcode") or item.get("pick_code") or ""))
        except ValueError as err:
            raise U115ApiError(f"115 生活事件附属文件 Pickcode 无效: {cloud_path}") from err
        mappings = self._matching_mappings(cloud_path)
        new_keys: set[str] = set()
        for mapping in mappings:
            mapping_id = self._mapping_id(mapping)
            source_path = normalize_cloud_path(str(mapping.get("source_path") or "/"))
            relative = PurePosixPath(cloud_path).relative_to(PurePosixPath(source_path))
            record_key = f"{mapping_id}:sidecar:{relative.as_posix()}"
            old_key = next(
                (
                    key
                    for key in old_keys
                    if str(records.get(key, {}).get("mapping_id") or key.split(":", 1)[0])
                    == mapping_id
                ),
                "",
            )
            output = Path(str(mapping["target_dir"])).expanduser().resolve().joinpath(
                *relative.parts
            )
            self._upsert_sidecar_record(
                old_key,
                record_key,
                output,
                mapping,
                item,
                cloud_path,
                pickcode,
                records,
            )
            new_keys.add(record_key)
        for key in old_keys - new_keys:
            self._remove_record(key, records)
        if old_keys or new_keys:
            self._store.save_strm_records(records)

    def _upsert_sidecar_record(
        self,
        old_key: str,
        new_key: str,
        output: Path,
        mapping: Dict[str, Any],
        item: Dict[str, Any],
        cloud_path: str,
        pickcode: str,
        records: Dict[str, Dict[str, Any]],
    ) -> None:
        fingerprint = f"{pickcode}:{self._item_size(item)}"
        previous = records.get(old_key) if old_key else None
        old_output_value = (
            str(previous.get("path") or "").strip()
            if isinstance(previous, dict)
            else ""
        )
        if (
            old_key
            and old_key != new_key
            and isinstance(previous, dict)
            and str(previous.get("fingerprint") or "") == fingerprint
            and old_output_value
            and Path(old_output_value).expanduser().is_file()
        ):
            self._relocate_sidecar_record(
                old_key,
                new_key,
                output,
                mapping,
                item,
                cloud_path,
                records,
            )
            return

        target_dir = Path(str(mapping["target_dir"])).expanduser().resolve()
        try:
            output = output.resolve()
            output.relative_to(target_dir)
            for key, record in records.items():
                if key in {old_key, new_key} or not isinstance(record, dict):
                    continue
                record_path = str(record.get("path") or "").strip()
                if record_path and self._same_path(record_path, output):
                    raise LifeEventRetryError(
                        f"附属文件输出路径已被其他记录占用，暂不消费事件：{output}"
                    )
            if (
                old_key == new_key
                and isinstance(previous, dict)
                and str(previous.get("fingerprint") or "") == fingerprint
                and output.is_file()
            ):
                records[new_key] = build_strm_record(
                    fingerprint=fingerprint,
                    output=output,
                    mapping=mapping,
                    item={**item, "pickcode": pickcode},
                    kind="sidecar",
                    cloud_path=cloud_path,
                )
                return
            output.parent.mkdir(parents=True, exist_ok=True)
            self._client_provider().download_file(pickcode, output, create_parent=False)
            records[new_key] = build_strm_record(
                fingerprint=fingerprint,
                output=output,
                mapping=mapping,
                item={**item, "pickcode": pickcode},
                kind="sidecar",
                cloud_path=cloud_path,
            )
            if old_key and old_key != new_key:
                self._remove_record(old_key, records)
            logger.info(f"【115生活监控】回传附属文件：{cloud_path} -> {output}")
        except (OSError, RuntimeError, ValueError) as err:
            if isinstance(err, LifeEventRetryError):
                raise
            raise LifeEventRetryError(
                f"回传附属文件失败，暂不消费事件：{cloud_path}，原因：{err}"
            ) from err

    def _relocate_sidecar_record(
        self,
        old_key: str,
        new_key: str,
        output: Path,
        mapping: Dict[str, Any],
        item: Dict[str, Any],
        cloud_path: str,
        records: Dict[str, Dict[str, Any]],
    ) -> None:
        record = records.get(old_key)
        if not isinstance(record, dict):
            return
        old_output_value = str(record.get("path") or "").strip()
        if not old_output_value:
            records.pop(old_key, None)
            return
        old_target = self._target_dir_for_record(old_key, record)
        new_target = Path(str(mapping["target_dir"])).expanduser().resolve()
        if old_target is None:
            raise LifeEventRetryError(
                f"无法确认附属文件所属目录，暂不消费事件：{old_output_value}"
            )
        try:
            old_output = Path(old_output_value).expanduser().resolve()
            old_output.relative_to(old_target)
            output = output.resolve()
            output.relative_to(new_target)
            if old_output != output:
                if output.exists():
                    raise LifeEventRetryError(f"附属文件目标已存在，暂不覆盖：{output}")
                output.parent.mkdir(parents=True, exist_ok=True)
                if old_output.exists():
                    old_output.replace(output)
            records.pop(old_key, None)
            records[new_key] = build_strm_record(
                fingerprint=str(record.get("fingerprint") or ""),
                output=output,
                mapping=mapping,
                item=item,
                kind="sidecar",
                cloud_path=cloud_path,
            )
        except (OSError, RuntimeError, ValueError) as err:
            if isinstance(err, LifeEventRetryError):
                raise
            raise LifeEventRetryError(
                f"迁移附属文件失败，暂不消费事件：{old_output_value}，原因：{err}"
            ) from err

    def _record_keys_for_item(
        self,
        records: Dict[str, Dict[str, Any]],
        item_id: str,
        old_paths: list[str],
        *,
        kind: str = "strm",
    ) -> set[str]:
        result: set[str] = set()
        for key, record in records.items():
            if not isinstance(record, dict):
                continue
            is_sidecar = ":sidecar:" in str(key)
            if (kind == "sidecar") != is_sidecar:
                continue
            if item_id and str(record.get("file_id") or "") == item_id:
                result.add(key)
                continue
            record_path = str(record.get("cloud_path") or "")
            if record_path and any(record_path == path for path in old_paths):
                result.add(key)
        return result

    def _upsert_file(
        self,
        mapping: Dict[str, Any],
        item: Dict[str, Any],
        cloud_path: str,
        pickcode: str,
        records: Dict[str, Dict[str, Any]],
        old_keys: set[str],
    ) -> str:
        mapping_id = self._mapping_id(mapping)
        source_path = normalize_cloud_path(str(mapping.get("source_path") or "/"))
        relative = PurePosixPath(cloud_path).relative_to(PurePosixPath(source_path))
        rel_text = relative.as_posix()
        record_key = f"{mapping_id}:{rel_text}"
        output = strm_output_path(Path(str(mapping["target_dir"])).expanduser().resolve().joinpath(*relative.parts))
        resolved_output = output.resolve()
        existing = []
        for key, record in records.items():
            if key in old_keys or key == record_key or not isinstance(record, dict):
                continue
            record_path = str(record.get("path") or "").strip()
            if not record_path:
                continue
            try:
                if Path(record_path).expanduser().resolve() == resolved_output:
                    existing.append((key, record))
            except (OSError, RuntimeError):
                logger.warning(f"【115生活监控】记录路径无法解析，保留旧记录：{record_path}")
                return ""
        candidate_mtime = self._item_mtime(item)
        for key, record in existing:
            if str(record.get("mapping_id") or key.split(":", 1)[0]) != mapping_id:
                logger.error(f"【115生活监控】输出路径已被其他映射占用，跳过：{output}")
                return ""
            if int(record.get("mtime") or 0) >= candidate_mtime:
                logger.debug(f"【115生活监控】输出冲突按 115 更新时间保留：{output}")
                return ""
        for key, _record in existing:
            records.pop(key, None)

        size = self._item_size(item)
        moviepilot_url = self._moviepilot_url_provider().strip().rstrip("/")
        fingerprint = f"v{STRM_URL_FORMAT_VERSION}:{pickcode}:{size}:{moviepilot_url}"
        content = build_strm_content(
            moviepilot_url,
            pickcode,
            self._store.get_redirect_secret(),
            str(item.get("name") or PurePosixPath(cloud_path).name),
        )
        target_dir = Path(str(mapping["target_dir"])).expanduser().resolve()
        write_strm_file(output, content, target_dir)
        records[record_key] = build_strm_record(
            fingerprint=fingerprint,
            output=output,
            mapping=mapping,
            item={**item, "pickcode": pickcode},
            cloud_path=cloud_path,
        )
        logger.info(f"【115生活监控】生成 STRM：{cloud_path} -> {output}")
        return record_key

    @staticmethod
    def _item_size(item: Dict[str, Any]) -> int:
        try:
            return max(0, int(float(item.get("size") or item.get("file_size") or 0)))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _item_mtime(item: Dict[str, Any]) -> int:
        try:
            return int(float(item.get("mtime") or item.get("update_time") or 0))
        except (TypeError, ValueError):
            return 0

    def _handle_delete(self, event: Dict[str, Any]) -> None:
        item_id = self._event_file_id(event)
        paths: list[str] = []
        stored = self._life_paths().get(item_id)
        if isinstance(stored, dict) and stored.get("path"):
            paths.append(self._event_path(str(stored["path"])))
        for key in ("path", "file_path", "old_path"):
            value = str(event.get(key) or "").strip()
            if value:
                paths.append(self._event_path(value))
        parent_id = self._event_parent_id(event)
        name = self._event_name(event)
        if name and parent_id:
            try:
                parent = self._client_provider().get_item_by_id(parent_id)
            except Exception as err:  # noqa: BLE001
                logger.warning(f"【115生活监控】删除事件父目录解析失败，保留本地文件：{err}")
                parent = None
            if parent and parent.get("path"):
                paths.append(self._event_path(f"{parent['path'].rstrip('/')}/{name}"))
        paths = list(dict.fromkeys(path for path in paths if path != "/"))
        records = self._store.get_strm_records()
        keys: set[str] = set()
        for key, record in records.items():
            if not isinstance(record, dict):
                continue
            if item_id and str(record.get("file_id") or "") == item_id:
                keys.add(key)
                continue
            record_path = str(record.get("cloud_path") or "")
            if record_path and any(self._path_matches(path, record_path) for path in paths):
                keys.add(key)
        if not keys:
            logger.warning(f"【115生活监控】无法定位删除事件对应 STRM，保留本地文件：{event}")
            return
        for key in keys:
            self._remove_record(key, records)
        self._store.save_strm_records(records)
        for path in paths:
            self._forget_paths(path)

    def _remove_records_under(
        self,
        prefix: str,
        *,
        keep_ids: set[str],
        exclude_prefix: str = "",
    ) -> None:
        records = self._store.get_strm_records()
        changed = False
        for key, record in list(records.items()):
            if not isinstance(record, dict):
                continue
            cloud_path = str(record.get("cloud_path") or "")
            if not cloud_path or not self._path_matches(prefix, cloud_path):
                continue
            if exclude_prefix and self._path_matches(exclude_prefix, cloud_path):
                continue
            if str(record.get("file_id") or "") in keep_ids:
                continue
            changed = self._remove_record(key, records) or changed
        if changed:
            self._store.save_strm_records(records)

    def _remove_record(self, key: str, records: Dict[str, Dict[str, Any]]) -> bool:
        record = records.get(key)
        if not isinstance(record, dict):
            return False
        output_value = str(record.get("path") or "").strip()
        if not output_value:
            records.pop(key, None)
            return True
        target_dir = self._target_dir_for_record(key, record)
        if target_dir is None:
            raise LifeEventRetryError(
                f"无法确认 STRM 所属目录，暂不消费事件：{output_value}"
            )
        try:
            output = Path(output_value).expanduser().resolve()
            output.relative_to(target_dir)
            if any(
                isinstance(other, dict)
                and str(other.get("path") or "")
                and self._same_path(str(other.get("path")), output)
                for other_key, other in records.items()
                if other_key != key
            ):
                records.pop(key, None)
                return True
            try:
                output.unlink(missing_ok=True)
            except OSError as err:
                raise LifeEventRetryError(
                    f"删除 STRM 失败，暂不消费事件：{output_value}，原因：{err}"
                ) from err
            records.pop(key, None)
            logger.info(f"【115生活监控】删除 STRM：{output}")
            return True
        except (OSError, RuntimeError, ValueError) as err:
            if isinstance(err, LifeEventRetryError):
                raise
            raise LifeEventRetryError(
                f"删除 STRM 路径无效，暂不消费事件：{output_value}，原因：{err}"
            ) from err

    def _target_dir_for_record(
        self,
        key: str,
        record: Dict[str, Any],
    ) -> Optional[Path]:
        mapping_id = str(record.get("mapping_id") or "")
        if not mapping_id:
            mapping_id = str(key).split(":", 1)[0]
        config = self._store.get_config()
        for mapping in config.get("strm_mappings") or []:
            if not isinstance(mapping, dict) or not str(mapping.get("target_dir") or "").strip():
                continue
            if self._mapping_id(mapping) == mapping_id:
                return Path(str(mapping["target_dir"])).expanduser().resolve()
        return None

    @staticmethod
    def _same_path(value: str, output: Path) -> bool:
        try:
            return Path(value).expanduser().resolve() == output
        except (OSError, RuntimeError):
            return False


# 保留一个更明确的别名，便于宿主或测试按语义导入。
LifeEventMonitor = LifeMonitor
