from datetime import datetime
import unittest
from zoneinfo import ZoneInfo

from plugins.p115liteassistant.checkin_schedule import (
    parse_checkin_time_range,
    pick_next_run_epoch,
)


class CheckinScheduleTest(unittest.TestCase):
    def test_invalid_time_range_uses_upstream_default_window(self):
        self.assertEqual(str(parse_checkin_time_range("invalid")[0]), "06:00:00")
        self.assertEqual(str(parse_checkin_time_range("invalid")[1]), "09:00:00")

    def test_pick_next_run_uses_current_or_next_window(self):
        timezone = ZoneInfo("Asia/Shanghai")
        before_window = datetime(2026, 7, 15, 5, 30, tzinfo=timezone)
        after_window = datetime(2026, 7, 15, 10, 0, tzinfo=timezone)
        first = pick_next_run_epoch(before_window, timezone, "06:00-09:00", lambda start, end: start)
        second = pick_next_run_epoch(after_window, timezone, "06:00-09:00", lambda start, end: start)

        self.assertEqual(datetime.fromtimestamp(first, timezone).strftime("%Y-%m-%d %H:%M"), "2026-07-15 06:00")
        self.assertEqual(datetime.fromtimestamp(second, timezone).strftime("%Y-%m-%d %H:%M"), "2026-07-16 06:00")
