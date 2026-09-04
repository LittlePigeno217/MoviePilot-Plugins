"""签到通知的排版与文案。

通知是这个插件唯一会主动找上门的界面：手机锁屏上只有一个标题、两三行正文。所以这里
守的是「一瞥能读懂」——标题自带结论、正文不复述标题、失败必须说原因、站点给了什么
必须出现在那一行上。

排版语法（两个插件共用，见 plugins/checkin/__init__.py 里那段说明）：
清单 → 小计 → 空行 → 下一步 → 落款。落款是打卡带，全篇唯一的装饰。
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

import unittest


def _load_helpers():
    """借用 test_schedule 里的宿主桩，不再复制一份。"""
    path = Path(__file__).with_name("test_schedule.py")
    spec = importlib.util.spec_from_file_location("_checkin_notify_helpers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_helpers = _load_helpers()
RecordingScheduler = _helpers.RecordingScheduler
load_checkin = _helpers.load_checkin


def day_before(back: int) -> str:
    """相对今天数日期。打卡带和连签都按 datetime.now() 算，日期不能写死。"""
    return (datetime.now() - timedelta(days=back)).strftime("%Y-%m-%d")


def history_entry(day: str, status: str, success: int, failure: int, sites: int = 3):
    return {
        "version": 2,
        "time": f"{day} 08:10:02",
        "status": status,
        "message": "-",
        "success_count": success,
        "failure_count": failure,
        "site_count": sites,
        "details": [{
            "site": "flzt", "site_name": "FLZT", "status": "签到成功", "message": "-",
            "account": "a@b.c", "reward_mb": "-", "total_traffic": "-", "time": f"{day} 08:10:01",
        }],
    }


def site_detail(name: str, status: str, message: str = "-", reward: str = "-", total: str = "-"):
    return {
        "site": name, "site_name": name, "status": status, "message": message,
        "account": "a@b.c", "reward_mb": reward, "total_traffic": total,
        "time": f"{day_before(0)} 08:10:02",
    }


class NotifyTest(unittest.TestCase):
    def setUp(self) -> None:
        module = load_checkin(RecordingScheduler())
        self.Checkin = module.Checkin
        self.plugin = module.Checkin()
        self.plugin.init_plugin({
            "enabled": True, "notify": True, "cron": "10 8 * * *",
            "sites": {"flzt": {"enabled": True, "email": "a@b.c", "password": "x"}},
        })
        self.addCleanup(self._cancel_timer)
        self.sent: dict = {}
        self.plugin.post_message = lambda **kwargs: self.sent.update(kwargs)

    def _cancel_timer(self) -> None:
        timer = getattr(self.Checkin, "_boot_timer", None)
        if timer:
            timer.cancel()
            self.Checkin._boot_timer = None

    def given_history(self, *entries) -> None:
        self.plugin.save_data("history", list(entries))

    def notify(self, **summary) -> tuple:
        payload = {"status": "全部成功", "message": "-", "success_count": 0, "failure_count": 0,
                   "time": f"{day_before(0)} 08:10:12", "details": []}
        payload.update(summary)
        self.plugin._notify_summary(payload)
        return self.sent.get("title", ""), self.sent.get("text", "")

    # ── 标题：锁屏上往往只看得到这一行 ────────────────────────────────
    def test_title_states_the_outcome(self):
        title, _ = self.notify(success_count=3, failure_count=0,
                               details=[site_detail("FLZT", "签到成功")] * 3)
        self.assertEqual(title, "自用签到 · 3 个站点都签上了")

    def test_title_counts_both_sides_when_partly_failed(self):
        title, _ = self.notify(status="部分成功", success_count=2, failure_count=1,
                               details=[site_detail("FLZT", "签到成功")] * 3)
        self.assertEqual(title, "自用签到 · 1 个没签上，2 个签上了")

    def test_title_says_none_when_all_failed(self):
        title, _ = self.notify(status="执行失败", success_count=0, failure_count=3,
                               details=[site_detail("FLZT", "执行失败", "超时")] * 3)
        self.assertEqual(title, "自用签到 · 一个都没签上")

    def test_title_separates_already_signed_from_a_fresh_run(self):
        """全是「今日已签到」时别让人以为这一次真拿到了什么。"""
        title, _ = self.notify(success_count=3, details=[site_detail("站点1", "今日已签到")] * 3)
        self.assertEqual(title, "自用签到 · 今天都已经签过了")

    def test_title_falls_back_to_the_reason_when_nothing_ran(self):
        title, _ = self.notify(status="执行失败", message="请先启用至少一个签到站点")
        self.assertEqual(title, "自用签到 · 请先启用至少一个签到站点")

    # ── 站点行：签到的意义是拿到东西，那一行必须把东西写出来 ──────────
    def test_traffic_site_reports_what_it_gave(self):
        _, text = self.notify(success_count=1, details=[
            site_detail("FLZT", "签到成功", "签到成功", reward="128", total="32.50 GB"),
        ])
        self.assertIn("✅ FLZT  +128 MB · 累计 32.50 GB", text)

    def test_traffic_rolls_up_to_gb(self):
        """真机上 FLZT 一次给一两个 G，「+1025.83 MB」要读的人自己换算。"""
        _, text = self.notify(success_count=1, details=[
            site_detail("FLZT", "签到成功", "操作成功", reward="1025.83", total="142.22 GB"),
        ])
        self.assertIn("✅ FLZT  +1.00 GB · 累计 142.22 GB", text)

    def test_megabyte_decimals_are_dropped(self):
        _, text = self.notify(success_count=1, details=[
            site_detail("站点", "签到成功", reward="661.64"),
        ])
        self.assertIn("+662 MB", text)

    def test_points_are_pulled_out_of_the_site_receipt(self):
        """恩山把积分写在回执里而不是字段里，以前那一行只显示「签上了」。"""
        _, text = self.notify(success_count=1, details=[site_detail(
            "恩山无线论坛", "签到成功", "今日积分：5；连续签到：4 天；总签到天数：126 天",
        )])
        self.assertIn("✅ 恩山无线论坛  +5 积分", text)

    def test_points_with_another_wording_are_also_pulled_out(self):
        _, text = self.notify(success_count=1, details=[
            site_detail("易破解", "签到成功", "本次签到增加：2.5积分"),
        ])
        self.assertIn("✅ 易破解  +2.5 积分", text)

    def test_trailing_zeros_are_trimmed(self):
        _, text = self.notify(success_count=1, details=[
            site_detail("易破解", "签到成功", "本次签到增加：3.00积分"),
        ])
        self.assertIn("+3 积分", text)

    def test_zero_gain_is_not_a_gain(self):
        """易破解每天回一句「本次签到增加：0积分」，`+0 积分` 占一格却什么都没说。"""
        _, text = self.notify(success_count=1, details=[
            site_detail("易破解", "签到成功", "本次签到增加：0积分"),
        ])
        self.assertEqual(text.split("\n")[0], "✅ 易破解")

    def test_row_stops_at_the_name_when_the_site_gave_nothing(self):
        """补一句「签上了」是把行首那个勾说第二遍，宁可留白。"""
        _, text = self.notify(success_count=1, details=[
            site_detail("某站", "签到成功", "签到成功"),
        ])
        self.assertEqual(text.split("\n")[0], "✅ 某站")

    def test_already_signed_reads_like_a_person_wrote_it(self):
        _, text = self.notify(status="部分成功", success_count=1, failure_count=1, details=[
            site_detail("FLZT", "今日已签到", "今日已签到，明天再来"),
            site_detail("易破解", "执行失败", "超时"),
        ])
        self.assertIn("✅ FLZT  今天已经签过了", text)

    def test_all_already_signed_does_not_repeat_the_title_on_every_row(self):
        """标题已经说了「今天都已经签过了」，三行再各抄一遍就是说四次。"""
        _, text = self.notify(success_count=3, details=[
            site_detail("FLZT", "今日已签到"), site_detail("恩山无线论坛", "今日已签到"),
            site_detail("易破解", "今日已签到"),
        ])
        self.assertEqual(text.split("\n")[:3], ["✅ FLZT", "✅ 恩山无线论坛", "✅ 易破解"])

    def test_already_signed_still_reports_the_gain(self):
        """收掉的只是那句会被复述四遍的话；恩山「早就签过了」那条仍然带着当天的积分。"""
        _, text = self.notify(success_count=2, details=[
            site_detail("FLZT", "今日已签到", "The user has already checked in today"),
            site_detail("恩山无线论坛", "今日已签到", "今日积分：1；连续签到：1 天；总签到天数：28 天"),
        ])
        self.assertEqual(text.split("\n")[:2], ["✅ FLZT", "✅ 恩山无线论坛  +1 积分"])

    def test_body_never_repeats_the_title(self):
        title, text = self.notify(status="部分成功", message="成功 2 个，失败 1 个",
                                  success_count=2, failure_count=1,
                                  details=[site_detail("FLZT", "签到成功")])
        self.assertNotIn("成功 2 个，失败 1 个", text)
        self.assertNotIn(title, text)

    def test_body_invites_action_when_no_site_ran(self):
        """空态是行动的邀请，不是一句「无数据」。"""
        _, text = self.notify(status="执行失败", message="请先启用至少一个签到站点")
        self.assertIn("去插件设置里打开一个站点", text)

    # ── 失败：原因是通知里最该有的东西 ────────────────────────────────
    def test_failure_carries_the_reason(self):
        _, text = self.notify(status="执行失败", success_count=0, failure_count=1,
                              details=[site_detail("易破解", "执行失败", "账号或密码未填写")])
        self.assertIn("❌ 易破解  账号或密码未填写", text)

    def test_long_reason_is_cut_at_a_punctuation_mark(self):
        """站点原因都写成「结论，加一串建议」，在标点处收住就只留结论。"""
        _, text = self.notify(status="执行失败", success_count=0, failure_count=1, details=[site_detail(
            "FLZT", "执行失败", "连不上站点（已启用代理），检查一下网络，或者把超时调大一点",
        )])
        self.assertIn("❌ FLZT  连不上站点（已启用代理）…", text)

    def test_reasons_are_worded_for_a_person(self):
        """「认证失败」「请求过于频繁」是系统词，看完还得再想一层才知道去改什么。"""
        plugin = self.plugin
        from requests.exceptions import HTTPError

        class FakeResponse:
            status_code = 401

        err = HTTPError(response=FakeResponse())
        self.assertEqual(
            plugin._format_request_error(err), "登录态失效或账号密码不对，去设置里重新填一次",
        )
        FakeResponse.status_code = 429
        self.assertEqual(plugin._format_request_error(err), "站点限流了，先歇一会儿再试")

    def test_reason_does_not_repeat_the_site_name(self):
        _, text = self.notify(status="执行失败", success_count=0, failure_count=1,
                              details=[site_detail("FLZT", "执行失败", "FLZT 还没填密码")])
        self.assertIn("❌ FLZT  还没填密码", text)

    def test_missing_reason_points_at_the_ledger(self):
        _, text = self.notify(status="执行失败", success_count=0, failure_count=1,
                              details=[site_detail("FLZT", "执行失败", "-")])
        self.assertIn("去插件运行台看这次的记录", text)

    def test_page_source_is_not_a_reason(self):
        """真机上恩山失败时给的是页面里的一段 CSS，压缩完只剩一个「body…」。"""
        _, text = self.notify(status="执行失败", success_count=0, failure_count=1, details=[site_detail(
            "恩山无线论坛", "执行失败",
            "body,div,html,p,span{margin:0;padding:0;border:0;outline:0;font-size:100%}",
        )])
        self.assertNotIn("body", text)
        self.assertIn("❌ 恩山无线论坛  没给原因，去插件运行台看这次的记录", text)

    def test_english_receipt_is_still_a_reason(self):
        """「没有中文」不等于「是源码」——FLZT 的回执就是一句英文。"""
        self.assertEqual(
            self.plugin._short_reason("The user has already checked in today"),
            "The user has already che…",
        )

    def test_failures_come_before_successes(self):
        """站点多到要折叠时，被折掉的必须是「都好」的那几个。"""
        _, text = self.notify(status="部分成功", success_count=2, failure_count=1, details=[
            site_detail("FLZT", "签到成功"), site_detail("恩山无线论坛", "签到成功"),
            site_detail("易破解", "执行失败", "超时"),
        ])
        self.assertTrue(text.split("\n")[0].startswith("❌ 易破解"))

    # ── 小计：三个以上站点给了同一种东西才值一行 ──────────────────────
    def test_no_subtotal_for_two_numbers(self):
        """两个数读者自己就加完了，第三个才开始需要合计。"""
        _, text = self.notify(success_count=2, details=[
            site_detail("站点1", "签到成功", reward="100"),
            site_detail("站点2", "签到成功", reward="120"),
        ])
        self.assertNotIn("今天到手", text)

    def test_subtotal_uses_the_same_reading_format(self):
        _, text = self.notify(success_count=3, details=[
            site_detail(f"站点{i}", "签到成功", reward="1025.83") for i in range(3)
        ])
        self.assertIn("今天到手 +3.01 GB 流量", text)

    def test_subtotal_sums_traffic_and_names_the_unit(self):
        _, text = self.notify(success_count=3, details=[
            site_detail("站点1", "签到成功", reward="100"),
            site_detail("站点2", "签到成功", reward="120"),
            site_detail("站点3", "签到成功", reward="80"),
        ])
        self.assertIn("今天到手 +300 MB 流量", text)

    def test_subtotal_switches_to_gb_when_it_gets_big(self):
        _, text = self.notify(success_count=3, details=[
            site_detail(f"站点{i}", "签到成功", reward="800") for i in range(3)
        ])
        self.assertIn("今天到手 +2.34 GB 流量", text)

    def test_traffic_and_points_are_settled_separately(self):
        """流量和积分不是同一种钱，不能加成一个数。"""
        _, text = self.notify(success_count=6, details=[
            *(site_detail(f"流量站{i}", "签到成功", reward="100") for i in range(3)),
            *(site_detail(f"积分站{i}", "签到成功", "今日积分：5") for i in range(3)),
        ])
        self.assertIn("今天到手 +300 MB 流量 · +15 积分", text)

    # ── 落款：打卡带，全篇唯一的装饰 ──────────────────────────────────
    def test_tape_closes_the_body(self):
        """签名图形放在末尾：前两行留给「要不要动手」，那才是锁屏上看得到的。"""
        self.given_history(
            history_entry(day_before(0), "全部成功", 3, 0),
            history_entry(day_before(1), "部分成功", 2, 1),
            history_entry(day_before(2), "执行失败", 0, 3),
        )
        _, text = self.notify(success_count=3, details=[site_detail("FLZT", "签到成功")])
        self.assertEqual(text.split("\n")[-1], "····□▣■  连续签上 2 天")

    def test_tape_reading_matches_the_ledger_page(self):
        """连签不足两天就报「7 天里签上 N 天」，和台账页那条 30 格刻痕一个说法。"""
        self.given_history(history_entry(day_before(3), "全部成功", 3, 0))
        _, text = self.notify(status="执行失败", success_count=0, failure_count=1,
                              details=[site_detail("FLZT", "执行失败", "超时")])
        self.assertIn("7 天里签上 1 天", text)

    def test_body_omits_the_tape_when_there_is_no_history(self):
        """一条记录都没有时整条带子都是点，没有信息量就不占那一行。"""
        _, text = self.notify(success_count=1, details=[site_detail("FLZT", "签到成功")])
        self.assertNotIn("·", text)
        self.assertEqual(text, "✅ FLZT")

    def test_streak_is_worded_differently_when_today_broke_it(self):
        """今天一个都没签上时说「这之前连着签了」，免得以为今天也算进去了。"""
        self.given_history(
            history_entry(day_before(1), "全部成功", 3, 0),
            history_entry(day_before(2), "全部成功", 3, 0),
        )
        _, text = self.notify(status="执行失败", success_count=0, failure_count=3,
                              details=[site_detail("FLZT", "执行失败", "超时")])
        self.assertIn("这之前连着签了 2 天", text)
        self.assertNotIn("连续签上", text)

    def test_streak_counts_today_when_it_signed(self):
        self.given_history(
            history_entry(day_before(0), "全部成功", 3, 0),
            history_entry(day_before(1), "全部成功", 3, 0),
        )
        _, text = self.notify(success_count=3, details=[site_detail("FLZT", "签到成功")])
        self.assertIn("连续签上 2 天", text)

    # ── 下一步：只在需要人动手时出现 ──────────────────────────────────
    def test_failure_says_the_sweep_will_retry(self):
        _, text = self.notify(status="执行失败", success_count=0, failure_count=1,
                              details=[site_detail("FLZT", "执行失败", "超时")])
        self.assertIn("没签上的每半小时自动再试一次，今天还剩 5 次", text)

    def test_exhausted_retries_ask_for_a_hand(self):
        self.plugin.save_data(
            "catchup_state", {"day": day_before(0), "count": self.plugin.CATCHUP_MAX_PER_DAY},
        )
        _, text = self.notify(status="执行失败", success_count=0, failure_count=1,
                              details=[site_detail("FLZT", "执行失败", "超时")])
        self.assertIn("今天的自动重试用完了，处理完原因可以手动跑一次", text)

    def test_success_says_nothing_about_retries(self):
        _, text = self.notify(success_count=1, details=[site_detail("FLZT", "签到成功")])
        self.assertNotIn("再试", text)

    # ── 排版纪律 ──────────────────────────────────────────────────────
    def test_body_uses_blank_lines_not_rules(self):
        """长横线在窄屏会折行，分区一律用空行。"""
        _, text = self.notify(status="执行失败", success_count=1, failure_count=1, details=[
            site_detail("FLZT", "签到成功"), site_detail("易破解", "执行失败", "超时"),
        ])
        for ruler in ("────", "━━", "│", "===="):
            self.assertNotIn(ruler, text)

    def test_no_markdown(self):
        """微信 / Bark 不渲染 Markdown，`**` 会原样显示出来。"""
        _, text = self.notify(success_count=1, details=[
            site_detail("FLZT", "签到成功", reward="128", total="1.00 GB"),
        ])
        for markup in ("**", "* ", "# ", "`"):
            self.assertNotIn(markup, text)

    def test_only_one_blank_line(self):
        """空行只用来分隔「发生了什么」和「接下来会怎样」，出现第二次就没了分区的意思。"""
        self.given_history(history_entry(day_before(1), "全部成功", 3, 0))
        _, text = self.notify(status="执行失败", success_count=1, failure_count=1, details=[
            site_detail("FLZT", "签到成功"), site_detail("易破解", "执行失败", "超时"),
        ])
        self.assertEqual(text.split("\n").count(""), 1)

    def test_status_marks_stay_at_two_symbols(self):
        """清单行只有两种状态位：✅ 和 ❌。多一个都是装饰。"""
        _, text = self.notify(status="部分成功", success_count=1, failure_count=1, details=[
            site_detail("FLZT", "签到成功"), site_detail("易破解", "执行失败", "超时"),
        ])
        for decoration in ("📝", "⚠️", "🎉", "⏸", "📌", "⏳"):
            self.assertNotIn(decoration, text)

    def test_numbers_keep_a_space_from_their_unit(self):
        _, text = self.notify(success_count=1, details=[
            site_detail("FLZT", "签到成功", reward="128", total="32.50 GB"),
        ])
        self.assertNotIn("128MB", text)
        self.assertIn("+128 MB", text)

    def test_long_site_list_is_folded(self):
        details = [site_detail(f"站点{i}", "签到成功") for i in range(12)]
        _, text = self.notify(success_count=12, details=details)
        self.assertIn("另外 4 个站点见插件运行台", text)
        self.assertEqual(text.count("✅"), self.plugin.NOTIFY_SITE_LIMIT)

    def test_notify_switch_off_sends_nothing(self):
        self.plugin._notify = False
        self.notify(success_count=1, details=[site_detail("FLZT", "签到成功")])
        self.assertEqual(self.sent, {})


if __name__ == "__main__":
    unittest.main()
