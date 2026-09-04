"""通知的排版与文案。

这几条消息是插件唯一会主动找上门的界面：手机锁屏上只有一个标题和两三行正文。所以守的是
「一瞥能读懂」——标题自带结论、正文不复述标题、失败必须说原因、说人话而不是系统术语。

排版语法和签到插件那边逐字一致（两个插件的消息落在同一个通知列表里，读的人只该学一遍）：
清单 → 小计 → 空行 → 下一步。清单行是「状态位 + 名称 + 两个空格 + 发生了什么」，
状态位只有 ✅ 成了 / ❌ 要你出手 / ⏳ 挂着等你确认三种。

排版纪律也在这里守：不画长横线（窄屏会折行）、不用 Markdown（微信 / Bark 不渲染）、
分区一律用空行、数字和单位之间留一个空格。
"""

import unittest

from app.plugins.p115liteassistant.api import Api


class RecordingNotifier:
    """记下每条通知的 headline 与正文行，不碰真实通道。"""

    def __init__(self, enabled=True):
        self.enabled = enabled
        self.calls = []

    def is_enabled(self, channel):
        return self.enabled

    def notify(self, channel, headline, lines, image=""):
        self.calls.append({
            "channel": channel,
            "headline": headline,
            "lines": [str(line) for line in lines],
            "text": "\n".join(str(line) for line in lines),
        })


# 只装通知方法需要的那点东西，其余一概不给 —— 借真实实现，造最小依赖。
# 借来的 classmethod 会拿 NotifyHost 当 cls，它们要的类属性也得一起带上。
_BORROWED = (
    "_row", "_short_note", "_duration_text",
    "_strm_change_text", "_strm_row_line", "_strm_text_notice", "_strm_aside_line",
    "_sweep_row", "_sweep_aside_line", "_sweep_entry_is_noteworthy", "_notify_strm_sweep",
    "_season_bar", "_season_ranges", "_season_episodes_map", "_season_lines",
    "_upload_haul_line", "_upload_text_lines",
    "_notify_checkin",
)
_CONSTANTS = (
    "_SWEEP_COUNT_KEYS", "NOTIFY_ROW_LIMIT", "NOTIFY_NOTE_LIMIT", "NOTE_MIN_CLAUSE",
    "SEASON_BAR_CELLS",
)

NotifyHost = type("NotifyHost", (), {
    **{name: Api.__dict__.get(name, getattr(Api, name)) for name in _BORROWED},
    **{name: getattr(Api, name) for name in _CONSTANTS},
    "__init__": lambda self, notifier: setattr(self, "_notifier", notifier),
})


def host(enabled=True):
    notifier = RecordingNotifier(enabled)
    return NotifyHost(notifier), notifier


NO_RULES = ("────", "━━", "│", "**", "• ", "====")


class RowGrammarTest(unittest.TestCase):
    """清单行的写法。两个插件共用，这里守的是那两个空格和三种状态位。"""

    def test_row_puts_the_mark_first(self):
        api, _ = host()
        self.assertEqual(api._row("✅", "电影", "新增 8 个"), "✅ 电影  新增 8 个")

    def test_row_stops_at_the_name_without_a_note(self):
        api, _ = host()
        self.assertEqual(api._row("✅", "电影"), "✅ 电影")

    def test_row_falls_back_when_the_name_is_missing(self):
        api, _ = host()
        self.assertEqual(api._row("❌", "", "没生成"), "❌ -  没生成")


class DurationTest(unittest.TestCase):
    """耗时读数说人话：毫秒是给日志看的。"""

    def test_sub_second(self):
        api, _ = host()
        self.assertEqual(api._duration_text(420), "不到 1 秒")

    def test_seconds(self):
        api, _ = host()
        self.assertEqual(api._duration_text(8600), "8.6 秒")

    def test_minutes(self):
        api, _ = host()
        self.assertEqual(api._duration_text(135000), "2 分 15 秒")

    def test_whole_minutes_drop_the_seconds(self):
        api, _ = host()
        self.assertEqual(api._duration_text(120000), "2 分")

    def test_no_milliseconds_anywhere(self):
        api, _ = host()
        self.assertNotIn("ms", api._duration_text(8600))


class CheckinNoticeTest(unittest.TestCase):
    """115 每日签到：标题说结论，正文只补标题装不下的。"""

    def test_title_carries_the_points(self):
        api, notifier = host()
        api._notify_checkin({"continuous_day": 45, "points_num": 5, "message": "签到成功"}, True)
        call = notifier.calls[0]
        self.assertEqual(call["headline"], "已签到，+5 积分")
        self.assertEqual(call["text"], "连续签到 45 天")

    def test_already_signed_reads_plainly(self):
        api, notifier = host()
        api._notify_checkin({"already": True, "continuous_day": 12, "message": "今日已签到"}, True)
        self.assertEqual(notifier.calls[0]["headline"], "今天已经签过了")
        self.assertEqual(notifier.calls[0]["text"], "连续签到 12 天")

    def test_streak_of_one_is_still_worth_a_line(self):
        """真机上刚断签重来那天，正文只剩一句「签到已记录」，标题已经说过了。"""
        api, notifier = host()
        api._notify_checkin({"points_num": 1, "continuous_day": 1, "message": "签到成功"}, True)
        call = notifier.calls[0]
        self.assertEqual(call["headline"], "已签到，+1 积分")
        self.assertEqual(call["text"], "连续签到 1 天")

    def test_body_never_restates_the_time(self):
        """通知自带到达时间，再写一行「时间：」是白占锁屏上的位置。"""
        api, notifier = host()
        api._notify_checkin({"time": "2026-09-04T08:10:02", "points_num": 5, "continuous_day": 3}, True)
        self.assertNotIn("时间", notifier.calls[0]["text"])
        self.assertNotIn("2026", notifier.calls[0]["text"])

    def test_failure_leads_with_the_reason(self):
        api, notifier = host()
        api._notify_checkin({"message": "Cookie 已失效，请重新扫码登录"}, False)
        call = notifier.calls[0]
        self.assertEqual(call["headline"], "没签上")
        self.assertEqual(call["text"], "Cookie 已失效，请重新扫码登录")

    def test_failure_without_reason_points_somewhere(self):
        api, notifier = host()
        api._notify_checkin({}, False)
        self.assertIn("去插件运行台看这次的记录", notifier.calls[0]["text"])

    def test_generic_receipt_is_not_echoed_twice(self):
        """115 回执常常就是「签到成功」四个字，标题已经说了就别再抄一行。"""
        api, notifier = host()
        api._notify_checkin({"points_num": 3, "continuous_day": 9, "message": "签到成功"}, True)
        self.assertEqual(notifier.calls[0]["text"].count("签到成功"), 0)

    def test_real_receipt_is_kept(self):
        api, notifier = host()
        api._notify_checkin(
            {"points_num": 3, "continuous_day": 9, "message": "本月签到满 20 天可领额外空间"}, True,
        )
        self.assertIn("本月签到满 20 天", notifier.calls[0]["text"])

    def test_no_rules_or_markdown(self):
        api, notifier = host()
        api._notify_checkin({"points_num": 5, "continuous_day": 45, "message": "签到成功"}, True)
        for ruler in NO_RULES:
            self.assertNotIn(ruler, notifier.calls[0]["text"])

    def test_disabled_channel_stays_quiet(self):
        api, notifier = host(enabled=False)
        api._notify_checkin({"points_num": 5}, True)
        self.assertEqual(notifier.calls, [])


class StrmNoticeTest(unittest.TestCase):
    """STRM 同步的纯文本通知。飞书卡片之外的渠道走的是这条路，映射详情不能丢。"""

    def test_headline_counts_what_was_made(self):
        api, _ = host()
        headline, _ = api._strm_text_notice([], {"added": 12, "updated": 4}, True)
        self.assertEqual(headline, "新增 12 个 STRM 文件")

    def test_headline_leads_with_failures(self):
        api, _ = host()
        headline, _ = api._strm_text_notice([], {"added": 8, "errors": 3}, True)
        self.assertEqual(headline, "3 个 STRM 文件没生成")

    def test_headline_falls_back_to_updates(self):
        api, _ = host()
        headline, _ = api._strm_text_notice([], {"updated": 4}, True)
        self.assertEqual(headline, "更新 4 个 STRM 文件")

    def test_headline_says_nothing_changed(self):
        api, _ = host()
        headline, _ = api._strm_text_notice([], {"skipped": 40}, True)
        self.assertEqual(headline, "没有需要更新的")

    def test_每条映射一行(self):
        api, _ = host()
        _, lines = api._strm_text_notice(
            [{"mapping": "电影", "added": 8}, {"mapping": "剧集", "added": 4, "updated": 2}],
            {"added": 12, "updated": 2}, True,
        )
        self.assertEqual(lines[0], "✅ 电影  新增 8 个")
        self.assertEqual(lines[1], "✅ 剧集  新增 4 个，更新 2 个")

    def test_changes_are_spelled_out_not_symbols(self):
        """+ ~ ✕ 省地方，但通知是给人看一眼的，不该先让人猜图例。"""
        api, _ = host()
        text = api._strm_change_text({"added": 3, "updated": 1, "removed": 2})
        self.assertEqual(text, "新增 3 个，更新 1 个，清理 2 个")
        for symbol in ("+3", "~1", "✕2"):
            self.assertNotIn(symbol, text)

    def test_failed_mapping_wears_the_cross_and_the_reason(self):
        api, _ = host()
        line = api._strm_row_line({
            "mapping": "剧集", "errors": 2,
            "message": "连接超时（已启用代理），请检查站点连通性",
        })
        self.assertEqual(line, "❌ 剧集  2 个没生成 · 连接超时（已启用代理）…")

    def test_untouched_mapping_says_it_is_current(self):
        api, _ = host()
        self.assertEqual(api._strm_row_line({"mapping": "电影"}), "✅ 电影  已经是最新的")

    def test_failures_come_first(self):
        """映射多到要折叠时，被折掉的必须是「都好」的那几条。"""
        api, _ = host()
        _, lines = api._strm_text_notice(
            [{"mapping": "电影", "added": 8}, {"mapping": "剧集", "errors": 1, "message": "超时"}],
            {"added": 8, "errors": 1}, True,
        )
        self.assertTrue(lines[0].startswith("❌ 剧集"))

    def test_aside_line_carries_what_nobody_watches(self):
        api, _ = host()
        _, lines = api._strm_text_notice(
            [{"mapping": "电影", "added": 1}],
            {"added": 1, "skipped": 412, "sidecars": 26}, True,
        )
        self.assertEqual(lines[-1], "跳过 412 个没变化的 · 顺带 26 个刮削文件")

    def test_full_run_words_the_skip_differently(self):
        api, _ = host()
        _, lines = api._strm_text_notice([], {"skipped": 45}, False)
        self.assertEqual(lines[-1], "45 个已经是最新的")

    def test_quiet_run_has_no_aside(self):
        api, _ = host()
        _, lines = api._strm_text_notice([{"mapping": "电影", "added": 1}], {"added": 1}, True)
        self.assertEqual(lines, ["✅ 电影  新增 1 个"])

    def test_long_mapping_list_is_folded(self):
        api, _ = host()
        entries = [{"mapping": f"库{i}", "added": 1} for i in range(11)]
        _, lines = api._strm_text_notice(entries, {"added": 11}, True)
        self.assertIn("另外 3 条映射见插件运行台", lines)


class SweepNoticeTest(unittest.TestCase):
    """反向删除：删掉的是 115 上的真文件，通知必须让人一眼看懂动了什么。全篇不加装饰。"""

    def notice(self, totals, entries=None):
        """真实的 entry 自己也带这些计数，totals 是它们的和 —— 照这个形状造。"""
        api, notifier = host()
        if entries is None:
            counted = {key: value for key, value in totals.items() if key in Api._SWEEP_COUNT_KEYS}
            entries = [{"mapping": "电影", **counted}]
        api._notify_strm_sweep(entries, totals)
        self.assertTrue(notifier.calls, "这一轮应该发通知，但什么都没发")
        return notifier.calls[0]

    def test_headline_counts_the_deletions(self):
        self.assertEqual(self.notice({"cloud_deleted": 3})["headline"], "删了 3 个网盘文件")

    def test_headline_leads_with_failures(self):
        self.assertEqual(
            self.notice({"cloud_deleted": 3, "errors": 2})["headline"], "2 个网盘文件没删掉"
        )

    def test_headline_surfaces_the_review_queue(self):
        self.assertEqual(self.notice({"pending": 5})["headline"], "5 个网盘文件等你确认")

    def test_one_place_has_one_name(self):
        """同一处存储不能在标题里叫「云端」、正文里叫「115 上」——读的人得先确认是不是一回事。"""
        call = self.notice({"cloud_deleted": 3, "scrapes_deleted": 1, "unidentified": 2})
        whole = call["headline"] + " " + call["text"]
        self.assertNotIn("云端", whole)
        self.assertIn("网盘", whole)

    def test_single_mapping_row_does_not_repeat_the_headline(self):
        """真机上常态就是一条映射：数标题刚说过，行里要说的是「哪条映射」。"""
        call = self.notice({"cloud_deleted": 3})
        self.assertEqual(call["headline"], "删了 3 个网盘文件")
        self.assertEqual(call["lines"][0], "✅ 电影")

    def test_destructive_action_says_whether_it_can_be_undone(self):
        """「删了 20 个文件」之后第一个念头是「找得回来吗」，那句话必须在通知里。"""
        text = self.notice({"cloud_deleted": 3})["text"]
        self.assertIn("115 回收站", text)
        self.assertIn("能还原", text)

    def test_why_it_was_allowed_to_delete_is_stated_once(self):
        """删除会被追问「凭什么删」，答案在末尾说一次，不在每行里各抄一遍。"""
        call = self.notice(
            {"cloud_deleted": 4},
            [{"mapping": "电影", "cloud_deleted": 2}, {"mapping": "剧集", "cloud_deleted": 2}],
        )
        self.assertEqual(call["text"].count("本地 STRM 没了"), 1)
        self.assertIn("✅ 电影  删了 2 个", call["text"])

    def test_collateral_goes_to_the_subtotal_line(self):
        """刮削文件和空文件夹不是谁点名要删的，但它们确实在网盘上被删了。"""
        text = self.notice({"cloud_deleted": 3, "scrapes_deleted": 2, "cloud_dirs_deleted": 1})["text"]
        self.assertIn("连带清掉网盘上 2 个刮削文件、1 个空文件夹", text)

    def test_deletions_are_still_reported_when_the_headline_is_taken(self):
        """标题被失败数占了的时候，删掉的那几个没别的地方报。"""
        text = self.notice({"cloud_deleted": 1, "errors": 2})["text"]
        self.assertIn("另外 1 个已经删了", text)

    def test_pending_row_does_not_repeat_the_count(self):
        """护栏原话截短之后剩下的正是标题那个数，抄第二遍不带任何新消息。"""
        call = self.notice(
            {"pending": 22},
            [{"mapping": "剧集", "pending": 22,
              "reason": "待删媒体 22 个，超过确认阈值 16，新增 6 个已转入待确认队列"}],
        )
        self.assertEqual(call["lines"][0], "⏳ 剧集")
        self.assertNotIn("阈值", call["text"])

    def test_pending_rows_carry_counts_when_there_are_several(self):
        call = self.notice(
            {"pending": 5},
            [{"mapping": "剧集", "pending": 3}, {"mapping": "动漫", "pending": 2}],
        )
        self.assertIn("⏳ 剧集  3 个先搁着没删", call["text"])
        self.assertIn("⏳ 动漫  2 个先搁着没删", call["text"])

    def test_guardrail_reason_is_kept_when_there_is_no_count(self):
        call = self.notice(
            {"pending": 2},
            [{"mapping": "剧集", "reason": "这一批要删的比阈值多，先搁一批等确认"}],
        )
        self.assertIn("⏳ 剧集  这一批要删的比阈值多…", call["text"])

    def test_review_queue_says_where_to_go(self):
        lines = self.notice({"pending": 5})["lines"]
        self.assertEqual(lines[-1], "一次要删这么多，先让你过一眼。去插件运行台确认了才真删")

    def test_missing_source_is_explained_in_plain_words(self):
        """「溯源缺失」是内部说法，用户只想知道那是什么、该怎么办。"""
        text = self.notice({"cloud_deleted": 1, "unidentified": 4})["text"]
        self.assertIn("4 条记录对不上网盘文件（旧版本留下的）", text)
        self.assertIn("跑一次全量 STRM 同步就能补上", text)
        self.assertNotIn("溯源", text)

    def test_worst_rows_come_first(self):
        call = self.notice(
            {"cloud_deleted": 1, "pending": 2, "errors": 1},
            [
                {"mapping": "电影", "cloud_deleted": 1},
                {"mapping": "剧集", "pending": 2},
                {"mapping": "动漫", "errors": 1, "reason": "115 说操作太频繁"},
            ],
        )
        marks = [line[0] for line in call["lines"] if line[:1] in {"✅", "❌", "⏳"}]
        self.assertEqual(marks, ["❌", "⏳", "✅"])

    def test_quiet_round_sends_nothing(self):
        """巡检两小时一次，什么都没发生的轮次不该响。"""
        api, notifier = host()
        api._notify_strm_sweep([{"mapping": "电影"}], {})
        self.assertEqual(notifier.calls, [])

    def test_no_rules_or_markdown(self):
        text = self.notice({"cloud_deleted": 3, "pending": 1})["text"]
        for ruler in NO_RULES:
            self.assertNotIn(ruler, text)

    def test_blank_line_separates_the_next_step(self):
        """分区靠空行，不靠横线。末尾按「最该动手的排前面」，安慰的那句垫最后。"""
        lines = self.notice({"cloud_deleted": 3, "pending": 2})["lines"]
        self.assertEqual(lines.count(""), 1)
        blank = lines.index("")
        self.assertTrue(lines[blank + 1].startswith("一次要删这么多"))
        self.assertIn("115 回收站", lines[-1])


class SeasonBarTest(unittest.TestCase):
    """库存带：一季有几集在 115 上。签名元素，也是这条通知里唯一的装饰。"""

    def test_bar_is_full_only_when_the_season_is(self):
        api, _ = host()
        self.assertEqual(api._season_bar(10, 10), "■" * 10)

    def test_bar_never_fills_on_a_near_miss(self):
        """59/60 集按比例算正好十格，图形说齐了、读数说没齐，眼睛先信图形。"""
        api, _ = host()
        self.assertEqual(api._season_bar(59, 60), "■" * 9 + "□")

    def test_bar_is_proportional(self):
        api, _ = host()
        self.assertEqual(api._season_bar(6, 12), "■" * 5 + "□" * 5)

    def test_empty_season_is_all_hollow(self):
        api, _ = host()
        self.assertEqual(api._season_bar(0, 8), "□" * 10)

    def test_no_bar_without_a_season_total(self):
        """TMDB 没答上来就别画一条骗人的带子。"""
        api, _ = host()
        self.assertEqual(api._season_bar(5, 0), "")

    def test_bar_width_is_fixed(self):
        """格数固定，长度才可预期 —— 一季 24 集画 24 格，手机上直接折行。"""
        api, _ = host()
        for total in (6, 12, 24, 60):
            self.assertEqual(len(api._season_bar(1, total)), api.SEASON_BAR_CELLS)

    def test_complete_season_reads_as_complete(self):
        api, _ = host()
        self.assertEqual(
            api._season_lines("第2季 第1-10集", {2: (10, 10)}),
            ["第 2 季  " + "■" * 10 + "  10 集齐了"],
        )

    def test_incomplete_season_reports_the_shortfall(self):
        api, _ = host()
        self.assertEqual(
            api._season_lines("第1季 第1-7集", {1: (7, 12)}),
            ["第 1 季  " + "■" * 5 + "□" * 5 + "  12 集里有 7 集"],
        )

    def test_falls_back_to_episode_numbers_without_tmdb(self):
        """画不出满不满，就老实报有哪几集，不含糊过去。"""
        api, _ = host()
        self.assertEqual(api._season_lines("第1季 第3、5-8集", {}), ["第 1 季  第 3、5-8 集"])

    def test_seasons_are_listed_in_order(self):
        api, _ = host()
        lines = api._season_lines("第2季 第1-2集，第1季 第1-7集", {1: (7, 12), 2: (2, 10)})
        self.assertTrue(lines[0].startswith("第 1 季"))
        self.assertTrue(lines[1].startswith("第 2 季"))

    def test_episode_sets_are_expanded_from_ranges(self):
        api, _ = host()
        self.assertEqual(api._season_episodes_map("第2季 第1-3、7集"), {2: {1, 2, 3, 7}})

    def test_movies_have_no_season_line(self):
        api, _ = host()
        self.assertEqual(api._season_lines("", {}), [])


class UploadNoticeTest(unittest.TestCase):
    """上传通道：以前一行挤七个「字段：值」，在手机上要横着读完才知道入库了第几集。"""

    def lines(self, **facts):
        api, _ = host()
        return api._upload_text_lines(facts)

    def test_season_bar_opens_the_body(self):
        lines = self.lines(season_lines=["第 2 季  " + "■" * 10 + "  10 集齐了"],
                           count=4, size="18.6 GB", library="剧集")
        self.assertTrue(lines[0].startswith("第 2 季"))
        self.assertEqual(lines[1], "")

    def test_batch_line_says_what_arrived_this_time(self):
        """库存带讲的是「现在有多少」，这一行讲「这一趟搬了多少」——后者才是消息的由来。"""
        lines = self.lines(season_lines=["第 2 季  ■■■■■■■■■■  10 集齐了"],
                           count=4, size="18.6 GB", instant=4, library="剧集")
        self.assertIn("这次进了 4 集 · 18.6 GB · 全部秒传", lines)

    def test_episodes_are_counted_in_episodes(self):
        lines = self.lines(season_lines=["第 1 季  第 3 集"], count=1, size="2.0 GB", library="剧集")
        self.assertTrue(any(line.startswith("这次进了 1 集") for line in lines))

    def test_movies_are_counted_in_files(self):
        lines = self.lines(count=1, size="22.4 GB", instant=1, library="电影")
        self.assertEqual(lines[0], "这次进了 1 个文件 · 22.4 GB · 全部秒传")

    def test_partial_instant_keeps_the_same_unit(self):
        lines = self.lines(season_lines=["第 1 季  第 1-3 集"], count=3, size="9.2 GB", instant=1)
        self.assertIn("其中 1 集秒传", lines[-2])

    def test_plain_upload_says_nothing_about_the_method(self):
        """上传是默认动作，写「上传 6 个」和前面那个数字是同一件事说两遍。"""
        lines = self.lines(count=6, size="12 GB", instant=0, library="电影")
        self.assertEqual(lines[0], "这次进了 6 个文件 · 12 GB")

    def test_placement_line_closes_the_body(self):
        lines = self.lines(count=12, size="45.6 GB", library="电影", strm=12, sidecars=3)
        self.assertEqual(lines[-1], "存进「电影」，生成 12 个 STRM，带上 3 个刮削文件")

    def test_sidecars_are_named_by_what_they_are(self):
        """「附属 3 个」看不出是什么；用户认识的是刮削文件。"""
        text = "\n".join(self.lines(count=1, size="1.0 GB", sidecars=2, library="电影"))
        self.assertIn("刮削文件", text)
        self.assertNotIn("附属", text)

    def test_zero_counts_are_left_out(self):
        lines = self.lines(count=1, size="1.0 GB", instant=1, library="电影", strm=0, sidecars=0)
        self.assertEqual(lines[-1], "存进「电影」")

    def test_unknown_library_falls_back(self):
        lines = self.lines(count=1, size="1.0 GB")
        self.assertEqual(lines[-1], "存进「媒体库」")

    def test_no_field_colon_style(self):
        """「类型：媒体，映射：电影」是给程序看的，不是给人看的。"""
        text = "\n".join(self.lines(count=1, size="1.0 GB", instant=1, library="电影"))
        for field in ("类型：", "映射：", "方式：", "大小："):
            self.assertNotIn(field, text)

    def test_no_rules_or_markdown(self):
        text = "\n".join(self.lines(season_lines=["第 1 季  第 1-3 集"], count=3, size="9 GB",
                                   library="剧集", strm=3, sidecars=6))
        for ruler in NO_RULES:
            self.assertNotIn(ruler, text)


if __name__ == "__main__":
    unittest.main()
