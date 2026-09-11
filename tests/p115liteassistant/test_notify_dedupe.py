import unittest
from time import monotonic
from unittest.mock import Mock

from app.plugins.p115liteassistant.api import Api as ProductionApi


from tests.p115liteassistant.helpers import make_test_journal


def Api(client_provider, store, *args, journal=None, **kwargs):
    return ProductionApi(
        client_provider, store, *args,
        journal=journal or make_test_journal(store), **kwargs
    )


class FakeStore:
    """提供通知去重测试所需的最小配置读取。"""

    def __init__(self, config):
        self._config = dict(config)

    def get_config(self):
        return dict(self._config)


def build_api(config):
    """构造带 Mock 通知器的 Api。"""
    notifier = Mock()
    notifier.is_enabled.return_value = True
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

        # 只发过上传通知，STRM 通知被抑制；飞书专用直发不再参与主路径
        notifier.notify.assert_called_once()
        notifier.send_upload_feishu_card.assert_not_called()

    def test_manual_strm_notice_returns_after_window_expires(self):
        api, notifier = build_api({"upload_generate_strm": True})

        api._notify_upload(dict(UPLOAD_ENTRY), True)
        api._strm_notify_quiet_until = monotonic() - 1
        api._notify_strm([], dict(EMPTY_TOTALS), True, manual=True)

        self.assertEqual(notifier.notify.call_count, 2)
        self.assertEqual(notifier.notify.call_args.args[1], "STRM 已是最新")

    def test_upload_without_strm_generation_does_not_suppress(self):
        api, notifier = build_api({"upload_generate_strm": False})

        api._notify_upload(dict(UPLOAD_ENTRY), True)
        api._notify_strm([], dict(EMPTY_TOTALS), True)

        # 自动 STRM 空跑默认静默，因此仍只有上传通知
        self.assertEqual(notifier.notify.call_count, 1)

    def test_silent_upload_does_not_arm_suppression(self):
        api, notifier = build_api({"upload_generate_strm": True})

        # 没传东西也没失败：上传通道不发卡，也不该抑制 STRM
        api._notify_upload({"errors": 0, "per_file_details": []}, True)
        api._notify_strm([], dict(EMPTY_TOTALS), True)

        notifier.notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
