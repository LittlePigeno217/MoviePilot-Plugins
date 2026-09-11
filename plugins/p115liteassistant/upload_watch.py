"""本地上传源目录的文件级实时监听、稳定性确认与有界去重队列。"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from threading import Event, Lock, Thread, current_thread
from time import monotonic, time
from typing import Any, Callable, Dict, Iterable, Optional, TypeAlias

from app.log import logger

from .file_types import DEFAULT_MEDIA_EXTENSIONS, DEFAULT_SIDECAR_EXTENSIONS, parse_extensions
from .log_utils import safe_error_text

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except Exception:  # noqa: BLE001  # pragma: no cover
    FileSystemEventHandler = object  # type: ignore[assignment,misc]
    Observer = None  # type: ignore[assignment]

LOG_TAG = "【上传监听】"
UPLOAD_STABLE_INTERVAL = 2.0
UPLOAD_STABLE_CHECKS = 3
UPLOAD_DEDUP_MAX = 4096
UPLOAD_STABILITY_MAX = 4096
UPLOAD_DEDUP_TTL = 600.0
UPLOAD_BATCH_SIZE = 1
UPLOAD_BATCH_TIME_BUDGET = 120

FileSignature: TypeAlias = tuple[int, int, int]
UploadKey: TypeAlias = tuple[str, str]
MappingRevision: TypeAlias = tuple[Any, ...]


def mapping_revision(
    mapping: Dict[str, Any],
    config: Dict[str, Any],
    *,
    canonical_source: str | None = None,
) -> MappingRevision:
    """固化会影响候选资格、路由与上传副作用的映射版本。"""
    source = canonical_source
    if source is None:
        source = str(Path(str(mapping.get("source") or "")).expanduser().resolve())
    target_text = str(mapping.get("target") or "").strip().replace("\\", "/")
    target = PurePosixPath(target_text).as_posix() if target_text else ""
    strm_text = str(mapping.get("strm_target") or "").strip()
    strm_target = str(Path(strm_text).expanduser().resolve()) if strm_text else ""
    media_extensions = tuple(sorted(parse_extensions(
        str(config.get("upload_media_extensions") or ""), DEFAULT_MEDIA_EXTENSIONS
    )))
    sidecar_extensions = tuple(sorted(parse_extensions(
        str(config.get("upload_sidecar_extensions") or ""), DEFAULT_SIDECAR_EXTENSIONS
    )))
    return (
        str(source), target, strm_target, bool(mapping.get("enabled", True)),
        media_extensions, sidecar_extensions,
        bool(config.get("upload_include_sidecars", True)),
        bool(config.get("upload_delete_source", False)),
        bool(config.get("upload_generate_strm", False)),
    )


@dataclass(frozen=True)
class UploadCandidate:
    file_path: str
    source_root: str
    mapping_id: str
    signature: FileSignature
    source: str = "watch"
    queued_at: float = 0.0
    mapping_revision: MappingRevision = ()

    @property
    def key(self) -> UploadKey:
        return self.source_root, self.file_path


@dataclass
class StabilityState:
    candidate: UploadCandidate
    last_signature: FileSignature
    stable_count: int
    first_seen: float


def file_signature(path: Path) -> FileSignature | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


class PendingUploadQueue:
    """FIFO 覆盖去重队列；queued/inflight/processed 三层均有界。"""

    def __init__(self, maxsize: int = UPLOAD_DEDUP_MAX, ttl: float = UPLOAD_DEDUP_TTL):
        self.maxsize = max(1, int(maxsize))
        self.ttl = max(0.0, float(ttl))
        self._queued: "OrderedDict[UploadKey, UploadCandidate]" = OrderedDict()
        self._inflight: dict[UploadKey, UploadCandidate] = {}
        self._started: set[UploadKey] = set()
        self._processed: "OrderedDict[UploadKey, tuple[FileSignature, float]]" = OrderedDict()
        self._lock = Lock()

    def _prune_locked(self, now: float) -> None:
        expired = [key for key, (_signature, stamp) in self._processed.items() if now - stamp >= self.ttl]
        for key in expired:
            self._processed.pop(key, None)
        while len(self._processed) > self.maxsize:
            self._processed.popitem(last=False)

    def offer(self, candidate: UploadCandidate) -> str:
        """提交候选并明确区分 accepted/duplicate/full，避免把容量拒绝当去重成功。"""
        now = monotonic()
        with self._lock:
            self._prune_locked(now)
            processed = self._processed.get(candidate.key)
            if processed and processed[0] == candidate.signature:
                self._processed.move_to_end(candidate.key)
                return "duplicate"
            inflight = self._inflight.get(candidate.key)
            if inflight and inflight.signature == candidate.signature:
                return "duplicate"
            if candidate.key not in self._queued and len(self._queued) >= self.maxsize:
                logger.warning(f"{LOG_TAG}待上传队列已达 {self.maxsize}，拒绝新候选：{candidate.file_path}")
                return "full"
            previous = self._queued.get(candidate.key)
            if previous is not None:
                if previous.signature == candidate.signature:
                    return "duplicate"
                candidate = replace(candidate, queued_at=min(previous.queued_at, candidate.queued_at))
            self._queued[candidate.key] = candidate
            return "accepted"

    def enqueue(self, candidate: UploadCandidate) -> bool:
        """兼容旧 bool 接口；调用方需要判断满队列时应使用 :meth:`offer`。"""
        return self.offer(candidate) == "accepted"

    def take(self, limit: int) -> list[UploadCandidate]:
        with self._lock:
            batch: list[UploadCandidate] = []
            for _ in range(min(max(0, int(limit)), len(self._queued))):
                key, candidate = self._queued.popitem(last=False)
                self._inflight[key] = candidate
                batch.append(candidate)
            return batch

    def mark_started(self, candidate: UploadCandidate) -> bool:
        with self._lock:
            current = self._inflight.get(candidate.key)
            if current != candidate:
                return False
            self._started.add(candidate.key)
            return True

    def finish(self, candidate: UploadCandidate, *, processed: bool) -> None:
        with self._lock:
            self._inflight.pop(candidate.key, None)
            self._started.discard(candidate.key)
            if processed:
                self._processed[candidate.key] = (candidate.signature, monotonic())
                self._processed.move_to_end(candidate.key)
                self._prune_locked(monotonic())

    def restore(self, candidates: Iterable[UploadCandidate]) -> None:
        with self._lock:
            restored = list(candidates)
            for candidate in restored:
                self._inflight.pop(candidate.key, None)
                self._started.discard(candidate.key)
            # 原批次应回到 FIFO 头部；倒序插入保持批内顺序。
            for candidate in reversed(restored):
                current = self._queued.pop(candidate.key, None)
                if current is not None and current.signature != candidate.signature:
                    candidate = current
                self._queued[candidate.key] = candidate
                self._queued.move_to_end(candidate.key, last=False)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            values = list(self._queued.values()) + list(self._inflight.values())
        by_key = {candidate.key: candidate for candidate in values}
        candidates = list(by_key.values())
        return {
            "pending": bool(candidates),
            "count": len(candidates),
            "source": ",".join(sorted({item.source for item in candidates if item.source})),
            "queued_at": min((item.queued_at for item in candidates), default=0.0),
        }

    def clear_invalid(self, valid_revisions: set[tuple[str, str, MappingRevision]]) -> int:
        """清除 queued 及尚未开始执行的 inflight 旧版本候选。"""
        with self._lock:
            def invalid(item: UploadCandidate) -> bool:
                return (item.mapping_id, item.source_root, item.mapping_revision) not in valid_revisions

            stale_queued = [key for key, item in self._queued.items() if invalid(item)]
            stale_inflight = [
                key for key, item in self._inflight.items()
                if key not in self._started and invalid(item)
            ]
            for key in stale_queued:
                self._queued.pop(key, None)
            for key in stale_inflight:
                self._inflight.pop(key, None)
            return len(stale_queued) + len(stale_inflight)

    def __bool__(self) -> bool:
        return bool(self.snapshot()["pending"])


class StabilityTracker:
    """只做本地 stat；连续签名稳定后交给 API 队列。"""

    def __init__(
        self,
        config_provider: Callable[[], Dict[str, Any]],
        ready_callback: Callable[[UploadCandidate], Any],
        interval: float = UPLOAD_STABLE_INTERVAL,
        checks: int = UPLOAD_STABLE_CHECKS,
        maxsize: int = UPLOAD_STABILITY_MAX,
        full_rescan_callback: Callable[[str], Any] | None = None,
    ):
        self._config_provider = config_provider
        self._ready_callback = ready_callback
        self._interval = float(interval)
        self._checks = max(1, int(checks))
        self._maxsize = max(1, int(maxsize))
        self._pending: dict[UploadKey, StabilityState] = {}
        self._full_rescan = False
        self._full_rescan_callback = full_rescan_callback
        self._mappings: list[tuple[Path, str, MappingRevision]] = []
        self._lock = Lock()
        self._thread: Thread | None = None
        self._stop_event = Event()
        self._accepting = False

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def configure(self) -> list[Path]:
        mappings: list[tuple[Path, str]] = []
        for mapping in self._config_provider().get("upload_mappings") or []:
            if not isinstance(mapping, dict) or not mapping.get("enabled", True):
                continue
            source = str(mapping.get("source") or "").strip()
            if not source:
                continue
            try:
                root = Path(source).expanduser().resolve(strict=True)
            except (OSError, RuntimeError, ValueError):
                logger.warning(f"{LOG_TAG}源目录无法解析，跳过：{source}")
                continue
            if not root.is_dir():
                logger.warning(f"{LOG_TAG}源目录不存在，暂不监听：{root}")
                continue
            mapping_id = str(mapping.get("id") or root)
            revision = mapping_revision(mapping, self._config_provider(), canonical_source=str(root))
            mappings.append((root, mapping_id, revision))
        for index, (root, _mapping_id, _revision) in enumerate(mappings):
            for other, _other_id, _other_revision in mappings[index + 1:]:
                if root == other or root in other.parents or other in root.parents:
                    logger.error(f"{LOG_TAG}上传源目录重叠，实时监听 fail-closed：{root} <-> {other}")
                    mappings = []
                    break
            if not mappings:
                break
        with self._lock:
            self._mappings = mappings
            valid = {
                (str(root), mapping_id, revision)
                for root, mapping_id, revision in mappings
            }
            for key, state in list(self._pending.items()):
                if (
                    state.candidate.source_root, state.candidate.mapping_id,
                    state.candidate.mapping_revision,
                ) not in valid:
                    self._pending.pop(key, None)
            if not mappings:
                self._full_rescan = False
        return [root for root, _mapping_id, _revision in mappings]

    def _extensions(self) -> set[str]:
        config = self._config_provider()
        extensions = parse_extensions(
            str(config.get("upload_media_extensions") or ""), DEFAULT_MEDIA_EXTENSIONS
        )
        if config.get("upload_include_sidecars", True):
            extensions |= parse_extensions(
                str(config.get("upload_sidecar_extensions") or ""), DEFAULT_SIDECAR_EXTENSIONS
            )
        return extensions

    def _candidate(self, path: str, source: str) -> UploadCandidate | None:
        text = str(path or "").strip()
        if not text or Path(text).suffix.lower() not in self._extensions():
            return None
        raw = Path(text).expanduser()
        try:
            if raw.is_symlink():
                return None
            resolved = raw.resolve(strict=True)
            if not resolved.is_file():
                return None
        except (OSError, RuntimeError, ValueError):
            return None
        with self._lock:
            matches = [(root, mapping_id, revision) for root, mapping_id, revision in self._mappings if _is_relative_to(resolved, root)]
        if len(matches) != 1:
            return None
        root, mapping_id, revision = matches[0]
        signature = file_signature(resolved)
        if signature is None:
            return None
        return UploadCandidate(
            file_path=str(resolved), source_root=str(root), mapping_id=mapping_id,
            signature=signature, source=str(source or "watch"), queued_at=time(),
            mapping_revision=revision,
        )

    def submit_path(self, path: str, source: str = "watch") -> bool:
        if not self._accepting:
            return False
        candidate = self._candidate(path, source)
        if candidate is None:
            return False
        with self._lock:
            if self._full_rescan:
                return True
            previous = self._pending.get(candidate.key)
            if previous is None and len(self._pending) >= self._maxsize:
                # 原子压缩为全量标记：已有和新来的事件都由一次全映射增量扫描回收。
                self._pending.clear()
                self._full_rescan = True
                logger.warning(
                    f"{LOG_TAG}稳定性候选达到 {self._maxsize}，已压为全量重扫标记"
                )
                return True
            first_seen = previous.first_seen if previous else monotonic()
            if previous and previous.last_signature == candidate.signature:
                previous.candidate = replace(candidate, queued_at=previous.candidate.queued_at)
            else:
                self._pending[candidate.key] = StabilityState(candidate, candidate.signature, 0, first_seen)
        return True

    def start(self) -> None:
        self.configure()
        with self._lock:
            self._accepting = True
            if self.is_running:
                return
            self._stop_event = Event()
            self._thread = Thread(target=self._run, name="p115liteassistant-upload-stability", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        with self._lock:
            self._accepting = False
            thread = self._thread
            stop_event = self._stop_event
        stop_event.set()
        if thread and thread.is_alive() and thread is not current_thread():
            thread.join(timeout=max(0.0, float(timeout)))
        with self._lock:
            if self._thread is thread and not (thread and thread.is_alive()):
                self._thread = None

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval):
            try:
                self.tick()
            except Exception as err:  # noqa: BLE001
                logger.error(f"{LOG_TAG}稳定性跟踪异常：{safe_error_text(err)}")

    @staticmethod
    def _callback_accepted(result: Any) -> bool:
        if isinstance(result, dict):
            if not result.get("success"):
                return False
            data = result.get("data")
            return not isinstance(data, dict) or bool(data.get("accepted", True))
        return result is not False

    def tick(self) -> int:
        # full-marker 优先；回调拒绝时标记保留，下轮继续尝试，绝不静默清空。
        with self._lock:
            full_rescan = self._full_rescan
        if full_rescan:
            callback = self._full_rescan_callback
            if callback is None:
                return 0
            try:
                accepted = self._callback_accepted(callback("stability-full"))
            except Exception as err:  # noqa: BLE001
                logger.error(f"{LOG_TAG}提交全量重扫失败：{safe_error_text(err)}")
                accepted = False
            if accepted:
                with self._lock:
                    self._full_rescan = False
                return 1
            return 0

        with self._lock:
            snapshot = [(key, state.candidate.file_path) for key, state in self._pending.items()]
        signatures = {key: file_signature(Path(path)) for key, path in snapshot}  # 锁外 stat
        ready: list[tuple[UploadKey, UploadCandidate]] = []
        with self._lock:
            for key, signature in signatures.items():
                state = self._pending.get(key)
                if state is None:
                    continue
                if signature is None:
                    self._pending.pop(key, None)
                elif signature == state.last_signature:
                    state.stable_count += 1
                    if state.stable_count >= self._checks:
                        ready.append((key, replace(state.candidate, signature=signature)))
                else:
                    state.last_signature = signature
                    state.stable_count = 0
                    state.candidate = replace(state.candidate, signature=signature)
        delivered = 0
        for key, candidate in ready:
            current = self._candidate(candidate.file_path, candidate.source)
            if (
                current is None or current.signature != candidate.signature
                or current.mapping_id != candidate.mapping_id
                or current.mapping_revision != candidate.mapping_revision
            ):
                with self._lock:
                    state = self._pending.get(key)
                    if state and state.candidate.mapping_revision == candidate.mapping_revision:
                        self._pending.pop(key, None)
                continue
            current = replace(current, queued_at=candidate.queued_at)
            try:
                accepted = self._callback_accepted(self._ready_callback(current))
            except Exception as err:  # noqa: BLE001
                logger.error(f"{LOG_TAG}提交稳定文件失败：{safe_error_text(err)}")
                accepted = False
            if not accepted:
                with self._lock:
                    self._pending.clear()
                    self._full_rescan = True
                logger.warning(f"{LOG_TAG}稳定候选未被消费端接受，已转为全量重扫")
                break
            with self._lock:
                state = self._pending.get(key)
                if state and state.candidate.signature == candidate.signature:
                    self._pending.pop(key, None)
            delivered += 1
        return delivered


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class UploadWatcher:
    """watchdog 只做目录事件忽略、后缀预筛和 tracker submit。"""

    TICK_SECONDS = 5.0

    def __init__(
        self,
        config_provider: Callable[[], Dict[str, Any]],
        tracker: StabilityTracker,
        observer_factory: Optional[Callable[[], Any]] = None,
    ):
        self._config_provider = config_provider
        self._tracker = tracker
        self._observer_factory = observer_factory or (Observer if Observer else None)
        self._observer: Any = None
        self._thread: Thread | None = None
        self._thread_lock = Lock()
        self._stop_event = Event()
        self._watched: list[Path] = []

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def watch_dirs(self) -> list[Path]:
        return self._tracker.configure()

    def start(self) -> None:
        with self._thread_lock:
            if self.is_running:
                return
            if self._observer_factory is None:
                logger.warning(f"{LOG_TAG}未安装 watchdog，实时监听不可用；可靠整理路径仍可逐文件提交")
                return
            dirs = self.watch_dirs()
            if not dirs:
                logger.warning(f"{LOG_TAG}没有可监听的本地源目录，实时监听未启动")
                return
            observer = self._observer_factory()
            handler = _UploadEventHandler(self)
            scheduled: list[Path] = []
            for directory in dirs:
                try:
                    observer.schedule(handler, str(directory), recursive=True)
                    scheduled.append(directory)
                except Exception as err:  # noqa: BLE001
                    logger.error(f"{LOG_TAG}登记目录失败：{directory}，原因：{safe_error_text(err)}")
            if not scheduled:
                return
            observer.start()
            self._observer = observer
            self._watched = scheduled
            self._stop_event = Event()
            self._thread = Thread(target=self._run, name="p115liteassistant-upload-watch", daemon=True)
            self._thread.start()
        logger.info(f"{LOG_TAG}已开始监听 {len(scheduled)} 个本地源目录，文件稳定后逐个上传")

    def stop(self, timeout: float = 5.0) -> None:
        with self._thread_lock:
            observer, thread, stop_event = self._observer, self._thread, self._stop_event
            self._observer = None
            self._watched = []
        stop_event.set()
        if observer is not None:
            try:
                observer.stop()
                observer.join(timeout=max(0.0, float(timeout)))
            except Exception as err:  # noqa: BLE001
                logger.warning(f"{LOG_TAG}停止监听器异常：{safe_error_text(err)}")
        if thread and thread.is_alive() and thread is not current_thread():
            thread.join(timeout=max(0.0, float(timeout)))
        with self._thread_lock:
            if self._thread is thread and not (thread and thread.is_alive()):
                self._thread = None

    def report_change(self, path: str, is_directory: bool = False, source: str = "watch") -> bool:
        if is_directory:
            return False
        text = str(path or "").strip()
        if not text or Path(text).suffix.lower() not in self._tracker._extensions():
            return False
        submitted = self._tracker.submit_path(text, source=source)
        if submitted:
            logger.debug(f"{LOG_TAG}捕获媒体/侧车变化事件：{text}")
        return submitted

    def _watched_dirs_alive(self) -> bool:
        for directory in self._watched:
            try:
                if directory.is_dir():
                    continue
            except OSError:
                pass
            logger.error(f"{LOG_TAG}监听目录已消失，停止实时监听：{directory}")
            return False
        return True

    def _run(self) -> None:
        while not self._stop_event.wait(self.TICK_SECONDS):
            if not self._watched_dirs_alive():
                Thread(target=self.stop, name="p115liteassistant-upload-watch-stop", daemon=True).start()
                return


class _UploadEventHandler(FileSystemEventHandler):
    def __init__(self, watcher: UploadWatcher):
        super().__init__()
        self._watcher = watcher

    def on_created(self, event: Any) -> None:
        self._watcher.report_change(getattr(event, "src_path", ""), bool(getattr(event, "is_directory", False)))

    def on_moved(self, event: Any) -> None:
        self._watcher.report_change(getattr(event, "dest_path", ""), bool(getattr(event, "is_directory", False)))

    def on_modified(self, event: Any) -> None:
        self._watcher.report_change(getattr(event, "src_path", ""), bool(getattr(event, "is_directory", False)))
