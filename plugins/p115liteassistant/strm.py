from __future__ import annotations

from datetime import datetime
from pathlib import Path, PurePosixPath
from time import monotonic
from typing import Any, Dict
from urllib.parse import quote


MEDIA_EXTENSIONS = {
    ".mkv", ".mp4", ".ts", ".m2ts", ".avi", ".mov", ".wmv", ".iso", ".rmvb", ".flv",
}


def build_strm_url(moviepilot_url: str, pickcode: str, api_token: str) -> str:
    base = moviepilot_url.rstrip("/")
    return (
        f"{base}/api/v1/plugin/P115LiteAssistant/redirect"
        f"?pickcode={quote(pickcode)}&apikey={quote(api_token)}"
    )


class StrmGenerator:
    def __init__(self, client, store, moviepilot_url: str, api_token: str, incremental: bool):
        self._client = client
        self._store = store
        self._moviepilot_url = moviepilot_url
        self._api_token = api_token
        self._incremental = incremental

    def run_mapping(self, mapping: Dict[str, Any]) -> Dict[str, Any]:
        started = monotonic()
        mapping_id = str(mapping.get("id") or mapping.get("source_cid") or "default")
        source_cid = str(mapping.get("source_cid") or "0")
        target_value = str(mapping.get("target_dir") or "").strip()
        if not self._moviepilot_url:
            raise ValueError("请先配置媒体服务器可访问的 MoviePilot 地址")
        if not target_value:
            raise ValueError("STRM 输出目录不能为空")
        target_dir = Path(target_value).expanduser()
        target_dir = target_dir.resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        if not target_dir.is_dir():
            raise ValueError(f"STRM 输出目录不可用: {target_dir}")

        records = self._store.get_strm_records()
        counts = {"added": 0, "updated": 0, "skipped": 0, "errors": 0}
        for item in self._client.iter_files(source_cid):
            name = str(item.get("name") or "")
            if PurePosixPath(name).suffix.lower() not in MEDIA_EXTENSIONS:
                continue
            pickcode = str(item.get("pickcode") or "")
            if not pickcode:
                counts["errors"] += 1
                continue
            rel_path = PurePosixPath(str(item.get("rel_path") or name))
            if any(part in {"", ".", ".."} for part in rel_path.parts):
                counts["errors"] += 1
                continue
            output = target_dir.joinpath(*rel_path.parts).with_suffix(".strm")
            try:
                output.resolve().relative_to(target_dir)
            except ValueError:
                counts["errors"] += 1
                continue
            record_key = f"{mapping_id}:{rel_path.as_posix()}"
            strm_url = build_strm_url(self._moviepilot_url, pickcode, self._api_token)
            fingerprint = f"{pickcode}:{item.get('size', 0)}:{self._moviepilot_url.rstrip('/')}"
            previous = records.get(record_key, {})
            if self._incremental and previous.get("fingerprint") == fingerprint and output.exists():
                counts["skipped"] += 1
                continue
            temp_output = None
            try:
                output.parent.mkdir(parents=True, exist_ok=True)
                temp_output = output.with_name(f".{output.name}.tmp")
                temp_output.write_text(strm_url + "\n", encoding="utf-8")
                temp_output.replace(output)
                records[record_key] = {"fingerprint": fingerprint, "path": str(output)}
                counts["updated" if previous else "added"] += 1
            except OSError:
                counts["errors"] += 1
            finally:
                if temp_output and temp_output.exists():
                    try:
                        temp_output.unlink(missing_ok=True)
                    except OSError:
                        counts["errors"] += 1
        self._store.save_strm_records(records)
        return {
            "kind": "strm",
            "time": datetime.now().isoformat(timespec="seconds"),
            "mapping": mapping.get("source_path") or source_cid,
            **counts,
            "duration_ms": int((monotonic() - started) * 1000),
        }
