from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


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
