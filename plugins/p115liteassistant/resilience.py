from __future__ import annotations

from threading import RLock
from time import monotonic, sleep
from typing import Callable, Dict, Generic, Optional, Tuple, Type, TypeVar


T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")


def retry_call(
    operation: Callable[[], T],
    *,
    attempts: int = 3,
    delay: float = 1.0,
    retryable: Tuple[Type[BaseException], ...] = (Exception,),
    sleeper: Callable[[float], None] = sleep,
) -> T:
    """以有限退避执行可恢复操作，最后一次失败保留原始异常。"""

    total = max(1, int(attempts))
    for attempt in range(1, total + 1):
        try:
            return operation()
        except retryable:
            if attempt >= total:
                raise
            sleeper(max(0.0, delay) * attempt)
    raise RuntimeError("重试操作未返回结果")


class TtlCache(Generic[K, V]):
    """线程安全的进程内短缓存，用于避免重复请求易变的 115 接口。"""

    def __init__(self, ttl_seconds: float):
        self._ttl_seconds = ttl_seconds
        self._items: Dict[K, Tuple[float, V]] = {}
        self._lock = RLock()

    def get(self, key: K) -> Optional[V]:
        with self._lock:
            item = self._items.get(key)
            if not item:
                return None
            expires_at, value = item
            if expires_at <= monotonic():
                self._items.pop(key, None)
                return None
            return value

    def set(self, key: K, value: V) -> None:
        with self._lock:
            self._items[key] = (monotonic() + self._ttl_seconds, value)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
