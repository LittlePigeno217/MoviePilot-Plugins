"""反向删除：护栏矩阵、刮削归属、空目录级联与待确认队列。

这里刻意不用 MagicMock —— 反向删除的每一次 115 调用都可能真删东西，用手写 Fake
才能把「谁被删了、删了几次」断言到位。
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.plugins.p115liteassistant.resilience import TtlCache
from app.plugins.p115liteassistant.reverse_delete import (
    ACTION_DELETE,
    ACTION_PENDING,
    ACTION_SKIPPED,
    DEFAULT_CONFIRM_THRESHOLD,
    STRM_DELETE_PENDING_MAX_BATCHES,
    ReverseDeleter,
    associated_media_name,
    is_protected_cloud_dir,
    media_name_stem,
    normalize_confirm_threshold,
)


def is_dir_entry(item):
    return str(item.get("fc")) == "0"


def cloud_dir_entry_id(item):
    return str(item.get("fid") or item.get("cid") or "")


#: 云端目录 ID：/Movies 是一级目录（受保护），/Movies/Film 才是媒体所在目录
SOURCE_CID = "6000"
TOP_DIR_ID = "7000"
MEDIA_DIR_ID = "7100"


class FakeStore:
    """只提供反向删除用到的那几个读写口。"""

    def __init__(self, config=None, records=None):
        self.config = {"strm_delete_cloud_on_missing": True}
        self.config.update(config or {})
        self.strm_records = dict(records or {})
        self.pending = {}
        self.saved_records = 0

    def get_config(self):
        return dict(self.config)

    def get_strm_records(self):
        return {key: dict(value) for key, value in self.strm_records.items()}

    def save_strm_records(self, records):
        self.strm_records = {key: dict(value) for key, value in records.items()}
        self.saved_records += 1

    def get_strm_delete_pending(self):
        return {key: dict(value) for key, value in self.pending.items()}

    def save_strm_delete_pending(self, batches):
        self.pending = {key: dict(value) for key, value in batches.items()}

    def pop_strm_delete_batch(self, batch_id):
        return self.pending.pop(str(batch_id), None)


class FakeClient:
    """按目录 ID 返回列表，并记录每一次删除调用。

    ``stale_dir_delete=True`` 时模拟 115 的异步目录删除：目录删掉后，它仍然会在父目录
    的列表里挂一会儿。只按列表长度判空的实现会在这里露馅。
    """

    def __init__(self, listings=None, parents=None, stale_dir_delete=False):
        self.stale_dir_delete = bool(stale_dir_delete)
        #: {目录ID: [列表项]}
        self.listings = {key: list(value) for key, value in (listings or {}).items()}
        #: {目录ID: {"parent_id":..., "path":...}}
        self.parents = dict(parents or {})
        self.deleted = []
        self.list_calls = []
        self.item_lookups = []

    def get_dir_list(self, cid):
        self.list_calls.append(str(cid))
        return list(self.listings.get(str(cid), []))

    def delete_file(self, file_id, mode=""):
        ids = [str(file_id)] if isinstance(file_id, (str, int)) else [str(v) for v in file_id]
        self.deleted.extend(ids)
        if not self.stale_dir_delete:
            for dir_id, items in self.listings.items():
                self.listings[dir_id] = [
                    item for item in items if str(item.get("fid") or item.get("cid")) not in set(ids)
                ]
        else:
            # 只把文件从列表里摘掉，目录条目留着 —— 复现 115 的异步删除
            for dir_id, items in self.listings.items():
                self.listings[dir_id] = [
                    item
                    for item in items
                    if cloud_dir_entry_id(item) not in set(ids) or is_dir_entry(item)
                ]
        # 真实的 115 一旦删掉目录就再也查不到它的父级了。Fake 必须照做，否则
        # 「删完再向上找父级」这种顺序错误在单测里根本暴露不出来。
        for item_id in ids:
            self.parents.pop(item_id, None)
            self.listings.pop(item_id, None)

    def get_item(self, path):
        self.item_lookups.append(str(path))
        return None

    def get_item_by_id(self, file_id):
        return dict(self.parents.get(str(file_id), {}))


def cloud_file(fid, name):
    """115 open 列表里的文件项：fc="1"，fid 是自己，cid 是父目录。"""
    return {"fc": "1", "fid": fid, "cid": MEDIA_DIR_ID, "fn": name}


def cloud_dir(cid, name, parent=TOP_DIR_ID):
    return {"fc": "0", "cid": cid, "pid": parent, "fn": name}


def mapping_for(target_dir):
    return {
        "id": "movies",
        "source_cid": SOURCE_CID,
        "source_path": "/Movies",
        "target_dir": str(target_dir),
    }


def media_record(target_dir, stem, fid, *, parent_id=MEDIA_DIR_ID, exists=False, **extra):
    """造一条媒体记录；``exists`` 决定本地 STRM 是否真的落地。"""
    output = Path(target_dir) / "Film" / f"{stem}.strm"
    if exists:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("http://mp/redirect\n", encoding="utf-8")
    record = {
        "fingerprint": f"v3:{stem}",
        "path": str(output),
        "kind": "strm",
        "mapping_id": "movies",
        "name": f"{stem}.mkv",
        "cloud_path": f"/Movies/Film/{stem}.mkv",
        "file_id": fid,
        "parent_id": parent_id,
        "pickcode": f"pick-{stem}",
    }
    record.update(extra)
    return f"movies:Film/{stem}.mkv", record


def anchor_strm(target_dir):
    """放一个与本映射记录无关的 STRM，让「目录里一个 .strm 都没有」的闸门放行。"""
    keep = Path(target_dir) / "Keep.strm"
    keep.write_text("http://mp/keep\n", encoding="utf-8")
    return keep


class PureHelperTest(unittest.TestCase):
    """归属判定与保护目录的纯函数。"""

    def test_media_name_stem_only_strips_media_suffix(self):
        self.assertEqual(media_name_stem("Film.mkv"), "Film")
        self.assertEqual(media_name_stem("Film.nfo"), "Film.nfo")

    def test_scrape_owner_covers_common_naming(self):
        names = {"Film.mkv"}
        for candidate in ("Film.nfo", "Film-poster.jpg", "Film.zh-CN.srt", "Film.mkv.nfo"):
            self.assertEqual(associated_media_name(candidate, names), "Film.mkv", candidate)

    def test_scrape_owner_prefers_most_specific_media(self):
        names = {"Film.mkv", "Film 2.mkv"}
        self.assertEqual(associated_media_name("Film 2.nfo", names), "Film 2.mkv")
        self.assertEqual(associated_media_name("Film.nfo", names), "Film.mkv")

    def test_scrape_owner_rejects_unrelated_name(self):
        self.assertEqual(associated_media_name("Other.nfo", {"Film.mkv"}), "")

    def test_top_level_and_source_dirs_are_protected(self):
        protected = {"", "0", SOURCE_CID}
        self.assertTrue(is_protected_cloud_dir("0", "/", protected))
        self.assertTrue(is_protected_cloud_dir(SOURCE_CID, "/Movies", protected))
        self.assertTrue(is_protected_cloud_dir(TOP_DIR_ID, "/Movies", protected))
        self.assertFalse(is_protected_cloud_dir(MEDIA_DIR_ID, "/Movies/Film", protected))

    def test_confirm_threshold_normalisation(self):
        self.assertEqual(normalize_confirm_threshold(0), 0)
        self.assertEqual(normalize_confirm_threshold("5"), 5)
        self.assertEqual(normalize_confirm_threshold(-1), DEFAULT_CONFIRM_THRESHOLD)
        self.assertEqual(normalize_confirm_threshold("abc"), DEFAULT_CONFIRM_THRESHOLD)


class GuardTest(unittest.TestCase):
    """护栏矩阵 —— 每一条不通过时都必须一次 115 请求都不发。"""

    @staticmethod
    def _deleter(store, client):
        return ReverseDeleter(lambda: client, store)

    def test_unmounted_target_dir_skips_whole_sweep(self):
        """输出目录整个不存在 = 媒体库没挂上，一个云端文件都不许删。"""
        with TemporaryDirectory() as directory:
            missing_dir = Path(directory) / "not-mounted"
            key, record = media_record(missing_dir, "Film", "8001")
            store = FakeStore(records={key: record})
            client = FakeClient()

            entry = self._deleter(store, client).sweep(mapping_for(missing_dir))

            self.assertEqual(entry["action"], ACTION_SKIPPED)
            self.assertIn("未挂载", entry["reason"])
            self.assertEqual(client.deleted, [])
            self.assertEqual(client.list_calls, [])
            self.assertIn(key, store.strm_records)

    def test_empty_target_dir_skips_whole_sweep(self):
        """目录在但一个 .strm 都没有：挂载点被空目录顶替，同样不许删。"""
        with TemporaryDirectory() as directory:
            key, record = media_record(directory, "Film", "8001")
            store = FakeStore(records={key: record})
            client = FakeClient()

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(entry["action"], ACTION_SKIPPED)
            self.assertIn(".strm", entry["reason"])
            self.assertEqual(client.deleted, [])
            self.assertIn(key, store.strm_records)

    def test_high_missing_ratio_skips_whole_sweep(self):
        """10 条记录缺 9 条：疑似掉盘或换了输出目录，整轮放弃。"""
        with TemporaryDirectory() as directory:
            records = {}
            for index in range(9):
                key, record = media_record(directory, f"Gone{index}", f"90{index}")
                records[key] = record
            key, record = media_record(directory, "Kept", "9100", exists=True)
            records[key] = record
            store = FakeStore(records=records)
            client = FakeClient()

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(entry["action"], ACTION_SKIPPED)
            self.assertIn("比例过高", entry["reason"])
            self.assertEqual(client.deleted, [])
            self.assertEqual(len(store.strm_records), 10)

    def test_guard_ratio_ignored_below_min_records(self):
        """只放几部片的小映射不该被比例熔断永久锁死。"""
        with TemporaryDirectory() as directory:
            anchor_strm(directory)
            records = {}
            for index in range(4):
                key, record = media_record(directory, f"Gone{index}", f"80{index}")
                records[key] = record
            store = FakeStore(records=records)
            client = FakeClient(
                listings={MEDIA_DIR_ID: [cloud_file(f"80{index}", f"Gone{index}.mkv") for index in range(4)]}
            )

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(entry["action"], ACTION_DELETE)
            self.assertEqual(entry["cloud_deleted"], 4)
            # 目录被清空后连目录一起删（/Movies/Film 有三段路径，不在保护范围内）
            self.assertEqual(entry["cloud_dirs_deleted"], 1)
            self.assertEqual(sorted(client.deleted), ["7100", "800", "801", "802", "803"])
            self.assertEqual(store.strm_records, {})

    def test_only_paths_narrows_scope_but_guard_uses_full_set(self):
        """实时监听只报了一个路径，但全集缺失率超阈值时照样整轮跳过。"""
        with TemporaryDirectory() as directory:
            records = {}
            for index in range(9):
                key, record = media_record(directory, f"Gone{index}", f"90{index}")
                records[key] = record
                if index == 0:
                    reported = record["path"]
            key, record = media_record(directory, "Kept", "9100", exists=True)
            records[key] = record
            store = FakeStore(records=records)
            client = FakeClient()

            entry = self._deleter(store, client).sweep(mapping_for(directory), [reported])

            self.assertEqual(entry["action"], ACTION_SKIPPED)
            self.assertIn("比例过高", entry["reason"])
            self.assertEqual(client.deleted, [])


class ScrapeAndDirTest(unittest.TestCase):
    """刮削文件归属、目录级联与「云端已经没有」的分支。"""

    @staticmethod
    def _deleter(store, client):
        return ReverseDeleter(lambda: client, store)

    def _fixture(self, directory, extra_files=()):
        """一个媒体被删、一个兄弟媒体留下，目录里放满各式刮削文件。"""
        anchor_strm(directory)
        gone_key, gone = media_record(directory, "Film", "8001")
        kept_key, kept = media_record(directory, "Other", "8010", exists=True)
        store = FakeStore(records={gone_key: gone, kept_key: kept})
        listing = [
            cloud_file("8001", "Film.mkv"),
            cloud_file("8002", "Film.nfo"),
            cloud_file("8003", "Film-poster.jpg"),
            cloud_file("8004", "Film.zh-CN.srt"),
            cloud_file("8010", "Other.mkv"),
            cloud_file("8011", "Other.nfo"),
            *extra_files,
        ]
        client = FakeClient(listings={MEDIA_DIR_ID: listing})
        return store, client, gone_key, kept_key

    def test_scrape_artifacts_matched_by_anchor(self):
        """已删媒体的 nfo / 海报 / 字幕一起走，兄弟媒体的刮削文件不许动。"""
        with TemporaryDirectory() as directory:
            store, client, gone_key, kept_key = self._fixture(directory)

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(entry["cloud_deleted"], 1)
            self.assertEqual(entry["scrapes_deleted"], 3)
            self.assertEqual(sorted(client.deleted), ["8001", "8002", "8003", "8004"])
            self.assertNotIn(gone_key, store.strm_records)
            self.assertIn(kept_key, store.strm_records)

    def test_non_empty_directory_is_kept(self):
        """目录里还有兄弟媒体，目录本身不能删。"""
        with TemporaryDirectory() as directory:
            store, client, _gone_key, _kept_key = self._fixture(directory)

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(entry["cloud_dirs_deleted"], 0)
            self.assertNotIn(MEDIA_DIR_ID, client.deleted)

    def test_unknown_leftover_file_keeps_directory(self):
        """目录里剩下插件不认识的东西时，宁可留着目录。"""
        with TemporaryDirectory() as directory:
            anchor_strm(directory)
            gone_key, gone = media_record(directory, "Film", "8001")
            store = FakeStore(records={gone_key: gone})
            client = FakeClient(
                listings={
                    MEDIA_DIR_ID: [
                        cloud_file("8001", "Film.mkv"),
                        cloud_file("8099", "notes.txt"),
                    ]
                }
            )

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(entry["cloud_deleted"], 1)
            self.assertEqual(entry["cloud_dirs_deleted"], 0)
            self.assertNotIn("8099", client.deleted)

    def test_dir_list_failure_keeps_scrapes(self):
        """目录列不出来时只删媒体本体，刮削文件与目录全部保留。"""
        with TemporaryDirectory() as directory:
            anchor_strm(directory)
            gone_key, gone = media_record(directory, "Film", "8001")
            store = FakeStore(records={gone_key: gone})

            class BrokenListClient(FakeClient):
                def get_dir_list(self, cid):
                    raise RuntimeError("115 目录接口开小差了")

            client = BrokenListClient()

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(entry["cloud_deleted"], 1)
            self.assertEqual(entry["scrapes_deleted"], 0)
            self.assertEqual(entry["cloud_dirs_deleted"], 0)
            self.assertGreaterEqual(entry["errors"], 1)
            self.assertEqual(client.deleted, ["8001"])

    def test_protected_top_level_dir_never_deleted(self):
        """一级目录（/Movies）即使空了也不删 —— 那是整个媒体库的根。"""
        with TemporaryDirectory() as directory:
            anchor_strm(directory)
            gone_key, gone = media_record(directory, "Film", "8001", parent_id=TOP_DIR_ID)
            gone["cloud_path"] = "/Movies/Film.mkv"
            store = FakeStore(records={gone_key: gone})
            client = FakeClient(
                listings={TOP_DIR_ID: [{"fc": "1", "fid": "8001", "cid": TOP_DIR_ID, "fn": "Film.mkv"}]}
            )

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(entry["cloud_deleted"], 1)
            self.assertEqual(entry["cloud_dirs_deleted"], 0)
            self.assertNotIn(TOP_DIR_ID, client.deleted)

    def test_already_gone_file_only_drops_record(self):
        """云端本来就没有这个文件了：只清记录，不发删除请求。"""
        with TemporaryDirectory() as directory:
            anchor_strm(directory)
            gone_key, gone = media_record(directory, "Film", "8001")
            kept_key, kept = media_record(directory, "Other", "8010", exists=True)
            store = FakeStore(records={gone_key: gone, kept_key: kept})
            client = FakeClient(listings={MEDIA_DIR_ID: [cloud_file("8010", "Other.mkv")]})

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(entry["cloud_deleted"], 0)
            self.assertEqual(entry["already_gone"], 1)
            self.assertEqual(client.deleted, [])
            self.assertNotIn(gone_key, store.strm_records)

    def test_delete_failure_keeps_record_for_retry(self):
        """删除失败要留着记录等下一轮，不能当成已经删掉。"""
        with TemporaryDirectory() as directory:
            anchor_strm(directory)
            gone_key, gone = media_record(directory, "Film", "8001")
            store = FakeStore(records={gone_key: gone})

            class FailingClient(FakeClient):
                def delete_file(self, file_id, mode=""):
                    raise RuntimeError("115 删除接口失败")

            client = FailingClient(listings={MEDIA_DIR_ID: [cloud_file("8001", "Film.mkv")]})

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(entry["cloud_deleted"], 0)
            self.assertEqual(entry["errors"], 1)
            self.assertIn(gone_key, store.strm_records)


class IdentityTest(unittest.TestCase):
    """存量脏数据：v1.2.7 及更早把父目录 ID 当成了文件 ID。"""

    @staticmethod
    def _deleter(store, client):
        return ReverseDeleter(lambda: client, store)

    def test_dirty_file_id_equal_parent_id_uses_listing_id(self):
        """记录里 file_id == parent_id 时必须按目录列表取真实 fid，绝不能删掉整个目录。"""
        with TemporaryDirectory() as directory:
            anchor_strm(directory)
            gone_key, gone = media_record(directory, "Film", MEDIA_DIR_ID)
            self.assertEqual(gone["file_id"], gone["parent_id"])  # 复现旧版本写坏的记录
            kept_key, kept = media_record(directory, "Other", "8010", exists=True)
            store = FakeStore(records={gone_key: gone, kept_key: kept})
            client = FakeClient(
                listings={
                    MEDIA_DIR_ID: [
                        cloud_file("8001", "Film.mkv"),
                        cloud_file("8010", "Other.mkv"),
                    ]
                }
            )

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(client.deleted, ["8001"])
            self.assertNotIn(MEDIA_DIR_ID, client.deleted)
            self.assertEqual(entry["cloud_deleted"], 1)
            self.assertIn(kept_key, store.strm_records)

    def test_unresolvable_file_id_is_skipped_not_deleted(self):
        """拿不到可信 ID 时什么都不删，只累计一个「溯源缺失」。"""
        with TemporaryDirectory() as directory:
            anchor_strm(directory)
            gone_key, gone = media_record(directory, "Film", MEDIA_DIR_ID)
            store = FakeStore(records={gone_key: gone})

            class BrokenListClient(FakeClient):
                def get_dir_list(self, cid):
                    raise RuntimeError("115 目录接口开小差了")

            client = BrokenListClient()

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(entry["cloud_deleted"], 0)
            self.assertEqual(entry["unidentified"], 1)
            self.assertEqual(client.deleted, [])
            self.assertIn(gone_key, store.strm_records)

    def test_missing_parent_id_is_recovered_by_cloud_path(self):
        """老记录没有 parent_id 时按云端路径反查，补齐后照常成组删除。"""
        with TemporaryDirectory() as directory:
            anchor_strm(directory)
            gone_key, gone = media_record(directory, "Film", "")
            gone.pop("parent_id")
            store = FakeStore(records={gone_key: gone})

            class LookupClient(FakeClient):
                def get_item(self, path):
                    self.item_lookups.append(str(path))
                    return {"fileid": "8001", "parent_id": MEDIA_DIR_ID, "path": path}

            client = LookupClient(listings={MEDIA_DIR_ID: [cloud_file("8001", "Film.mkv")]})

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(client.item_lookups, ["/Movies/Film/Film.mkv"])
            self.assertEqual(entry["cloud_deleted"], 1)
            self.assertIn("8001", client.deleted)

    def test_empty_dir_cascade_climbs_until_protected(self):
        """空目录向上级联，到一级目录就停。"""
        with TemporaryDirectory() as directory:
            anchor_strm(directory)
            gone_key, gone = media_record(directory, "Film", "8001")
            gone["cloud_path"] = "/Movies/Sub/Film/Film.mkv"
            store = FakeStore(records={gone_key: gone})
            client = FakeClient(
                listings={
                    MEDIA_DIR_ID: [cloud_file("8001", "Film.mkv")],
                    "7200": [cloud_dir(MEDIA_DIR_ID, "Film", parent="7200")],
                    TOP_DIR_ID: [cloud_dir("7200", "Sub", parent=TOP_DIR_ID)],
                },
                parents={
                    MEDIA_DIR_ID: {"parent_id": "7200", "path": "/Movies/Sub/Film"},
                    "7200": {"parent_id": TOP_DIR_ID, "path": "/Movies/Sub"},
                    TOP_DIR_ID: {"parent_id": SOURCE_CID, "path": "/Movies"},
                },
            )

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(entry["cloud_deleted"], 1)
            self.assertEqual(entry["cloud_dirs_deleted"], 2)
            self.assertIn(MEDIA_DIR_ID, client.deleted)
            self.assertIn("7200", client.deleted)
            self.assertNotIn(TOP_DIR_ID, client.deleted)


class ConfirmQueueTest(unittest.TestCase):
    """按规模分级：小批量直接删，超阈值先进待确认队列。"""

    @staticmethod
    def _deleter(store, client):
        return ReverseDeleter(lambda: client, store)

    def _many(self, directory, count):
        anchor_strm(directory)
        records = {}
        listing = []
        for index in range(count):
            key, record = media_record(directory, f"Gone{index:02d}", f"81{index:02d}")
            records[key] = record
            listing.append(cloud_file(f"81{index:02d}", f"Gone{index:02d}.mkv"))
        keep_key, keep = media_record(directory, "Keep", "8199", exists=True)
        records[keep_key] = keep
        listing.append(cloud_file("8199", "Keep.mkv"))
        return records, listing

    def test_over_threshold_enqueues_pending_batch(self):
        with TemporaryDirectory() as directory:
            records, listing = self._many(directory, 4)
            store = FakeStore({"strm_delete_confirm_threshold": 3}, records=records)
            client = FakeClient(listings={MEDIA_DIR_ID: listing})

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(entry["action"], ACTION_PENDING)
            self.assertEqual(entry["pending"], 4)
            self.assertEqual(client.deleted, [])
            self.assertEqual(len(store.pending), 1)
            batch = next(iter(store.pending.values()))
            self.assertEqual(batch["mapping_id"], "movies")
            self.assertEqual(batch["count"], 4)
            self.assertEqual(len(batch["items"]), 4)
            # 记录一条都不许少
            self.assertEqual(len(store.strm_records), 5)

    def test_pending_batch_replaces_previous_for_same_mapping(self):
        """待删集合是当前快照，重算比追加更准；批次 ID 与首次发现时间保留。"""
        with TemporaryDirectory() as directory:
            records, listing = self._many(directory, 4)
            store = FakeStore({"strm_delete_confirm_threshold": 3}, records=records)
            client = FakeClient(listings={MEDIA_DIR_ID: listing})
            deleter = self._deleter(store, client)

            deleter.sweep(mapping_for(directory))
            first = next(iter(store.pending.values()))
            deleter.sweep(mapping_for(directory))

            self.assertEqual(len(store.pending), 1)
            second = next(iter(store.pending.values()))
            self.assertEqual(second["id"], first["id"])
            self.assertEqual(second["created_at"], first["created_at"])

    def test_threshold_zero_never_holds_for_confirmation(self):
        with TemporaryDirectory() as directory:
            records, listing = self._many(directory, 4)
            store = FakeStore({"strm_delete_confirm_threshold": 0}, records=records)
            client = FakeClient(listings={MEDIA_DIR_ID: listing})

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(entry["action"], ACTION_DELETE)
            self.assertEqual(entry["cloud_deleted"], 4)
            self.assertEqual(store.pending, {})

    def test_bypass_confirm_executes_over_threshold(self):
        """人工确认后只跳过规模闸门，其余护栏照跑。"""
        with TemporaryDirectory() as directory:
            records, listing = self._many(directory, 4)
            store = FakeStore({"strm_delete_confirm_threshold": 3}, records=records)
            client = FakeClient(listings={MEDIA_DIR_ID: listing})

            entry = self._deleter(store, client).sweep(
                mapping_for(directory), bypass_confirm=True
            )

            self.assertEqual(entry["action"], ACTION_DELETE)
            self.assertEqual(entry["cloud_deleted"], 4)

    def test_confirm_rechecks_local_existence(self):
        """确认之前用户把文件放回来了，就一个都不该删。"""
        with TemporaryDirectory() as directory:
            records, listing = self._many(directory, 4)
            for record in records.values():
                output = Path(record["path"])
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text("restored\n", encoding="utf-8")
            store = FakeStore({"strm_delete_confirm_threshold": 3}, records=records)
            client = FakeClient(listings={MEDIA_DIR_ID: listing})

            entry = self._deleter(store, client).sweep(
                mapping_for(directory), bypass_confirm=True
            )

            self.assertEqual(entry["action"], ACTION_SKIPPED)
            self.assertEqual(client.deleted, [])
            self.assertEqual(len(store.strm_records), 5)

    def test_small_delete_never_touches_pending_batches(self):
        """小批次的直接删除既不作废别人的批次，也不许碰批次里的文件。"""
        with TemporaryDirectory() as directory:
            records, listing = self._many(directory, 3)
            held_key = "movies:Film/Gone02.mkv"
            held = records[held_key]
            store = FakeStore({"strm_delete_confirm_threshold": 5}, records=records)
            store.pending = {
                "deadbeef": {
                    "id": "deadbeef", "mapping_id": "movies", "count": 1,
                    "created_at": "2026-09-01T00:00:00",
                    # 队列里存的是 decide() 归一化后的路径（与生产一致）
                    "items": [{"record_key": held_key,
                               "path": str(Path(held["path"]).resolve()),
                               "cloud_path": held["cloud_path"], "file_id": held["file_id"],
                               "parent_id": held["parent_id"], "name": held["name"]}],
                }
            }
            client = FakeClient(listings={MEDIA_DIR_ID: listing})

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(entry["action"], ACTION_DELETE)
            # 只删了不在队列里的那两个
            self.assertEqual(entry["cloud_deleted"], 2)
            self.assertEqual(entry["queued"], 1)
            self.assertNotIn(held["file_id"], client.deleted)
            self.assertEqual(sorted(client.deleted), ["8100", "8101"])
            # 批次原样留着，队列里的记录也不许被清
            self.assertIn("deadbeef", store.pending)
            self.assertEqual(store.pending["deadbeef"]["count"], 1)
            self.assertIn(held_key, store.strm_records)

    def test_switch_off_does_nothing(self):
        with TemporaryDirectory() as directory:
            records, listing = self._many(directory, 2)
            store = FakeStore({"strm_delete_cloud_on_missing": False}, records=records)
            client = FakeClient(listings={MEDIA_DIR_ID: listing})

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(entry["action"], ACTION_SKIPPED)
            self.assertEqual(client.deleted, [])
            self.assertEqual(client.list_calls, [])


class DurabilityTest(unittest.TestCase):
    """删除已经发生就必须落盘，哪怕这一轮被异常打断。"""

    def test_records_persist_when_execute_is_interrupted(self):
        with TemporaryDirectory() as directory:
            anchor_strm(directory)
            first_key, first = media_record(directory, "AAA", "8001")
            second_key, second = media_record(directory, "BBB", "8002", parent_id="7300")
            # 放在另一个云端目录下，才不会被 /Movies/Film 的整目录删除顺带清掉
            second["cloud_path"] = "/Movies/Other/BBB.mkv"
            store = FakeStore(records={first_key: first, second_key: second})

            class HalfBrokenClient(FakeClient):
                def get_dir_list(self, cid):
                    if str(cid) == "7300":
                        raise KeyboardInterrupt("模拟任务被打断")
                    return super().get_dir_list(cid)

            client = HalfBrokenClient(
                listings={MEDIA_DIR_ID: [cloud_file("8001", "AAA.mkv")]}
            )
            deleter = ReverseDeleter(lambda: client, store)

            with self.assertRaises(KeyboardInterrupt):
                deleter.sweep(mapping_for(directory))

            # 第一组已经删掉了，记录不能留在盘上
            self.assertIn("8001", client.deleted)
            self.assertNotIn(first_key, store.strm_records)
            self.assertGreaterEqual(store.saved_records, 1)
            # 第二组没动过，记录必须保留待下一轮
            self.assertIn(second_key, store.strm_records)

    def test_directory_without_known_cloud_path_is_kept(self):
        """定位不到云端路径就判断不了层级，宁可留着目录。"""
        with TemporaryDirectory() as directory:
            anchor_strm(directory)
            key, record = media_record(directory, "Film", "8001")
            record.pop("cloud_path")
            store = FakeStore(records={key: record})
            client = FakeClient(listings={MEDIA_DIR_ID: [cloud_file("8001", "Film.mkv")]})

            entry = ReverseDeleter(lambda: client, store).sweep(mapping_for(directory))

            self.assertEqual(entry["cloud_deleted"], 1)
            self.assertEqual(entry["cloud_dirs_deleted"], 0)
            self.assertNotIn(MEDIA_DIR_ID, client.deleted)


class AsyncDirDeleteTest(unittest.TestCase):
    """115 的目录删除是异步的：刚删完子目录，父目录要重试才删得掉。"""

    @staticmethod
    def _deleter(store, client):
        # 注入空 sleeper，单测不真等退避
        return ReverseDeleter(lambda: client, store, sleeper=lambda _s: None)

    def _one_missing(self, directory):
        anchor_strm(directory)
        key, record = media_record(directory, "Film", "8001")
        record["cloud_path"] = "/Movies/Sub/Film/Film.mkv"
        return {key: record}

    def test_directory_delete_retries_while_115_is_still_busy(self):
        with TemporaryDirectory() as directory:
            store = FakeStore(records=self._one_missing(directory))

            class BusyOnceClient(FakeClient):
                def __init__(self, **kwargs):
                    super().__init__(**kwargs)
                    self.dir_attempts = 0

                def delete_file(self, file_id, mode=""):
                    ids = [str(file_id)] if isinstance(file_id, (str, int)) else [str(v) for v in file_id]
                    if ids == [MEDIA_DIR_ID]:
                        self.dir_attempts += 1
                        if self.dir_attempts == 1:
                            raise RuntimeError("删除[Film]操作尚未执行完成，请稍后再试！")
                    return super().delete_file(file_id, mode)

            client = BusyOnceClient(
                listings={MEDIA_DIR_ID: [cloud_file("8001", "Film.mkv")]},
                parents={MEDIA_DIR_ID: {"parent_id": TOP_DIR_ID, "path": "/Movies/Sub/Film"}},
            )

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            # 第一次被「尚未执行完成」挡下，重试一次就删掉了
            self.assertEqual(client.dir_attempts, 2)
            self.assertGreaterEqual(entry["cloud_dirs_deleted"], 1)
            self.assertEqual(entry["errors"], 0)
            self.assertIn(MEDIA_DIR_ID, client.deleted)

    def test_delete_of_already_missing_target_is_not_an_error(self):
        """上一轮删过、或用户自己删了：115 回「不存在或已删除」，不该算失败。"""
        with TemporaryDirectory() as directory:
            store = FakeStore(records=self._one_missing(directory))

            class GoneClient(FakeClient):
                def delete_file(self, file_id, mode=""):
                    raise RuntimeError("文件（夹）不存在或已删除。")

            client = GoneClient(listings={MEDIA_DIR_ID: [cloud_file("8001", "Film.mkv")]})

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(entry["errors"], 0)
            self.assertEqual(entry["cloud_deleted"], 1)

    def test_persistent_dir_failure_is_reported_after_retries(self):
        with TemporaryDirectory() as directory:
            store = FakeStore(records=self._one_missing(directory))

            class AlwaysBusyClient(FakeClient):
                def __init__(self, **kwargs):
                    super().__init__(**kwargs)
                    self.dir_attempts = 0

                def delete_file(self, file_id, mode=""):
                    ids = [str(file_id)] if isinstance(file_id, (str, int)) else [str(v) for v in file_id]
                    if ids == [MEDIA_DIR_ID]:
                        self.dir_attempts += 1
                        raise RuntimeError("删除[Film]操作尚未执行完成，请稍后再试！")
                    return super().delete_file(file_id, mode)

            client = AlwaysBusyClient(listings={MEDIA_DIR_ID: [cloud_file("8001", "Film.mkv")]})

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(client.dir_attempts, 4)
            self.assertEqual(entry["cloud_dirs_deleted"], 0)
            self.assertEqual(entry["errors"], 1)


class DeleteBlacklistTest(unittest.TestCase):
    """删掉的东西要记进共享黑名单：正向同步不重建、生活监控不刷告警。"""

    def test_media_scrape_and_dir_ids_are_all_remembered(self):
        recent = TtlCache(600.0)
        with TemporaryDirectory() as directory:
            anchor_strm(directory)
            key, record = media_record(directory, "Film", "8001")
            record["pickcode"] = "pick-film"
            store = FakeStore(records={key: record})
            client = FakeClient(
                listings={
                    MEDIA_DIR_ID: [
                        cloud_file("8001", "Film.mkv"),
                        cloud_file("8002", "Film.nfo"),
                    ]
                }
            )

            entry = ReverseDeleter(lambda: client, store, recent).sweep(mapping_for(directory))

            self.assertEqual(entry["cloud_deleted"], 1)
            self.assertEqual(entry["scrapes_deleted"], 1)
            self.assertEqual(entry["cloud_dirs_deleted"], 1)
            # 媒体本体：pickcode（给正向同步）+ 文件 ID（给生活监控）
            self.assertTrue(recent.get("pick-film"))
            self.assertTrue(recent.get("id:8001"))
            # 刮削文件与被删的目录同样要记
            self.assertTrue(recent.get("id:8002"))
            self.assertTrue(recent.get(f"id:{MEDIA_DIR_ID}"))

    def test_without_cache_sweep_still_works(self):
        with TemporaryDirectory() as directory:
            anchor_strm(directory)
            key, record = media_record(directory, "Film", "8001")
            store = FakeStore(records={key: record})
            client = FakeClient(listings={MEDIA_DIR_ID: [cloud_file("8001", "Film.mkv")]})

            entry = ReverseDeleter(lambda: client, store).sweep(mapping_for(directory))

            self.assertEqual(entry["cloud_deleted"], 1)


class StaleListingCascadeTest(unittest.TestCase):
    """115 的目录删除是异步的：刚删掉的子目录还会在父目录列表里挂一会儿。

    只看「父目录列表是否为空」的实现会在每一级都判成非空，级联等于白做 —— 真机上就是
    这样把两个已经空掉的剧集目录留在了 115 上。
    """

    @staticmethod
    def _deleter(store, client):
        return ReverseDeleter(lambda: client, store, sleeper=lambda _s: None)

    def test_empty_ancestors_are_deleted_despite_stale_listing(self):
        with TemporaryDirectory() as directory:
            anchor_strm(directory)
            key, record = media_record(directory, "Film", "8001")
            record["cloud_path"] = "/Movies/Show/Season 1/Film.mkv"
            store = FakeStore(records={key: record})
            client = FakeClient(
                stale_dir_delete=True,
                listings={
                    # Season 1：只有一个媒体文件
                    MEDIA_DIR_ID: [cloud_file("8001", "Film.mkv")],
                    # Show：只有 Season 1；删掉后 115 仍会把它列出来一会儿
                    "7200": [cloud_dir(MEDIA_DIR_ID, "Season 1", parent="7200")],
                    # /Movies：除了 Show 还有别的剧，级联到这里必须停
                    TOP_DIR_ID: [
                        cloud_dir("7200", "Show", parent=TOP_DIR_ID),
                        cloud_dir("7300", "Other Show", parent=TOP_DIR_ID),
                    ],
                },
                parents={
                    MEDIA_DIR_ID: {"parent_id": "7200", "path": "/Movies/Show/Season 1"},
                    "7200": {"parent_id": TOP_DIR_ID, "path": "/Movies/Show"},
                    TOP_DIR_ID: {"parent_id": SOURCE_CID, "path": "/Movies"},
                },
            )

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(entry["cloud_deleted"], 1)
            # Season 1 与 Show 都要删掉
            self.assertEqual(entry["cloud_dirs_deleted"], 2)
            self.assertIn(MEDIA_DIR_ID, client.deleted)
            self.assertIn("7200", client.deleted)
            # /Movies 还有别的剧，且是一级目录，绝不能删
            self.assertNotIn(TOP_DIR_ID, client.deleted)
            self.assertEqual(entry["errors"], 0)

    def test_ancestor_with_real_sibling_content_is_kept(self):
        """父目录里除了刚删掉的子目录还有别的东西，就不能删。"""
        with TemporaryDirectory() as directory:
            anchor_strm(directory)
            key, record = media_record(directory, "Film", "8001")
            record["cloud_path"] = "/Movies/Show/Season 1/Film.mkv"
            store = FakeStore(records={key: record})
            client = FakeClient(
                stale_dir_delete=True,
                listings={
                    MEDIA_DIR_ID: [cloud_file("8001", "Film.mkv")],
                    "7200": [
                        cloud_dir(MEDIA_DIR_ID, "Season 1", parent="7200"),
                        cloud_file("8500", "poster.jpg"),
                    ],
                },
                parents={
                    MEDIA_DIR_ID: {"parent_id": "7200", "path": "/Movies/Show/Season 1"},
                    "7200": {"parent_id": TOP_DIR_ID, "path": "/Movies/Show"},
                },
            )

            entry = self._deleter(store, client).sweep(mapping_for(directory))

            self.assertEqual(entry["cloud_dirs_deleted"], 1)
            self.assertNotIn("7200", client.deleted)
            self.assertNotIn("8500", client.deleted)


class IndependentBatchTest(unittest.TestCase):
    """B 方案：每次超阈值的新发现独立成一张批次，互不覆盖。"""

    @staticmethod
    def _deleter(store, client):
        return ReverseDeleter(lambda: client, store, sleeper=lambda _s: None)

    def _fixture(self, directory, missing, present=6):
        """造 missing 个缺失 + present 个还在的，缺失比例压在熔断线以下。"""
        anchor_strm(directory)
        records, listing = {}, []
        for index in range(missing):
            key, record = media_record(directory, f"Gone{index:02d}", f"81{index:02d}")
            records[key] = record
            listing.append(cloud_file(f"81{index:02d}", f"Gone{index:02d}.mkv"))
        for index in range(present):
            key, record = media_record(directory, f"Keep{index}", f"82{index}", exists=True)
            records[key] = record
            listing.append(cloud_file(f"82{index}", f"Keep{index}.mkv"))
        return records, listing

    def _restore(self, directory, stem):
        out = Path(directory) / "Film" / f"{stem}.strm"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("restored\n", encoding="utf-8")

    def _drop_local(self, directory, stem):
        (Path(directory) / "Film" / f"{stem}.strm").unlink(missing_ok=True)

    def test_second_discovery_creates_a_separate_batch(self):
        with TemporaryDirectory() as directory:
            records, listing = self._fixture(directory, 4)
            store = FakeStore({"strm_delete_confirm_threshold": 3}, records=records)
            client = FakeClient(listings={MEDIA_DIR_ID: listing})
            deleter = self._deleter(store, client)
            mapping = mapping_for(directory)

            first = deleter.sweep(mapping)
            self.assertEqual(first["action"], ACTION_PENDING)
            self.assertEqual(first["pending"], 4)
            self.assertEqual(len(store.pending), 1)

            # 又删了两个本地 STRM：原来那 4 个还在等确认，这 2 个要单独成一张
            for index in (0, 1):
                key, record = media_record(directory, f"New{index}", f"83{index}")
                store.strm_records[key] = record
                client.listings[MEDIA_DIR_ID].append(cloud_file(f"83{index}", f"New{index}.mkv"))

            second = deleter.sweep(mapping)

            self.assertEqual(second["action"], ACTION_PENDING)
            self.assertEqual(second["pending"], 2)      # 只装新增的
            self.assertEqual(second["queued"], 4)       # 老的 4 个仍在队列里
            self.assertEqual(len(store.pending), 2)
            counts = sorted(b["count"] for b in store.pending.values())
            self.assertEqual(counts, [2, 4])
            self.assertEqual(client.deleted, [])
            # 两张卡片覆盖的路径不重叠
            covered = [
                item["path"] for b in store.pending.values() for item in b["items"]
            ]
            self.assertEqual(len(covered), len(set(covered)))

    def test_same_discovery_twice_does_not_pile_up(self):
        """同一批文件反复被巡检发现，不该不停生成内容重复的卡片。"""
        with TemporaryDirectory() as directory:
            records, listing = self._fixture(directory, 4)
            store = FakeStore({"strm_delete_confirm_threshold": 3}, records=records)
            client = FakeClient(listings={MEDIA_DIR_ID: listing})
            deleter = self._deleter(store, client)
            mapping = mapping_for(directory)

            deleter.sweep(mapping)
            batch_id = next(iter(store.pending))
            again = deleter.sweep(mapping)

            self.assertEqual(again["action"], ACTION_SKIPPED)
            self.assertEqual(again["queued"], 4)
            self.assertIn("等人工处理", again["reason"])
            self.assertEqual(list(store.pending), [batch_id])
            self.assertEqual(client.deleted, [])

    def test_restored_files_are_pruned_from_the_batch(self):
        """用户把文件放回去了，队列里对应的条目要自动剔掉。"""
        with TemporaryDirectory() as directory:
            records, listing = self._fixture(directory, 4)
            store = FakeStore({"strm_delete_confirm_threshold": 3}, records=records)
            client = FakeClient(listings={MEDIA_DIR_ID: listing})
            deleter = self._deleter(store, client)
            mapping = mapping_for(directory)

            deleter.sweep(mapping)
            self.assertEqual(next(iter(store.pending.values()))["count"], 4)

            for stem in ("Gone00", "Gone01", "Gone02"):
                self._restore(directory, stem)
            deleter.sweep(mapping)

            batch = next(iter(store.pending.values()))
            self.assertEqual(batch["count"], 1)
            self.assertEqual(client.deleted, [])

    def test_batch_is_revoked_when_every_item_is_restored(self):
        with TemporaryDirectory() as directory:
            records, listing = self._fixture(directory, 4)
            store = FakeStore({"strm_delete_confirm_threshold": 3}, records=records)
            client = FakeClient(listings={MEDIA_DIR_ID: listing})
            deleter = self._deleter(store, client)
            mapping = mapping_for(directory)

            deleter.sweep(mapping)
            for index in range(4):
                self._restore(directory, f"Gone{index:02d}")
            deleter.sweep(mapping)

            self.assertEqual(store.pending, {})
            self.assertEqual(client.deleted, [])

    def test_batches_merge_into_oldest_once_capped(self):
        """批次攒到上限还没人处理，新增的并进最旧那张，不丢也不无限涨。"""
        with TemporaryDirectory() as directory:
            records, listing = self._fixture(directory, 2, present=30)
            store = FakeStore({"strm_delete_confirm_threshold": 1}, records=records)
            client = FakeClient(listings={MEDIA_DIR_ID: listing})
            deleter = self._deleter(store, client)
            mapping = mapping_for(directory)

            deleter.sweep(mapping)                      # 第 1 张：2 个
            oldest_id = next(iter(store.pending))
            oldest_created = store.pending[oldest_id]["created_at"]

            # 再制造 MAX_BATCHES 轮新增，最后一轮必须并入最旧那张
            for round_index in range(STRM_DELETE_PENDING_MAX_BATCHES):
                key, record = media_record(directory, f"Extra{round_index:02d}", f"84{round_index:02d}")
                store.strm_records[key] = record
                client.listings[MEDIA_DIR_ID].append(
                    cloud_file(f"84{round_index:02d}", f"Extra{round_index:02d}.mkv")
                )
                deleter.sweep(mapping)

            self.assertEqual(len(store.pending), STRM_DELETE_PENDING_MAX_BATCHES)
            merged = store.pending[oldest_id]
            self.assertEqual(merged["created_at"], oldest_created)
            self.assertGreater(merged["count"], 2)
            # 一个文件都没丢：队列覆盖的路径数 = 全部缺失数
            covered = {item["path"] for b in store.pending.values() for item in b["items"]}
            self.assertEqual(len(covered), 2 + STRM_DELETE_PENDING_MAX_BATCHES)
            self.assertEqual(client.deleted, [])
