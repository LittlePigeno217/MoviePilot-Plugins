import unittest
from unittest.mock import Mock, patch

from app.plugins.p115liteassistant.upload_watch import UploadWatcher


class UploadWatcherTest(unittest.TestCase):
    @patch("app.plugins.p115liteassistant.upload_watch.logger.warning")
    def test_missing_watchdog_reports_transfer_complete_fallback(self, warning):
        trigger = Mock()
        watcher = UploadWatcher(lambda: {}, trigger)
        watcher._observer_factory = None

        watcher.start()

        trigger.assert_not_called()
        message = warning.call_args.args[0]
        self.assertIn("媒体整理完成事件", message)
        self.assertNotIn("定时", message)


if __name__ == "__main__":
    unittest.main()
