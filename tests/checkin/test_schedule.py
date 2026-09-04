"""定时任务的注册、时区与漏签补跑。

这些用例守的是「有某些天没有定时执行」那一类故障：APScheduler 默认
misfire_grace_time=1，错过 1 秒就丢弃整次触发；插件自己的 /config 接口保存配置时
MoviePilot 不会帮忙重装任务；remove_plugin_job() 认的是插件 id 而不是 job id。
三处任一回归，定时签到都会在用户毫无察觉的情况下停摆。
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path


def _restore_real_apscheduler() -> None:
    """把 sys.modules 里被别的用例替换过的 apscheduler 换回真货。

    同进程内 test_ypojie 会注册一份只接受单参数的 from_crontab 假桩，而「时区」与
    「今天该不该触发」这两件事只有真实 CronTrigger 才验证得出来。
    """
    for name in [key for key in list(sys.modules) if key == "apscheduler" or key.startswith("apscheduler.")]:
        del sys.modules[name]
    importlib.import_module("apscheduler.triggers.cron")


class RecordingScheduler:
    """记下插件对调度器说过的每一句话。"""

    def __init__(self) -> None:
        self.removed: list = []
        self.updated: list = []
        self.tasks: list = []

    def remove_plugin_job(self, pid):
        self.removed.append(pid)

    def update_plugin_job(self, pid):
        self.updated.append(pid)

    def list(self):
        return list(self.tasks)


class FakePluginBase:
    """_PluginBase 的替身：只提供插件真正用到的那几个宿主能力。"""

    def __init__(self) -> None:
        self.data: dict = {}
        self.saved_config: dict | None = None
        self.messages: list = []

    def get_data(self, key: str):
        return self.data.get(key)

    def save_data(self, key: str, value) -> None:
        self.data[key] = value

    def update_config(self, config: dict) -> None:
        self.saved_config = dict(config)

    def post_message(self, **kwargs) -> None:
        self.messages.append(kwargs)


def load_checkin(scheduler: RecordingScheduler, tz: str = "Asia/Shanghai"):
    """用真实 apscheduler + MoviePilot 桩加载插件模块。"""
    _restore_real_apscheduler()
    root = Path(__file__).resolve().parents[2]
    module_path = root / "plugins" / "checkin" / "__init__.py"

    config_module = types.ModuleType("app.core.config")
    config_module.settings = types.SimpleNamespace(PROXY=None, TZ=tz)
    log_module = types.ModuleType("app.log")
    quiet = lambda *a, **k: None  # noqa: E731
    log_module.logger = types.SimpleNamespace(info=quiet, warning=quiet, error=quiet, debug=quiet)
    plugins_module = types.ModuleType("app.plugins")
    plugins_module._PluginBase = FakePluginBase
    scheduler_module = types.ModuleType("app.scheduler")
    scheduler_module.Scheduler = lambda: scheduler
    schemas_module = types.ModuleType("app.schemas")
    schemas_module.NotificationType = types.SimpleNamespace(Plugin="Plugin")

    sys.modules.update({
        "app": types.ModuleType("app"),
        "app.core": types.ModuleType("app.core"),
        "app.core.config": config_module,
        "app.log": log_module,
        "app.plugins": plugins_module,
        "app.scheduler": scheduler_module,
        "app.schemas": schemas_module,
    })

    spec = importlib.util.spec_from_file_location("checkin_schedule_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def make_plugin(scheduler: RecordingScheduler, **config):
    module = load_checkin(scheduler)
    plugin = module.Checkin()
    payload = {
        "enabled": True,
        "notify": False,
        "cron": "10 8 * * *",
        "sites": {"flzt": {"enabled": True, "email": "a@b.c", "password": "x"}},
    }
    payload.update(config)
    plugin.init_plugin(payload)
    return plugin


class TimerCleanupMixin:
    """每次 init_plugin 都会挂一个启动兜底定时器，用例跑完要收掉。"""

    def cleanup_timer(self, plugin) -> None:
        timer = getattr(plugin.__class__, '_boot_timer', None)
        if timer:
            timer.cancel()
            plugin.__class__._boot_timer = None


class ServiceRegistrationTest(TimerCleanupMixin, unittest.TestCase):
    def setUp(self) -> None:
        self.scheduler = RecordingScheduler()

    def test_registers_main_job_and_catchup_sweep(self):
        """两条任务：用户的 cron，加一条每 30 分钟的漏签补跑。"""
        plugin = make_plugin(self.scheduler)
        services = plugin.get_service()
        self.assertEqual([item["id"] for item in services], ["checkin", "checkin_catchup"])
        self.assertEqual(services[0]["func"], plugin._scheduled_run)
        self.assertEqual(services[1]["func"], plugin._catchup_run)

    def test_jobs_survive_a_missed_fire_time(self):
        """kwargs 会被原样展开进 add_job()，调度参数必须在里面。

        少了 misfire_grace_time，APScheduler 用默认的 1 秒：NAS 休眠、容器抢 CPU、
        MoviePilot 恰好重启，当天就被静默跳过。
        """
        services = make_plugin(self.scheduler).get_service()
        for service in services:
            self.assertEqual(service["kwargs"]["misfire_grace_time"], 1800)
            self.assertTrue(service["kwargs"]["coalesce"])
            self.assertEqual(service["kwargs"]["max_instances"], 1)

    def test_trigger_follows_moviepilot_timezone(self):
        """不显式传 settings.TZ 的话，触发时刻会跟着容器的 /etc/localtime 走偏。"""
        trigger = make_plugin(self.scheduler)._build_trigger("10 8 * * *")
        self.assertEqual(str(trigger.timezone), "Asia/Shanghai")

    def test_disabled_plugin_registers_nothing(self):
        self.assertEqual(make_plugin(self.scheduler, enabled=False).get_service(), [])

    def test_invalid_cron_registers_nothing(self):
        self.assertEqual(make_plugin(self.scheduler, cron="每天八点").get_service(), [])

    def test_stop_service_addresses_the_plugin_id(self):
        """remove_plugin_job() 按插件 id 匹配，传小写类名会静默失配。"""
        make_plugin(self.scheduler).stop_service()
        self.assertIn("Checkin", self.scheduler.removed)
        self.assertNotIn("checkin", self.scheduler.removed)

    def test_saving_config_reinstalls_the_job(self):
        """插件的 /config 走自己的接口，框架不会帮忙重装任务 —— 必须自己叫一次。"""
        plugin = make_plugin(self.scheduler)
        self.scheduler.updated.clear()
        result = plugin._save_config({
            "enabled": True,
            "cron": "30 7 * * *",
            "sites": {"flzt": {"enabled": True, "email": "a@b.c", "password": "x"}},
        })
        self.assertTrue(result["success"])
        self.assertEqual(self.scheduler.updated, ["Checkin"])
        self.assertEqual(plugin._cron, "30 7 * * *")
        _, fire = plugin._today_schedule()
        self.assertEqual(fire.strftime("%H:%M"), "07:30")

    def test_status_reports_the_main_job_not_the_sweep(self):
        """两条任务都由本插件提供，按 provider 匹配会把「下次」说成几分钟后的巡检。"""
        plugin = make_plugin(self.scheduler)
        self.scheduler.tasks = [
            types.SimpleNamespace(id="checkin_catchup", provider=plugin.plugin_name, status="等待", next_run="12分钟"),
            types.SimpleNamespace(id="checkin", provider=plugin.plugin_name, status="等待", next_run="9小时30分钟"),
        ]
        data = plugin._get_status()["data"]
        self.assertEqual(data["next_run_time"], "9 小时 30 分钟后")


class StubAdapter:
    """假站点：记下被要求签到过几次，永远成功。"""

    site_key = "flzt"
    site_name = "FLZT"
    mode = "账号密码"

    def __init__(self) -> None:
        self.calls = 0

    def validate_config(self, site_config):
        return []

    def is_configured(self, site_config):
        return True

    def get_account_label(self, site_config):
        return "a@b.c"

    def run_checkin(self, site_config):
        self.calls += 1
        return {
            "site": self.site_key,
            "site_name": self.site_name,
            "status": "签到成功",
            "message": "签到成功",
            "reward_mb": "16",
            "total_traffic": "1.00 GB",
            "account": "a@b.c",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


def freeze(plugin, *, now: str, fire: str | None) -> None:
    """固定「此刻」与「今天该跑的时刻」，让补跑闸门与真实钟表脱钩。"""
    now_dt = datetime.strptime(now, "%Y-%m-%d %H:%M")
    fire_dt = datetime.strptime(fire, "%Y-%m-%d %H:%M") if fire else None
    plugin._today_schedule = lambda: (now_dt, fire_dt)


class CatchupTest(TimerCleanupMixin, unittest.TestCase):
    """漏签补跑的四道闸门：不该跑不跑，该跑就跑，跑过不重复。"""

    def setUp(self) -> None:
        self.scheduler = RecordingScheduler()
        self.plugin = make_plugin(self.scheduler)
        self.adapter = StubAdapter()
        self.plugin._adapters = {"flzt": self.adapter}

    def tearDown(self) -> None:
        self.cleanup_timer(self.plugin)

    def record(self, day: str, *, failure: int, site_count: int = 1) -> None:
        """往历史里塞一条当天的执行记录。"""
        self.plugin.save_data("history", [{
            "version": 2,
            "time": f"{day} 08:10:02",
            "status": "全部成功" if not failure else "执行失败",
            "message": "-",
            "success_count": site_count - failure,
            "failure_count": failure,
            "site_count": site_count,
            "details": [
                {"site": "flzt", "site_name": "FLZT", "status": "签到成功" if index >= failure else "执行失败",
                 "message": "-", "account": "a@b.c", "reward_mb": "-", "total_traffic": "-", "time": f"{day} 08:10:02"}
                for index in range(site_count)
            ],
        }])

    def test_catches_up_a_day_the_scheduler_skipped(self):
        """机器在 08:10 那会儿没在跑，醒来后巡检把这天补上。"""
        freeze(self.plugin, now="2026-09-03 10:00", fire="2026-09-03 08:10")
        self.plugin._catchup_run()
        self.assertEqual(self.adapter.calls, 1)
        self.assertEqual(self.plugin.get_data("catchup_state"), {"day": "2026-09-03", "count": 1})

    def test_waits_when_the_hour_has_not_come(self):
        """还没到点，主任务自己会跑，巡检不抢。"""
        freeze(self.plugin, now="2026-09-03 06:00", fire="2026-09-03 08:10")
        self.plugin._catchup_run()
        self.assertEqual(self.adapter.calls, 0)

    def test_skips_a_day_already_fully_signed(self):
        """今天已经一个不落地签完，绝不再签第二遍。"""
        self.record("2026-09-03", failure=0)
        freeze(self.plugin, now="2026-09-03 10:00", fire="2026-09-03 08:10")
        self.plugin._catchup_run()
        self.assertEqual(self.adapter.calls, 0)

    def test_retries_a_day_that_partly_failed(self):
        """跑过但有站点失败：留着机会等网络恢复。"""
        self.record("2026-09-03", failure=1, site_count=2)
        freeze(self.plugin, now="2026-09-03 10:00", fire="2026-09-03 08:10")
        self.plugin._catchup_run()
        self.assertEqual(self.adapter.calls, 1)

    def test_stops_after_the_daily_retry_budget(self):
        """补到上限就收手，不能一天对站点发几十次请求。"""
        self.plugin.save_data("catchup_state", {"day": "2026-09-03", "count": self.plugin.CATCHUP_MAX_PER_DAY})
        freeze(self.plugin, now="2026-09-03 10:00", fire="2026-09-03 08:10")
        self.plugin._catchup_run()
        self.assertEqual(self.adapter.calls, 0)

    def test_budget_resets_on_a_new_day(self):
        """昨天补满了不影响今天。"""
        self.plugin.save_data("catchup_state", {"day": "2026-09-02", "count": self.plugin.CATCHUP_MAX_PER_DAY})
        freeze(self.plugin, now="2026-09-03 10:00", fire="2026-09-03 08:10")
        self.plugin._catchup_run()
        self.assertEqual(self.adapter.calls, 1)

    def test_ignores_days_the_cron_never_fires(self):
        """cron 是每周一，今天是周四 —— 今天本来就不该签。"""
        freeze(self.plugin, now="2026-09-03 10:00", fire=None)
        self.plugin._catchup_run()
        self.assertEqual(self.adapter.calls, 0)

    def test_disabled_plugin_never_catches_up(self):
        plugin = make_plugin(self.scheduler, enabled=False)
        plugin._adapters = {"flzt": self.adapter}
        freeze(plugin, now="2026-09-03 10:00", fire="2026-09-03 08:10")
        plugin._catchup_run()
        self.assertEqual(self.adapter.calls, 0)

    def test_yields_to_a_run_already_in_flight(self):
        """定时、巡检、手动三条入口共用一把锁，签到接口经不起并发重放。"""
        freeze(self.plugin, now="2026-09-03 10:00", fire="2026-09-03 08:10")
        self.assertTrue(self.plugin._run_lock.acquire(blocking=False))
        try:
            self.plugin._catchup_run()
            self.assertEqual(self.plugin._run_once_api()["message"], "已有一次签到正在执行，请稍后再试")
        finally:
            self.plugin._run_lock.release()
        self.assertEqual(self.adapter.calls, 0)

    def test_status_surfaces_a_pending_catchup(self):
        """台账页要能说清「今天那一次到底跑了没有」。"""
        freeze(self.plugin, now="2026-09-03 10:00", fire="2026-09-03 08:10")
        catchup = self.plugin._get_status()["data"]["catchup"]
        self.assertEqual(catchup["due_at"], "08:10")
        self.assertTrue(catchup["pending"])
        self.record("2026-09-03", failure=0)
        self.assertFalse(self.plugin._get_status()["data"]["catchup"]["pending"])


if __name__ == "__main__":
    unittest.main()


class BootRegistrationTest(TimerCleanupMixin, unittest.TestCase):
    """启动兜底：MoviePilot 的批量注册漏掉本插件时，插件自己把任务装回去。

    真机上这是「有些天不签到」最直接的原因 —— 容器重启后
    /api/v1/dashboard/schedule2 里一条 checkin 任务都没有，且日志毫无异常，
    直到有人保存一次配置才补上。
    """

    def setUp(self) -> None:
        self.scheduler = RecordingScheduler()

    def test_init_arms_a_boot_timer(self):
        plugin = make_plugin(self.scheduler)
        self.addCleanup(self.cleanup_timer, plugin)
        timer = plugin.__class__._boot_timer
        self.assertIsNotNone(timer)
        self.assertTrue(timer.daemon)
        self.assertEqual(timer.interval, plugin.BOOT_REGISTER_DELAY)

    def test_disabled_plugin_arms_nothing(self):
        plugin = make_plugin(self.scheduler, enabled=False)
        self.addCleanup(self.cleanup_timer, plugin)
        self.assertIsNone(plugin.__class__._boot_timer)

    def test_stop_service_cancels_the_pending_timer(self):
        """停用插件后定时器不该再把任务装回来。"""
        plugin = make_plugin(self.scheduler)
        self.addCleanup(self.cleanup_timer, plugin)
        timer = plugin.__class__._boot_timer
        plugin.stop_service()
        self.assertIsNone(plugin.__class__._boot_timer)
        self.assertTrue(timer.finished.is_set())

    def test_registers_when_the_scheduler_is_missing_the_job(self):
        plugin = make_plugin(self.scheduler)
        self.addCleanup(self.cleanup_timer, plugin)
        self.scheduler.tasks = [types.SimpleNamespace(id="fnossign_fnossign", provider="飞牛论坛签到")]
        self.scheduler.updated.clear()
        plugin._register_if_absent()
        self.assertEqual(self.scheduler.updated, ["Checkin"])

    def test_leaves_an_already_registered_job_alone(self):
        """框架这次没漏掉，就别再摘一遍装一遍。"""
        plugin = make_plugin(self.scheduler)
        self.addCleanup(self.cleanup_timer, plugin)
        self.scheduler.tasks = [types.SimpleNamespace(id=plugin.JOB_ID, provider=plugin.plugin_name)]
        self.scheduler.updated.clear()
        plugin._register_if_absent()
        self.assertEqual(self.scheduler.updated, [])

    def test_recognizes_the_prefixed_job_id(self):
        """MoviePilot 2.15.6 的 job id 是 Checkin_checkin，不是 checkin。

        只认裸 service_id 的话，任务明明在位也会被判成缺失 —— 每次初始化都白摘装一轮，
        还刷一条说「调度器里没有本插件的定时任务」的 WARNING。
        """
        plugin = make_plugin(self.scheduler)
        self.addCleanup(self.cleanup_timer, plugin)
        self.scheduler.tasks = [
            types.SimpleNamespace(id="Checkin_checkin_catchup", provider=plugin.plugin_name),
            types.SimpleNamespace(id="Checkin_checkin", provider=plugin.plugin_name),
        ]
        self.scheduler.updated.clear()
        plugin._register_if_absent()
        self.assertEqual(self.scheduler.updated, [])

    def test_status_reads_the_prefixed_main_job(self):
        """状态页也要认得带前缀的主任务，否则「下次」会落到补跑巡检那条上。"""
        plugin = make_plugin(self.scheduler)
        self.addCleanup(self.cleanup_timer, plugin)
        self.scheduler.tasks = [
            types.SimpleNamespace(id="Checkin_checkin_catchup", provider=plugin.plugin_name, status="等待", next_run="15分钟"),
            types.SimpleNamespace(id="Checkin_checkin", provider=plugin.plugin_name, status="等待", next_run="9小时55分钟"),
        ]
        self.assertEqual(plugin._get_status()["data"]["next_run_time"], "9 小时 55 分钟后")
