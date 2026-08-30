import unittest

from app.plugins.p115liteassistant.notify import (
    CHANNELS,
    DEFAULT_NOTIFY_TYPE,
    Notifier,
    normalize_notify_type,
)


class FakePoster:
    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)


class NotifyTypeTest(unittest.TestCase):
    def test_unknown_type_falls_back_to_plugin(self):
        self.assertEqual(normalize_notify_type("Nope"), DEFAULT_NOTIFY_TYPE)
        self.assertEqual(normalize_notify_type(None), DEFAULT_NOTIFY_TYPE)
        self.assertEqual(normalize_notify_type(""), DEFAULT_NOTIFY_TYPE)

    def test_known_type_kept(self):
        self.assertEqual(normalize_notify_type("SiteMessage"), "SiteMessage")


class NotifierTest(unittest.TestCase):
    def setUp(self):
        self.config = {key: False for meta in CHANNELS.values() for key in (meta["enabled_key"],)}
        self.poster = FakePoster()
        self.notifier = Notifier(lambda: self.config, poster=self.poster, title_prefix="115")

    def test_disabled_channel_sends_nothing(self):
        self.notifier.notify("strm", "完成", ["新增 1"])
        self.assertEqual(self.poster.calls, [])

    def test_channels_are_independent(self):
        self.config["checkin_notify"] = True
        self.assertFalse(self.notifier.is_enabled("strm"))
        self.assertFalse(self.notifier.is_enabled("upload"))
        self.assertTrue(self.notifier.is_enabled("checkin"))

        self.notifier.notify("strm", "完成", ["新增 1"])
        # None 占位符被跳过，空字符串保持为空白行分隔
        self.notifier.notify("checkin", "签到成功", ["连续 3 天", "", None, "+5 积分"])

        self.assertEqual(len(self.poster.calls), 1)
        call = self.poster.calls[0]
        self.assertEqual(call["title"], "115 · 每日签到 签到成功")
        self.assertEqual(call["text"], "连续 3 天\n\n+5 积分")

    def test_empty_body_becomes_placeholder(self):
        self.config["upload_notify"] = True
        self.notifier.notify("upload", "", [])
        self.assertEqual(self.poster.calls[0]["text"], "-")
        self.assertEqual(self.poster.calls[0]["title"], "115 · 上传通道")

    def test_unknown_channel_ignored(self):
        self.config["strm_notify"] = True
        self.notifier.notify("nope", "完成", ["x"])
        self.assertEqual(self.poster.calls, [])

    def test_poster_failure_does_not_raise(self):
        def boom(**_kwargs):
            raise RuntimeError("host down")

        self.config["strm_notify"] = True
        notifier = Notifier(lambda: self.config, poster=boom)
        notifier.notify("strm", "完成", ["新增 1"])

    def test_missing_poster_reports_disabled(self):
        self.config["strm_notify"] = True
        self.assertFalse(Notifier(lambda: self.config).is_enabled("strm"))

    def test_config_failure_reports_disabled(self):
        def boom():
            raise RuntimeError("no store")

        self.assertFalse(Notifier(boom, poster=self.poster).is_enabled("strm"))


if __name__ == "__main__":
    unittest.main()
