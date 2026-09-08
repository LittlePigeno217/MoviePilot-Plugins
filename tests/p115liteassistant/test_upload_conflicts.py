import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from app.plugins.p115liteassistant.records import IncrementalRecordStore
from app.plugins.p115liteassistant.uploader import DirectoryUploader, UploadIdentityConflict


class FakeStore:
    """只提供冲突队列与上传记录的内存实现。"""

    def __init__(self):
        self.conflicts = {}

    def get_upload_conflicts(self):
        return dict(self.conflicts)

    def save_upload_conflicts(self, conflicts):
        self.conflicts = dict(conflicts)


def build_uploader(policy, store):
    uploader = DirectoryUploader.__new__(DirectoryUploader)
    uploader._config = {"upload_conflict_policy": policy}
    uploader._store = store
    uploader._client = Mock()
    return uploader


def make_conflict(target="/影视/沙丘 第二部/沙丘.mkv", remote_pc="pc-remote"):
    return UploadIdentityConflict(
        "上传记录对不上网盘文件",
        local_path="/media/link/沙丘 第二部/沙丘.mkv",
        target=target,
        recorded_pickcode="pc-recorded",
        remote_pickcode=remote_pc,
        recorded_size=10,
    )


def make_records(path, pickcode="pc-recorded"):
    store = IncrementalRecordStore(
        {path: {"size": 10, "mtime_ns": 1, "target": "/x", "pickcode": pickcode}}
    )
    return store


class ConflictPolicyTest(unittest.TestCase):
    """「上传身份冲突」按配置的策略处理：ask 挂清单，adopt 认远端，reupload 删远端重传。"""

    def test_ask_policy_queues_the_conflict(self):
        store = FakeStore()
        uploader = build_uploader("ask", store)
        records = make_records("/media/link/沙丘 第二部/沙丘.mkv")

        uploader._handle_upload_conflict(make_conflict(), records)

        self.assertEqual(len(store.conflicts), 1)
        entry = next(iter(store.conflicts.values()))
        self.assertEqual(entry["remote_pickcode"], "pc-remote")
        self.assertIn("first_seen", entry)
        # 记录一个字都没动
        self.assertEqual(records.get(Path("/media/link/沙丘 第二部/沙丘.mkv"))["pickcode"], "pc-recorded")

    def test_ask_policy_second_sighting_keeps_first_seen(self):
        store = FakeStore()
        uploader = build_uploader("ask", store)

        uploader._handle_upload_conflict(make_conflict(), make_records("/media/link/沙丘 第二部/沙丘.mkv"))
        first_seen = next(iter(store.conflicts.values()))["first_seen"]
        uploader._handle_upload_conflict(make_conflict(), make_records("/media/link/沙丘 第二部/沙丘.mkv"))

        self.assertEqual(len(store.conflicts), 1)
        self.assertEqual(next(iter(store.conflicts.values()))["first_seen"], first_seen)

    def test_adopt_policy_adopts_remote_pickcode(self):
        store = FakeStore()
        uploader = build_uploader("adopt", store)
        path = "/media/link/沙丘 第二部/沙丘.mkv"
        records = make_records(path)

        uploader._handle_upload_conflict(make_conflict(), records)

        self.assertEqual(store.conflicts, {})
        self.assertEqual(records.get(Path(path))["pickcode"], "pc-remote")

    def test_reupload_policy_deletes_remote_and_clears_record(self):
        store = FakeStore()
        uploader = build_uploader("reupload", store)
        uploader._client.get_item.return_value = {"fileid": "9001"}
        path = "/media/link/沙丘 第二部/沙丘.mkv"
        records = make_records(path)

        uploader._handle_upload_conflict(make_conflict(), records)

        uploader._client.delete_file.assert_called_once_with("9001")
        self.assertIsNone(records._records.get(path))
        self.assertEqual(store.conflicts, {})

    def test_auto_policy_failure_falls_back_to_queue(self):
        """自动处理出岔子（远端够不着）时不硬扛，退回挂清单，事不能丢。"""
        store = FakeStore()
        uploader = build_uploader("reupload", store)
        uploader._client.get_item.side_effect = RuntimeError("网络不可达")

        uploader._handle_upload_conflict(make_conflict(), make_records("/media/link/沙丘 第二部/沙丘.mkv"))

        self.assertEqual(len(store.conflicts), 1)
        uploader._client.delete_file.assert_not_called()

    def test_unknown_policy_is_ask(self):
        store = FakeStore()
        uploader = build_uploader("whatever", store)

        uploader._handle_upload_conflict(make_conflict(), make_records("/media/link/沙丘 第二部/沙丘.mkv"))

        self.assertEqual(len(store.conflicts), 1)


if __name__ == "__main__":
    unittest.main()
