"""媒体清单：路径解析、按片身份归组、三处路径与做种判定。

这些是纯函数，所以这里不碰 115、不碰下载器、不碰数据库 —— 传进去的都是字典和临时目录。
清单是现在唯一的主界面，它把 990 条逐文件记录聚合成几百行，聚错一行用户就会照着删错东西，
所以判定口径必须被钉住。
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.plugins.p115liteassistant.media_ledger import (
    build_ledger,
    identity,
    locate,
    parse_episode,
    seed_count,
    season_of_dir,
    split_title,
)


class ParseTest(unittest.TestCase):
    def test_episode_writings(self):
        """四种集号写法都要认，电影必须解析不出来 —— 解析出来就会被当成剧集。"""
        self.assertEqual(parse_episode("某剧 - S01E07 - 标题.strm"), (1, 7))
        self.assertEqual(parse_episode("某剧.S02E13.2160p.strm"), (2, 13))
        self.assertEqual(parse_episode("某剧 E09.strm"), (1, 9))
        self.assertEqual(parse_episode("某剧 第 12 集.strm"), (1, 12))
        self.assertIsNone(parse_episode("沙丘 第二部 (2024) - 2160p.strm"))

    def test_season_dir(self):
        for name, want in (("Season 04", 4), ("S3", 3), ("第 2 季", 2), ("电影", None)):
            self.assertEqual(season_of_dir(name), want, name)

    def test_title_year(self):
        self.assertEqual(split_title("沙丘 第二部 (2024)"), ("沙丘 第二部", "2024"))
        self.assertEqual(split_title("珠光宝气（2008）"), ("珠光宝气", "2008"))
        # 没有年份就整段当标题，不猜
        self.assertEqual(split_title("手工放的"), ("手工放的", ""))

    def test_locate_movie_and_season(self):
        movie = locate("/strm/电影/沙丘 第二部 (2024)/沙丘 第二部 (2024) - 2160p.strm")
        self.assertEqual((movie["kind"], movie["title"], movie["year"]), ("movie", "沙丘 第二部", "2024"))

        # 季目录命中时标题取上一层，而不是把「Season 04」当片名
        episode = locate("/strm/剧集/陀枪师姐 (2004)/Season 04/陀枪师姐 - S04E19.strm")
        self.assertEqual(episode["kind"], "tv")
        self.assertEqual(episode["title"], "陀枪师姐")
        self.assertEqual(episode["season"], 4)
        self.assertEqual(episode["episode"], 19)

    def test_locate_prefers_dir_season(self):
        """目录写的季号优先于文件名里的 —— 目录是刮削器排的，比文件名可靠。"""
        spot = locate("/strm/剧集/某剧 (2024)/Season 02/某剧 - S09E03.strm")
        self.assertEqual(spot["season"], 2)

    def test_identity_ignores_path(self):
        """同一部片在网盘侧和本地侧路径不同，身份必须相同，否则合不成一行。"""
        left = locate("/strm/电影/沙丘 第二部 (2024)/a.strm")
        right = locate("/watch/inbox/沙丘 第二部 (2024)/a.mkv")
        self.assertEqual(identity(left), identity(right))


class SeedCountTest(unittest.TestCase):
    def test_matches_file_and_ancestor(self):
        """种子可能就是这个文件，也可能是它上面某一层目录（整季一个种子）。"""
        content = {"/media/剧集/某剧/S01", "/media/电影/某片.mkv"}
        self.assertEqual(seed_count(["/media/电影/某片.mkv"], content), 1)
        self.assertEqual(seed_count(["/media/剧集/某剧/S01/e01.mkv"], content), 1)
        self.assertEqual(seed_count(["/media/剧集/别的剧/e01.mkv"], content), 0)

    def test_empty_content_never_matches(self):
        """拿不到种子列表时一个都不能算命中 —— 那会放开本该拦住的删除。"""
        self.assertEqual(seed_count(["/media/电影/某片.mkv"], set()), 0)


class BuildLedgerTest(unittest.TestCase):
    """三个来源拼一本总账：同一部片必须合成一行，入库状态按「网盘上有没有」推。"""

    def test_merges_cloud_and_local_into_one_row(self):
        with TemporaryDirectory() as raw:
            source = Path(raw) / "inbox"
            (source / "沙丘 第二部 (2024)").mkdir(parents=True)
            uploaded = source / "沙丘 第二部 (2024)" / "沙丘 第二部 (2024) - 2160p.mkv"
            uploaded.write_bytes(b"x" * 10)
            (source / "某剧 (2024)" / "Season 01").mkdir(parents=True)
            pending = source / "某剧 (2024)" / "Season 01" / "某剧 - S01E01.mkv"
            pending.write_bytes(b"y" * 20)

            rows = build_ledger(
                records={
                    "m1:a": {
                        "path": "/strm/电影/沙丘 第二部 (2024)/沙丘 第二部 (2024) - 2160p.strm",
                        "cloud_path": "/影视/电影/沙丘 第二部 (2024)/沙丘 第二部 (2024) - 2160p.mkv",
                        "file_id": "9001",
                        "pickcode": "pc1",
                        "size": 100,
                        "mtime": 1_600_000_000,
                    },
                    # 刮削记录不该算进「几个文件」
                    "m1:sidecar:b": {"path": "/strm/电影/沙丘 第二部 (2024)/x.nfo", "size": 1},
                },
                strm_mappings=[{"id": "m1", "target_dir": "/strm"}],
                upload_mappings=[{"id": "u1", "source": str(source), "target": "/影视"}],
                upload_records={str(uploaded): {"uploaded_at": "2026-09-01 00:00:00"}},
                pending_paths=set(),
                media_extensions=[".mkv"],
            )

        by_title = {row["title"]: row for row in rows}
        self.assertEqual(set(by_title), {"沙丘 第二部", "某剧"})

        # 网盘侧与本地侧同一部片合成一行：三处路径都挂在这一行上
        dune = by_title["沙丘 第二部"]
        self.assertEqual(dune["in_library"], "yes")
        self.assertEqual(len(dune["strm_paths"]), 1)
        self.assertEqual(len(dune["source_paths"]), 1)
        self.assertEqual(dune["file_ids"], ["9001"])
        # 已经传上去、本地源文件还占着地方
        self.assertIn("source_left", dune["flags"])
        self.assertEqual(dune["source_uploaded"], 1)
        # 源文件字节要单独记：清单顶上「源文件可回收」算的就是这个，
        # 而 size 对已入库的行是网盘体积，两者不能混
        self.assertEqual(dune["source_size"], 10)
        self.assertEqual(dune["size"], 100)
        # 入库时间取这一部最早那个文件的 mtime —— 清单默认按它升序排
        self.assertEqual(dune["library_at"], 1_600_000_000)

        # 只在本地、还没传上去 → 未入库，也就没有入库时间
        show = by_title["某剧"]
        self.assertEqual(show["library_at"], 0)
        self.assertEqual(show["in_library"], "no")
        self.assertEqual(show["season"], 1)
        self.assertEqual(show["source_pending"], 1)
        self.assertEqual(show["upload_target"], "/影视/某剧 (2024)/Season 01")

    def test_upload_conflict_flags_the_row(self):
        """上传身份冲突要长在它所属的那一行上：标记进 flags，明细进 conflicts。"""
        with TemporaryDirectory() as raw:
            source = Path(raw) / "inbox"
            (source / "沙丘 第二部 (2024)").mkdir(parents=True)
            conflicted = source / "沙丘 第二部 (2024)" / "沙丘 第二部 (2024) - 2160p.mkv"
            conflicted.write_bytes(b"x" * 10)

            rows = build_ledger(
                records={},
                strm_mappings=[],
                upload_mappings=[{"id": "u1", "source": str(source), "target": "/影视"}],
                upload_records={},
                pending_paths=set(),
                media_extensions=[".mkv"],
                upload_conflicts={
                    str(conflicted): {
                        "path": str(conflicted),
                        "target": "/影视/沙丘 第二部 (2024)/沙丘 第二部 (2024) - 2160p.mkv",
                        "reason": "上传记录对不上网盘文件",
                        "first_seen": "2026-09-07 06:00:00",
                    }
                },
            )

        self.assertEqual(len(rows), 1)
        dune = rows[0]
        self.assertIn("record_conflict", dune["flags"])
        self.assertEqual(len(dune["conflicts"]), 1)
        self.assertEqual(
            dune["conflicts"][0]["reason"], "上传记录对不上网盘文件"
        )
        self.assertEqual(dune["conflicts"][0]["target"], "/影视/沙丘 第二部 (2024)/沙丘 第二部 (2024) - 2160p.mkv")

    def test_keeps_all_strm_mapping_ids_for_same_media_row(self):
        rows = build_ledger(
            records={
                "m1:a": {
                    "path": "/strm-a/剧集/某剧 (2024)/Season 01/某剧 - S01E01.strm",
                    "file_id": "1",
                },
                "m2:b": {
                    "path": "/strm-b/剧集/某剧 (2024)/Season 01/某剧 - S01E03.strm",
                    "mapping_id": "m2",
                    "file_id": "2",
                },
            },
            strm_mappings=[
                {"id": "m1", "target_dir": "/strm-a"},
                {"id": "m2", "target_dir": "/strm-b"},
            ],
            upload_mappings=[],
            upload_records={},
            pending_paths=set(),
            media_extensions=[".mkv"],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["channel_ids"], ["m1", "m2"])
        self.assertEqual(rows[0]["channel_id"], "m1")
        self.assertEqual(rows[0]["missing"], [2])

    def test_legacy_once_mapping_id_with_colon_is_preserved(self):
        rows = build_ledger(
            records={
                "once:99:a": {
                    "path": "/strm/剧集/某剧 (2024)/Season 01/某剧 - S01E01.strm",
                    "file_id": "1",
                }
            },
            strm_mappings=[],
            upload_mappings=[],
            upload_records={},
            pending_paths=set(),
            media_extensions=[".mkv"],
        )

        self.assertEqual(rows[0]["channel_id"], "once:99")
        self.assertEqual(rows[0]["channel_ids"], ["once:99"])

    def test_missing_strm_file_is_counted(self):
        rows = build_ledger(
            records={"m1:a": {"path": "/strm/电影/不存在 (2024)/a.strm", "file_id": "1", "size": 1}},
            strm_mappings=[{"id": "m1", "target_dir": "/strm"}],
            upload_mappings=[],
            upload_records={},
            pending_paths=set(),
            media_extensions=[".mkv"],
        )
        self.assertEqual(rows[0]["strm_gone"], 1)
        self.assertIn("strm_gone", rows[0]["flags"])

    def test_library_at_takes_earliest(self):
        """一季陆续入库时，入库时间要取最早那一集 —— 回答的是「在库里待了多久」。"""
        rows = build_ledger(
            records={
                "m1:a": {"path": "/strm/剧集/某剧 (2024)/Season 01/某剧 - S01E01.strm", "mtime": 300, "file_id": "1"},
                "m1:b": {"path": "/strm/剧集/某剧 (2024)/Season 01/某剧 - S01E02.strm", "mtime": 100, "file_id": "2"},
                "m1:c": {"path": "/strm/剧集/某剧 (2024)/Season 01/某剧 - S01E03.strm", "mtime": 200, "file_id": "3"},
            },
            strm_mappings=[{"id": "m1", "target_dir": "/strm"}],
            upload_mappings=[],
            upload_records={},
            pending_paths=set(),
            media_extensions=[".mkv"],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["library_at"], 100)

    def test_library_at_falls_back_to_upload_record_when_strm_mtime_missing(self):
        """STRM 记录缺 mtime（旧版本写入/增量跳过），入库时间回退到上传记录的上传时刻。"""
        with TemporaryDirectory() as raw:
            source = Path(raw) / "inbox"
            (source / "沙丘 第二部 (2024)").mkdir(parents=True)
            uploaded = source / "沙丘 第二部 (2024)" / "沙丘 第二部 (2024) - 2160p.mkv"
            uploaded.write_bytes(b"x" * 10)

            rows = build_ledger(
                records={
                    # STRM 记录在网盘上（有 pickcode/file_id），但没有 mtime —— 旧数据就是这样的
                    "m1:a": {
                        "path": "/strm/电影/沙丘 第二部 (2024)/沙丘 第二部 (2024) - 2160p.strm",
                        "cloud_path": "/影视/电影/沙丘 第二部 (2024)/沙丘 第二部 (2024) - 2160p.mkv",
                        "file_id": "9001",
                        "pickcode": "pc1",
                        "size": 100,
                    },
                },
                strm_mappings=[{"id": "m1", "target_dir": "/strm"}],
                upload_mappings=[{"id": "u1", "source": str(source), "target": "/影视"}],
                # 上传记录里记录着真正落到网盘的时刻（ISO 字符串）
                upload_records={str(uploaded): {"uploaded_at": "2026-09-01T08:00:00"}},
                pending_paths=set(),
                media_extensions=[".mkv"],
            )

        self.assertEqual(len(rows), 1)
        dune = rows[0]
        self.assertEqual(dune["in_library"], "yes")
        self.assertGreater(dune["library_at"], 0)
        # 2026-09-01T08:00:00 本地时区 → epoch 秒
        from datetime import datetime
        self.assertEqual(
            dune["library_at"],
            int(datetime(2026, 9, 1, 8, 0, 0).timestamp()),
        )

    def test_library_at_stays_zero_without_any_source(self):
        """没有任何 STRM mtime、也没有上传记录时，library_at 保持 0（前端显示还没入库）。"""
        with TemporaryDirectory() as raw:
            source = Path(raw) / "inbox"
            (source / "某剧 (2024)" / "Season 01").mkdir(parents=True)
            pending = source / "某剧 (2024)" / "Season 01" / "某剧 - S01E01.mkv"
            pending.write_bytes(b"y" * 20)

            rows = build_ledger(
                records={},
                strm_mappings=[],
                upload_mappings=[{"id": "u1", "source": str(source), "target": "/影视"}],
                upload_records={},
                pending_paths=set(),
                media_extensions=[".mkv"],
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["in_library"], "no")
        self.assertEqual(rows[0]["library_at"], 0)

    def test_library_at_falls_back_to_upload_record_even_if_local_source_gone(self):
        """本地源文件已删、只剩上传记录时，也要能从上传记录反查入库时间。"""
        source_path = "/media/inbox/沙丘 第二部 (2024)/沙丘 第二部 (2024) - 2160p.mkv"

        rows = build_ledger(
            records={
                # STRM 记录在网盘上、缺 mtime（旧数据）；本地源目录可能已经不存在
                "m1:a": {
                    "path": "/strm/电影/沙丘 第二部 (2024)/沙丘 第二部 (2024) - 2160p.strm",
                    "cloud_path": "/影视/电影/沙丘 第二部 (2024)/沙丘 第二部 (2024) - 2160p.mkv",
                    "file_id": "9001",
                    "pickcode": "pc1",
                    "size": 100,
                },
            },
            strm_mappings=[{"id": "m1", "target_dir": "/strm"}],
            upload_mappings=[{"id": "u1", "source": "/media/inbox", "target": "/影视"}],
            # 本地源文件不存在，也能靠上传记录补全
            upload_records={source_path: {"uploaded_at": "2026-09-01T08:00:00"}},
            pending_paths=set(),
            media_extensions=[".mkv"],
        )

        self.assertEqual(len(rows), 1)
        dune = rows[0]
        self.assertEqual(dune["in_library"], "yes")
        self.assertGreater(dune["library_at"], 0)
        from datetime import datetime
        self.assertEqual(
            dune["library_at"],
            int(datetime(2026, 9, 1, 8, 0, 0).timestamp()),
        )

    def test_library_at_fallback_takes_earliest_upload_record(self):
        """多集多文件时，上传记录兜底也取最早那一笔 —— 与 STRM mtime 口径一致。"""
        records = {}
        for idx, when in (("01", "2026-09-01T08:00:00"), ("02", "2026-09-02T08:00:00"), ("03", "2026-09-03T08:00:00")):
            records[f"/media/inbox/某剧 (2024)/Season 01/某剧 - S01E{idx}.mkv"] = {"uploaded_at": when}

        rows = build_ledger(
            records={
                "m1:a": {"path": "/strm/剧集/某剧 (2024)/Season 01/某剧 - S01E01.strm", "file_id": "1"},
                "m1:b": {"path": "/strm/剧集/某剧 (2024)/Season 01/某剧 - S01E02.strm", "file_id": "2"},
                "m1:c": {"path": "/strm/剧集/某剧 (2024)/Season 01/某剧 - S01E03.strm", "file_id": "3"},
            },
            strm_mappings=[{"id": "m1", "target_dir": "/strm"}],
            upload_mappings=[{"id": "u1", "source": "/media/inbox", "target": "/影视"}],
            upload_records=records,
            pending_paths=set(),
            media_extensions=[".mkv"],
        )

        self.assertEqual(len(rows), 1)
        from datetime import datetime
        self.assertEqual(
            rows[0]["library_at"],
            int(datetime(2026, 9, 1, 8, 0, 0).timestamp()),
        )
