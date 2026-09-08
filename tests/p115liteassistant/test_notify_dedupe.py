import unittest
from time import monotonic
from unittest.mock import Mock

from app.plugins.p115liteassistant.api import Api


class FakeStore:
    """提供通知去重测试所需的最小配置读取。"""

    def __init__(self, config):
        self._config = dict(config)

    def get_config(self):
        return dict(self._config)


def build_api(config):
    """构造带 Mock 通知器的 Api：is_enabled 恒真，飞书卡片恒发成功。"""
    notifier = Mock()
    notifier.is_enabled.return_value = True
    notifier.send_upload_feishu_card.return_value = True
    api = Api(lambda: Mock(), FakeStore(config), notifier=notifier)
    return api, notifier


UPLOAD_ENTRY = {
    "errors": 0,
    "per_file_details": [
        {"method": "upload", "name": "Film.mkv", "local_path": ""},
    ],
}

EMPTY_TOTALS = {
    "added": 0,
    "updated": 0,
    "removed": 0,
    "sidecars": 0,
    "skipped": 0,
    "errors": 0,
    "duration_ms": 5,
}


class StrmNotifyQuietTest(unittest.TestCase):
    """验证「上传 + 生成 STRM」一张卡说完入库，STRM 通道不再叠卡。"""

    def test_upload_card_suppresses_strm_card_within_window(self):
        api, notifier = build_api({"upload_generate_strm": True})

        api._notify_upload(dict(UPLOAD_ENTRY), True)
        api._notify_strm([], dict(EMPTY_TOTALS), True)

        # 只发过上传那张卡，STRM 卡被抑制
        notifier.send_upload_feishu_card.assert_called_once()
        self.assertNotIn("STRM 同步", notifier.send_upload_feishu_card.call_args.args[0])

    def test_strm_card_returns_after_window_expires(self):
        api, notifier = build_api({"upload_generate_strm": True})

        api._notify_upload(dict(UPLOAD_ENTRY), True)
        api._strm_notify_quiet_until = monotonic() - 1
        api._notify_strm([], dict(EMPTY_TOTALS), True)

        self.assertEqual(notifier.send_upload_feishu_card.call_count, 2)

    def test_upload_without_strm_generation_does_not_suppress(self):
        api, notifier = build_api({"upload_generate_strm": False})

        api._notify_upload(dict(UPLOAD_ENTRY), True)
        api._notify_strm([], dict(EMPTY_TOTALS), True)

        self.assertEqual(notifier.send_upload_feishu_card.call_count, 2)

    def test_silent_upload_does_not_arm_suppression(self):
        api, notifier = build_api({"upload_generate_strm": True})

        # 没传东西也没失败：上传通道不发卡，也不该抑制 STRM
        api._notify_upload({"errors": 0, "per_file_details": []}, True)
        api._notify_strm([], dict(EMPTY_TOTALS), True)

        notifier.send_upload_feishu_card.assert_called_once()
        self.assertIn("STRM", notifier.send_upload_feishu_card.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
