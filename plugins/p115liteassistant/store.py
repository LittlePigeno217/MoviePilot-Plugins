from __future__ import annotations

from copy import deepcopy
from secrets import token_hex
from threading import RLock
from typing import Any, Dict, List

from .records import IncrementalRecordStore, TaskHistory


DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "cookie": "",
    "tokens": {},
    "login_client_type": "",
    "moviepilot_address": "",
    "link_redirect_mode": "cookie",
    "strm_incremental": True,
    "strm_download_sidecars": False,
    "strm_mappings": [],
    "upload_mappings": [],
    "upload_include_sidecars": True,
    "upload_generate_strm": False,
    "upload_delete_source": False,
    "upload_media_extensions": ".mp4,.mkv,.ts,.iso,.rmvb,.avi,.mov,.mpeg,.mpg,.wmv,.3gp,.asf,.m4v,.flv,.m2ts,.tp,.f4v",
    "upload_sidecar_extensions": ".nfo,.jpg,.jpeg,.png,.webp,.srt,.ass,.ssa,.sup",
    "checkin_enabled": False,
    "checkin_cron": "15 8 * * *",
    "checkin_time_range": "06:00-09:00",
    "same_playback": False,
}


class Store:
    """所有状态都通过插件实例持久化，避免与其他 115 插件共享数据。"""

    _CONFIG_KEY = "p115liteassistant_config"
    _STRM_RECORDS_KEY = "p115liteassistant_strm_records"
    _UPLOAD_RECORDS_KEY = "p115liteassistant_upload_records"
    _HISTORY_KEY = "p115liteassistant_history"
    _CHECKIN_SCHEDULE_KEY = "p115liteassistant_checkin_schedule"
    _REDIRECT_SECRET_KEY = "p115liteassistant_redirect_secret"

    def __init__(self, plugin):
        self._plugin = plugin
        self._config_lock = RLock()

    def get_config(self) -> Dict[str, Any]:
        with self._config_lock:
            config = deepcopy(DEFAULT_CONFIG)
            saved = self._plugin.get_data(self._CONFIG_KEY) or {}
            if isinstance(saved, dict):
                config.update({key: value for key, value in saved.items() if key in DEFAULT_CONFIG})
            return config

    def save_config(self, config: Dict[str, Any]) -> None:
        with self._config_lock:
            self._plugin.save_data(self._CONFIG_KEY, config)

    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        with self._config_lock:
            config = self.get_config()
            config.update({key: value for key, value in updates.items() if key in DEFAULT_CONFIG})
            self.save_config(config)
            return config

    def get_strm_records(self) -> Dict[str, Dict[str, Any]]:
        records = self._plugin.get_data(self._STRM_RECORDS_KEY) or {}
        return records if isinstance(records, dict) else {}

    def save_strm_records(self, records: Dict[str, Dict[str, Any]]) -> None:
        self._plugin.save_data(self._STRM_RECORDS_KEY, records)

    def get_redirect_secret(self) -> str:
        with self._config_lock:
            secret = self._plugin.get_data(self._REDIRECT_SECRET_KEY)
            if isinstance(secret, str) and len(secret) >= 32:
                return secret
            secret = token_hex(32)
            self._plugin.save_data(self._REDIRECT_SECRET_KEY, secret)
            return secret

    def get_upload_records(self) -> IncrementalRecordStore:
        records = self._plugin.get_data(self._UPLOAD_RECORDS_KEY) or {}
        return IncrementalRecordStore(records if isinstance(records, dict) else {})

    def save_upload_records(self, records: IncrementalRecordStore) -> None:
        self._plugin.save_data(self._UPLOAD_RECORDS_KEY, records.to_dict())

    def get_history(self) -> List[Dict[str, Any]]:
        items = self._plugin.get_data(self._HISTORY_KEY) or []
        return list(items) if isinstance(items, list) else []

    def append_history(self, item: Dict[str, Any]) -> None:
        history = TaskHistory(self.get_history())
        history.add(item)
        self._plugin.save_data(self._HISTORY_KEY, history.items)

    def get_checkin_schedule(self) -> Dict[str, Any]:
        state = self._plugin.get_data(self._CHECKIN_SCHEDULE_KEY) or {}
        return dict(state) if isinstance(state, dict) else {}

    def save_checkin_schedule(self, state: Dict[str, Any]) -> None:
        self._plugin.save_data(self._CHECKIN_SCHEDULE_KEY, dict(state))
