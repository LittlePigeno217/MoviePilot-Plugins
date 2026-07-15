import unittest

from app.core.config import settings
from plugins.p115liteassistant.api import Api


class FakeStore:
    def __init__(self):
        self.config = {
            "enabled": True,
            "checkin_enabled": True,
            "checkin_time_range": "06:00-09:00",
        }
        self.history = []
        self.schedule = {"next_run_ts": 0}

    def get_config(self):
        return dict(self.config)

    def append_history(self, entry):
        self.history.append(entry)

    def get_checkin_schedule(self):
        return dict(self.schedule)

    def save_checkin_schedule(self, state):
        self.schedule = dict(state)


class FakeClient:
    def __init__(self):
        self.browse_calls = 0
        self.download_calls = 0
        self.checkin_calls = 0

    def get_dir_list(self, cid):
        self.browse_calls += 1
        return [
            {"fn": "Zeta", "cid": "2"},
            {"fn": "Alpha", "cid": "1"},
        ]

    def get_download_url(self, pickcode):
        self.download_calls += 1
        return f"https://download.example/{pickcode}"

    def checkin(self):
        self.checkin_calls += 1
        return {"already": False, "continuous_day": 3, "points_num": 5, "message": "签到成功"}


class ApiReliabilityTest(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.store = FakeStore()
        self.api = Api(lambda: self.client, self.store, lambda: "token")

    def test_browse_115_sorts_and_caches_short_lived_results(self):
        first = self.api.browse_115("0")
        second = self.api.browse_115("0")

        self.assertTrue(first["success"])
        self.assertEqual([item["name"] for item in first["data"]["items"]], ["Alpha", "Zeta"])
        self.assertEqual(second["data"], first["data"])
        self.assertEqual(self.client.browse_calls, 1)

    def test_local_directory_root_is_moviepilot_root(self):
        self.assertEqual(Api._local_roots(), [settings.ROOT_PATH.resolve()])

    def test_redirect_uses_short_lived_pickcode_cache(self):
        first = self.api.redirect("pick", "token")
        second = self.api.redirect("pick", "token")

        self.assertEqual(first.headers["location"], "https://download.example/pick")
        self.assertEqual(second.headers["location"], "https://download.example/pick")
        self.assertEqual(self.client.download_calls, 1)

    def test_scheduled_checkin_runs_once_and_records_the_day(self):
        result = self.api.run_scheduled_checkin()
        repeated = self.api.run_scheduled_checkin()

        self.assertTrue(result["success"])
        self.assertTrue(repeated["success"])
        self.assertEqual(self.client.checkin_calls, 1)
        self.assertTrue(self.store.schedule["last_done_date"])
        self.assertGreater(self.store.schedule["next_run_ts"], 0)
