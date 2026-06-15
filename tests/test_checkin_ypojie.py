from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


def load_checkin_module():
    root = Path(__file__).resolve().parents[1]
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


class FakeResponse:
    def __init__(self, text="", status_code=200, payload=None, url="https://www.ypojie.com/vip"):
        self.text = text
        self.status_code = status_code
        self._payload = payload
        self.url = url
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.calls = []
        self.vip_calls = 0

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if url.endswith("/wp-login.php"):
            return FakeResponse('<input name="log"><input name="pwd">', url=url)
        if url.endswith("/vip"):
            self.vip_calls += 1
            balance = "92.00" if self.vip_calls == 1 else "93.00"
            return FakeResponse(f"Hi, tester 今日签到 个人中心 我的资产 可用余额 {balance}积分", url=url)
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if url.endswith("/wp-login.php"):
            return FakeResponse("dashboard", url="https://www.ypojie.com/vip")
        if url.endswith("/wp-admin/admin-ajax.php"):
            return FakeResponse(payload={"status": 200, "msg": None}, url=url)
        raise AssertionError(f"unexpected POST {url}")


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
                "易破解已启用但未填写账号",
                "易破解已启用但未填写密码",
            ],
        )

    def test_ypojie_logs_in_with_wordpress_credentials_and_reuses_session(self):
        module = load_checkin_module()
        fake_session = FakeSession()
        original_session = module.requests.Session
        module.requests.Session = lambda: fake_session
        try:
            adapter = module.YpojieSiteAdapter(FakePlugin())

            result = adapter.run_checkin(
                {
                    "enabled": True,
                    "use_proxy": True,
                    "email": "user@example.com",
                    "password": "secret",
                }
            )
        finally:
            module.requests.Session = original_session

        self.assertEqual(result["status"], "签到成功")
        self.assertEqual(result["message"], "本次签到增加：1积分")
        self.assertEqual(result["account"], "masked@example.com")

        login_posts = [call for call in fake_session.calls if call[0] == "POST" and call[1].endswith("/wp-login.php")]
        self.assertEqual(len(login_posts), 1)
        login_data = login_posts[0][2]["data"]
        self.assertEqual(login_data["log"], "user@example.com")
        self.assertEqual(login_data["pwd"], "secret")
        self.assertEqual(login_data["rememberme"], "forever")
        self.assertEqual(login_data["redirect_to"], "https://www.ypojie.com/vip")
        self.assertEqual(login_data["testcookie"], "1")

        ajax_posts = [call for call in fake_session.calls if call[0] == "POST" and call[1].endswith("/wp-admin/admin-ajax.php")]
        self.assertEqual(len(ajax_posts), 1)
        self.assertEqual(ajax_posts[0][2]["data"], {"action": "epd_checkin"})
        self.assertEqual(ajax_posts[0][2]["proxies"], {"https": "http://proxy.local:7890"})


class RightForumStatsTest(unittest.TestCase):
    def test_current_page_message_includes_checkin_stats(self):
        module = load_checkin_module()
        adapter = module.RightForumSiteAdapter(FakePlugin())

        result = adapter._evaluate_current_page(
            """
            <div class="erqd-points-container">
              <div>今日积分： 1</div>
              <div>连续签到： 2 天</div>
              <div>总签到天数： 22 天</div>
            </div>
            <div>今日已签到</div>
            """
        )

        self.assertEqual(result["status"], "今日已签到")
        self.assertEqual(result["message"], "今日积分：1；连续签到：2 天；总签到天数：22 天")


if __name__ == "__main__":
    unittest.main()
