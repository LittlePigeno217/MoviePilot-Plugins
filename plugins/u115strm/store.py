from typing import Any, Dict, List

try:  # 运行时作为包用相对导入；单测直接导入模块时回退绝对导入
    from .models import SyncRecord, HistoryEntry
except ImportError:  # pragma: no cover
    from models import SyncRecord, HistoryEntry

CONFIG_KEY = "config"
SYNC_STATE_KEY = "sync_state"
HISTORY_KEY = "history"

DEFAULT_CONFIG = {
    "cookie": "",
    "tokens": {},
    "app_id": "",
    "auth_server": "",
    "mappings": [],
    "schedule_cron": "",
    "incremental": True,
    "sync_metadata": False,
    "moviepilot_url": "",
}


class Store:
    """插件持久化，经宿主的 save_data/get_data 存取。"""

    def __init__(self, host: Any):
        self._host = host  # 提供 save_data(key, value) / get_data(key) 的对象（插件实例）

    def get_config(self) -> Dict:
        data = self._host.get_data(CONFIG_KEY) or {}
        return {**DEFAULT_CONFIG, **data}

    def save_config(self, config: Dict) -> None:
        self._host.save_data(CONFIG_KEY, config)

    def get_sync_state(self) -> Dict[str, dict]:
        return self._host.get_data(SYNC_STATE_KEY) or {}

    def set_sync_record(self, record: SyncRecord) -> None:
        state = self.get_sync_state()
        state[record.file_key] = record.to_dict()
        self._host.save_data(SYNC_STATE_KEY, state)

    def bulk_set_sync_records(self, records: List[SyncRecord]) -> None:
        if not records:
            return
        state = self.get_sync_state()
        for r in records:
            state[r.file_key] = r.to_dict()
        self._host.save_data(SYNC_STATE_KEY, state)

    def get_history(self) -> List[dict]:
        return self._host.get_data(HISTORY_KEY) or []

    def append_history(self, entry: HistoryEntry, keep: int = 100) -> None:
        history = self.get_history()
        history.insert(0, entry.to_dict())
        self._host.save_data(HISTORY_KEY, history[:keep])
