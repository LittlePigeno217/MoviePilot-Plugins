"""本地 STRM 删除的实时监听：目录事件 -> 防抖 -> 上报给反向删除巡检。

监听器只负责「谁被删了」，删不删由 :class:`ReverseDeleter` 决定 —— 那边会再确认
「记录里有、本地确实没有」，并且照样跑未挂载与缺失比例熔断。所以即使事件误报
（媒体服务器刮削时常「删掉再写回」）也不会误删 115 上的文件。

它只是**加速手段**：网络挂载（NFS/SMB/CIFS）上 inotify 收不到其它主机产生的删除
事件，真正兜底的是定时巡检。
"""

from __future__ import annotations

from pathlib import Path
from threading import Event, Lock, Thread, current_thread
from time import monotonic
from typing import Any, Callable, Dict, Optional

from app.log import logger

from .log_utils import safe_error_text

try:  # watchdog 由 requirements.txt 声明；缺失时只是不启动监听，不影响其它功能
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except Exception:  # noqa: BLE001  # pragma: no cover - 取决于运行环境
    FileSystemEventHandler = object  # type: ignore[assignment,misc]
    Observer = None  # type: ignore[assignment]


#: 只关心 STRM 本体。刮削文件单独被删不触发 —— 反向删除以媒体为单位，云端刮削文件
#: 跟着媒体一起走，单独删一个 .nfo 本来就不该动云端。
WATCHED_SUFFIX = ".strm"

LOG_TAG = "【STRM监听】"


class StrmDeleteWatcher:
    """监听各映射的 STRM 输出目录，本地 .strm 被删就上报一次反向删除。"""

    #: 事件安静多久才认为删除已经定型
    DEBOUNCE_SECONDS = 30.0
    #: 队列巡检间隔
    TICK_SECONDS = 5.0
    #: 单批最多上报多少条路径；超了就整体巡检，交给缺失比例熔断兜底
    MAX_BATCH_PATHS = 500

    def __init__(
        self,
        config_provider: Callable[[], Dict[str, Any]],
        sweep_trigger: Callable[[Optional[list[str]]], Any],
        observer_factory: Optional[Callable[[], Any]] = None,
    ):
        self._config_provider = config_provider
        self._sweep_trigger = sweep_trigger
        self._observer_factory = observer_factory or (Observer if Observer else None)
        self._observer: Any = None
        self._thread: Optional[Thread] = None
        self._thread_lock = Lock()
        self._stop_event = Event()
        self._pending_lock = Lock()
        #: 本地路径 -> 最后一次事件的时间戳（单调时钟）
        self._pending: Dict[str, float] = {}
        #: 本轮实际登记成功的目录，用于掉盘自检
        self._watched: list[Path] = []

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive())

    def watch_dirs(self) -> list[Path]:
        """返回需要监听的 STRM 输出目录（已启用映射、目录当前存在）。"""
        config = self._config_provider()
        dirs: list[Path] = []
        seen: set[Path] = set()
        for mapping in config.get("strm_mappings") or []:
            if not isinstance(mapping, dict) or not mapping.get("enabled", True):
                continue
            target = str(mapping.get("target_dir") or "").strip()
            if not target:
                continue
            try:
                resolved = Path(target).expanduser().resolve()
            except (OSError, RuntimeError, ValueError):
                logger.warning(f"{LOG_TAG}输出目录无法解析，跳过：{target}")
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            if not resolved.is_dir():
                # 媒体库没挂上时不要监听：inotify 会盯着挂载点下的空目录，挂载完成后
                # 也不会自动生效，不如等下一次配置保存或重启重新登记。
                logger.warning(f"{LOG_TAG}输出目录不存在，暂不监听：{resolved}")
                continue
            dirs.append(resolved)
        return dirs

    def start(self) -> None:
        """启动监听。watchdog 不可用或没有可监听目录时安静退出。"""
        with self._thread_lock:
            if self.is_running:
                return
            if self._observer_factory is None:
                logger.warning(
                    f"{LOG_TAG}未安装 watchdog，实时监听不可用；反向删除仍会按定时巡检执行"
                )
                return
            dirs = self.watch_dirs()
            if not dirs:
                logger.warning(f"{LOG_TAG}没有可监听的 STRM 输出目录，实时监听未启动")
                return
            observer = self._observer_factory()
            handler = _StrmDeleteHandler(self)
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
            self._thread = Thread(
                target=self._run,
                name="p115liteassistant-strm-watch",
                daemon=True,
            )
            self._thread.start()
        logger.info(
            f"{LOG_TAG}已开始监听 {len(scheduled)} 个 STRM 输出目录，"
            f"删除事件安静 {self.DEBOUNCE_SECONDS:g} 秒后上报反向删除"
        )

    def stop(self, timeout: float = 5.0) -> None:
        """停止监听，并清空未处理的事件队列。"""
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
            self._pending.clear()
        if thread:
            logger.info(f"{LOG_TAG}已停止")

    # ---- 事件入口（watchdog 回调与单测都走这里）----

    def report_removed(self, path: str, is_directory: bool = False) -> None:
        """登记一条「本地路径已消失」的事件。

        目录事件按前缀交给巡检处理，文件只收 ``.strm``：本地这一侧只有 STRM 是媒体的
        替身，刮削文件的去留跟着媒体走。
        """
        text = str(path or "").strip()
        if not text:
            return
        if not is_directory and Path(text).suffix.lower() != WATCHED_SUFFIX:
            return
        with self._pending_lock:
            self._pending[text] = monotonic()
        logger.debug(f"{LOG_TAG}捕获删除事件：{text}")

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
                f"{LOG_TAG}监听目录已消失，判定媒体库掉盘，停止实时监听：{directory}；"
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
                # stop() 要 join 当前线程，只能另起一个线程去收尾
                Thread(
                    target=self.stop,
                    name="p115liteassistant-strm-watch-stop",
                    daemon=True,
                ).start()
                return
            try:
                self.drain_once()
            except Exception as err:  # noqa: BLE001
                logger.error(f"{LOG_TAG}处理删除事件失败：{safe_error_text(err)}")

    def drain_once(self) -> list[str]:
        """把安静够久的事件交给反向删除巡检，返回本次上报的路径。"""
        ready = self._take_ready()
        if not ready:
            return []
        if len(ready) > self.MAX_BATCH_PATHS:
            logger.warning(
                f"{LOG_TAG}一次捕获到 {len(ready)} 条删除事件，改为整体巡检，"
                "由缺失比例熔断决定是否动云端"
            )
            self._dispatch(None)
            return ready
        logger.info(f"{LOG_TAG}{len(ready)} 个本地 STRM 已删除，上报反向删除")
        self._dispatch(ready)
        return ready

    def _take_ready(self) -> list[str]:
        """取出安静时间够长、且确认本地已经不存在的路径。"""
        now = monotonic()
        ready: list[str] = []
        with self._pending_lock:
            for path, stamp in list(self._pending.items()):
                if now - stamp < self.DEBOUNCE_SECONDS:
                    continue
                self._pending.pop(path, None)
                try:
                    if Path(path).exists():
                        # 删掉又写回来了（刮削器改写、移动回原位），当没发生过
                        logger.debug(f"{LOG_TAG}路径已恢复，忽略：{path}")
                        continue
                except OSError:
                    continue
                ready.append(path)
        return ready

    def _dispatch(self, paths: Optional[list[str]]) -> None:
        """把路径交给编排层。

        排队与补跑都由编排层负责（``Api._enqueue_strm_sweep``）：抢不到 115 数据任务锁
        的事件会记在那边，锁释放后自动补跑。监听器不留第二份队列。
        """
        try:
            self._sweep_trigger(paths)
        except Exception as err:  # noqa: BLE001
            logger.error(f"{LOG_TAG}上报删除事件失败：{safe_error_text(err)}")


class _StrmDeleteHandler(FileSystemEventHandler):
    """把 watchdog 事件翻译成 :meth:`StrmDeleteWatcher.report_removed`。"""

    def __init__(self, watcher: StrmDeleteWatcher):
        super().__init__()
        self._watcher = watcher

    def on_deleted(self, event: Any) -> None:
        self._watcher.report_removed(
            getattr(event, "src_path", ""),
            bool(getattr(event, "is_directory", False)),
        )

    def on_moved(self, event: Any) -> None:
        # 移走等于原地没了：目标可能在监听范围之外，也可能只是本地改名，两种情况都由
        # 巡检按「记录里有、本地没有」重新判定。
        self._watcher.report_removed(
            getattr(event, "src_path", ""),
            bool(getattr(event, "is_directory", False)),
        )
