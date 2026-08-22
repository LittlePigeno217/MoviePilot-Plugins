from __future__ import annotations

from base64 import urlsafe_b64encode
from copy import deepcopy
from hashlib import pbkdf2_hmac
from secrets import token_hex
from threading import RLock
from typing import Any, Dict, List

from .crypto import decrypt, decrypt_tokens, encrypt, encrypt_tokens
from .notify import DEFAULT_NOTIFY_TYPE, RESOURCE_NOTIFY_TYPE
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
    "strm_notify": False,
    "strm_notify_type": RESOURCE_NOTIFY_TYPE,
    "strm_mappings": [],
    "upload_mappings": [],
    "upload_notify": False,
    "upload_notify_type": RESOURCE_NOTIFY_TYPE,
    "upload_include_sidecars": True,
    "upload_generate_strm": False,
    "upload_delete_source": False,
    "upload_media_extensions": ".mp4,.mkv,.ts,.iso,.rmvb,.avi,.mov,.mpeg,.mpg,.wmv,.3gp,.asf,.m4v,.flv,.m2ts,.tp,.f4v",
    "upload_sidecar_extensions": ".nfo,.jpg,.jpeg,.png,.webp,.srt,.ass,.ssa,.sup",
    "checkin_enabled": False,
    "checkin_cron": "15 8 * * *",
    "checkin_time_range": "06:00-09:00",
    "checkin_notify": False,
    "checkin_notify_type": DEFAULT_NOTIFY_TYPE,
    "same_playback": False,
    "life_monitor_enabled": False,
}


class Store:
    """所有状态都通过插件实例持久化，避免与其他 115 插件共享数据。"""

    _CONFIG_KEY = "p115liteassistant_config"
    _STRM_RECORDS_KEY = "p115liteassistant_strm_records"
    _UPLOAD_RECORDS_KEY = "p115liteassistant_upload_records"
    _HISTORY_KEY = "p115liteassistant_history"
    _CHECKIN_SCHEDULE_KEY = "p115liteassistant_checkin_schedule"
    _REDIRECT_SECRET_KEY = "p115liteassistant_redirect_secret"
    _LIFE_CURSOR_KEY = "p115liteassistant_life_cursor"
    _LIFE_API_STATE_KEY = "p115liteassistant_life_api_state"
    _LIFE_PATHS_KEY = "p115liteassistant_life_paths"

    # 落盘前加密的字段。密钥由 302 取链用的随机 secret 派生，二者同生共死：
    # 插件数据被清空时，密文和密钥一起消失，不会留下解不开的残留。
    _ENCRYPTION_SALT = b"p115liteassistant_v1"
    _ENCRYPTED_FIELDS = ("cookie", "tokens")

    def __init__(self, plugin):
        self._plugin = plugin
        self._config_lock = RLock()
        self._encryption_key_cache: bytes | None = None

    def _encryption_key(self) -> bytes:
        """从 302 取链 secret 派生 Fernet 密钥。

        PBKDF2 迭代 10 万次成本不低，密钥在实例内缓存一次；secret 本身一旦生成
        就不再变化，所以缓存不会读到过期值。
        """
        if self._encryption_key_cache is None:
            secret = self.get_redirect_secret()
            derived = pbkdf2_hmac("sha256", secret.encode("utf-8"), self._ENCRYPTION_SALT, 100_000)
            self._encryption_key_cache = urlsafe_b64encode(derived)
        return self._encryption_key_cache

    def _encrypt_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """加密敏感字段的副本，供落盘使用。"""
        key = self._encryption_key()
        result = dict(config)
        for field in self._ENCRYPTED_FIELDS:
            value = result.get(field)
            if field == "tokens":
                if isinstance(value, dict):
                    result[field] = encrypt_tokens(value, key)
            elif isinstance(value, str) and value:
                result[field] = encrypt(value, key)
        return result

    def _decrypt_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """解密敏感字段。

        解不开就保留原值：这是 1.2.0 之前存下的明文，下一次保存会自动加密，
        用户不需要重新扫码。
        """
        key = self._encryption_key()
        result = dict(config)
        for field in self._ENCRYPTED_FIELDS:
            value = result.get(field)
            if not isinstance(value, str) or not value:
                continue
            if field == "tokens":
                parsed = decrypt_tokens(value, key)
                result[field] = parsed if parsed is not None else {}
            else:
                plaintext = decrypt(value, key)
                if plaintext is not None:
                    result[field] = plaintext
        return result

    def get_config(self) -> Dict[str, Any]:
        with self._config_lock:
            config = deepcopy(DEFAULT_CONFIG)
            saved = self._plugin.get_data(self._CONFIG_KEY) or {}
            if isinstance(saved, dict):
                config.update({key: value for key, value in saved.items() if key in DEFAULT_CONFIG})
                # Upstream calls this switch ``monitor_life_enabled``; accept it
                # as a migration alias while keeping one canonical value here.
                if "life_monitor_enabled" not in saved and "monitor_life_enabled" in saved:
                    config["life_monitor_enabled"] = bool(saved["monitor_life_enabled"])
            # 插件内部一律看到明文，加密只发生在存储边界
            return self._decrypt_config(config)

    def save_config(self, config: Dict[str, Any]) -> None:
        with self._config_lock:
            self._plugin.save_data(self._CONFIG_KEY, self._encrypt_config(config))

    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        with self._config_lock:
            updates = dict(updates)
            if "monitor_life_enabled" in updates and "life_monitor_enabled" not in updates:
                updates["life_monitor_enabled"] = updates["monitor_life_enabled"]
            config = self.get_config()
            config.update({key: value for key, value in updates.items() if key in DEFAULT_CONFIG})
            self.save_config(config)
            return config

    def get_strm_records(self) -> Dict[str, Dict[str, Any]]:
        records = self._plugin.get_data(self._STRM_RECORDS_KEY) or {}
        return deepcopy(records) if isinstance(records, dict) else {}

    def save_strm_records(self, records: Dict[str, Dict[str, Any]]) -> None:
        self._plugin.save_data(self._STRM_RECORDS_KEY, deepcopy(records))

    def get_life_cursor(self) -> Dict[str, Any]:
        state = self._plugin.get_data(self._LIFE_CURSOR_KEY) or {}
        if not isinstance(state, dict):
            return {"from_time": 0, "from_id": 0}
        try:
            from_time = int(float(state.get("from_time") or 0))
        except (TypeError, ValueError):
            from_time = 0
        try:
            from_id = int(state.get("from_id") or 0)
        except (TypeError, ValueError):
            from_id = 0
        return {"from_time": max(0, from_time), "from_id": max(0, from_id)}

    def save_life_cursor(self, from_time: int, from_id: int) -> None:
        self._plugin.save_data(
            self._LIFE_CURSOR_KEY,
            {"from_time": max(0, int(from_time)), "from_id": max(0, int(from_id))},
        )

    def get_life_api_state(self) -> Dict[str, Any]:
        state = self._plugin.get_data(self._LIFE_API_STATE_KEY) or {}
        return dict(state) if isinstance(state, dict) else {}

    def save_life_api_state(self, state: Dict[str, Any]) -> None:
        self._plugin.save_data(self._LIFE_API_STATE_KEY, dict(state))

    def get_life_paths(self) -> Dict[str, Dict[str, Any]]:
        state = self._plugin.get_data(self._LIFE_PATHS_KEY) or {}
        return deepcopy(state) if isinstance(state, dict) else {}

    def save_life_paths(self, paths: Dict[str, Dict[str, Any]]) -> None:
        self._plugin.save_data(self._LIFE_PATHS_KEY, deepcopy(paths))

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

    def get_recent_uploaded_media(
        self,
        media_extensions: set[str],
        limit: int = 12,
    ) -> List[Dict[str, Any]]:
        return self.get_upload_records().recent_media(media_extensions, limit)

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
