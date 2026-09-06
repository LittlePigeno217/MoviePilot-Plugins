"""网盘核对与做种判定：预算、冷却、撞限流即停，以及「不知道」不能被写成「没有」。

这两块都会影响破坏性动作能不能按下去，所以口径必须被钉住：核对结果决定「网盘上没了」这个
筛选，做种结果决定「删除源文件」锁不锁。判错的代价是让人照着删还在的东西。

这里不用 MagicMock：手写 Fake 才能断言「问了几次、第几次停下、停下时存了什么」。
"""

import unittest

from app.plugins.p115liteassistant.client import U115AccessLimitError
from app.plugins.p115liteassistant.cloud_check import (
    check_rows,
    cooldown_left,
    merge,
    pick_rows,
)
from app.plugins.p115liteassistant.seeding import _history_identity, _torrent_content_path


class FakeClient:
    """只实现 check_rows 用到的三个方法。``gone`` 里的路径返回 None（网盘上没了）。"""

    def __init__(self, gone=(), limit_at=None, error_at=None):
        self.gone = set(gone)
        self.limit_at = limit_at
        self.error_at = error_at
        self.asked = []

    @staticmethod
    def new_access_limit_state():
        return {"event": None, "lock": None, "message": ""}

    @staticmethod
    def run_with_access_limit_state(_state, operation):
        return operation()

    def get_item(self, path):
        self.asked.append(path)
        index = len(self.asked)
        if self.limit_at == index:
            raise U115AccessLimitError("已达到当前访问上限")
        if self.error_at == index:
            raise RuntimeError("网络抖了一下")
        return None if path in self.gone else {"fileid": "1"}


def row(index, folder=None):
    return {"id": f"movie|片 {index}||", "cloud_folder": folder if folder is not None else f"/影视/片 {index}"}


class CheckRowsTest(unittest.TestCase):
    def test_states_and_budget(self):
        client = FakeClient(gone={"/影视/片 2"})
        rows = [row(1), row(2), row(3)]
        results, stopped = check_rows(lambda: client, rows, budget=2)
        self.assertEqual(stopped, "")
        # 预算 2 就只问 2 行，第三行留着下次
        self.assertEqual(len(client.asked), 2)
        self.assertEqual(results[rows[0]["id"]]["state"], "yes")
        self.assertEqual(results[rows[1]["id"]]["state"], "no")
        self.assertNotIn(rows[2]["id"], results)

    def test_stops_on_access_limit_and_keeps_what_it_got(self):
        client = FakeClient(limit_at=3)
        results, stopped = check_rows(lambda: client, [row(i) for i in range(1, 6)], budget=5)
        self.assertIn("访问上限", stopped)
        # 前两行的答案要留下，别因为第三行炸了就整批丢掉
        self.assertEqual(len(results), 2)

    def test_stops_on_first_error(self):
        """一个错就停：同一个毛病重复问几十次只会更快撞上限流。"""
        client = FakeClient(error_at=2)
        results, stopped = check_rows(lambda: client, [row(i) for i in range(1, 6)], budget=5)
        self.assertIn("出错", stopped)
        self.assertEqual(len(client.asked), 2)
        self.assertEqual(len(results), 1)

    def test_skips_rows_without_cloud_folder(self):
        client = FakeClient()
        results, _ = check_rows(lambda: client, [row(1, folder=""), row(2)], budget=5)
        self.assertEqual(len(client.asked), 1)
        self.assertEqual(len(results), 1)


class BudgetTest(unittest.TestCase):
    def test_pick_oldest_first(self):
        rows = [row(1), row(2), row(3)]
        cache = {"rows": {rows[0]["id"]: {"checked_at": 100}, rows[1]["id"]: {"checked_at": 50}}}
        # 没核对过的排最前，然后才是最久没核对的
        picked = [item["id"] for item in pick_rows(rows, cache, 3)]
        self.assertEqual(picked, [rows[2]["id"], rows[1]["id"], rows[0]["id"]])

    def test_merge_sets_cooldown_only_when_limited(self):
        merged = merge({}, {"a": {"state": "yes"}}, limited=False)
        self.assertEqual(cooldown_left(merged), 0)
        merged = merge(merged, {"b": {"state": "no"}}, limited=True)
        self.assertGreater(cooldown_left(merged), 0)
        # 两轮的结果要并起来，不是互相覆盖
        self.assertEqual(set(merged["rows"]), {"a", "b"})


class SeedingTest(unittest.TestCase):
    def test_content_path_from_both_downloaders(self):
        class Qb:
            content_path = "/media/电影/某片.mkv"

        class Tr:
            download_dir = "/media/剧集"
            name = "某剧 S01"

        self.assertEqual(_torrent_content_path(Qb()), "/media/电影/某片.mkv")
        self.assertTrue(_torrent_content_path(Tr()).endswith("某剧 S01"))
        self.assertEqual(_torrent_content_path(object()), "")

    def test_history_identity_prefers_dest_path(self):
        class History:
            dest = "/媒体库/电影/沙丘 第二部 (2024)/沙丘 第二部 (2024) - 2160p.mkv"
            title = "别的名字"
            year = "1999"
            type = "电影"
            seasons = ""

        self.assertEqual(_history_identity(History()), "movie|沙丘 第二部|2024|")

    def test_history_identity_falls_back_to_fields(self):
        class History:
            dest = ""
            title = "某剧"
            year = "2024"
            type = "电视剧"
            seasons = "S03"

        self.assertEqual(_history_identity(History()), "tv|某剧|2024|3")
