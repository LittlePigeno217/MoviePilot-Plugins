from __future__ import annotations

from datetime import date, datetime, time, timedelta
from random import uniform
from re import fullmatch
from typing import Callable, Tuple


DEFAULT_CHECKIN_TIME_RANGE = "06:00-09:00"


def parse_checkin_time_range(value: str) -> Tuple[time, time]:
    """解析 HH:MM-HH:MM；非法配置回退到上游默认窗口。"""

    text = str(value or DEFAULT_CHECKIN_TIME_RANGE).strip()
    matched = fullmatch(r"([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-3]):([0-5]\d)", text)
    if not matched:
        return time(6, 0), time(9, 0)
    return time(int(matched.group(1)), int(matched.group(2))), time(int(matched.group(3)), int(matched.group(4)))


def random_epoch_for_date(
    value: date,
    timezone,
    time_range: str,
    randomizer: Callable[[float, float], float] = uniform,
) -> float:
    start_time, end_time = parse_checkin_time_range(time_range)
    start = datetime.combine(value, start_time, tzinfo=timezone)
    end = datetime.combine(value, end_time, tzinfo=timezone)
    return randomizer(start.timestamp(), end.timestamp())


def pick_next_run_epoch(
    now: datetime,
    timezone,
    time_range: str,
    randomizer: Callable[[float, float], float] = uniform,
) -> float:
    """在当前或次日签到窗口中选择一个随机执行时刻。"""

    start_time, end_time = parse_checkin_time_range(time_range)
    today_start = datetime.combine(now.date(), start_time, tzinfo=timezone)
    today_end = datetime.combine(now.date(), end_time, tzinfo=timezone)
    if now < today_start:
        return randomizer(today_start.timestamp(), today_end.timestamp())
    if now < today_end:
        return randomizer(now.timestamp(), today_end.timestamp())
    return random_epoch_for_date(now.date() + timedelta(days=1), timezone, time_range, randomizer)
