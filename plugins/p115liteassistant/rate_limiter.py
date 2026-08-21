from __future__ import annotations

from collections import OrderedDict, deque
from threading import Lock
from time import monotonic
from typing import Deque, Optional


class RateLimiter:
    """按 key 的滑动窗口限流器，不阻塞调用方。

    每个 key 保留窗口内的请求时间戳，判断时先丢掉过期的再计数。这样窗口是真正
    滑动的：持续打请求不会把窗口一直往后推、导致 key 被永久锁死。
    """

    def __init__(self, limit: int, window_seconds: float, maxsize: int = 4096):
        self._limit = max(1, int(limit))
        self._window = max(0.001, float(window_seconds))
        self._maxsize = max(1, int(maxsize))
        self._lock = Lock()
        self._hits: OrderedDict[str, Deque[float]] = OrderedDict()

    def _prune(self, key: str, now: float) -> Deque[float]:
        hits = self._hits.get(key)
        if hits is None:
            hits = deque()
            self._hits[key] = hits
        cutoff = now - self._window
        while hits and hits[0] <= cutoff:
            hits.popleft()
        return hits

    def _evict(self) -> None:
        # 淘汰最久未活动的 key，避免被大量伪造来源 IP 撑爆内存
        while len(self._hits) > self._maxsize:
            self._hits.popitem(last=False)

    def check(self, key: str) -> bool:
        """在限额内返回 True 并记一次；超限返回 False 且不记账。"""
        now = monotonic()
        with self._lock:
            hits = self._prune(key, now)
            if len(hits) >= self._limit:
                self._hits.move_to_end(key)
                return False
            hits.append(now)
            self._hits.move_to_end(key)
            self._evict()
            return True

    def remaining(self, key: str) -> int:
        """返回该 key 当前还能发多少次请求。"""
        now = monotonic()
        with self._lock:
            return max(0, self._limit - len(self._prune(key, now)))

    def retry_after(self, key: str) -> Optional[int]:
        """超限时返回建议的等待秒数，未超限返回 None。"""
        now = monotonic()
        with self._lock:
            hits = self._prune(key, now)
            if len(hits) < self._limit:
                return None
            return max(1, int(self._window - (now - hits[0])) + 1)
