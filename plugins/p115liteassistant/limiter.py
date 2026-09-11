from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic, sleep
from typing import Callable, Optional

Clock = Callable[[], float]
Waiter = Callable[[float], None]
Cancelled = Optional[Callable[[], bool]]

ROUTES = frozenset(
    {
        "auth",
        "directory",
        "metadata",
        "upload_control",
        "download_link",
        "life_ios",
        "life_web",
        "mutation",
        "other_open",
    }
)


def _wait(delay: float, waiter: Waiter, cancelled: Cancelled) -> None:
    remaining = max(0.0, float(delay))
    if remaining <= 0 or (cancelled is not None and cancelled()):
        return
    if cancelled is None:
        waiter(remaining)
        return
    # 带取消源时分段等待，使任务停止/共享访问上限无需等完整预约时长。
    while remaining > 0 and not cancelled():
        step = min(0.1, remaining)
        waiter(step)
        remaining -= step


class RateLimiter:
    """线程安全的预约式固定间隔 QPS 控制器。"""

    def __init__(
        self,
        qps: float,
        *,
        clock: Clock = monotonic,
        waiter: Waiter = sleep,
    ) -> None:
        self.interval = 0.0 if qps <= 0 else 1.0 / float(qps)
        self._clock = clock
        self._waiter = waiter
        self._lock = Lock()
        self._next_allowed_at = 0.0
        self._reserved = False

    def acquire(self, *, cancelled: Cancelled = None) -> None:
        if cancelled is not None and cancelled():
            return
        with self._lock:
            now = self._clock()
            if not self._reserved:
                reserved_at = now
                self._reserved = True
            else:
                reserved_at = max(now, self._next_allowed_at)
            self._next_allowed_at = reserved_at + self.interval
            delay = max(0.0, reserved_at - now)
        _wait(delay, self._waiter, cancelled)


class CooldownSlot:
    """首调立即、后续严格按 cooldown 预约的端点槽。"""

    def __init__(
        self,
        cooldown: float,
        *,
        clock: Clock = monotonic,
        waiter: Waiter = sleep,
    ) -> None:
        self.cooldown = max(0.0, float(cooldown))
        self._clock = clock
        self._waiter = waiter
        self._lock = Lock()
        self._next_allowed_at = 0.0
        self._reserved = False

    def acquire(self, *, cancelled: Cancelled = None) -> None:
        if cancelled is not None and cancelled():
            return
        with self._lock:
            now = self._clock()
            if not self._reserved:
                reserved_at = now
                self._reserved = True
            else:
                reserved_at = max(now, self._next_allowed_at)
            self._next_allowed_at = reserved_at + self.cooldown
            delay = max(0.0, reserved_at - now)
        _wait(delay, self._waiter, cancelled)

    def acquire_after(self, *, cancelled: Cancelled = None) -> None:
        """成功动作后的冷却：当前调用也必须完整等待一个 cooldown。"""
        if cancelled is not None and cancelled():
            return
        with self._lock:
            now = self._clock()
            reserved_at = max(now, self._next_allowed_at) if self._reserved else now
            target = reserved_at + self.cooldown
            self._next_allowed_at = target
            self._reserved = True
            delay = max(0.0, target - now)
        _wait(delay, self._waiter, cancelled)


@dataclass(frozen=True)
class RateLimitProfile:
    open_qps: float
    directory_qps: float
    directory_page_cooldown: float
    metadata_cooldown: float
    upload_cooldown: float
    mutation_cooldown: float
    life_ios_cooldown: float
    life_web_cooldown: float
    download_link_qps: float


PROFILE_PRESETS = {
    "conservative": RateLimitProfile(1, 2, 1.5, 1.0, 1.0, 1.0, 3.0, 3.0, 1),
    "balanced": RateLimitProfile(2, 4, 0.75, 0.5, 0.5, 0.5, 2.0, 2.0, 1),
    "fast": RateLimitProfile(3, 5, 0.25, 0.25, 0.25, 0.25, 1.0, 1.0, 1),
}


def get_rate_limit_profile(name: str) -> RateLimitProfile:
    return PROFILE_PRESETS.get(str(name or "").strip().lower(), PROFILE_PRESETS["balanced"])


class RequestPacer:
    """实例级请求预算：Open 总预算固定先于端点族预算预约。"""

    def __init__(
        self,
        profile: RateLimitProfile | str = "balanced",
        *,
        clock: Clock = monotonic,
        waiter: Waiter = sleep,
    ) -> None:
        self.profile = (
            get_rate_limit_profile(profile) if isinstance(profile, str) else profile
        )
        value = self.profile
        self.open_global = RateLimiter(value.open_qps, clock=clock, waiter=waiter)
        self.directory_page = CooldownSlot(
            value.directory_page_cooldown, clock=clock, waiter=waiter
        )
        self._routes = {
            "auth": CooldownSlot(value.metadata_cooldown, clock=clock, waiter=waiter),
            "directory": RateLimiter(value.directory_qps, clock=clock, waiter=waiter),
            "metadata": CooldownSlot(value.metadata_cooldown, clock=clock, waiter=waiter),
            "upload_control": CooldownSlot(value.upload_cooldown, clock=clock, waiter=waiter),
            "download_link": RateLimiter(value.download_link_qps, clock=clock, waiter=waiter),
            "life_ios": CooldownSlot(value.life_ios_cooldown, clock=clock, waiter=waiter),
            "life_web": CooldownSlot(value.life_web_cooldown, clock=clock, waiter=waiter),
            "mutation": CooldownSlot(value.mutation_cooldown, clock=clock, waiter=waiter),
            "other_open": CooldownSlot(value.metadata_cooldown, clock=clock, waiter=waiter),
        }

    def acquire(
        self,
        route: str,
        *,
        is_open: bool,
        cancelled: Cancelled = None,
    ) -> None:
        normalized = str(route or "").strip().lower()
        if is_open and normalized not in ROUTES:
            normalized = "other_open"
        if is_open:
            self.open_global.acquire(cancelled=cancelled)
        slot = self._routes.get(normalized)
        if slot is not None:
            slot.acquire(cancelled=cancelled)

    def acquire_directory_page(self, *, cancelled: Cancelled = None) -> None:
        self.directory_page.acquire_after(cancelled=cancelled)
