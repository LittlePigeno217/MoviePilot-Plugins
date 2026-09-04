from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


def load_checkin_module():
    root = Path(__file__).resolve().parents[2]
    module_path = root / "plugins" / "checkin" / "__init__.py"

    app_module = types.ModuleType("app")
    core_module = types.ModuleType("app.core")
    config_module = types.ModuleType("app.core.config")
    config_module.settings = types.SimpleNamespace(PROXY={"https": "http://proxy.local:7890"})
    log_module = types.ModuleType("app.log")
    log_module.logger = types.SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None)
    plugins_module = types.ModuleType("app.plugins")
    plugins_module._PluginBase = object
    scheduler_module = types.ModuleType("app.scheduler")
    scheduler_module.Scheduler = lambda: types.SimpleNamespace(remove_plugin_job=lambda *a, **k: None, list=lambda: [])
    schemas_module = types.ModuleType("app.schemas")
    schemas_module.NotificationType = types.SimpleNamespace(Plugin="Plugin")
    apscheduler_module = types.ModuleType("apscheduler")
    triggers_module = types.ModuleType("apscheduler.triggers")
    cron_module = types.ModuleType("apscheduler.triggers.cron")
    cron_module.CronTrigger = types.SimpleNamespace(from_crontab=lambda expr: expr)

    sys.modules.update(
        {
            "apscheduler": apscheduler_module,
            "apscheduler.triggers": triggers_module,
            "apscheduler.triggers.cron": cron_module,
            "app": app_module,
            "app.core": core_module,
            "app.core.config": config_module,
            "app.log": log_module,
            "app.plugins": plugins_module,
            "app.scheduler": scheduler_module,
            "app.schemas": schemas_module,
        }
    )

    spec = importlib.util.spec_from_file_location("checkin_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FakePlugin:
    USER_AGENT = "test-agent"
    plugin_name = "自用签到工具"
    _timeout = 10
    _retry_count = 1

    @staticmethod
    def _to_bool(value):
        return bool(value)

    @staticmethod
    def _mask_email(email):
        return "masked@example.com" if email else "-"

    @staticmethod
    def _is_already_checked_in(message):
        return "已签到" in (message or "")

    @staticmethod
    def _clean_text(text):
        import re

        cleaned = re.sub(r"<[^>]+>", " ", text or "")
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    @staticmethod
    def _extract_dialog_message(text):
        return ""

    @staticmethod
    def _format_request_error(err, use_proxy=None):
        return str(err)

    @staticmethod
    def _get_proxies(use_proxy=None):
        return {"https": "http://proxy.local:7890"} if use_proxy else None


class YpojieAccountPasswordTest(unittest.TestCase):
    def test_ypojie_uses_account_password_config(self):
        module = load_checkin_module()
        adapter = module.YpojieSiteAdapter(FakePlugin())

        self.assertEqual(adapter.mode, "账号密码")
        self.assertEqual(
            adapter.default_config(),
            {
                "enabled": False,
                "use_proxy": False,
                "email": "",
                "password": "",
            },
        )
        self.assertTrue(adapter.is_configured({"email": "user@example.com", "password": "secret"}))
        self.assertEqual(
            adapter.validate_config({"enabled": True, "email": "", "password": ""}),
            [
                "易破解还没填账号",
                "易破解还没填密码",
            ],
        )


# 恩山的签到页正文，留了真机上关键的那几处：全站签到人数、签到按钮、三行读数
RIGHT_FORUM_PAGE = """
<title>恩山无线论坛 -  Powered by Discuz!</title>
<input type="hidden" name="formhash" value="043eec36" />
<div class="erqd-todays-count">今日已签到：<span class="erqd-count">2818</span> 人</div>
<button id="signin-btn" class="erqd-checkin-btn">立即签到</button>
<div class="erqd-points-container">
  <div>今日积分： 1</div>
  <div>连续签到： 2 天</div>
  <div>总签到天数： 22 天</div>
</div>
"""

# 人机验证挑战页：HTTP 200，正文只有一段重置 CSS 加一坨 JS，任何关键词都命中不了
CHALLENGE_PAGE = (
    "<!doctypehtml><meta charset=\"UTF-8\"><title></title>"
    "<style type=\"text/css\">body,div,html,p,span{margin:0;padding:0;border:0}</style>"
    "<script>void 0===window.console&&(console={log:function(){}}),window._waf_is_mobile=!1"
    "</script><textarea id=\"renderData\">var requestInfo = {\"sceneId\":\"19x5u7lo\"};</textarea>"
)


class RightForumStatsTest(unittest.TestCase):
    def test_stats_line_is_read_off_the_page(self):
        module = load_checkin_module()
        adapter = module.RightForumSiteAdapter(FakePlugin())
        self.assertEqual(
            adapter._extract_right_forum_stats(RIGHT_FORUM_PAGE),
            "今日积分：1；连续签到：2 天；总签到天数：22 天",
        )

    def test_site_wide_counter_is_not_my_own_state(self):
        """页面上那句「今日已签到：2818 人」是全站人数。

        拿它当自己的状态，插件就会一天都不真发签到请求 —— 所以现在只认接口回的 JSON，
        页面正文一个关键词都不猜。
        """
        module = load_checkin_module()
        adapter = module.RightForumSiteAdapter(FakePlugin())
        self.assertFalse(hasattr(adapter, "_is_right_forum_already"))
        self.assertFalse(hasattr(adapter, "_evaluate_current_page"))

    def test_challenge_page_is_named_not_dumped(self):
        """挑战页以前被截成一句 `body,div,html,p,span{margin:0…` 当失败原因报出来。"""
        module = load_checkin_module()
        adapter = module.RightForumSiteAdapter(FakePlugin())
        self.assertTrue(adapter._is_challenge(CHALLENGE_PAGE))
        self.assertFalse(adapter._is_challenge(RIGHT_FORUM_PAGE))
        with self.assertRaises(RuntimeError) as caught:
            adapter._ensure_usable(CHALLENGE_PAGE)
        self.assertIn("人机验证", str(caught.exception))

    def test_missing_plugin_module_is_named(self):
        """`?id=erling_qd:sign` 少了 `_in`，站点回的是这句；以前它被当成签到失败原因。"""
        module = load_checkin_module()
        adapter = module.RightForumSiteAdapter(FakePlugin())
        with self.assertRaises(RuntimeError) as caught:
            adapter._ensure_usable("指定的插件模块文件(./source/plugin/erling_qd/sign.inc.php)不存在或存在语法错误")
        self.assertIn("签到插件当前不可用", str(caught.exception))

    def test_rewrite_url_matches_the_plugin_module(self):
        """Discuz 的 `<插件>-<模块>.html` 等价于 `plugin.php?id=<插件>:<模块>`，两条必须同模块。"""
        module = load_checkin_module()
        adapter = module.RightForumSiteAdapter(FakePlugin())
        self.assertEqual(adapter.sign_page, "/plugin.php?id=erling_qd:sign_in")
        self.assertEqual(adapter.sign_page_rewrite, "/erling_qd-sign_in.html")
        self.assertIn("erling_qd:sign_in", adapter.sign_page)

    def test_stats_prefer_the_json_reading(self):
        """credit 就是这一次到手的分，比事后再拉一遍页面准，也省一个请求。"""
        module = load_checkin_module()
        adapter = module.RightForumSiteAdapter(FakePlugin())
        self.assertEqual(
            adapter._stats_from_payload(
                {"success": True, "credit": 1, "continuous_days": 2, "message": "签到成功"},
                "连续签到：0 天；总签到天数：28 天",
            ),
            "今日积分：1；连续签到：2 天；总签到天数：28 天",
        )

    def test_stats_fall_back_to_the_page_when_json_is_bare(self):
        module = load_checkin_module()
        adapter = module.RightForumSiteAdapter(FakePlugin())
        self.assertEqual(
            adapter._stats_from_payload({"success": False, "message": "今日已签到"}, "连续签到：2 天"),
            "连续签到：2 天",
        )


if __name__ == "__main__":
    unittest.main()


class RightForumSignTest(unittest.TestCase):
    """签到那一步：照页面上那段 JS 发同一个 POST，只认它回的 JSON。"""

    def adapter(self, post_body, page=RIGHT_FORUM_PAGE):
        module = load_checkin_module()
        plugin = FakePlugin()
        calls = []

        def request_text(method, base_url, path, **kwargs):
            calls.append((method, path, kwargs.get("data")))
            if method == "GET":
                return page
            return post_body

        plugin._request_text = request_text
        plugin._extract_formhash = staticmethod(lambda text: "043eec36")
        return module.RightForumSiteAdapter(plugin), calls

    def test_success_reads_the_json(self):
        adapter, calls = self.adapter(
            '{"success":true,"credit":1,"continuous_days":2,"message":"\u7b7e\u5230\u6210\u529f"}'
        )
        result = adapter.run_checkin({"cookie": "rHEX_2132_auth=x; rHEX_2132_saltkey=y"})
        self.assertEqual(result["status"], "签到成功")
        self.assertEqual(result["message"], "今日积分：1；连续签到：2 天；总签到天数：22 天")
        self.assertEqual(calls[0][:2], ("GET", "/plugin.php?id=erling_qd:sign_in"))
        self.assertEqual(calls[1][:2], ("POST", "/plugin.php?id=erling_qd:action&action=sign"))
        self.assertEqual(calls[1][2], {"formhash": "043eec36"})

    def test_already_signed_is_not_a_failure(self):
        adapter, _ = self.adapter('{"success":false,"message":"今日已签到"}')
        result = adapter.run_checkin({"cookie": "rHEX_2132_auth=x; rHEX_2132_saltkey=y"})
        self.assertEqual(result["status"], "今日已签到")

    def test_source_check_failure_says_what_to_do(self):
        adapter, _ = self.adapter('{"success":false,"message":"请求来源验证失败"}')
        with self.assertRaises(RuntimeError) as caught:
            adapter.run_checkin({"cookie": "rHEX_2132_auth=x; rHEX_2132_saltkey=y"})
        self.assertIn("来源校验失败", str(caught.exception))

    def test_non_json_response_is_summarised(self):
        """接口回了一页 HTML（挡在前面的网关之类），别把整页当原因抄出来。"""
        adapter, _ = self.adapter("<html><body>502 Bad Gateway</body></html>")
        with self.assertRaises(RuntimeError) as caught:
            adapter.run_checkin({"cookie": "rHEX_2132_auth=x; rHEX_2132_saltkey=y"})
        reason = str(caught.exception)
        self.assertIn("没回 JSON", reason)
        self.assertLessEqual(len(reason), 80)

    def test_challenge_on_the_sign_page_is_named(self):
        adapter, _ = self.adapter("{}", page=CHALLENGE_PAGE)
        with self.assertRaises(RuntimeError) as caught:
            adapter.run_checkin({"cookie": "rHEX_2132_auth=x; rHEX_2132_saltkey=y"})
        self.assertIn("人机验证", str(caught.exception))

    def test_missing_cookie_is_refused_early(self):
        adapter, calls = self.adapter("{}")
        with self.assertRaises(ValueError):
            adapter.run_checkin({"cookie": "  "})
        self.assertEqual(calls, [])

    def test_repeat_sign_is_reported_as_already_signed(self):
        """站点对重复签到也回 success=true、message 还是「签到成功」，只有 credit 归零。

        当天第一次是 credit:1，之后每次都是 credit:0。只认 success 就会天天报「已签到」，
        把「今天早就签过了」说成这一次的战果。
        """
        adapter, _ = self.adapter(
            '{"success":true,"credit":0,"continuous_days":"2","message":"签到成功"}'
        )
        result = adapter.run_checkin({"cookie": "rHEX_2132_auth=x; rHEX_2132_saltkey=y"})
        self.assertEqual(result["status"], "今日已签到")

    def test_first_sign_of_the_day_is_a_success(self):
        adapter, _ = self.adapter(
            '{"success":true,"credit":1,"continuous_days":2,"message":"签到成功"}'
        )
        result = adapter.run_checkin({"cookie": "rHEX_2132_auth=x; rHEX_2132_saltkey=y"})
        self.assertEqual(result["status"], "签到成功")
        self.assertIn("今日积分：1", result["message"])
