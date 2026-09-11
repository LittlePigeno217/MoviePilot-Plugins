from __future__ import annotations

import inspect
import threading
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime
from hashlib import sha256
from hmac import compare_digest, new as new_hmac
from pathlib import Path, PurePosixPath
from time import monotonic
from typing import Any, Callable, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit

from app.log import logger
from p115pickcode import is_valid_pickcode

from .client import U115AccessLimitError, U115AuthError
from .file_types import DEFAULT_MEDIA_EXTENSIONS, DEFAULT_SIDECAR_EXTENSIONS, parse_extensions
from .log_utils import safe_error_text
from .resilience import TtlCache, retry_call
from .strm_core import (
    CloudIdentity,
    CollisionDecision,
    CommitJournal,
    CommitUnit,
    PreparedMaterialization,
    FileOperation,
    LegacyOwnerResolution,
    MaterializeRequest,
    MaterializeResult,
    OwnedRemovalRequest,
    RecordClaim,
    RecordClaims,
    RecordMutation,
    RemoveResult,
    ReservationDecision,
    ReservationToken,
    SessionClaim,
    SessionReservations,
    SiblingCandidate,
    StrmMaterializer,
    StrmOwnershipConflict,
    StrmRecoveryBlockedError,
    build_record_mutation,
    resolve_legacy_strm_owner,
    resolve_legacy_upload_owner,
    stable_materialization_order,
    strm_journal_enabled,
)


MEDIA_EXTENSIONS = set(DEFAULT_MEDIA_EXTENSIONS)
STRM_WRITE_WORKERS = 8
STRM_WRITE_PREFETCH = 256
STRM_PROGRESS_INTERVAL = 1000
STRM_URL_FORMAT_VERSION = 3
REDIRECT_SIGNATURE_VERSION = 1


def normalize_pickcode(value: str) -> str:
    pickcode = str(value or "").strip().lower()
    try:
        valid = bool(pickcode) and is_valid_pickcode(pickcode)
    except (LookupError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError(f"无效 pickcode: {pickcode or '-'}")
    return pickcode


def normalize_moviepilot_url(value: str) -> str:
    moviepilot_url = str(value or "").strip().rstrip("/")
    parsed = urlsplit(moviepilot_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("请配置媒体服务器可访问的 MoviePilot HTTP(S) 地址")
    if parsed.query or parsed.fragment:
        raise ValueError("MoviePilot 地址不能包含查询参数或片段")
    return moviepilot_url


def build_redirect_signature(redirect_secret: str, pickcode: str) -> str:
    secret = str(redirect_secret or "")
    if not secret:
        raise ValueError("STRM 播放签名密钥为空")
    normalized_pickcode = normalize_pickcode(pickcode)
    payload = f"p115liteassistant:v{REDIRECT_SIGNATURE_VERSION}:{normalized_pickcode}"
    return new_hmac(secret.encode("utf-8"), payload.encode("utf-8"), sha256).hexdigest()


def verify_redirect_signature(redirect_secret: str, pickcode: str, signature: str) -> bool:
    candidate = str(signature or "").strip().lower()
    if not candidate:
        return False
    try:
        expected = build_redirect_signature(redirect_secret, pickcode)
    except ValueError:
        return False
    return compare_digest(candidate, expected)


def build_strm_url(
    moviepilot_url: str,
    pickcode: str,
    redirect_secret: str,
    file_name: str = "",
) -> str:
    base = normalize_moviepilot_url(moviepilot_url)
    pickcode = normalize_pickcode(pickcode)
    query = {"pickcode": pickcode}
    if file_name:
        query["file_name"] = str(file_name)
    query["sign"] = build_redirect_signature(redirect_secret, pickcode)
    return f"{base}/api/v1/plugin/P115LiteAssistant/redirect?{urlencode(query)}"


def build_strm_content(
    moviepilot_url: str,
    pickcode: str,
    redirect_secret: str,
    file_name: str = "",
) -> str:
    return build_strm_url(moviepilot_url, pickcode, redirect_secret, file_name) + "\n"


def strm_file_matches(output: Path, expected_content: str) -> bool:
    if output.is_symlink() or not output.is_file():
        return False
    expected = expected_content.encode("utf-8")
    try:
        return output.stat().st_size == len(expected) and output.read_bytes() == expected
    except OSError:
        return False


def strm_source_file_name(path: Path) -> str:
    """Best-effort read of the ``file_name`` query param of an existing STRM.

    Returns ``""`` for missing, oversized, unreadable or legacy files without
    the parameter -- callers must treat that as "no information", not "no
    conflict".
    """

    try:
        if not path.is_file() or path.stat().st_size > 4096:
            return ""
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    for key, value in parse_qsl(urlsplit(text).query):
        if key == "file_name":
            return value
    return ""


def strm_output_path(media_path: Path) -> Path:
    if media_path.suffix.lower() == ".iso":
        return media_path.with_name(f"{media_path.stem}.iso.strm")
    return media_path.with_suffix(".strm")


def strm_conflict_output_path(media_path: Path) -> Path:
    """Disambiguated output used when several media share one stem.

    Replacing the extension maps ``A.MOV`` and ``A.mp4`` onto the same
    ``A.strm``, so only one of them could ever reach the media server.
    Keeping the original extension (``A.MOV.strm`` / ``A.mp4.strm``) makes
    the mapping injective. This is only applied to stems that actually
    collide, so unaffected libraries keep their existing file names -- and
    with them their sidecar pairing and scrape history.
    """

    return media_path.with_name(f"{media_path.name}.strm")


def normalize_cloud_path(path: str) -> str:
    normalized = PurePosixPath((path or "/").replace("\\", "/")).as_posix()
    if normalized == ".":
        normalized = "/"
    return normalized if normalized.startswith("/") else f"/{normalized}"


def mapping_cloud_path(mapping: Dict[str, Any], rel_path: str) -> str:
    source_path = normalize_cloud_path(str(mapping.get("source_path") or "/"))
    relative = PurePosixPath(str(rel_path or "").replace("\\", "/"))
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"远端相对路径无效: {rel_path}")
    if source_path == "/":
        return normalize_cloud_path(f"/{relative.as_posix()}")
    return normalize_cloud_path(f"{source_path.rstrip('/')}/{relative.as_posix()}")


def build_strm_record(
    *,
    fingerprint: str,
    output: Path,
    mapping: Dict[str, Any],
    item: Dict[str, Any],
    kind: str = "strm",
    cloud_path: str = "",
) -> Dict[str, Any]:
    """Build a record while keeping legacy fields stable for older installs."""

    record: Dict[str, Any] = {
        "fingerprint": fingerprint,
        "path": str(output),
        "kind": kind,
        "mapping_id": str(mapping.get("id") or mapping.get("source_cid") or "default"),
    }
    if cloud_path:
        record["cloud_path"] = normalize_cloud_path(cloud_path)
    for key in ("fileid", "file_id"):
        value = str(item.get(key) or "").strip()
        if value:
            record["file_id"] = value
            break
    pickcode = str(item.get("pickcode") or item.get("pick_code") or "").strip()
    if pickcode:
        record["pickcode"] = pickcode
    for source_key, target_key in (("size", "size"), ("mtime", "mtime")):
        value = item.get(source_key)
        if value not in (None, ""):
            try:
                record[target_key] = int(float(value))
            except (TypeError, ValueError):
                pass
    name = str(item.get("name") or item.get("file_name") or "").strip()
    if name:
        record["name"] = name
    parent_id = str(item.get("parent_id") or "").strip()
    if parent_id:
        record["parent_id"] = parent_id
    return record


def uploaded_strm_path(local_path: Path, source_root: Path, target_root: Path) -> Path:
    source_root = source_root.resolve()
    target_root = target_root.expanduser().resolve()
    rel_path = local_path.resolve().relative_to(source_root)
    return strm_output_path(target_root.joinpath(*rel_path.parts))


class StrmGenerator:
    def __init__(
        self,
        client,
        store,
        moviepilot_url: str,
        incremental: bool,
        download_sidecars: bool = False,
        sidecar_extensions: str = "",
        recent_deletes: Optional[TtlCache] = None,
        journal: CommitJournal | None = None,
    ):
        self._client = client
        self._store = store
        self._redirect_secret = store.get_redirect_secret()
        self._moviepilot_url = str(moviepilot_url or "").strip().rstrip("/")
        self._incremental = incremental
        self._download_sidecars = download_sidecars
        self._sidecar_extensions = parse_extensions(
            sidecar_extensions,
            DEFAULT_SIDECAR_EXTENSIONS,
        )
        #: 反向删除刚清掉的 pickcode，与 ReverseDeleter 共享同一个实例
        self._recent_deletes = recent_deletes
        if journal is None:
            raise ValueError("StrmGenerator 必须注入插件唯一 CommitJournal")
        self._journal = journal

    def _recently_deleted(self, item: Dict[str, Any]) -> bool:
        """这个文件是不是刚被反向删除过。

        115 的列表接口有延迟，反向删除刚清掉的文件可能还会出现在枚举结果里；照着它
        重建就等于把用户手动删掉的 STRM 又写回去。两边共享一份短期黑名单，谁也不用
        等谁 —— 黑名单过期后若文件确实还在云端，下一轮同步照样会把它补回来。
        """
        if self._recent_deletes is None:
            return False
        pickcode = str(item.get("pickcode") or item.get("pick_code") or "").strip().lower()
        return bool(pickcode) and bool(self._recent_deletes.get(pickcode))

    def _build_url(self, pickcode: str, file_name: str) -> str:
        return build_strm_url(
            self._moviepilot_url,
            pickcode,
            self._redirect_secret,
            file_name,
        )

    @staticmethod
    def _item_mtime(item: Dict[str, Any]) -> int:
        try:
            return int(float(item.get("mtime") or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _item_size(item: Dict[str, Any]) -> int:
        try:
            return max(0, int(float(item.get("size") or 0)))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _record_path_matches(previous: Dict[str, Any], output: Path) -> bool:
        previous_path = str(previous.get("path") or "").strip()
        if not previous_path:
            return False
        try:
            return Path(previous_path).expanduser().resolve() == output.resolve()
        except (OSError, RuntimeError):
            return False

    @staticmethod
    def _record_claims_output(
        records: Dict[str, Any],
        output: Path,
        excluded_keys: set[str] | None = None,
    ) -> bool:
        excluded_keys = excluded_keys or set()
        for record_key, record in records.items():
            if record_key in excluded_keys:
                continue
            if not isinstance(record, dict):
                continue
            record_path = str(record.get("path") or "").strip()
            if not record_path:
                continue
            try:
                if Path(record_path).expanduser().resolve() == output:
                    return True
            except (OSError, RuntimeError):
                logger.warning(f"【STRM同步】记录路径无法解析，保留旧文件：{record_path}")
                return True
        return False

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
            abort_on=(U115AccessLimitError, U115AuthError),
        )

    def run_mapping(self, mapping: Dict[str, Any]) -> Dict[str, Any]:
        started = monotonic()
        mapping_id = str(mapping.get("id") or mapping.get("source_cid") or "default")
        source_cid = str(mapping.get("source_cid") or "").strip()
        target_value = str(mapping.get("target_dir") or "").strip()
        normalize_moviepilot_url(self._moviepilot_url)
        if not source_cid:
            raise ValueError("115 源目录不能为空")
        if not target_value:
            raise ValueError("STRM 输出目录不能为空")
        target_dir = Path(target_value).expanduser()
        target_dir = target_dir.resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        if not target_dir.is_dir():
            raise ValueError(f"STRM 输出目录不可用: {target_dir}")

        records = self._store.get_strm_records()
        upload_records_getter = getattr(self._store, "get_upload_records", None)
        upload_records = (
            upload_records_getter() if callable(upload_records_getter) else {}
        )
        initial_records = dict(records)
        materializer = StrmMaterializer(
            self._store,
            self._moviepilot_url,
            self._redirect_secret,
        )
        reservations = SessionReservations()
        counts = {
            "added": 0,
            "updated": 0,
            "removed": 0,
            "sidecars": 0,
            "skipped": 0,
            "conflicts": 0,
            "errors": 0,
        }
        created_directories = {target_dir}
        directory_lock = threading.Lock()
        mapping_record_prefix = f"{mapping_id}:"
        mapping_record_keys = {
            key for key in records if str(key).startswith(mapping_record_prefix)
        }
        seen_record_keys: set[str] = set()
        claimed_outputs: Dict[Path, str] = {}
        claimed_record_keys: Dict[Path, str] = {}
        claimed_mtimes: Dict[Path, int] = {}
        duplicate_logged_outputs: set[Path] = set()
        conflicting_outputs: set[Path] = set()
        # base output -> (rel_path, media path, record key) of the media that
        # currently owns the extension-replaced name, plus the set of base
        # names already abandoned because two stems collided.
        base_output_owners: Dict[Path, tuple[str, Path, str]] = {}
        relocated_bases: set[Path] = set()
        # Seed abandoned bases from the previous run: when two or more records
        # already map onto one bare name, the conflict is settled and both
        # sides keep their extension-qualified outputs. Without this the first
        # enumerated sibling would rewrite the bare name and get renamed back
        # every sync, churning mtimes and re-logging the conflict forever.
        seeded_base_counts: Dict[Path, int] = {}
        for seeded_key in mapping_record_keys:
            seeded_rel = str(seeded_key)[len(mapping_record_prefix):]
            if seeded_rel.startswith("sidecar:"):
                continue
            seeded_path = PurePosixPath(seeded_rel)
            if seeded_path.is_absolute() or any(
                part in {"", ".", ".."} for part in seeded_path.parts
            ):
                continue
            seeded_base = strm_output_path(target_dir.joinpath(*seeded_path.parts))
            seeded_base_counts[seeded_base] = seeded_base_counts.get(seeded_base, 0) + 1
        relocated_bases.update(
            base for base, count in seeded_base_counts.items() if count >= 2
        )
        same_stem_conflicts: list[str] = []
        output_record_keys: Dict[Path, set[str]] = {}
        completed_count_by_output: Dict[Path, str] = {}
        # record key -> 物化完成后才可清理的旧输出；保存旧 record 快照，
        # 让 owned-remove 在记录被新路径覆盖后仍能验证旧文件所有权。
        obsolete_outputs: Dict[str, tuple[Path, Dict[str, Any]]] = {}
        pending: Dict[
            Future[PreparedMaterialization],
            tuple[
                str, str, str, Dict[str, Any], str, Path, Dict[str, Any], ReservationToken
            ],
        ] = {}
        processed = 0
        new_access_limit_state = getattr(self._client, "new_access_limit_state", None)
        run_with_access_limit_state = getattr(
            self._client,
            "run_with_access_limit_state",
            None,
        )
        access_limit_state = (
            new_access_limit_state()
            if callable(new_access_limit_state) and callable(run_with_access_limit_state)
            else None
        )

        def submit_write(
            executor: ThreadPoolExecutor,
            operation: Callable[..., PreparedMaterialization],
            *args: Any,
            **kwargs: Any,
        ) -> Future[PreparedMaterialization]:
            if access_limit_state is None:
                return executor.submit(operation, *args, **kwargs)
            return executor.submit(
                run_with_access_limit_state,
                access_limit_state,
                lambda: operation(*args, **kwargs),
            )

        def collect(done: set[Future[PreparedMaterialization]]) -> None:
            nonlocal processed
            for future in done:
                (
                    kind,
                    record_key,
                    fingerprint,
                    previous,
                    rel_path_text,
                    output,
                    next_record,
                    reservation_token,
                ) = pending.pop(future)
                processed += 1
                try:
                    prepared = future.result()
                    result = materializer.commit(prepared, self._journal)
                    mutation = result.mutations[-1]
                    next_record = {**next_record, **dict(mutation.after or {})}
                    output = result.output
                    if output in conflicting_outputs:
                        records.pop(record_key, None)
                        logger.debug(f"【STRM同步】丢弃存在路径冲突的输出：{output}")
                    else:
                        was_existing_record = bool(initial_records.get(record_key))
                        previous_path = str(
                            (previous or {}).get("output_path")
                            or (previous or {}).get("path")
                            or ""
                        ).strip()
                        if kind == "strm" and previous_path:
                            previous_output = Path(previous_path)
                            if previous_output != output:
                                obsolete_outputs[record_key] = (
                                    previous_output,
                                    dict(previous),
                                )
                        records.clear()
                        records.update(self._store.get_strm_records())
                        records[record_key] = next_record
                        if result.action == "skipped":
                            count_key = "skipped"
                            logger.debug(f"【STRM同步】文件未变化，跳过：{rel_path_text}")
                        elif kind == "sidecar":
                            count_key = "sidecars"
                        else:
                            count_key = "updated" if was_existing_record else "added"
                            logger.debug(
                                f"【STRM同步】{'更新' if previous else '生成'} STRM 成功："
                                f"{rel_path_text} -> {output}"
                            )
                        counts[count_key] += 1
                        completed_count_by_output[output] = count_key
                except (U115AccessLimitError, U115AuthError):
                    for queued in pending:
                        queued.cancel()
                    self._store.save_strm_records(records)
                    raise
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
                iter_files = self._client.iter_files
                if access_limit_state is not None:
                    try:
                        parameters = inspect.signature(iter_files).parameters.values()
                    except (TypeError, ValueError):
                        parameters = ()
                    accepts_access_limit_state = any(
                        parameter.name == "access_limit_state"
                        or parameter.kind == inspect.Parameter.VAR_KEYWORD
                        for parameter in parameters
                    )
                    if accepts_access_limit_state:
                        items = iter(
                            iter_files(
                                source_cid,
                                access_limit_state=access_limit_state,
                            )
                        )
                    else:
                        items = iter(iter_files(source_cid))
                else:
                    items = iter(iter_files(source_cid))
            except Exception:
                self._store.save_strm_records(records)
                raise
            while True:
                try:
                    item = next(items)
                except StopIteration:
                    break
                except Exception:
                    try:
                        drain_pending()
                    except (U115AccessLimitError, U115AuthError):
                        # A sibling worker may already have observed the same
                        # shared cancellation; retain the scan exception.
                        pass
                    self._store.save_strm_records(records)
                    raise
                name = str(item.get("name") or "")
                extension = PurePosixPath(name).suffix.lower()
                kind = "strm" if extension in MEDIA_EXTENSIONS else "sidecar"
                if kind == "sidecar" and (
                    not self._download_sidecars or extension not in self._sidecar_extensions
                ):
                    continue
                if self._recently_deleted(item):
                    counts["skipped"] += 1
                    logger.debug(f"【STRM同步】该文件刚被反向删除，跳过重建：{name}")
                    continue
                rel_path = PurePosixPath(str(item.get("rel_path") or name).replace("\\", "/"))
                if rel_path.is_absolute() or any(part in {"", ".", ".."} for part in rel_path.parts):
                    counts["errors"] += 1
                    logger.warning(f"【STRM同步】文件相对路径无效，跳过：{rel_path.as_posix()}")
                    continue
                rel_path_text = rel_path.as_posix()
                try:
                    cloud_path = mapping_cloud_path(mapping, rel_path_text)
                except ValueError:
                    counts["errors"] += 1
                    logger.warning(f"【STRM同步】文件远端路径无效，跳过：{rel_path_text}")
                    continue
                media_output = target_dir.joinpath(*rel_path.parts)
                output = media_output
                if kind == "strm":
                    output = strm_output_path(media_output)
                    record_key = f"{mapping_id}:{rel_path_text}"
                    if output in relocated_bases:
                        # This stem already collided, so nobody keeps the bare
                        # name any more.
                        output = strm_conflict_output_path(media_output)
                    else:
                        owner = base_output_owners.get(output)
                        if owner is not None and owner[0] != rel_path_text:
                            base_output = output
                            owner_rel_path, owner_media, owner_record_key = owner
                            owner_output = strm_conflict_output_path(owner_media)
                            # The incumbent may still be queued; make sure its
                            # write landed before renaming it.
                            drain_pending()
                            owner_record = self._store.get_strm_records().get(owner_record_key)
                            if isinstance(owner_record, dict):
                                records[owner_record_key] = dict(owner_record)
                            if not isinstance(owner_record, dict):
                                counts["errors"] += 1
                                logger.error(
                                    "【STRM同步】同名媒体 incumbent 记录不存在："
                                    f"{owner_record_key}"
                                )
                                continue
                            owner_after = {
                                **owner_record,
                                "path": str(owner_output),
                                "output_path": str(owner_output),
                            }
                            try:
                                relocation = materializer.prepare_relocation(
                                    old_output=base_output,
                                    new_output=owner_output,
                                    target_root=target_dir,
                                    mutations=(RecordMutation(
                                        owner_record_key, "strm", owner_record_key,
                                        owner_record, owner_after, "strm",
                                        "same stem relocation",
                                    ),),
                                )
                                self._journal.execute(relocation)
                                records.clear()
                                records.update(self._store.get_strm_records())
                            except Exception as err:  # noqa: BLE001
                                counts["errors"] += 1
                                logger.error(
                                    "【STRM同步】重命名同名媒体输出失败："
                                    f"{base_output} -> {owner_output}，"
                                    f"原因：{safe_error_text(err)}"
                                )
                                continue
                            for bookkeeping in (
                                claimed_outputs,
                                claimed_record_keys,
                                claimed_mtimes,
                                output_record_keys,
                                completed_count_by_output,
                            ):
                                if base_output in bookkeeping:
                                    bookkeeping[owner_output] = bookkeeping.pop(base_output)
                            # incumbent 记录已切换到扩展限定名；裸名若仍存在，
                            # 后续按旧 record 快照走 owned-remove。
                            owner_previous = initial_records.get(owner_record_key)
                            if isinstance(owner_previous, dict):
                                obsolete_outputs[owner_record_key] = (
                                    base_output,
                                    dict(owner_previous),
                                )
                            relocated_bases.add(base_output)
                            base_output_owners.pop(base_output, None)
                            output = strm_conflict_output_path(media_output)
                            same_stem_conflicts.append(
                                f"{owner_rel_path} + {rel_path_text}"
                            )
                            logger.warning(
                                "【STRM同步】同目录存在同名不同格式的媒体，"
                                f"改用带扩展名的输出：{owner_rel_path} -> {owner_output.name}，"
                                f"{rel_path_text} -> {output.name}"
                            )
                else:
                    record_key = f"{mapping_id}:sidecar:{rel_path_text}"
                mapping_record_keys.add(record_key)
                seen_record_keys.add(record_key)
                try:
                    pickcode = normalize_pickcode(str(item.get("pickcode") or ""))
                except ValueError:
                    counts["errors"] += 1
                    logger.warning(f"【STRM同步】文件 Pickcode 无效，跳过：{name or '-'}")
                    continue
                output_record_keys.setdefault(output, set()).add(record_key)
                resolved_output = output.resolve()
                if self._record_claims_output(
                    records,
                    resolved_output,
                    excluded_keys=mapping_record_keys,
                ):
                    conflicting_outputs.add(output)
                    counts["errors"] += 1
                    logger.error(
                        "【STRM同步】输出路径已被其他映射占用，跳过："
                        f"{rel_path_text} -> {output}"
                    )
                    continue
                conflicting_path = claimed_outputs.get(output)
                if conflicting_path is not None:
                    counts["conflicts"] += 1
                    winner_record_key = claimed_record_keys[output]
                    candidate_mtime = self._item_mtime(item)
                    if candidate_mtime <= claimed_mtimes[output]:
                        if record_key != winner_record_key:
                            seen_record_keys.discard(record_key)
                        counts["skipped"] += 1
                        if output not in duplicate_logged_outputs:
                            duplicate_logged_outputs.add(output)
                            logger.warning(
                                "【STRM同步】输出路径存在多个媒体，按 115 更新时间保留："
                                f"{conflicting_path}，跳过：{rel_path_text}"
                                f"（输出：{output}）"
                            )
                        continue

                    drain_pending()
                    seen_record_keys.discard(winner_record_key)
                    seen_record_keys.add(record_key)
                    displaced_record = records.get(winner_record_key)
                    if isinstance(displaced_record, dict):
                        displaced_claims = RecordClaims.from_records(
                            records,
                            upload_records,
                            mapping_ids={mapping_id},
                            upload_mappings=(self._store.get_config().get("upload_mappings") or []),
                        )
                        removal = materializer.remove_if_owned(
                            record_ref=("strm", winner_record_key),
                            record=displaced_record,
                            claims=displaced_claims,
                            target_root=target_dir,
                            expected_owner_id=mapping_id,
                        )
                        if not removal.may_drop_record or removal.unit is None:
                            counts["errors"] += 1
                            logger.error(
                                "【STRM同步】无法安全替换同路径旧候选："
                                f"{output}，原因：{removal.reason}"
                            )
                            continue
                        try:
                            if winner_record_key != record_key:
                                self._journal.execute(removal.unit)
                        except Exception as err:  # noqa: BLE001
                            counts["errors"] += 1
                            logger.error(
                                "【STRM同步】替换旧候选事务失败："
                                f"{output}，原因：{safe_error_text(err)}"
                            )
                            continue
                    records.pop(winner_record_key, None)
                    counts["skipped"] += 1
                    completed_key = completed_count_by_output.pop(output, "")
                    if winner_record_key != record_key:
                        if completed_key in counts and counts[completed_key] > 0:
                            counts[completed_key] -= 1
                    else:
                        # 同一个 record key 的较新云候选替换本轮 winner；先撤销旧候选计数。
                        if completed_key in counts and counts[completed_key] > 0:
                            counts[completed_key] -= 1
                        initial_records.pop(record_key, None)
                    if output not in duplicate_logged_outputs:
                        duplicate_logged_outputs.add(output)
                        logger.warning(
                            "【STRM同步】输出路径存在多个媒体，按 115 更新时间替换："
                            f"{conflicting_path} -> {rel_path_text}"
                            f"（输出：{output}）"
                        )
                    else:
                        logger.warning(
                            "【STRM同步】输出路径存在更多媒体，按 115 更新时间替换："
                            f"{conflicting_path} -> {rel_path_text}"
                            f"（输出：{output}）"
                        )
                claimed_outputs[output] = rel_path_text
                claimed_record_keys[output] = record_key
                claimed_mtimes[output] = self._item_mtime(item)
                if kind == "strm":
                    # Bare-name ownership is recorded only once an item has
                    # actually claimed the path: items rejected above (invalid
                    # pickcode, cross-mapping claim) or outvoted by mtime must
                    # never cause a later sibling to relocate this file. A
                    # claimant holding the path as its conflict name is not a
                    # bare-name owner either -- same-base contenders then go
                    # through the mtime winner-selection instead of a rename.
                    if output == strm_output_path(media_output):
                        base_output_owners[output] = (
                            rel_path_text,
                            media_output,
                            record_key,
                        )
                    else:
                        base_output_owners.pop(output, None)
                fingerprint = (
                    f"v{STRM_URL_FORMAT_VERSION}:{pickcode}:{item.get('size', 0)}:"
                    f"{self._moviepilot_url}"
                )
                content = ""
                if kind == "sidecar":
                    fingerprint = f"{pickcode}:{item.get('size', 0)}"
                else:
                    content = self._build_url(pickcode, name) + "\n"
                next_record = build_strm_record(
                    fingerprint=fingerprint,
                    output=output,
                    mapping=mapping,
                    item={**item, "pickcode": pickcode},
                    kind=kind,
                    cloud_path=cloud_path,
                )
                previous = records.get(record_key) or initial_records.get(record_key)
                persisted_previous = self._store.get_strm_records().get(record_key)
                if isinstance(persisted_previous, dict):
                    previous = persisted_previous
                    records[record_key] = dict(persisted_previous)
                cloud_identity = CloudIdentity(
                    pickcode=pickcode,
                    file_id=str(item.get("fileid") or item.get("file_id") or ""),
                    path=cloud_path,
                )
                request = MaterializeRequest(
                    source_id=record_key,
                    container="strm",
                    key=record_key,
                    kind=kind,
                    target_root=target_dir,
                    owner_id=mapping_id,
                    relative_path=rel_path_text,
                    output=output,
                    cloud_identity=cloud_identity,
                    fingerprint=fingerprint,
                    content=content if kind == "strm" else None,
                    pickcode=pickcode,
                    file_name=name,
                    size=None,
                    downloader=(
                        lambda code, temp: retry_call(
                            lambda: self._client.download_file(
                                code, temp, create_parent=False
                            ),
                            attempts=3,
                            delay=1.0,
                            abort_on=(U115AccessLimitError, U115AuthError),
                        )
                        if kind == "sidecar"
                        else None
                    ),
                    producer="generator",
                )
                claims = RecordClaims.from_records(
                    records,
                    upload_records,
                    mapping_ids={
                        str(record.get("mapping_id") or "")
                        for record in records.values()
                        if isinstance(record, dict) and record.get("mapping_id")
                    }
                    | {mapping_id},
                    upload_mappings=(self._store.get_config().get("upload_mappings") or []),
                )
                collision_previous = previous
                if previous and self._record_path_matches(previous, output):
                    collision_previous = {
                        **previous,
                        "cloud_identity": cloud_identity.to_record(),
                    }
                decision = materializer.validate_collision(
                    request,
                    claims,
                    previous=collision_previous,
                    excluded_claims=frozenset({("strm", record_key)}),
                )
                request, decision = stable_materialization_order([(request, decision)])[0]
                session_claim = SessionClaim(
                    request.container,
                    request.key,
                    request.owner_id,
                    request.cloud_identity,
                    request.kind,
                )
                reservation = materializer.reserve(request, decision, reservations)
                if not reservation.confirmed_candidate:
                    counts["conflicts"] += 1
                    counts["skipped"] += 1
                    continue
                decision = materializer.settle_relocation(
                    request,
                    decision,
                    reservation,
                    claims,
                    previous=previous,
                    same_container_only=True,
                )
                reservation_token = materializer.confirm(reservations, reservation)
                self._prepare_output_parent(
                    decision.output,
                    target_dir,
                    created_directories,
                    directory_lock,
                )
                future = submit_write(
                    executor,
                    materializer.prepare,
                    request,
                    claims,
                    decision=decision,
                    previous=previous,
                    incremental=self._incremental,
                    reservation=reservation_token,
                    session_reservations=reservations,
                )
                pending[future] = (
                    kind,
                    record_key,
                    fingerprint,
                    previous,
                    rel_path_text,
                    output,
                    next_record,
                    reservation_token,
                )
                if len(pending) >= STRM_WRITE_PREFETCH:
                    done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
                    collect(done)
            drain_pending()
        for conflicting_output in conflicting_outputs:
            logger.warning(
                "【STRM同步】冲突输出缺少可验证 owner，保留文件与记录等待重试："
                f"{conflicting_output}"
            )
        for obsolete_key, (obsolete_output, obsolete_record) in obsolete_outputs.items():
            if not obsolete_output.exists() and not obsolete_output.is_symlink():
                continue
            cleanup_records = dict(records)
            cleanup_records[obsolete_key] = obsolete_record
            cleanup_claims = RecordClaims.from_records(
                cleanup_records,
                upload_records,
                mapping_ids={mapping_id}
                | {
                    str(record.get("mapping_id") or "")
                    for record in cleanup_records.values()
                    if isinstance(record, dict) and record.get("mapping_id")
                },
                upload_mappings=(self._store.get_config().get("upload_mappings") or []),
            )
            removal = materializer.remove_if_owned(
                record_ref=("strm", obsolete_key),
                record=obsolete_record,
                claims=cleanup_claims,
                target_root=target_dir,
                expected_owner_id=mapping_id,
            )
            if not removal.may_drop_record or removal.unit is None:
                counts["errors"] += 1
                logger.warning(
                    "【STRM同步】旧输出 ownership 无法确认，保留文件："
                    f"{obsolete_output}，原因：{removal.reason}"
                )
            else:
                # 新输出的记录已经由物化 journal 提交；旧路径清理只提交 file op，
                # 不能再用 obsolete before 删除同 key 的新记录。
                cleanup_unit = CommitUnit.create((), removal.unit.file_ops, journal_required=True)
                try:
                    self._journal.execute(cleanup_unit)
                except Exception as err:  # noqa: BLE001
                    counts["errors"] += 1
                    logger.warning(
                        "【STRM同步】旧输出事务清理失败，保留："
                        f"{obsolete_output}，原因：{safe_error_text(err)}"
                    )
        config_mapping_ids = {
            str(item.get("id") or item.get("source_cid") or "default")
            for item in self._store.get_config().get("strm_mappings") or []
            if isinstance(item, dict)
        }
        stale_mapping_ids = config_mapping_ids | {mapping_id} | {
            str(record.get("mapping_id") or "")
            for record in records.values()
            if isinstance(record, dict) and record.get("mapping_id")
        }
        # legacy key 仅接受候选完整 mapping id 的唯一最长前缀，不从 key 猜第一段。
        for key, record in records.items():
            resolved = resolve_legacy_strm_owner(
                str(key),
                stale_mapping_ids,
                record_mapping_id=(
                    str(record.get("mapping_id") or "")
                    if isinstance(record, dict) else ""
                ),
            )
            if resolved.confidence != "ambiguous" and resolved.mapping_id:
                stale_mapping_ids.add(resolved.mapping_id)
        stale_claims = RecordClaims.from_records(
            records,
            upload_records,
            mapping_ids=stale_mapping_ids,
            upload_mappings=(self._store.get_config().get("upload_mappings") or []),
        )
        for record_key in mapping_record_keys - seen_record_keys:
            stale_record = records.get(record_key)
            if not isinstance(stale_record, dict):
                continue
            removal = materializer.remove_if_owned(
                record_ref=("strm", record_key),
                record=stale_record,
                claims=stale_claims,
                target_root=target_dir,
                expected_owner_id=mapping_id,
            )
            if removal.may_drop_record and removal.unit is not None:
                try:
                    self._journal.execute(removal.unit)
                except Exception as err:  # noqa: BLE001
                    counts["errors"] += 1
                    logger.warning(
                        "【STRM同步】失效输出事务清理失败，保留记录与文件："
                        f"{stale_record.get('path')}，原因：{safe_error_text(err)}"
                    )
                    continue
                records.pop(record_key, None)
                counts["removed"] += 1
                logger.debug(
                    f"【STRM同步】清理远端已删除条目的输出：{stale_record.get('path')}"
                )
            else:
                counts["errors"] += 1
                logger.warning(
                    "【STRM同步】失效输出 ownership 无法确认，保留记录与文件："
                    f"{stale_record.get('path')}，原因：{removal.reason}"
                )
        if same_stem_conflicts:
            logger.info(
                "【STRM同步】同名不同格式的媒体已改用带扩展名的输出："
                f"{len(same_stem_conflicts)} 组（{'；'.join(same_stem_conflicts[:5])}"
                f"{' 等' if len(same_stem_conflicts) > 5 else ''}）"
            )
        if counts["conflicts"]:
            logger.info(
                "【STRM同步】输出路径冲突已按 115 更新时间完成选优："
                f"冲突候选 {counts['conflicts']} 个"
            )
        return {
            "kind": "strm",
            "time": datetime.now().isoformat(timespec="seconds"),
            "mapping": mapping.get("source_path") or source_cid,
            **counts,
            "duration_ms": int((monotonic() - started) * 1000),
        }
