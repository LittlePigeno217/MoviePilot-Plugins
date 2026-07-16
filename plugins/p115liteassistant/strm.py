from __future__ import annotations

import threading
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from time import monotonic
from typing import Any, Dict
from urllib.parse import quote

from app.log import logger

from .file_types import DEFAULT_MEDIA_EXTENSIONS, DEFAULT_SIDECAR_EXTENSIONS, parse_extensions
from .log_utils import safe_error_text
from .resilience import retry_call


MEDIA_EXTENSIONS = set(DEFAULT_MEDIA_EXTENSIONS)
STRM_WRITE_WORKERS = 8
STRM_WRITE_PREFETCH = 256
STRM_PROGRESS_INTERVAL = 1000


def build_strm_url(moviepilot_url: str, pickcode: str, api_token: str) -> str:
    base = moviepilot_url.rstrip("/")
    return (
        f"{base}/api/v1/plugin/P115LiteAssistant/redirect"
        f"?pickcode={quote(pickcode)}&apikey={quote(api_token)}"
    )


def _atomic_write_text(output: Path, content: str) -> None:
    temp_output = output.with_name(f".{output.name}.{threading.get_ident()}.tmp")
    try:
        temp_output.write_text(content, encoding="utf-8")
        temp_output.replace(output)
    finally:
        temp_output.unlink(missing_ok=True)


def write_strm_file(output: Path, content: str, target_dir: Path) -> None:
    output.resolve().relative_to(target_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(output, content)


def uploaded_strm_path(local_path: Path, source_root: Path, target_root: Path) -> Path:
    source_root = source_root.resolve()
    target_root = target_root.expanduser().resolve()
    rel_path = local_path.resolve().relative_to(source_root)
    return target_root.joinpath(*rel_path.parts).with_suffix(".strm")


def write_uploaded_strm(
    local_path: Path,
    source_root: Path,
    target_root: Path,
    pickcode: str,
    moviepilot_url: str,
    api_token: str,
) -> Path:
    if not (len(pickcode) == 17 and pickcode.isalnum()):
        raise ValueError(f"无效 pickcode: {pickcode or '-'}")
    target_root = target_root.expanduser().resolve()
    output = uploaded_strm_path(local_path, source_root, target_root)
    write_strm_file(
        output,
        build_strm_url(moviepilot_url, pickcode, api_token) + "\n",
        target_root,
    )
    return output


class StrmGenerator:
    def __init__(
        self,
        client,
        store,
        moviepilot_url: str,
        api_token: str,
        incremental: bool,
        download_sidecars: bool = False,
        sidecar_extensions: str = "",
    ):
        self._client = client
        self._store = store
        self._moviepilot_url = moviepilot_url
        self._api_token = api_token
        self._api_token_signature = sha256(api_token.encode("utf-8")).hexdigest()
        self._incremental = incremental
        self._url_prefix = (
            f"{moviepilot_url.rstrip('/')}/api/v1/plugin/P115LiteAssistant/redirect?pickcode="
        )
        self._url_suffix = f"&apikey={quote(api_token)}"
        self._download_sidecars = download_sidecars
        self._sidecar_extensions = parse_extensions(
            sidecar_extensions,
            DEFAULT_SIDECAR_EXTENSIONS,
        )

    def _build_url(self, pickcode: str) -> str:
        return f"{self._url_prefix}{quote(pickcode)}{self._url_suffix}"

    @staticmethod
    def _write_strm(
        output: Path,
        content: str,
        target_dir: Path,
        created_directories: set[Path],
        directory_lock: threading.Lock,
    ) -> None:
        StrmGenerator._prepare_output_parent(
            output,
            target_dir,
            created_directories,
            directory_lock,
        )
        _atomic_write_text(output, content)

    @staticmethod
    def _prepare_output_parent(
        output: Path,
        target_dir: Path,
        created_directories: set[Path],
        directory_lock: threading.Lock,
    ) -> None:
        parent = output.parent
        with directory_lock:
            if parent in created_directories:
                return
            parent.resolve().relative_to(target_dir)
            parent.mkdir(parents=True, exist_ok=True)
            created_directories.add(parent)

    def _download_sidecar(
        self,
        output: Path,
        pickcode: str,
        target_dir: Path,
        created_directories: set[Path],
        directory_lock: threading.Lock,
    ) -> None:
        self._prepare_output_parent(
            output,
            target_dir,
            created_directories,
            directory_lock,
        )
        retry_call(
            lambda: self._client.download_file(pickcode, output, create_parent=False),
            attempts=3,
            delay=1.0,
        )

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
        counts = {"added": 0, "updated": 0, "sidecars": 0, "skipped": 0, "errors": 0}
        created_directories = {target_dir}
        directory_lock = threading.Lock()
        claimed_outputs: Dict[Path, str] = {}
        pending: Dict[
            Future[None],
            tuple[str, str, str, Dict[str, Any], str, Path],
        ] = {}
        processed = 0

        def collect(done: set[Future[None]]) -> None:
            nonlocal processed
            for future in done:
                kind, record_key, fingerprint, previous, rel_path_text, output = pending.pop(future)
                processed += 1
                try:
                    future.result()
                    records[record_key] = {"fingerprint": fingerprint, "path": str(output)}
                    if kind == "sidecar":
                        counts["sidecars"] += 1
                        logger.debug(f"【STRM同步】附属文件回传成功：{rel_path_text} -> {output}")
                    else:
                        counts["updated" if previous else "added"] += 1
                        logger.debug(
                            f"【STRM同步】{'更新' if previous else '生成'} STRM 成功："
                            f"{rel_path_text} -> {output}"
                        )
                except Exception as err:  # noqa: BLE001
                    counts["errors"] += 1
                    action = "回传附属文件" if kind == "sidecar" else "生成 STRM"
                    logger.error(f"【STRM同步】{action}失败：{rel_path_text} -> {output}，原因：{safe_error_text(err)}")
                if processed % STRM_PROGRESS_INTERVAL == 0:
                    logger.info(
                        f"【STRM同步】已处理 {processed} 个文件，"
                        f"新增 {counts['added']}，更新 {counts['updated']}，"
                        f"附属文件 {counts['sidecars']}，跳过 {counts['skipped']}，"
                        f"失败 {counts['errors']}"
                    )

        def drain_pending() -> None:
            while pending:
                done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
                collect(done)

        with ThreadPoolExecutor(
            max_workers=STRM_WRITE_WORKERS,
            thread_name_prefix="p115-strm-write",
        ) as executor:
            try:
                items = iter(self._client.iter_files(source_cid))
            except Exception:
                self._store.save_strm_records(records)
                raise
            while True:
                try:
                    item = next(items)
                except StopIteration:
                    break
                except Exception:
                    drain_pending()
                    self._store.save_strm_records(records)
                    raise
                name = str(item.get("name") or "")
                extension = PurePosixPath(name).suffix.lower()
                kind = "strm" if extension in MEDIA_EXTENSIONS else "sidecar"
                if kind == "sidecar" and (
                    not self._download_sidecars or extension not in self._sidecar_extensions
                ):
                    continue
                pickcode = str(item.get("pickcode") or "")
                if not pickcode:
                    counts["errors"] += 1
                    logger.warning(f"【STRM同步】文件缺少 Pickcode，跳过：{name or '-'}")
                    continue
                rel_path = PurePosixPath(str(item.get("rel_path") or name).replace("\\", "/"))
                if rel_path.is_absolute() or any(part in {"", ".", ".."} for part in rel_path.parts):
                    counts["errors"] += 1
                    logger.warning(f"【STRM同步】文件相对路径无效，跳过：{rel_path.as_posix()}")
                    continue
                rel_path_text = rel_path.as_posix()
                output = target_dir.joinpath(*rel_path.parts)
                if kind == "strm":
                    output = output.with_suffix(".strm")
                    record_key = f"{mapping_id}:{rel_path_text}"
                else:
                    record_key = f"{mapping_id}:sidecar:{rel_path_text}"
                conflicting_path = claimed_outputs.get(output)
                if conflicting_path is not None:
                    counts["errors"] += 1
                    logger.error(
                        "【STRM同步】输出路径冲突，跳过："
                        f"{rel_path_text} 与 {conflicting_path} 均映射到 {output}"
                    )
                    continue
                claimed_outputs[output] = rel_path_text
                fingerprint = (
                    f"{pickcode}:{item.get('size', 0)}:{self._moviepilot_url.rstrip('/')}:"
                    f"{self._api_token_signature}"
                )
                if kind == "sidecar":
                    fingerprint = f"{pickcode}:{item.get('size', 0)}"
                previous = records.get(record_key, {})
                if self._incremental and previous.get("fingerprint") == fingerprint and output.exists():
                    counts["skipped"] += 1
                    logger.debug(f"【STRM同步】文件未变化，跳过：{rel_path_text}")
                    continue
                if kind == "strm":
                    future = executor.submit(
                        self._write_strm,
                        output,
                        self._build_url(pickcode) + "\n",
                        target_dir,
                        created_directories,
                        directory_lock,
                    )
                else:
                    future = executor.submit(
                        self._download_sidecar,
                        output,
                        pickcode,
                        target_dir,
                        created_directories,
                        directory_lock,
                    )
                pending[future] = (
                    kind,
                    record_key,
                    fingerprint,
                    previous,
                    rel_path_text,
                    output,
                )
                if len(pending) >= STRM_WRITE_PREFETCH:
                    done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
                    collect(done)
            drain_pending()
        self._store.save_strm_records(records)
        return {
            "kind": "strm",
            "time": datetime.now().isoformat(timespec="seconds"),
            "mapping": mapping.get("source_path") or source_cid,
            **counts,
            "duration_ms": int((monotonic() - started) * 1000),
        }
