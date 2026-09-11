from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock, Thread

from app.plugins.p115liteassistant.limiter import (
    CooldownSlot,
    PROFILE_PRESETS,
    RateLimitProfile,
    RateLimiter,
    RequestPacer,
    get_rate_limit_profile,
)


class FakeTime:
    def __init__(self, value: float = 0.0):
        self.value = value
        self.waits = []
        self.lock = Lock()

    def clock(self):
        with self.lock:
            return self.value

    def wait(self, delay):
        with self.lock:
            self.waits.append(delay)
            self.value += delay


def test_profiles_are_bounded_and_unknown_falls_back_to_balanced():
    assert get_rate_limit_profile("missing") == PROFILE_PRESETS["balanced"]
    assert PROFILE_PRESETS["fast"].directory_qps == 5
    assert {profile.download_link_qps for profile in PROFILE_PRESETS.values()} == {1}


def test_rate_limiter_fake_clock_order_and_qps_disabled():
    fake = FakeTime()
    limiter = RateLimiter(2, clock=fake.clock, waiter=fake.wait)
    for _ in range(4):
        limiter.acquire()
    assert fake.waits == [0.5, 0.5, 0.5]

    disabled = FakeTime()
    limiter = RateLimiter(0, clock=disabled.clock, waiter=disabled.wait)
    for _ in range(3):
        limiter.acquire()
    assert disabled.waits == []


def test_rate_limiter_concurrent_reservations_are_spaced():
    fake = FakeTime()
    limiter = RateLimiter(4, clock=fake.clock, waiter=fake.wait)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: limiter.acquire(), range(4)))
    assert sorted(fake.waits) == [0.25, 0.25, 0.25]
    assert fake.value == 0.75


def test_rate_limiter_concurrent_actual_release_times_are_strictly_spaced():
    class CoordinatedTime:
        def __init__(self):
            self.value = 0.0
            self.condition = __import__("threading").Condition()
            self.waiting = 0

        def clock(self):
            with self.condition:
                return self.value

        def wait(self, delay):
            target = delay
            with self.condition:
                self.waiting += 1
                self.condition.notify_all()
                self.condition.wait_for(lambda: self.value >= target)

        def wait_until_blocked(self, count):
            with self.condition:
                assert self.condition.wait_for(lambda: self.waiting >= count, timeout=1)

        def advance_to(self, value):
            with self.condition:
                self.value = value
                self.condition.notify_all()

    coordinated = CoordinatedTime()
    limiter = RateLimiter(4, clock=coordinated.clock, waiter=coordinated.wait)
    start = Barrier(5)
    releases = []
    release_lock = Lock()

    def acquire_and_record():
        start.wait()
        limiter.acquire()
        with release_lock:
            released_at = coordinated.clock()
            releases.append(released_at)
        with coordinated.condition:
            coordinated.condition.notify_all()

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(acquire_and_record) for _ in range(4)]
        start.wait()
        coordinated.wait_until_blocked(3)
        with coordinated.condition:
            assert coordinated.condition.wait_for(lambda: releases == [0.0], timeout=1)
        for release_at in (0.25, 0.5, 0.75):
            coordinated.advance_to(release_at)
            with coordinated.condition:
                assert coordinated.condition.wait_for(
                    lambda: len(releases) >= int(release_at / 0.25) + 1,
                    timeout=1,
                )
        for future in futures:
            future.result(timeout=1)

    assert releases == [0.0, 0.25, 0.5, 0.75]
    assert all(
        later - earlier >= 0.25
        for earlier, later in zip(releases, releases[1:])
    )


def test_rate_limiter_cancelled_while_waiting_exits_without_pending_reservation():
    cancelled = Event()
    waiting = Event()
    waiter_steps = []

    def waiter(delay):
        waiter_steps.append(delay)
        waiting.set()
        cancelled.set()

    limiter = RateLimiter(1, clock=lambda: 0.0, waiter=waiter)
    limiter.acquire()
    worker = Thread(target=lambda: limiter.acquire(cancelled=cancelled.is_set))
    worker.start()
    assert waiting.wait(timeout=1)
    worker.join(timeout=1)

    assert not worker.is_alive()
    assert waiter_steps == [0.1]
    assert limiter._next_allowed_at == 2.0

    cancelled.clear()
    limiter.acquire()
    assert waiter_steps[-1] == 2.0
    assert limiter._next_allowed_at == 3.0


def test_rate_limiter_cancelled_does_not_wait():
    fake = FakeTime()
    limiter = RateLimiter(1, clock=fake.clock, waiter=fake.wait)
    limiter.acquire()
    limiter.acquire(cancelled=lambda: True)
    assert fake.waits == []


def test_cooldown_first_call_concurrent_and_clock_rollback():
    fake = FakeTime(10)
    slot = CooldownSlot(2, clock=fake.clock, waiter=fake.wait)
    slot.acquire()
    slot.acquire()
    assert fake.waits == [2]

    fake.value = 1  # monotonic provider rollback must not collapse reservations
    slot.acquire()
    assert fake.waits[-1] == 13


def test_request_pacer_always_reserves_open_before_route():
    profile = RateLimitProfile(2, 4, 0.75, 0.5, 0.5, 0.5, 2, 2, 1)
    pacer = RequestPacer(profile)
    order = []
    pacer.open_global.acquire = lambda **_kwargs: order.append("open")
    pacer._routes["directory"].acquire = lambda **_kwargs: order.append("route")
    pacer.acquire("directory", is_open=True)
    assert order == ["open", "route"]


def test_unknown_open_route_uses_other_open_but_cookie_none_is_unlimited():
    pacer = RequestPacer("balanced")
    order = []
    pacer.open_global.acquire = lambda **_kwargs: order.append("open")
    pacer._routes["other_open"].acquire = lambda **_kwargs: order.append("other")
    pacer.acquire("unknown", is_open=True)
    pacer.acquire("", is_open=False)
    assert order == ["open", "other"]


def test_request_pacer_parallel_routes_complete_without_lock_order_deadlock():
    profile = RateLimitProfile(0, 0, 0, 0, 0, 0, 0, 0, 0)
    pacer = RequestPacer(profile)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [
            pool.submit(pacer.acquire, route, is_open=True)
            for route in ("directory", "metadata", "upload_control", "mutation")
            for _ in range(8)
        ]
        assert all(future.result(timeout=1) is None for future in futures)


def test_post_success_cooldown_waits_on_first_use():
    fake = FakeTime()
    slot = CooldownSlot(0.75, clock=fake.clock, waiter=fake.wait)
    slot.acquire_after()
    slot.acquire_after()
    assert fake.waits == [0.75, 0.75]
