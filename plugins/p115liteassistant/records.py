from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Protocol


class IncrementalRecordStore:
    """基于本地文件大小与修改时间的上传增量记录。"""

    def __init__(self, records: Dict[str, Dict[str, Any]] | None = None):
        self._records = dict(records or {})

    @staticmethod
    def _fingerprint(path: Path) -> Dict[str, int]:
        stat = path.stat()
        return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}

    @staticmethod
    def _path_key(path: Path | str) -> str:
        """只用于比较的路径键；不改持久化内容，兼容分隔符和 Windows 短路径。"""
        raw = str(path)
        try:
            raw = str(Path(raw).expanduser().resolve(strict=False))
        except (OSError, RuntimeError, ValueError):
            pass
        return raw.replace("\\", "/").casefold()

    def _stored_key(self, path: Path | str) -> str | None:
        raw = str(path)
        if raw in self._records:
            return raw
        wanted = self._path_key(raw)
        return next(
            (key for key in self._records if self._path_key(key) == wanted),
            None,
        )

    def has_changed(
        self,
        path: Path,
        target: str | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> bool:
        current = self._fingerprint(path)
        previous = self._records.get(self._stored_key(path) or "")
        if not previous or any(previous.get(key) != value for key, value in current.items()):
            return True
        if target is not None and previous.get("target") != target:
            return True
        return any(previous.get(key) != value for key, value in (metadata or {}).items())

    def mark_uploaded(
        self,
        path: Path,
        target: str,
        uploaded_at: str | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        self._records[str(path)] = {
            **self._fingerprint(path),
            "target": target,
            "uploaded_at": uploaded_at or datetime.now().isoformat(timespec="seconds"),
            **(metadata or {}),
        }

    def update_metadata(self, path: Path, metadata: Dict[str, Any]) -> None:
        key = self._stored_key(path)
        record = self._records.get(key or "")
        if record is None:
            raise KeyError(f"上传记录不存在: {path}")
        record.update(metadata)

    def get_by_key(self, key: Path | str) -> Dict[str, Any]:
        record = self._records.get(self._stored_key(key) or "")
        return dict(record) if record else {}

    def upsert_by_key(self, key: Path | str, record: Dict[str, Any]) -> None:
        stored = self._stored_key(key)
        if stored is not None and stored != str(key):
            self._records.pop(stored, None)
        self._records[str(key)] = dict(record)

    def delete_by_key(self, key: Path | str) -> None:
        stored = self._stored_key(key)
        if stored is not None:
            self._records.pop(stored, None)

    def get(self, path: Path) -> Dict[str, Any]:
        record = self._records.get(self._stored_key(path) or "")
        return dict(record) if record else {}

    def remove(self, path: Path) -> None:
        """删掉一条上传记录（重传覆盖场景：远端清了，记录也得清）。"""
        key = self._stored_key(path)
        if key is not None:
            self._records.pop(key, None)

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._records)

    def recent_media(self, media_extensions: set[str], limit: int = 12) -> List[Dict[str, Any]]:
        items = []
        for path, record in self._records.items():
            if Path(path).suffix.lower() not in media_extensions:
                continue
            uploaded_at = str(record.get("uploaded_at") or "")
            if not uploaded_at:
                continue
            items.append(
                {
                    "name": Path(path).name,
                    "path": path,
                    "target": str(record.get("target") or ""),
                    "uploaded_at": uploaded_at,
                    "method": str(record.get("method") or "upload"),
                }
            )
        return sorted(items, key=lambda item: item["uploaded_at"], reverse=True)[:limit]


class TaskHistory:
    def __init__(self, items: Iterable[Dict[str, Any]] | None = None, limit: int = 50):
        self.limit = limit
        self.items: List[Dict[str, Any]] = list(items or [])[:limit]

    def add(self, item: Dict[str, Any]) -> None:
        self.items.insert(0, item)
        del self.items[self.limit :]


class MutationApplyItem:
    """单条 RecordMutation 的提交结果。"""

    def __init__(self, mutation, applied: bool, retryable: bool = False, error: str = ""):
        self.mutation = mutation
        self.applied = bool(applied)
        self.retryable = bool(retryable)
        self.error = str(error or "")


class MutationApplyResult:
    """按 container 固定顺序提交后的逐项结果。"""

    def __init__(self, items: Iterable[MutationApplyItem]):
        self.items = tuple(items)

    @property
    def success(self) -> bool:
        return all(item.applied for item in self.items)

    @property
    def applied(self) -> tuple:
        return tuple(item.mutation for item in self.items if item.applied)

    @property
    def failed(self) -> tuple:
        return tuple(item.mutation for item in self.items if not item.applied)

    @property
    def retryable(self) -> bool:
        return any(item.retryable for item in self.items if not item.applied)


def apply_record_mutations(
    mutations: Iterable[Any],
    *,
    strm_records: Dict[str, Dict[str, Any]],
    upload_records: IncrementalRecordStore,
) -> MutationApplyResult:
    """按 ``strm -> upload`` 固定顺序应用 mutation。

    每条 mutation 都做 compare-before；upload 只能通过
    :class:`IncrementalRecordStore` 的正式接口变更。调用方在结果成功后再持久化两个
    container；部分失败会明确返回，不能据此推进游标或删除上传源文件。
    """

    ordered = tuple(mutations)
    results: list[MutationApplyItem] = []
    blocked = False
    for container in ("strm", "upload"):
        for mutation in (item for item in ordered if item.container == container):
            if blocked:
                results.append(
                    MutationApplyItem(mutation, False, True, "前序 mutation 提交失败")
                )
                continue
            try:
                current = (
                    strm_records.get(mutation.key)
                    if container == "strm"
                    else upload_records.get_by_key(mutation.key)
                )
                expected = dict(mutation.before) if mutation.before is not None else None
                actual = dict(current) if current else None
                if actual != expected:
                    raise RuntimeError(
                        f"compare-before 失败: {container}/{mutation.key}"
                    )
                if container == "strm":
                    if mutation.after is None:
                        strm_records.pop(mutation.key, None)
                    else:
                        strm_records[mutation.key] = dict(mutation.after)
                elif mutation.after is None:
                    upload_records.delete_by_key(mutation.key)
                else:
                    upload_records.upsert_by_key(mutation.key, dict(mutation.after))
                results.append(MutationApplyItem(mutation, True))
            except Exception as err:  # noqa: BLE001 - result must retain retry state
                blocked = True
                results.append(MutationApplyItem(mutation, False, True, str(err)))
    return MutationApplyResult(results)


class RecordContainerAdapter(Protocol):
    """CommitJournal 对领域 container 的显式适配器。"""

    container: str

    def snapshot(self) -> Dict[str, Dict[str, Any]]: ...
    def save(self, records: Mapping[str, Mapping[str, Any]]) -> None: ...


class StrmRecordAdapter:
    container = "strm"

    def __init__(self, store: Any):
        self.store = store

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        return {str(key): dict(value) for key, value in self.store.get_strm_records().items()}

    def save(self, records: Mapping[str, Mapping[str, Any]]) -> None:
        self.store.save_strm_records(
            {str(key): dict(value) for key, value in records.items()}
        )


class UploadRecordAdapter:
    container = "upload"

    def __init__(self, store: Any):
        self.store = store

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        current = self.store.get_upload_records()
        raw = current if isinstance(current, Mapping) else current.to_dict()
        return {str(key): dict(value) for key, value in raw.items()}

    def save(self, records: Mapping[str, Mapping[str, Any]]) -> None:
        current = self.store.get_upload_records()
        if isinstance(current, Mapping):
            # 仅测试桩/legacy store 使用 dict；生产 Store 返回 IncrementalRecordStore。
            self.store.save_upload_records(
                {str(key): dict(value) for key, value in records.items()}
            )
            return
        rebuilt = IncrementalRecordStore()
        for key, value in records.items():
            rebuilt.upsert_by_key(str(key), dict(value))
        self.store.save_upload_records(rebuilt)
