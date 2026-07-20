import unittest
from unittest.mock import Mock

from app.core.event import Event
from app.schemas.types import EventType

try:
    from plugins.p115liteassistant import P115LiteAssistant
except ModuleNotFoundError:
    from app.plugins.p115liteassistant import P115LiteAssistant


class FakeStore:
    """提供媒体整理事件测试所需的最小插件配置。"""

    def __init__(self, config):
        self._config = config

    def get_config(self):
        """返回当前插件配置。"""
        return dict(self._config)


class TransferUploadTest(unittest.TestCase):
    """验证媒体整理完成后目录上传的触发条件。"""

    @staticmethod
    def build_plugin(config):
        """构造仅包含事件处理依赖的插件实例。"""
        plugin = object.__new__(P115LiteAssistant)
        plugin._store = FakeStore(config)
        plugin._api = Mock()
        return plugin

    @staticmethod
    def transfer_event():
        """构造 MoviePilot 的媒体整理完成事件。"""
        return Event(EventType.TransferComplete, {"fileitem": object()})

    def test_enabled_plugin_triggers_incremental_upload(self):
        plugin = self.build_plugin(
            {
                "enabled": True,
                "upload_mappings": [{"enabled": True, "source": "/media", "target": "/115"}],
            }
        )

        plugin.upload_after_transfer_complete(self.transfer_event())

        plugin._api.trigger_upload.assert_called_once_with(True)

    def test_disabled_plugin_does_not_trigger_upload(self):
        plugin = self.build_plugin(
            {
                "enabled": False,
                "upload_mappings": [{"enabled": True, "source": "/media", "target": "/115"}],
            }
        )

        plugin.upload_after_transfer_complete(self.transfer_event())

        plugin._api.trigger_upload.assert_not_called()

    def test_plugin_without_enabled_upload_mapping_does_not_trigger_upload(self):
        plugin = self.build_plugin(
            {
                "enabled": True,
                "upload_mappings": [{"enabled": False, "source": "/media", "target": "/115"}],
            }
        )

        plugin.upload_after_transfer_complete(self.transfer_event())

        plugin._api.trigger_upload.assert_not_called()
