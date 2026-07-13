from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from app.log import logger
except ImportError:
    # Mock logger for testing/standalone usage
    import sys
    class MockLogger:
        def error(self, msg):
            print(f"ERROR: {msg}", file=sys.stderr)
        def warning(self, msg):
            print(f"WARNING: {msg}")
        def info(self, msg):
            print(f"INFO: {msg}")
    logger = MockLogger()

try:
    import orjson
except ImportError:
    # Fallback to standard json if orjson is not available
    import json as json_module
    class OrJsonMock:
        @staticmethod
        def loads(data):
            if isinstance(data, bytes):
                data = data.decode()
            return json_module.loads(data)
        @staticmethod
        def dumps(data):
            return json_module.dumps(data).encode()
    orjson = OrJsonMock()


class IncrementalRecordStore:
    def __init__(self, records: Optional[Dict[str, Dict[str, Any]]] = None):
        self._records: Dict[str, Dict[str, Any]] = dict(records or {})

    @staticmethod
    def fingerprint(path: Path) -> Dict[str, int]:
        stat = path.stat()
        return {
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
        }

    @staticmethod
    def key(path: Path) -> str:
        return str(Path(path))

    def has_changed(self, path: Path) -> bool:
        key = self.key(path)
        current = self.fingerprint(path)
        stored = self._records.get(key)
        if not stored:
            return True
        return (
            int(stored.get("size", -1)) != current["size"]
            or int(stored.get("mtime_ns", -1)) != current["mtime_ns"]
        )

    def mark_uploaded(
        self, path: Path, target: str, uploaded_at: Optional[str] = None
    ) -> None:
        current = self.fingerprint(path)
        self._records[self.key(path)] = {
            **current,
            "target": target,
            "uploaded_at": uploaded_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def clear(self) -> None:
        self._records.clear()

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._records)


class TaskHistory:
    def __init__(self, items: Optional[List[Dict[str, Any]]] = None, limit: int = 50):
        self.limit = limit
        self.items: List[Dict[str, Any]] = list(items or [])[:limit]

    def add(self, item: Dict[str, Any]) -> None:
        self.items.insert(0, item)
        del self.items[self.limit :]

    def to_list(self) -> List[Dict[str, Any]]:
        return list(self.items)


@dataclass
class PathMapping:
    """路径映射记录"""
    enabled: bool
    source: str
    sourceDesc: str
    target: str
    targetCid: str
    id: Optional[int] = None
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    def to_dict(self) -> Dict:
        data = asdict(self)
        # Convert datetime to ISO format strings for JSON serialization
        if self.createdAt:
            data["createdAt"] = self.createdAt.isoformat() if isinstance(self.createdAt, datetime) else self.createdAt
        if self.updatedAt:
            data["updatedAt"] = self.updatedAt.isoformat() if isinstance(self.updatedAt, datetime) else self.updatedAt
        return data


@dataclass
class P115DirCache:
    """115 目录缓存"""
    cid: str
    data: Dict  # 子目录列表
    cachedAt: datetime
    expireAt: datetime

    def is_expired(self) -> bool:
        return datetime.now() > self.expireAt

    def to_dict(self) -> Dict:
        return {
            "cid": self.cid,
            "data": self.data,
            "cachedAt": self.cachedAt.isoformat() if isinstance(self.cachedAt, datetime) else self.cachedAt,
            "expireAt": self.expireAt.isoformat() if isinstance(self.expireAt, datetime) else self.expireAt
        }


class PathMappingManager:
    """路径映射管理器"""

    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.mappings_file = self.config_path / "path_mappings.json"
        self.cache_file = self.config_path / "115_dir_cache.json"
        self._ensure_files()

    def _ensure_files(self):
        """确保配置文件存在"""
        self.config_path.mkdir(parents=True, exist_ok=True)
        self.mappings_file.touch(exist_ok=True)
        self.cache_file.touch(exist_ok=True)
        if self.mappings_file.stat().st_size == 0:
            self.mappings_file.write_text(orjson.dumps([]).decode())
        if self.cache_file.stat().st_size == 0:
            self.cache_file.write_text(orjson.dumps({}).decode())

    def get_mappings(self) -> List[PathMapping]:
        """获取所有路径映射"""
        try:
            data = orjson.loads(self.mappings_file.read_text())
            result = []
            for item in data:
                # Convert ISO format strings back to datetime
                if isinstance(item.get("createdAt"), str):
                    item["createdAt"] = datetime.fromisoformat(item["createdAt"])
                if isinstance(item.get("updatedAt"), str):
                    item["updatedAt"] = datetime.fromisoformat(item["updatedAt"])
                result.append(PathMapping(**item))
            return result
        except Exception:
            return []

    def save_mappings(self, mappings: List[PathMapping]) -> bool:
        """保存路径映射"""
        try:
            data = [m.to_dict() for m in mappings]
            self.mappings_file.write_text(orjson.dumps(data).decode())
            return True
        except Exception as e:
            logger.error(f"保存路径映射失败: {e}")
            return False

    def get_115_cache(self, cid: str) -> Optional[Dict]:
        """获取 115 目录缓存"""
        try:
            cache_data = orjson.loads(self.cache_file.read_text())
            if cid not in cache_data:
                return None
            cached_item = cache_data[cid]
            # Convert ISO format strings back to datetime
            if isinstance(cached_item.get("cachedAt"), str):
                cached_item["cachedAt"] = datetime.fromisoformat(cached_item["cachedAt"])
            if isinstance(cached_item.get("expireAt"), str):
                cached_item["expireAt"] = datetime.fromisoformat(cached_item["expireAt"])
            cached = P115DirCache(**cached_item)
            if cached.is_expired():
                self.clear_cache(cid)
                return None
            return cached.data
        except Exception:
            return None

    def set_115_cache(self, cid: str, data: Dict, ttl_hours: int = 24) -> bool:
        """设置 115 目录缓存"""
        try:
            cache_data = orjson.loads(self.cache_file.read_text())
            cached = P115DirCache(
                cid=cid,
                data=data,
                cachedAt=datetime.now(),
                expireAt=datetime.now() + timedelta(hours=ttl_hours)
            )
            cache_data[cid] = cached.to_dict()
            self.cache_file.write_text(orjson.dumps(cache_data).decode())
            return True
        except Exception as e:
            logger.error(f"设置 115 缓存失败: {e}")
            return False

    def clear_cache(self, cid: str) -> bool:
        """清除指定 cid 的缓存"""
        try:
            cache_data = orjson.loads(self.cache_file.read_text())
            cache_data.pop(cid, None)
            self.cache_file.write_text(orjson.dumps(cache_data).decode())
            return True
        except Exception:
            return False

    def clear_expired_caches(self) -> int:
        """清除所有过期缓存"""
        try:
            cache_data = orjson.loads(self.cache_file.read_text())
            expired_cids = []
            for cid, item in cache_data.items():
                try:
                    # Make a copy to avoid modifying the original
                    item_copy = dict(item)
                    # Convert ISO format strings back to datetime
                    if isinstance(item_copy.get("cachedAt"), str):
                        item_copy["cachedAt"] = datetime.fromisoformat(item_copy["cachedAt"])
                    if isinstance(item_copy.get("expireAt"), str):
                        item_copy["expireAt"] = datetime.fromisoformat(item_copy["expireAt"])
                    cached = P115DirCache(**item_copy)
                    if cached.is_expired():
                        expired_cids.append(cid)
                except Exception as e:
                    logger.warning(f"无法处理缓存项 {cid}: {e}")
                    continue
            for cid in expired_cids:
                cache_data.pop(cid)
            self.cache_file.write_text(orjson.dumps(cache_data).decode())
            return len(expired_cids)
        except Exception as e:
            logger.error(f"清除过期缓存失败: {e}")
            return 0
