"""本地上传源目录的实时监听：媒体/侧车文件出现 -> 防抖 -> 触发增量上传。

与 :class:`StrmDeleteWatcher` 同款骨架：watchdog 监听目录事件，事件安静够久后
回调编排层。它只负责「源目录有新东西了」，传不传、传哪些由
:meth:`~app.plugins.p115liteassistant.api.Api.trigger_upload` 决定 —— 那边会再跑
一次增量上传，用上传增量记录（size + mtime 指纹）挑出真正的新变化。

它不是上传的兜底：`upload_after_transfer_complete`（媒体整理事件）和定时/手动
触发仍在，实时监听只是加速 —— 网络挂载（NFS/SMB/CIFS）上的 inotify 收不到其它
主机直接扔进源目录的事件，那些靠定时增量扫描补上。
"""

from __future__ import annotations

from pathlib import Path
from threading import Event, Lock, Thread, current_thread
from time import monotonic
from typing import Any, Callable, Dict, Optional

from app.log import logger

from .file_types import (
    DEFAULT_MEDIA_EXTENSIONS,
    DEFAULT_SIDECAR_EXTENSIONS,
    parse_extensions,
)
from .log_utils import safe_error_text

try:  # watchdog 由 requirements.txt 声明；缺失时只是不启动监听，不影响其它功能
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except Exception:  # noqa: BLE001  # pragma: no cover - 取决于运行环境
    FileSystemEventHandler = object  # type: ignore[assignment,misc]
    Observer = None  # type: ignore[assignment]

LOG_TAG = "【上传监听】"


class UploadWatcher:
    """监听各上传映射的本地源目录，媒体/侧车文件出现且稳定后触发增量上传。"""

    #: 事件安静多久才认为写入已经定型（与 STRM 监听一致，大文件批量拷贝时避免中途触发）
    DEBOUNCE_SECONDS = 30.0
    #: 队列巡检间隔
    TICK_SECONDS = 5.0

    def __init__(
        self,
        config_provider: Callable[[], Dict[str, Any]],
        upload_trigger: Callable[[], Any],
        observer_factory: Optional[Callable[[], Any]] = None,
    ):
        self._config_provider = config_provider
        self._upload_trigger = upload_trigger
        self._observer_factory = observer_factory or (Observer if Observer else None)
        self._observer: Any = None
        self._thread: Optional[Thread] = None
        self._thread_lock = Lock()
        self._stop_event = Event()
        self._pending_lock = Lock()
        #: 事件触碰时间（单调时钟）。有任意一条未定型就整批等待，等最后一次事件安静下来。
        self._dirty_since: Optional[float] = None
        #: 本轮实际登记成功的目录，用于掉盘自检
        self._watched: list[Path] = []

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive())

    # ---- 配置 ----

    def _media_extensions(self, config: Dict[str, Any]) -> set[str]:
        media = parse_extensions(
            str(config.get("upload_media_extensions") or ""), DEFAULT_MEDIA_EXTENSIONS
        )
        sidecar = parse_extensions(
            str(config.get("upload_sidecar_extensions") or ""), DEFAULT_SIDECAR_EXTENSIONS
        )
        return media | sidecar

    def watch_dirs(self) -> list[Path]:
        """返回需要监听的本地源目录（已启用上传映射、目录当前存在）。"""
        config = self._config_provider()
        dirs: list[Path] = []
        seen: set[Path] = set()
        for mapping in config.get("upload_mappings") or []:
            if not isinstance(mapping, dict) or not mapping.get("enabled", True):
                continue
            source = str(mapping.get("source") or "").strip()
            if not source:
                continue
            try:
                resolved = Path(source).expanduser().resolve()
            except (OSError, RuntimeError, ValueError):
                logger.warning(f"{LOG_TAG}源目录无法解析，跳过：{source}")
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            if not resolved.is_dir():
                # 媒体库没挂上时不要监听：inotify 会盯着挂载点下的空目录，挂载完成后
                # 也不会自动生效，不如等下一次配置保存或重启重新登记。
                logger.warning(f"{LOG_TAG}源目录不存在，暂不监听：{resolved}")
                continue
            dirs.append(resolved)
        return dirs

    # ---- 生命周期 ----

    def start(self) -> None:
        """启动监听。watchdog 不可用或没有可监听目录时安静退出。"""
        with self._thread_lock:
            if self.is_running:
                return
            if self._observer_factory is None:
                logger.warning(
                    f"{LOG_TAG}未安装 watchdog，实时监听不可用；仍按定时/手动增量扫描兜底"
                )
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
                except Exception as err:  # noqa: BLE001
                    logger.error(
                        f"{LOG_TAG}登记目录失败：{directory}，原因：{safe_error_text(err)}"
                    )
                    continue
                scheduled.append(directory)
            if not scheduled:
                logger.error(f"{LOG_TAG}所有目录都登记失败，实时监听未启动")
                return
            try:
                observer.start()
            except Exception as err:  # noqa: BLE001
                logger.error(f"{LOG_TAG}启动失败：{safe_error_text(err)}")
                return
            self._observer = observer
            self._watched = scheduled
            self._stop_event = Event()
            self._dirty_since = None
            self._thread = Thread(
                target=self._run,
                name="p115liteassistant-upload-watch",
                daemon=True,
            )
            self._thread.start()
        logger.info(
            f"{LOG_TAG}已开始监听 {len(scheduled)} 个本地源目录，"
            f"媒体/侧车事件安静 {self.DEBOUNCE_SECONDS:g} 秒后触发增量上传"
        )

    def stop(self, timeout: float = 5.0) -> None:
        """停止监听，丢弃未处理的事件。"""
        with self._thread_lock:
            observer = self._observer
            thread = self._thread
            stop_event = self._stop_event
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
        with self._pending_lock:
            self._dirty_since = None
        if thread:
            logger.info(f"{LOG_TAG}已停止")

    # ---- 事件入口（watchdog 回调与单测都走这里）----

    def report_change(self, path: str, is_directory: bool = False) -> None:
        """登记一条「源目录有媒体/侧车文件变化」的时间戳。

        目录事件忽略：递归监听下子文件事件会各自到达；批量大目录时顶层目录事件
        只会把一大片子目录整个变成脏（触发一次全量增量上传也没错，但没必要）。
        """
        text = str(path or "").strip()
        if not text:
            return
        if is_directory:
            return
        if Path(text).suffix.lower() not in self._media_extensions(self._config_provider()):
            return
        with self._pending_lock:
            self._dirty_since = monotonic()
        logger.debug(f"{LOG_TAG}捕获媒体/侧车变化事件：{text}")

    # ---- 队列排空 ----

    def _watched_dirs_alive(self) -> bool:
        """已登记的目录是不是都还在。掉盘后 inotify 会盯着失效的 inode 静默失聪。"""
        for directory in self._watched:
            try:
                if directory.is_dir():
                    continue
            except OSError:
                pass
            logger.error(
                f"{LOG_TAG}监听目录已消失，判定存储掉盘，停止实时监听：{directory}；"
                "挂载恢复后保存一次配置或重启 MoviePilot 即可重新登记"
            )
            return False
        return True

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(self.TICK_SECONDS)
            if self._stop_event.is_set():
                return
            if not self._watched_dirs_alive():
                Thread(
                    target=self.stop,
                    name="p115liteassistant-upload-watch-stop",
                    daemon=True,
                ).start()
                return
            try:
                self.drain_once()
            except Exception as err:  # noqa: BLE001
                logger.error(f"{LOG_TAG}处理上传事件失败：{safe_error_text(err)}")

    def drain_once(self) -> bool:
        """事件安静够久就触发一次增量上传。返回是否触发了。"""
        with self._pending_lock:
            stamp = self._dirty_since
            if stamp is None or monotonic() - stamp < self.DEBOUNCE_SECONDS:
                return False
            self._dirty_since = None
        logger.info(f"{LOG_TAG}源目录变化已安静 {self.DEBOUNCE_SECONDS:g} 秒，触发增量上传")
        try:
            self._upload_trigger()
        except Exception as err:  # noqa: BLE001
            logger.error(f"{LOG_TAG}触发增量上传失败：{safe_error_text(err)}")
        return True


class _UploadEventHandler(FileSystemEventHandler):
    """把 watchdog 事件翻译成 :meth:`UploadWatcher.report_change`。"""

    def __init__(self, watcher: UploadWatcher):
        super().__init__()
        self._watcher = watcher

    def on_created(self, event: Any) -> None:
        self._watcher.report_change(
            getattr(event, "src_path", ""),
            bool(getattr(event, "is_directory", False)),
        )

    def on_moved(self, event: Any) -> None:
        # 移入源目录 / 源目录内改名都可能是新文件；移走的不触发（uploader 不做删除）
        self._watcher.report_change(
            getattr(event, "dest_path", ""),
            bool(getattr(event, "is_directory", False)),
        )

    def on_modified(self, event: Any) -> None:
        self._watcher.report_change(
            getattr(event, "src_path", ""),
            bool(getattr(event, "is_directory", False)),
        )