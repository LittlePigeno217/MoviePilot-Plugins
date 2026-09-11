import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, call

from app.core.event import Event
from app.schemas.types import EventType
from app.plugins.p115liteassistant import P115LiteAssistant


class FakeStore:
    def __init__(self, config): self._config = config
    def get_config(self): return dict(self._config)


class TransferUploadTest(unittest.TestCase):
    @staticmethod
    def build_plugin(config):
        plugin = object.__new__(P115LiteAssistant)
        plugin._store = FakeStore(config)
        plugin._upload_stability = Mock()
        return plugin

    def test_reliable_fileitem_path_submits_only_that_file(self):
        with TemporaryDirectory() as directory:
            movie = Path(directory) / "Film.mkv"; movie.write_bytes(b"x")
            plugin = self.build_plugin({"enabled": True})
            event = Event(EventType.TransferComplete, {"fileitem": type("Item", (), {"path": movie})()})
            plugin.upload_after_transfer_complete(event)
            plugin._upload_stability.submit_path.assert_called_once_with(str(movie), source="transfer")

    def test_rejected_absolute_path_falls_through_and_stops_after_first_accepted_path(self):
        plugin = self.build_plugin({"enabled": True})
        plugin._upload_stability.submit_path.side_effect = [False, True]
        event = Event(
            EventType.TransferComplete,
            {
                "target_path": "/downloads/rejected.mkv",
                "dest": "/media/accepted.mkv",
                "fileitem": {"path": "/media/must-not-be-tried.mkv"},
            },
        )

        plugin.upload_after_transfer_complete(event)

        self.assertEqual(
            plugin._upload_stability.submit_path.call_args_list,
            [
                call("/downloads/rejected.mkv", source="transfer"),
                call("/media/accepted.mkv", source="transfer"),
            ],
        )

    def test_missing_or_relative_path_does_not_trigger_full_scan(self):
        plugin = self.build_plugin({"enabled": True})
        for fileitem in (object(), {"path": "relative/Film.mkv"}):
            with self.subTest(fileitem=fileitem):
                plugin._upload_stability.reset_mock()
                plugin.upload_after_transfer_complete(Event(EventType.TransferComplete, {"fileitem": fileitem}))
                plugin._upload_stability.submit_path.assert_not_called()

    def test_disabled_plugin_does_not_submit(self):
        plugin = self.build_plugin({"enabled": False})
        plugin.upload_after_transfer_complete(Event(EventType.TransferComplete, {"target_path": "/media/Film.mkv"}))
        plugin._upload_stability.submit_path.assert_not_called()


if __name__ == "__main__":
    unittest.main()
