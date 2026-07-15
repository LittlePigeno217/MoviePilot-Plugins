from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List


class IncrementalRecordStore:
    """基于本地文件大小与修改时间的上传增量记录。"""

    def __init__(self, records: Dict[str, Dict[str, Any]] | None = None):
        self._records = dict(records or {})

    @staticmethod
    def _fingerprint(path: Path) -> Dict[str, int]:
        stat = path.stat()
        return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}

    def has_changed(self, path: Path, target: str | None = None) -> bool:
        current = self._fingerprint(path)
        previous = self._records.get(str(path))
        if not previous or any(previous.get(key) != value for key, value in current.items()):
            return True
        return target is not None and previous.get("target") != target

    def mark_uploaded(
        self,
        path: Path,
        target: str,
        uploaded_at: str | None = None,
    ) -> None:
        self._records[str(path)] = {
            **self._fingerprint(path),
            "target": target,
            "uploaded_at": uploaded_at or datetime.now().isoformat(timespec="seconds"),
        }

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._records)


class TaskHistory:
    def __init__(self, items: Iterable[Dict[str, Any]] | None = None, limit: int = 50):
        self.limit = limit
        self.items: List[Dict[str, Any]] = list(items or [])[:limit]

    def add(self, item: Dict[str, Any]) -> None:
        self.items.insert(0, item)
        del self.items[self.limit :]
