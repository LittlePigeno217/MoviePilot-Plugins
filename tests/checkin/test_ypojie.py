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
                "易破解已启用但未填写账号",
                "易破解已启用但未填写密码",
            ],
        )


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
