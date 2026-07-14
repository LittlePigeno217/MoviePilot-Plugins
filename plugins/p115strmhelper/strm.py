import time
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import quote

try:  # 运行时相对导入；单测直接导入模块时回退绝对导入
    from .models import Mapping, SyncRecord, HistoryEntry
except ImportError:  # pragma: no cover
    from models import Mapping, SyncRecord, HistoryEntry

MEDIA_EXTS = {".mkv", ".mp4", ".ts", ".m2ts", ".avi", ".mov", ".wmv", ".iso", ".rmvb", ".flv"}


def build_strm_url(moviepilot_url: str, pickcode: str, api_token: str) -> str:
    base = (moviepilot_url or "").rstrip("/")
    return (
        f"{base}/api/v1/plugin/P115StrmHelper/redirect"
        f"?pickcode={quote(pickcode)}&apikey={quote(api_token)}"
    )


def _is_media(name: str) -> bool:
    return PurePosixPath(name).suffix.lower() in MEDIA_EXTS


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class StrmGenerator:
    """遍历 115 源目录，生成 .strm，支持增量跳过与刮削镜像。"""

    def __init__(self, client, store, moviepilot_url, api_token,
                 incremental=True, metadata_sync=None):
        self._client = client
        self._store = store
        self._mp_url = moviepilot_url
        self._token = api_token
        self._incremental = incremental
        self._metadata = metadata_sync  # MetadataSync 或 None；非 None 时镜像 sidecar

    def run_mapping(self, mapping: Mapping) -> HistoryEntry:
        start = time.time()
        added = updated = skipped = errors = 0
        state = self._store.get_sync_state()
        records = []
        for item in self._client.iter_files(mapping.source_cid, recursive=True):
            if not _is_media(item.get("name", "")):
                if self._metadata:
                    self._metadata.mirror(item, mapping.target_dir)
                continue
            try:
                rel = PurePosixPath(item["rel_path"])
                strm_path = Path(mapping.target_dir) / rel.with_suffix(".strm")
                file_key = f"{mapping.id}:{item['rel_path']}"
                sig = str(item.get("size") or "")
                existing = state.get(file_key)
                if self._incremental and existing and existing.get("sha1") == sig and strm_path.exists():
                    skipped += 1
                    continue
                strm_path.parent.mkdir(parents=True, exist_ok=True)
                strm_path.write_text(
                    build_strm_url(self._mp_url, item["pickcode"], self._token),
                    encoding="utf-8",
                )
                records.append(SyncRecord(file_key, item["pickcode"], sig, str(strm_path)))
                if existing:
                    updated += 1
                else:
                    added += 1
            except Exception:  # noqa: BLE001
                errors += 1
        self._store.bulk_set_sync_records(records)
        return HistoryEntry(
            time=_now_iso(),
            mapping_id=mapping.id,
            added=added,
            updated=updated,
            skipped=skipped,
            errors=errors,
            duration_ms=int((time.time() - start) * 1000),
            message="完成" if not errors else f"{errors} 个文件出错",
        )
