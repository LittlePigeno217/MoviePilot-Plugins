from __future__ import annotations

from collections import OrderedDict
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

    def __init__(self, ttl_seconds: float, maxsize: Optional[int] = None):
        self._ttl_seconds = ttl_seconds
        self._maxsize = maxsize
        self._items: OrderedDict[K, Tuple[float, V]] = OrderedDict()
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
            self._items.move_to_end(key)
            return value

    def set(self, key: K, value: V, ttl_seconds: Optional[float] = None) -> None:
        with self._lock:
            ttl = self._ttl_seconds if ttl_seconds is None else ttl_seconds
            self._items.pop(key, None)
            self._items[key] = (monotonic() + max(0.0, ttl), value)
            if self._maxsize is not None:
                while len(self._items) > self._maxsize:
                    self._items.popitem(last=False)

    def count(self, predicate: Callable[[K], bool]) -> int:
        now = monotonic()
        with self._lock:
            expired = [key for key, (expires_at, _value) in self._items.items() if expires_at <= now]
            for key in expired:
                self._items.pop(key, None)
            return sum(1 for key in self._items if predicate(key))

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
