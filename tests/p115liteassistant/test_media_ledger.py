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
