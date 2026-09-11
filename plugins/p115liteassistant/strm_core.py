"""STRM 双轨统一内核。

本模块提供规划、文件物化、记录 mutation 与 journal 协议；StrmGenerator、
LifeMonitor 与 DirectoryUploader 共享该内核，并由各调用方适配持久化 schema。
"""
from __future__ import annotations

import json
import os
import shutil
import threading
from dataclasses import asdict, dataclass, field, replace
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import (
    AbstractSet,
    Any,
    Callable,
    Iterable,
    Literal,
    Mapping,
    Optional,
    Sequence,
)
from uuid import uuid4

CollisionStatus = Literal[
    "free",
    "same_content",
    "same_owner",
    "same_identity_shared",
    "same_identity_takeover",
    "same_stem",
    "occupied",
    "candidate_lost",
]
RemoveDisposition = Literal[
    "unlinked",
    "already_missing",
    "shared_claim",
    "owner_mismatch",
    "ambiguous_legacy_owner",
    "unsafe_path",
    "claim_conflict",
    "io_error",
]
Container = Literal["strm", "upload"]
MaterialKind = Literal["strm", "sidecar"]
JournalStage = Literal[
    "prepared", "files_applied", "strm_saved", "upload_saved", "committed", "blocked"
]

JOURNAL_FEATURE_FLAG = "P115_STRM_JOURNAL_ENABLED"


def strm_journal_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """返回 journal 开关；未设置以及所有非真值均为关闭。"""

    source = os.environ if environ is None else environ
    value = source.get(JOURNAL_FEATURE_FLAG, "")
    return str(value).strip().casefold() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class CloudIdentity:
    pickcode: str = ""
    file_id: str = ""
    path: str = ""

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "CloudIdentity":
        nested = record.get("cloud_identity")
        if isinstance(nested, Mapping):
            nested_map: Mapping[str, Any] = nested
        else:
            nested_map = {}
        pickcode = str(record.get("pickcode") or nested_map.get("pickcode") or "").lower()
        file_id = str(
            record.get("file_id")
            or record.get("fileid")
            or nested_map.get("file_id")
            or nested_map.get("fileid")
            or ""
        )
        path = str(record.get("cloud_path") or nested_map.get("path") or "")
        if isinstance(nested, str):
            prefix, _, value = nested.partition(":")
            if prefix == "pickcode" and not pickcode:
                pickcode = value.lower()
            elif prefix == "file_id" and not file_id:
                file_id = value
            elif prefix == "path" and not path:
                path = value
        return cls(pickcode=pickcode, file_id=file_id, path=_normal_cloud_path(path))

    @property
    def reliable(self) -> bool:
        return bool(self.pickcode or self.file_id)

    def matches(self, other: "CloudIdentity") -> bool:
        if self.pickcode and other.pickcode:
            return self.pickcode == other.pickcode
        if self.file_id and other.file_id:
            return self.file_id == other.file_id
        return False

    def to_record(self) -> dict[str, str]:
        return {
            key: value
            for key, value in (
                ("pickcode", self.pickcode),
                ("file_id", self.file_id),
                ("path", self.path),
            )
            if value
        }


@dataclass(frozen=True)
class RecordMutation:
    source_id: str
    container: Container
    key: str
    before: Mapping[str, Any] | None
    after: Mapping[str, Any] | None
    kind: MaterialKind
    reason: str = ""


@dataclass(frozen=True)
class RemoveResult:
    disposition: RemoveDisposition
    may_drop_record: bool
    reason: str
    unit: CommitUnit | None = None


@dataclass(frozen=True)
class OwnedRemovalRequest:
    record_ref: tuple[Container, str]
    record: Mapping[str, Any]
    target_root: Path
    expected_owner_id: str


@dataclass(frozen=True)
class RecordClaim:
    container: Container
    key: str
    output: Path
    kind: MaterialKind
    owner: str
    cloud_identity: CloudIdentity
    owner_confidence: Literal["explicit", "inferred", "ambiguous"]
    record: Mapping[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class SessionClaim:
    container: Container
    key: str
    owner: str
    cloud_identity: CloudIdentity
    kind: MaterialKind = "strm"

    @property
    def ref(self) -> tuple[Container, str]:
        return self.container, self.key


@dataclass(frozen=True)
class ReservationToken:
    """worker 写入前必须再次确认的 reservation 世代令牌。"""

    output: Path
    claim_ref: tuple[Container, str]
    generation: int


@dataclass
class SessionReservation:
    output: Path
    winner: SessionClaim
    losers: list[SessionClaim] = field(default_factory=list)
    generation: int = 0
    confirmed: bool = False
    finalized: bool = False

    @property
    def token(self) -> ReservationToken:
        return ReservationToken(self.output, self.winner.ref, self.generation)


ReservationStatus = Literal[
    "reserved", "retained", "preempted", "candidate_lost", "relocated"
]


@dataclass(frozen=True)
class ReservationDecision:
    status: ReservationStatus
    output: Path
    winner: SessionClaim
    generation: int
    token: ReservationToken | None = None
    preempted: SessionClaim | None = None
    reason: str = ""

    @property
    def confirmed_candidate(self) -> bool:
        return self.token is not None and self.status != "candidate_lost"


class SessionReservations:
    """单批物化的线程安全路径预约表。

    reserve/relocate/release 只允许由规划主线程调用；worker 仅携带 token 调用
    confirm。generation 在 winner 变化和 release 后永不复用，因此已被抢占的 worker
    无法在旧路径落盘。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._reservations: dict[Path, SessionReservation] = {}
        self._last_generation: dict[Path, int] = {}

    @staticmethod
    def _output(path: Path) -> Path:
        # reservation 标识的是调用方规划的词法路径，不能因父目录随后被换成
        # symlink 而改键；真实边界在 temp/replace 前另行 resolve 复核。
        return Path(os.path.abspath(Path(path).expanduser()))

    @staticmethod
    def _claim_ref(value: SessionClaim | tuple[Container, str]) -> tuple[Container, str]:
        return value.ref if isinstance(value, SessionClaim) else (value[0], str(value[1]))

    @classmethod
    def _rank(cls, output: Path, claim: SessionClaim) -> tuple[str, str, str, str]:
        return (
            os.path.normcase(str(cls._output(output))),
            claim.kind,
            claim.container,
            claim.key,
        )

    @staticmethod
    def _copy(reservation: SessionReservation) -> SessionReservation:
        return SessionReservation(
            reservation.output,
            reservation.winner,
            list(reservation.losers),
            reservation.generation,
            reservation.confirmed,
            reservation.finalized,
        )

    def snapshot(self) -> dict[Path, SessionReservation]:
        with self._lock:
            return {
                output: self._copy(reservation)
                for output, reservation in self._reservations.items()
            }

    def get(self, output: Path) -> SessionReservation | None:
        with self._lock:
            reservation = self._reservations.get(self._output(output))
            return self._copy(reservation) if reservation else None

    def reserve(self, output: Path, candidate: SessionClaim) -> ReservationDecision:
        normalized = self._output(output)
        with self._lock:
            current = self._reservations.get(normalized)
            if current is None:
                generation = self._last_generation.get(normalized, -1) + 1
                current = SessionReservation(normalized, candidate, generation=generation)
                self._reservations[normalized] = current
                self._last_generation[normalized] = generation
                return ReservationDecision(
                    "reserved", normalized, candidate, generation, current.token
                )

            if current.winner.ref == candidate.ref:
                current.winner = candidate
                return ReservationDecision(
                    "retained", normalized, candidate, current.generation, current.token
                )

            if self._rank(normalized, candidate) < self._rank(normalized, current.winner):
                previous = current.winner
                current.losers = [item for item in current.losers if item.ref != candidate.ref]
                if all(item.ref != previous.ref for item in current.losers):
                    current.losers.append(previous)
                current.losers.sort(key=lambda item: self._rank(normalized, item))
                current.winner = candidate
                current.generation += 1
                current.confirmed = False
                current.finalized = False
                self._last_generation[normalized] = current.generation
                return ReservationDecision(
                    "preempted",
                    normalized,
                    candidate,
                    current.generation,
                    current.token,
                    previous,
                    "稳定候选排序抢占原 winner",
                )

            if all(item.ref != candidate.ref for item in current.losers):
                current.losers.append(candidate)
                current.losers.sort(key=lambda item: self._rank(normalized, item))
            return ReservationDecision(
                "candidate_lost",
                normalized,
                current.winner,
                current.generation,
                None,
                None,
                "session reservation 已由稳定排序更小的候选占用",
            )

    def confirm(
        self,
        output: Path | ReservationToken,
        claim_ref: SessionClaim | tuple[Container, str] | None = None,
        generation: int | None = None,
    ) -> bool:
        if isinstance(output, ReservationToken):
            token = output
            normalized = self._output(token.output)
            wanted_ref = token.claim_ref
            wanted_generation = token.generation
        else:
            if claim_ref is None or generation is None:
                return False
            normalized = self._output(output)
            wanted_ref = self._claim_ref(claim_ref)
            wanted_generation = generation
        with self._lock:
            current = self._reservations.get(normalized)
            matched = bool(
                current
                and current.output == normalized
                and current.winner.ref == wanted_ref
                and current.generation == wanted_generation
                and not current.finalized
            )
            if matched:
                current.confirmed = True
            return matched

    def is_confirmed(self, token: ReservationToken) -> bool:
        normalized = self._output(token.output)
        with self._lock:
            current = self._reservations.get(normalized)
            return bool(
                current
                and current.output == normalized
                and current.winner.ref == token.claim_ref
                and current.generation == token.generation
                and current.confirmed
                and not current.finalized
            )

    def guard(
        self,
        token: ReservationToken,
        callback: Callable[[], None],
    ) -> bool:
        """在预约锁内复核 token 并执行不改变 reservation 状态的短操作。"""

        normalized = self._output(token.output)
        with self._lock:
            current = self._reservations.get(normalized)
            if not (
                current
                and current.output == normalized
                and current.winner.ref == token.claim_ref
                and current.generation == token.generation
                and current.confirmed
                and not current.finalized
            ):
                return False
            callback()
            return True

    def finalize(
        self,
        token: ReservationToken,
        callback: Callable[[], None],
    ) -> bool:
        """在预约锁内复核并执行快速最终落盘。

        下载、内容构造和临时文件写入必须在锁外完成；callback 只做同目录
        ``os.replace`` 等快速 finalize。锁内再次核验 output、claim、generation、
        当前 winner 与 confirm 状态，使 preempt 不能穿过最终 replace。
        """

        normalized = self._output(token.output)
        with self._lock:
            current = self._reservations.get(normalized)
            if not (
                current
                and current.output == normalized
                and current.winner.ref == token.claim_ref
                and current.generation == token.generation
                and current.confirmed
                and not current.finalized
            ):
                return False
            callback()
            current.finalized = True
            return True

    def release(
        self,
        claim_ref: SessionClaim | tuple[Container, str] | ReservationToken,
        output: Path | None = None,
    ) -> bool:
        token_generation: int | None = None
        if isinstance(claim_ref, ReservationToken):
            token = claim_ref
            wanted_ref = token.claim_ref
            normalized = self._output(token.output)
            token_generation = token.generation
        else:
            if output is None:
                return False
            wanted_ref = self._claim_ref(claim_ref)
            normalized = self._output(output)
        with self._lock:
            current = self._reservations.get(normalized)
            if current is None:
                return False
            if token_generation is not None and current.generation != token_generation:
                return False
            if current.winner.ref == wanted_ref:
                # 失败 winner 不自动转让给可能已经启动过的 loser；由主线程重新 reserve。
                self._last_generation[normalized] = current.generation + 1
                del self._reservations[normalized]
                return True
            old_count = len(current.losers)
            current.losers = [item for item in current.losers if item.ref != wanted_ref]
            return len(current.losers) != old_count

    def relocate(
        self,
        claim_ref: SessionClaim | tuple[Container, str],
        old_output: Path,
        new_output: Path,
    ) -> ReservationDecision:
        wanted_ref = self._claim_ref(claim_ref)
        old_normalized = self._output(old_output)
        new_normalized = self._output(new_output)
        with self._lock:
            old = self._reservations.get(old_normalized)
            candidate = None
            if old:
                if old.winner.ref == wanted_ref:
                    candidate = old.winner
                else:
                    candidate = next(
                        (item for item in old.losers if item.ref == wanted_ref), None
                    )
            if candidate is None:
                fallback = SessionClaim(wanted_ref[0], wanted_ref[1], "", CloudIdentity())
                winner = old.winner if old else fallback
                return ReservationDecision(
                    "candidate_lost",
                    new_normalized,
                    winner,
                    old.generation if old else self._last_generation.get(new_normalized, -1),
                    reason="旧路径不存在该候选 reservation",
                )
            if old_normalized == new_normalized:
                return self.reserve(new_normalized, candidate)

            decision = self.reserve(new_normalized, candidate)
            if decision.status == "candidate_lost":
                return decision
            self.release(wanted_ref, old_normalized)
            return replace(decision, status="relocated")


@dataclass(frozen=True)
class SiblingCandidate:
    source_path: str
    key: str
    kind: MaterialKind = "strm"
    mtime: int = 0


@dataclass(frozen=True)
class CollisionDecision:
    status: CollisionStatus
    output: Path
    reason: str = ""
    incumbent: RecordClaim | None = None

    @property
    def writable(self) -> bool:
        return self.status in {
            "free", "same_content", "same_owner", "same_identity_shared",
            "same_identity_takeover", "same_stem",
        }


@dataclass(frozen=True)
class MaterializeRequest:
    source_id: str
    container: Container
    key: str
    kind: MaterialKind
    target_root: Path
    owner_id: str
    relative_path: str = ""
    output: Path | None = None
    cloud_identity: CloudIdentity = field(default_factory=CloudIdentity)
    fingerprint: str = ""
    content: bytes | str | None = None
    pickcode: str = ""
    file_name: str = ""
    size: int | None = None
    mtime: int | None = None
    etag: str = ""
    sha256: str = ""
    downloader: Callable[[str, Path], None] | None = field(
        default=None, compare=False, repr=False
    )
    producer: str = ""


@dataclass(frozen=True)
class MaterializeResult:
    action: Literal["created", "updated", "skipped", "relocated"]
    output: Path
    fingerprint: str
    content_matched: bool
    collision: CollisionDecision
    mutations: tuple[RecordMutation, ...]


@dataclass
class PreparedMaterialization:
    """严格物化的 prepare 产物；最终目标只能由 journal 提交。"""

    result: MaterializeResult
    unit: CommitUnit | None
    reservation: ReservationToken
    session_reservations: SessionReservations
    _journal_owned: bool = field(default=False, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def hand_off(self) -> None:
        self._journal_owned = True

    def discard(self) -> None:
        if self._closed:
            return
        if not self._journal_owned and self.unit is not None:
            for operation in self.unit.file_ops:
                if operation.temp and operation.temp.is_file() and not operation.temp.is_symlink():
                    operation.temp.unlink(missing_ok=True)
        self._closed = True


@dataclass(frozen=True)
class LegacyOwnerResolution:
    mapping_id: str = ""
    kind: MaterialKind | None = None
    confidence: Literal["explicit", "inferred", "ambiguous"] = "ambiguous"
    reason: str = ""


@dataclass(frozen=True)
class FileOperation:
    """一个可恢复的文件替换或删除。

    replace 的 ``temp`` 必须已经位于目标同目录；unlink 不需要 temp。backup 为空时由
    journal 分配同目录备份名。
    """

    action: Literal["replace", "unlink"]
    target: Path
    temp: Path | None = None
    backup: Path | None = None
    before_sha256: str = ""
    after_sha256: str = ""
    target_existed_before: bool | None = None


@dataclass(frozen=True)
class CommitUnit:
    id: str
    mutations: tuple[RecordMutation, ...]
    file_ops: tuple[FileOperation, ...] = ()
    journal_required: bool = True

    @classmethod
    def create(
        cls,
        mutations: Iterable[RecordMutation],
        file_ops: Iterable[FileOperation] = (),
        *,
        journal_required: bool = True,
    ) -> "CommitUnit":
        return cls(
            id=uuid4().hex,
            mutations=tuple(mutations),
            file_ops=tuple(file_ops),
            journal_required=journal_required,
        )


def _normal_cloud_path(value: str) -> str:
    if not value:
        return ""
    normalized = PurePosixPath(str(value).replace("\\", "/")).as_posix()
    return normalized if normalized.startswith("/") else f"/{normalized}"


def _record_output(record: Mapping[str, Any]) -> str:
    return str(record.get("output_path") or record.get("path") or "").strip()


def _record_kind(key: str, record: Mapping[str, Any]) -> MaterialKind:
    return "sidecar" if str(record.get("kind") or "") == "sidecar" or ":sidecar:" in key else "strm"


def _owner_name(container: Container, value: str) -> str:
    value = str(value or "")
    if value.startswith(f"{container}:"):
        return value
    return f"{container}:{value}"


def resolve_legacy_strm_owner(
    key: str,
    mapping_ids: Iterable[str],
    once_ids: Iterable[str] = (),
    *,
    record_mapping_id: str = "",
) -> LegacyOwnerResolution:
    """按完整 mapping id 的最长前缀解析 legacy key，不使用 split(':', 1)。"""

    key = str(key)
    candidates: list[tuple[int, str, MaterialKind]] = []
    for mapping_id in {str(item) for item in (*tuple(mapping_ids), *tuple(once_ids)) if str(item)}:
        for kind, prefix in (
            ("sidecar", f"{mapping_id}:sidecar:"),
            ("strm", f"{mapping_id}:"),
        ):
            if key.startswith(prefix):
                candidates.append((len(prefix), mapping_id, kind))
    if not candidates:
        return LegacyOwnerResolution(reason="legacy key 没有匹配的 mapping 前缀")
    longest = max(length for length, _mapping_id, _kind in candidates)
    winners = {(mapping_id, kind) for length, mapping_id, kind in candidates if length == longest}
    if len(winners) != 1:
        return LegacyOwnerResolution(reason="legacy key 最长前缀并列")
    mapping_id, kind = next(iter(winners))
    if record_mapping_id and record_mapping_id != mapping_id:
        return LegacyOwnerResolution(reason="记录 mapping_id 与 key 最长前缀不一致")
    return LegacyOwnerResolution(mapping_id, kind, "inferred", "最长 mapping 前缀唯一")


def resolve_legacy_upload_owner(
    record_key: str,
    record: Mapping[str, Any],
    mappings: Iterable[Mapping[str, Any]],
) -> LegacyOwnerResolution:
    """按 source、远端 target 与 STRM 输出根三条件解析 legacy upload owner。"""

    try:
        local = Path(record_key).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return LegacyOwnerResolution(reason="上传记录本地路径不可解析")
    remote_target = _normal_cloud_path(str(record.get("target") or ""))
    output_value = _record_output(record)
    matches: list[tuple[int, str, Mapping[str, Any]]] = []
    for mapping in mappings:
        if not mapping.get("enabled", True):
            continue
        source_value = str(mapping.get("source") or "").strip()
        remote_root = _normal_cloud_path(str(mapping.get("target") or ""))
        strm_root_value = str(mapping.get("strm_target") or "").strip()
        if not source_value or not remote_target or not remote_root:
            continue
        if not output_value or not strm_root_value:
            continue
        try:
            source = Path(source_value).expanduser().resolve(strict=False)
            local.relative_to(source)
        except (OSError, RuntimeError, ValueError):
            continue
        if not (
            remote_target == remote_root
            or remote_target.startswith(f"{remote_root.rstrip('/')}/")
        ):
            continue
        if not _in_root(Path(output_value), Path(strm_root_value)):
            continue
        mapping_id = str(mapping.get("id") or source)
        matches.append((len(source.parts), mapping_id, mapping))
    if not matches:
        return LegacyOwnerResolution(
            reason="上传记录 source/remote target/STRM target 三条件无唯一匹配"
        )
    depth = max(item[0] for item in matches)
    winners = [item for item in matches if item[0] == depth]
    if len(winners) != 1:
        return LegacyOwnerResolution(reason="上传记录三条件匹配的最长 source root 并列")
    _depth, mapping_id, _mapping = winners[0]
    return LegacyOwnerResolution(
        mapping_id,
        _record_kind(record_key, record),
        "inferred",
        "source/remote target/STRM target 三条件唯一匹配",
    )


class RecordClaims:
    def __init__(self, claims: Iterable[RecordClaim] = ()):
        self._claims = tuple(claims)

    def __iter__(self):
        return iter(self._claims)

    def for_output(
        self,
        output: Path,
        *,
        excluded: AbstractSet[tuple[str, str]] = frozenset(),
    ) -> tuple[RecordClaim, ...]:
        wanted = _safe_resolve(output)
        return tuple(
            claim
            for claim in self._claims
            if (claim.container, claim.key) not in excluded
            and _safe_resolve(claim.output) == wanted
        )

    def get(self, record_ref: tuple[str, str]) -> RecordClaim | None:
        return next(
            (
                claim
                for claim in self._claims
                if (claim.container, claim.key) == tuple(record_ref)
            ),
            None,
        )

    @classmethod
    def from_records(
        cls,
        strm_records: Mapping[str, Mapping[str, Any]] | None = None,
        upload_records: Mapping[str, Mapping[str, Any]] | Any = None,
        *,
        mapping_ids: Iterable[str] = (),
        once_ids: Iterable[str] = (),
        upload_mappings: Iterable[Mapping[str, Any]] = (),
    ) -> "RecordClaims":
        upload_raw = upload_records
        if not isinstance(upload_raw, Mapping):
            to_dict = getattr(upload_raw, "to_dict", None)
            upload_raw = to_dict() if callable(to_dict) else {}
        claims: list[RecordClaim] = []
        for key, raw in (strm_records or {}).items():
            if not isinstance(raw, Mapping) or not _record_output(raw):
                continue
            explicit = str(raw.get("owner_id") or "")
            if explicit:
                owner, confidence = _owner_name("strm", explicit), "explicit"
            else:
                resolved = resolve_legacy_strm_owner(
                    str(key), mapping_ids, once_ids,
                    record_mapping_id=str(raw.get("mapping_id") or ""),
                )
                owner = _owner_name("strm", resolved.mapping_id) if resolved.mapping_id else ""
                confidence = resolved.confidence
            claims.append(RecordClaim(
                "strm", str(key), Path(_record_output(raw)), _record_kind(str(key), raw),
                owner, CloudIdentity.from_record(raw), confidence, raw,
            ))
        for key, raw in (upload_raw or {}).items():
            if not isinstance(raw, Mapping) or not _record_output(raw):
                continue
            explicit = str(raw.get("owner_id") or "")
            if explicit:
                owner, confidence = _owner_name("upload", explicit), "explicit"
            else:
                resolved = resolve_legacy_upload_owner(str(key), raw, upload_mappings)
                owner = _owner_name("upload", resolved.mapping_id) if resolved.mapping_id else ""
                confidence = resolved.confidence
            claims.append(RecordClaim(
                "upload", str(key), Path(_record_output(raw)), _record_kind(str(key), raw),
                owner, CloudIdentity.from_record(raw), confidence, raw,
            ))
        return cls(claims)


def stable_materialization_order(
    items: Iterable[tuple[MaterializeRequest, CollisionDecision]],
) -> list[tuple[MaterializeRequest, CollisionDecision]]:
    """主线程固定排序；worker 完成顺序不参与 winner 决策。"""

    return sorted(
        items,
        key=lambda item: (
            os.path.normcase(str(_safe_resolve(item[1].output))),
            item[0].kind,
            item[0].container,
            item[0].key,
        ),
    )


def build_record_mutation(
    request: MaterializeRequest,
    *,
    before: Mapping[str, Any] | None,
    output: Path,
    reason: str,
    drop: bool = False,
    verified_sidecar_metadata: Mapping[str, Any] | None = None,
) -> RecordMutation:
    """保留旧顶层字段并补齐统一 schema；不写 Store。"""

    after: dict[str, Any] | None
    if drop:
        after = None
    else:
        after = dict(before or {})
        after.update({
            "producer": request.producer or request.source_id,
            "owner_id": request.owner_id,
            "output_path": str(output),
            "kind": request.kind,
            "fingerprint": request.fingerprint,
            "cloud_identity": request.cloud_identity.to_record(),
        })
        if request.kind == "sidecar":
            for key in ("size", "mtime", "etag", "sha256"):
                after.pop(key, None)
            metadata = (
                dict(verified_sidecar_metadata)
                if verified_sidecar_metadata is not None
                else _validated_sidecar_metadata(request, output)
            ) if request.cloud_identity.reliable else {}
            for key, value in metadata.items():
                requested = getattr(request, key, None)
                if key in {"size", "mtime", "etag", "sha256"} and requested not in (None, ""):
                    after[key] = value
        if request.container == "strm":
            after["path"] = str(output)
        else:
            after.setdefault("strm_target", str(request.target_root))
            if request.content is not None:
                raw = request.content.encode() if isinstance(request.content, str) else request.content
                after["strm_signature"] = sha256(raw).hexdigest()
    return RecordMutation(
        request.source_id,
        request.container,
        request.key,
        dict(before) if before is not None else None,
        after,
        request.kind,
        reason,
    )


class StrmOwnershipConflict(ValueError):
    pass


class StrmRecoveryBlockedError(RuntimeError):
    """未完成 STRM journal 无法安全恢复，输出任务必须停止。"""


def _safe_resolve(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _in_root(path: Path, root: Path) -> bool:
    try:
        _safe_resolve(path).relative_to(_safe_resolve(root))
        current = path.expanduser()
        while current != current.parent and current != root:
            if current.exists() and current.is_symlink():
                return False
            current = current.parent
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def _default_output(request: MaterializeRequest) -> Path:
    if request.output is not None:
        return request.output
    relative = PurePosixPath(request.relative_path.replace("\\", "/"))
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"无效相对路径: {request.relative_path}")
    path = request.target_root.joinpath(*relative.parts)
    if request.kind == "sidecar":
        return path
    if path.suffix.lower() == ".iso":
        return path.with_name(f"{path.stem}.iso.strm")
    return path.with_suffix(".strm")


def _same_stem_output(output: Path, source_path: str) -> Path:
    name = PurePosixPath(source_path).name
    return output.with_name(f"{name}.strm")


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _strm_payload_bytes(
    request: MaterializeRequest,
    moviepilot_url: str,
    redirect_secret: str,
) -> bytes:
    """唯一的 STRM payload 构造入口，供 collision 与 prepare 共用。"""

    if request.kind != "strm":
        raise ValueError("非 STRM 请求没有可预生成 payload")
    payload = request.content
    if payload is None:
        from .strm import build_strm_content

        payload = build_strm_content(
            moviepilot_url,
            request.pickcode,
            redirect_secret,
            request.file_name,
        )
    return payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)


def _strm_content_matches(output: Path, payload: bytes) -> bool:
    """只接受普通文件的完整 bytes 一致；任何读取异常均 fail-closed。"""

    if output.is_symlink() or not output.is_file():
        return False
    try:
        return output.stat().st_size == len(payload) and output.read_bytes() == payload
    except OSError:
        return False


@dataclass(frozen=True)
class _DiskTargetState:
    kind: Literal["missing", "file", "symlink", "other"]
    device: int = 0
    inode: int = 0
    size: int = 0
    mtime_ns: int = 0
    ctime_ns: int = 0
    sha256: str = ""


def _disk_target_state(path: Path) -> _DiskTargetState:
    """不跟随 symlink 地记录目标状态，用于最终 replace 的 compare-before。"""

    if path.is_symlink():
        return _DiskTargetState("symlink")
    try:
        stat = path.stat()
    except FileNotFoundError:
        return _DiskTargetState("missing")
    if not path.is_file():
        return _DiskTargetState(
            "other", stat.st_dev, stat.st_ino, stat.st_size,
            stat.st_mtime_ns, stat.st_ctime_ns,
        )
    return _DiskTargetState(
        "file", stat.st_dev, stat.st_ino, stat.st_size,
        stat.st_mtime_ns, stat.st_ctime_ns, _file_sha256(path),
    )


def _assert_safe_target_parent(output: Path, target_root: Path) -> None:
    """在每次创建 temp / replace 前重新解析父目录边界。"""

    parent = output.parent
    if not parent.is_dir() or parent.is_symlink() or not _in_root(parent, target_root):
        raise StrmOwnershipConflict("occupied/refused: 输出父目录越界或已被符号链接替换")
    try:
        _safe_resolve(parent).relative_to(_safe_resolve(target_root))
    except (OSError, RuntimeError, ValueError) as error:
        raise StrmOwnershipConflict(
            "occupied/refused: 输出父目录已漂移到 target_root 外"
        ) from error


def _write_temp(output: Path, target_root: Path, payload: bytes) -> Path:
    _assert_safe_target_parent(output, target_root)
    temp = output.with_name(f".{output.name}.{threading.get_ident()}.{uuid4().hex}.tmp")
    with temp.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return temp


def _create_temp(output: Path, target_root: Path) -> Path:
    _assert_safe_target_parent(output, target_root)
    temp = output.with_name(f".{output.name}.{uuid4().hex}.tmp")
    with temp.open("xb"):
        pass
    return temp


def _sync_temp(temp: Path) -> None:
    with temp.open("rb") as handle:
        os.fsync(handle.fileno())


class StrmMaterializer:
    """统一 STRM/sidecar 文件内核；不保存 Store。"""

    def __init__(self, store: Any = None, moviepilot_url: str = "", redirect_secret: str = ""):
        self._store = store
        self._moviepilot_url = str(moviepilot_url or "").rstrip("/")
        self._redirect_secret = str(redirect_secret or "")
        if not self._redirect_secret and store is not None:
            getter = getattr(store, "get_redirect_secret", None)
            if callable(getter):
                self._redirect_secret = str(getter())

    def validate_collision(
        self,
        request: MaterializeRequest,
        claims: RecordClaims,
        *,
        session_claims: Mapping[Path, SessionClaim | SessionReservation] | None = None,
        session_reservations: SessionReservations | None = None,
        sibling_candidates: Iterable[SiblingCandidate] = (),
        excluded_claims: AbstractSet[tuple[str, str]] = frozenset(),
        previous: Mapping[str, Any] | None = None,
    ) -> CollisionDecision:
        requested_output = _default_output(request)
        output = _safe_resolve(requested_output)
        if not _in_root(requested_output, request.target_root):
            return CollisionDecision("occupied", output, "输出越界或经过符号链接")

        siblings = [item for item in sibling_candidates if item.kind == "strm"]
        if request.kind == "strm" and siblings:
            own_base = output
            same_base = [item for item in siblings if _safe_resolve(
                _default_output(replace(request, relative_path=item.source_path, output=None, key=item.key))
            ) == own_base and item.key != request.key]
            if same_base:
                output = _safe_resolve(_same_stem_output(output, request.relative_path or request.file_name))

        session_value = (
            session_reservations.get(output)
            if session_reservations is not None
            else (session_claims or {}).get(output)
        )
        session = (
            session_value.winner
            if isinstance(session_value, SessionReservation)
            else session_value
        )
        if session and session.ref != (request.container, request.key):
            return CollisionDecision(
                "candidate_lost", output, "session reservation 已由主线程确认给其他候选"
            )

        incumbents = claims.for_output(output, excluded=excluded_claims)
        if not incumbents:
            if output.exists() or output.is_symlink():
                if requested_output.is_symlink() or output.is_symlink() or not output.is_file():
                    return CollisionDecision(
                        "occupied", output, "磁盘输出已存在且不是安全的普通文件"
                    )
                previous_identity = CloudIdentity.from_record(previous or {})
                previous_output = _record_output(previous or {})
                previous_owner = str(
                    (previous or {}).get("owner_id")
                    or (previous or {}).get("mapping_id")
                    or ""
                )
                identity_owned = bool(
                    previous
                    and previous_output
                    and _safe_resolve(Path(previous_output)) == output
                    and request.cloud_identity.reliable
                    and (
                        (
                            previous_identity.reliable
                            and previous_identity.matches(request.cloud_identity)
                        )
                        or previous_owner == request.owner_id
                    )
                )
                if not identity_owned:
                    if request.kind == "strm":
                        try:
                            payload = _strm_payload_bytes(
                                request, self._moviepilot_url, self._redirect_secret
                            )
                        except (OSError, TypeError, ValueError):
                            payload = None
                        if payload is not None and _strm_content_matches(output, payload):
                            return CollisionDecision(
                                "same_content", output,
                                "无其他 claim 的既有 STRM 与期望 payload 完全一致",
                            )
                    return CollisionDecision(
                        "occupied", output, "磁盘输出已存在且没有身份一致的 previous/claim"
                    )
            return CollisionDecision("same_stem" if output != _safe_resolve(_default_output(request)) else "free", output)
        if output.exists() or output.is_symlink():
            previous_identity = CloudIdentity.from_record(previous or {})
            identity_owned = bool(
                request.cloud_identity.reliable
                and (
                    any(
                        incumbent.cloud_identity.reliable
                        and incumbent.cloud_identity.matches(request.cloud_identity)
                        for incumbent in incumbents
                    )
                    or (
                        previous_identity.reliable
                        and previous_identity.matches(request.cloud_identity)
                    )
                )
            )
            if output.is_symlink() or not output.is_file() or not identity_owned:
                return CollisionDecision(
                    "occupied", output, "磁盘输出缺少身份一致的 previous/claim", incumbents[0]
                )
        wanted_owner = _owner_name(request.container, request.owner_id)
        if any(
            incumbent.owner_confidence == "ambiguous" or not incumbent.owner
            for incumbent in incumbents
        ):
            return CollisionDecision(
                "occupied", output, "现有 claim owner 含糊", incumbents[0]
            )
        same_owner = [item for item in incumbents if item.owner == wanted_owner]
        identity_matches = [
            item
            for item in incumbents
            if request.cloud_identity.reliable
            and item.cloud_identity.reliable
            and item.cloud_identity.matches(request.cloud_identity)
        ]
        if len(same_owner) == len(incumbents):
            return CollisionDecision("same_owner", output, "全部 claims 属于同 owner", same_owner[0])
        if len(identity_matches) == len(incumbents):
            return CollisionDecision(
                "same_identity_shared", output, "全部 claims 属于同一可靠云身份", identity_matches[0]
            )
        refs = ", ".join(f"{item.container}/{item.key}" for item in incumbents)
        return CollisionDecision(
            "occupied",
            output,
            f"同输出 claims 所有权或身份不一致：{refs}",
            incumbents[0],
        )

    def reserve(
        self,
        request: MaterializeRequest,
        decision: CollisionDecision,
        reservations: SessionReservations,
    ) -> ReservationDecision:
        """规划线程为已通过 collision 的 request 建立 reservation。"""

        if not decision.writable:
            raise StrmOwnershipConflict(decision.reason or decision.status)
        return reservations.reserve(
            decision.output,
            SessionClaim(
                request.container,
                request.key,
                request.owner_id,
                request.cloud_identity,
                request.kind,
            ),
        )

    def settle_relocation(
        self,
        request: MaterializeRequest,
        decision: CollisionDecision,
        reservation: ReservationDecision,
        claims: RecordClaims,
        *,
        previous: Mapping[str, Any] | None = None,
        same_container_only: bool = True,
    ) -> CollisionDecision:
        """确认 relocation 边界；真正旧输出清理由 owned-remove 完成。

        阶段 C 不在调用方 rename。跨容器 incumbent 只允许同身份共享，绝不迁移。
        """

        if not reservation.confirmed_candidate:
            raise StrmOwnershipConflict(reservation.reason or reservation.status)
        incumbent = decision.incumbent
        if (
            same_container_only
            and incumbent is not None
            and incumbent.container != request.container
            and decision.status not in {"same_identity_shared"}
        ):
            raise StrmOwnershipConflict("跨容器 relocation 默认关闭")
        return decision

    @staticmethod
    def confirm(
        reservations: SessionReservations,
        reservation: ReservationDecision,
    ) -> ReservationToken:
        token = reservation.token
        if token is None or not reservations.confirm(token):
            raise StrmOwnershipConflict("reservation confirm 失败")
        return token

    def prepare(
        self,
        request: MaterializeRequest,
        claims: RecordClaims,
        *,
        decision: CollisionDecision | None = None,
        previous: Mapping[str, Any] | None = None,
        incremental: bool = True,
        reservation: ReservationToken | ReservationDecision,
        session_reservations: SessionReservations,
        extra_mutations: Iterable[RecordMutation] = (),
        extra_file_ops: Iterable[FileOperation] = (),
    ) -> PreparedMaterialization:
        """只创建 temp/FileOperation/RecordMutation，不替换最终目标。"""

        decision = decision or self.validate_collision(request, claims, previous=previous)
        if not decision.writable:
            raise StrmOwnershipConflict(decision.reason or decision.status)
        output = decision.output
        token = reservation.token if isinstance(reservation, ReservationDecision) else reservation
        if (
            token is None
            or token.claim_ref != (request.container, request.key)
            or _safe_resolve(token.output) != _safe_resolve(output)
            or not session_reservations.is_confirmed(token)
        ):
            raise StrmOwnershipConflict(
                "严格 prepare 要求已 confirm 且 generation/winner 匹配的 reservation"
            )
        if not _in_root(output, request.target_root):
            raise StrmOwnershipConflict(
                f"occupied/refused: 输出父目录越界或已被符号链接替换: {output}"
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        _assert_safe_target_parent(output, request.target_root)
        planned = _disk_target_state(output)
        if planned.kind in {"symlink", "other"}:
            raise StrmOwnershipConflict("occupied/refused: 规划目标不是普通文件或不存在状态")
        existed = planned.kind == "file"
        temp: Path | None = None
        temp_sha256 = ""
        content_matched = False
        verified_sidecar_metadata: dict[str, Any] | None = None
        skip = False

        def guarded(callback: Callable[[], None], message: str) -> None:
            if not session_reservations.guard(token, callback):
                raise StrmOwnershipConflict(message)

        try:
            if request.kind == "strm":
                payload_bytes = _strm_payload_bytes(
                    request, self._moviepilot_url, self._redirect_secret
                )
                content_matched = _strm_content_matches(output, payload_bytes)
                if decision.status == "same_content" and not content_matched:
                    raise StrmOwnershipConflict(
                        "occupied/refused: same_content 在 prepare 二次校验时已不匹配"
                    )
                skip = bool(
                    incremental
                    and decision.status != "same_content"
                    and _incremental_record_matches(previous, request, output)
                    and content_matched
                )
                if not skip:
                    def create_payload_temp() -> None:
                        nonlocal temp, temp_sha256
                        _assert_safe_target_parent(output, request.target_root)
                        if _disk_target_state(output) != planned:
                            raise StrmOwnershipConflict(
                                "occupied/refused: collision 决策后的磁盘 incumbent 状态已漂移"
                            )
                        temp = _write_temp(output, request.target_root, payload_bytes)
                        temp_sha256 = _file_sha256(temp)
                    guarded(create_payload_temp, "reservation 在 temp 创建前已失效")
            else:
                skip = bool(incremental and _sidecar_incremental_matches(previous, request, output))
                content_matched = skip
                if skip:
                    verified_sidecar_metadata = _validated_sidecar_metadata(request, output)
                else:
                    if request.downloader is None:
                        raise ValueError("sidecar 物化缺少 downloader")
                    def create_download_temp() -> None:
                        nonlocal temp
                        _assert_safe_target_parent(output, request.target_root)
                        if _disk_target_state(output) != planned:
                            raise StrmOwnershipConflict(
                                "occupied/refused: collision 决策后的磁盘 incumbent 状态已漂移"
                            )
                        temp = _create_temp(output, request.target_root)
                    guarded(create_download_temp, "reservation 在 temp 创建前已失效")
                    assert temp is not None
                    request.downloader(request.pickcode, temp)
                    _assert_safe_target_parent(output, request.target_root)
                    if temp.is_symlink() or not temp.is_file():
                        raise OSError("sidecar downloader 未生成普通文件")
                    if request.size is not None and temp.stat().st_size != request.size:
                        raise OSError("sidecar 下载大小不匹配")
                    if request.sha256 and _file_sha256(temp).casefold() != request.sha256.casefold():
                        raise OSError("sidecar 下载摘要不匹配")
                    _sync_temp(temp)
                    temp_sha256 = _file_sha256(temp)
                    verified_sidecar_metadata = _validated_sidecar_metadata(request, temp)

            _assert_safe_target_parent(output, request.target_root)
            if _disk_target_state(output) != planned:
                raise StrmOwnershipConflict(
                    "occupied/refused: collision 决策后的磁盘 incumbent 状态已漂移"
                )
            mutation = build_record_mutation(
                request, before=previous, output=output,
                reason="incremental skip" if skip else "materialized",
                verified_sidecar_metadata=verified_sidecar_metadata,
            )
            result = MaterializeResult(
                "skipped" if skip else ("updated" if existed else "created"),
                output, request.fingerprint, content_matched, decision,
                (mutation, *tuple(extra_mutations)),
            )
            file_ops = list(extra_file_ops)
            if not skip:
                assert temp is not None
                file_ops.append(FileOperation(
                    "replace", output, temp=temp, before_sha256=(planned.sha256 if existed else ""),
                    after_sha256=temp_sha256, target_existed_before=existed,
                ))
            unit = CommitUnit.create(result.mutations, file_ops, journal_required=True)
            return PreparedMaterialization(result, unit, token, session_reservations)
        except Exception:
            if temp is not None and temp.is_file() and not temp.is_symlink():
                temp.unlink(missing_ok=True)
            raise

    def commit(
        self, prepared: PreparedMaterialization, journal: "CommitJournal"
    ) -> MaterializeResult:
        """在 reservation finalize 锁内执行唯一 journal 提交。"""

        if prepared._closed:
            raise StrmOwnershipConflict("prepared materialization 已关闭")
        try:
            def execute() -> None:
                prepared.hand_off()
                journal.execute(prepared.unit)
            if not prepared.session_reservations.finalize(
                prepared.reservation, execute
            ):
                prepared.discard()
                raise StrmOwnershipConflict("reservation 在 journal 提交前已失效")
            prepared._closed = True
            return prepared.result
        finally:
            prepared.session_reservations.release(prepared.reservation)

    def prepare_relocation(
        self,
        *,
        old_output: Path,
        new_output: Path,
        target_root: Path,
        mutations: Iterable[RecordMutation],
    ) -> CommitUnit:
        """复制旧文件到新目录 temp，并以 replace+unlink 构造可恢复 relocation。"""

        old_output = Path(old_output).expanduser()
        new_output = Path(new_output).expanduser()
        if not _in_root(old_output, target_root) or not _in_root(new_output, target_root):
            raise StrmOwnershipConflict("relocation 输出越界或经过符号链接")
        if old_output.is_symlink() or not old_output.is_file():
            raise StrmOwnershipConflict("relocation 源不是普通文件")
        if new_output.exists() or new_output.is_symlink():
            raise StrmOwnershipConflict("relocation 目标已存在")
        new_output.parent.mkdir(parents=True, exist_ok=True)
        _assert_safe_target_parent(new_output, target_root)
        temp = _create_temp(new_output, target_root)
        try:
            shutil.copy2(old_output, temp)
            _sync_temp(temp)
            digest = _file_sha256(temp)
            old_digest = _file_sha256(old_output)
            return CommitUnit.create(
                mutations,
                (
                    FileOperation("replace", new_output, temp=temp,
                                  after_sha256=digest, target_existed_before=False),
                    FileOperation("unlink", old_output, before_sha256=old_digest,
                                  target_existed_before=True),
                ),
                journal_required=True,
            )
        except Exception:
            temp.unlink(missing_ok=True)
            raise

    def prepare_owned_removals(
        self,
        requests: Iterable[OwnedRemovalRequest],
        claims: RecordClaims,
    ) -> tuple[RemoveResult, ...]:
        """按输出路径分组准备删除；纯 prepare，不修改文件或记录。"""

        grouped: dict[Path, list[OwnedRemovalRequest]] = {}
        early: list[RemoveResult] = []
        for request in requests:
            output_value = _record_output(request.record)
            if not output_value:
                early.append(RemoveResult("unsafe_path", False, "记录没有 output_path/path"))
                continue
            output = Path(output_value)
            if not _in_root(output, request.target_root):
                early.append(RemoveResult("unsafe_path", False, "输出越界或经过符号链接"))
                continue
            grouped.setdefault(_safe_resolve(output), []).append(request)

        results = list(early)
        for output, group in grouped.items():
            refs = frozenset(request.record_ref for request in group)
            group_claims: list[RecordClaim] = []
            refusal: RemoveResult | None = None
            for request in group:
                claim = claims.get(request.record_ref)
                expected = _owner_name(request.record_ref[0], request.expected_owner_id)
                if claim is None or claim.owner_confidence == "ambiguous" or not claim.owner:
                    refusal = RemoveResult(
                        "ambiguous_legacy_owner", False, "owner 无法唯一确认"
                    )
                    break
                if claim.owner != expected:
                    refusal = RemoveResult(
                        "owner_mismatch", False,
                        f"期望 {expected}，实际 {claim.owner}",
                    )
                    break
                group_claims.append(claim)
            if refusal is not None:
                results.append(refusal)
                continue

            others = claims.for_output(output, excluded=refs)
            if any(
                item.owner_confidence == "ambiguous" or not item.owner
                for item in others
            ):
                results.append(RemoveResult(
                    "claim_conflict", False, "同路径存在含糊 claim"
                ))
                continue

            mutations = tuple(
                RecordMutation(
                    source_id=request.record_ref[1],
                    container=request.record_ref[0],
                    key=request.record_ref[1],
                    before=dict(request.record),
                    after=None,
                    kind=claim.kind,
                    reason="owned removal",
                )
                for request, claim in zip(group, group_claims)
            )
            if others:
                unit = CommitUnit.create(mutations, journal_required=True)
                results.append(RemoveResult(
                    "shared_claim", True,
                    "仍有其他有效 claim，仅删除当前记录", unit,
                ))
                continue
            try:
                if not output.exists() and not output.is_symlink():
                    unit = CommitUnit.create(mutations, journal_required=True)
                    results.append(RemoveResult(
                        "already_missing", True, "文件已不存在", unit
                    ))
                    continue
                if output.is_symlink() or not output.is_file():
                    results.append(RemoveResult(
                        "unsafe_path", False, "目标不是普通文件"
                    ))
                    continue
                digest = _file_sha256(output)
            except OSError as err:
                results.append(RemoveResult("io_error", False, str(err)))
                continue
            unit = CommitUnit.create(
                mutations,
                (FileOperation(
                    "unlink", output, before_sha256=digest,
                    target_existed_before=True,
                ),),
                journal_required=True,
            )
            results.append(RemoveResult(
                "unlinked", True, "已准备删除唯一 owner 的输出", unit
            ))
        return tuple(results)

    def remove_if_owned(
        self,
        *,
        record_ref: tuple[Container, str],
        record: Mapping[str, Any],
        claims: RecordClaims,
        target_root: Path,
        expected_owner_id: str,
    ) -> RemoveResult:
        """准备单条 owned removal；不 unlink，也不保存记录。"""

        return self.prepare_owned_removals((OwnedRemovalRequest(
            record_ref=record_ref,
            record=record,
            target_root=target_root,
            expected_owner_id=expected_owner_id,
        ),), claims)[0]



def _incremental_record_matches(
    previous: Mapping[str, Any] | None,
    request: MaterializeRequest,
    output: Path,
) -> bool:
    return bool(
        previous
        and str(previous.get("fingerprint") or "") == request.fingerprint
        and _record_output(previous)
        and _safe_resolve(Path(_record_output(previous))) == _safe_resolve(output)
    )


def _requested_sidecar_metadata(request: MaterializeRequest) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in ("size", "mtime", "etag", "sha256"):
        value = getattr(request, key)
        if value not in (None, ""):
            metadata[key] = value.casefold() if key == "sha256" else value
    return metadata


def _validated_sidecar_metadata(
    request: MaterializeRequest,
    output: Path,
) -> dict[str, Any]:
    """只从已存在的普通文件验证 request 声明；不触发下载。"""

    if (
        request.kind != "sidecar"
        or not request.cloud_identity.reliable
        or output.is_symlink()
        or not output.is_file()
    ):
        return {}
    try:
        requested = _requested_sidecar_metadata(request)
        stat = output.stat()
        if "size" in requested and stat.st_size != requested["size"]:
            requested.pop("size")
        if "mtime" in requested and int(stat.st_mtime) != int(requested["mtime"]):
            requested.pop("mtime")
        # downloader 没有返回可核验的实体标签，不能把云端 etag 当作实测值。
        requested.pop("etag", None)
        if "sha256" in requested and _file_sha256(output).casefold() != requested["sha256"]:
            requested.pop("sha256")
        return requested
    except OSError:
        return {}


def _sidecar_incremental_matches(
    previous: Mapping[str, Any] | None,
    request: MaterializeRequest,
    output: Path,
) -> bool:
    if not _incremental_record_matches(previous, request, output):
        return False
    if not request.cloud_identity.reliable or output.is_symlink() or not output.is_file():
        return False
    previous_identity = CloudIdentity.from_record(previous)
    if not previous_identity.reliable or not previous_identity.matches(request.cloud_identity):
        return False
    metadata_fields = ("size", "mtime", "etag", "sha256")
    if not any(previous.get(key) not in (None, "") for key in metadata_fields) and not any(
        getattr(request, key) not in (None, "") for key in metadata_fields
    ):
        return False
    try:
        stat = output.stat()
        measured = False
        recorded_size = previous.get("size")
        if recorded_size not in (None, ""):
            if stat.st_size != recorded_size:
                return False
            measured = True
        if request.size is not None:
            if previous.get("size") != request.size or stat.st_size != request.size:
                return False
            measured = True

        recorded_mtime = previous.get("mtime")
        if recorded_mtime not in (None, ""):
            if int(stat.st_mtime) != int(recorded_mtime):
                return False
            measured = True
        if request.mtime is not None:
            if previous.get("mtime") != request.mtime or int(stat.st_mtime) != int(request.mtime):
                return False
            measured = True

        if request.etag and previous.get("etag") != request.etag:
            return False

        recorded_sha256 = str(previous.get("sha256") or "").casefold()
        requested_sha256 = request.sha256.casefold()
        if requested_sha256 and recorded_sha256 != requested_sha256:
            return False
        digest = requested_sha256 or recorded_sha256
        if digest:
            if _file_sha256(output).casefold() != digest:
                return False
            measured = True
        # etag 不能从本地普通文件实测；只有 etag 时仍需重下。
        return measured
    except (OSError, TypeError, ValueError):
        return False


def _fsync_dir(path: Path) -> None:
    """持久化目录项变化；仅目录已经不存在时跳过。"""

    try:
        fd = os.open(Path(path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except FileNotFoundError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_parent_dirs(paths: Iterable[Path]) -> None:
    parents = {str(_safe_resolve(Path(path).parent)): Path(path).parent for path in paths}
    for key in sorted(parents):
        _fsync_dir(parents[key])


class CommitJournal:
    """五阶段 CommitUnit journal 与恢复器。"""

    def __init__(
        self,
        store: Any,
        journal_dir: Path,
        *,
        enabled: bool | None = None,
        fault_injector: Callable[[JournalStage], None] | None = None,
    ):
        from .records import StrmRecordAdapter, UploadRecordAdapter
        self.store = store
        self.journal_dir = Path(journal_dir)
        # 阶段 C 生产路径始终启用 journal；enabled=False 仅用于恢复和拒绝测试。
        self.enabled = True if enabled is None else bool(enabled)
        self.fault_injector = fault_injector
        self.adapters = {
            "strm": StrmRecordAdapter(store),
            "upload": UploadRecordAdapter(store),
        }
        self._lock = threading.RLock()

    def execute(self, unit: CommitUnit) -> None:
        if not unit.journal_required:
            raise RuntimeError("生产 CommitUnit 必须 journal_required=True")
        with self._lock:
            self._execute_locked(unit)

    def _execute_locked(self, unit: CommitUnit) -> None:
        if unit.journal_required and not self.enabled:
            raise RuntimeError(f"{JOURNAL_FEATURE_FLAG} 默认关闭，拒绝 journal_required CommitUnit")
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        unit = self._with_backups(unit)
        self._compare_before(unit)
        self._write(unit, "prepared")
        self._fault("prepared")
        self._apply_files(unit)
        self._write(unit, "files_applied")
        self._fault("files_applied")
        try:
            snapshots = self._apply_mutations(unit)
            if any(m.container == "strm" for m in unit.mutations):
                self._save_container("strm", snapshots["strm"])
            self._write(unit, "strm_saved")
            self._fault("strm_saved")
            if any(m.container == "upload" for m in unit.mutations):
                self._save_container("upload", snapshots["upload"])
            self._write(unit, "upload_saved")
            self._fault("upload_saved")
            self._verify_after(unit)
            self._write(unit, "committed")
            self._fault("committed")
        except Exception as save_error:
            # 故障注入模拟进程崩溃，保留 journal 给启动恢复；真实保存失败立即回滚。
            if type(save_error).__name__ == "CrashAt":
                raise
            try:
                self._restore_before_records(unit)
                self._rollback_files(unit)
                self._verify_before(unit)
            except Exception as rollback_error:
                self._write_blocked(unit, str(rollback_error))
                raise StrmRecoveryBlockedError(
                    f"CommitUnit {unit.id} 保存失败且无法可靠回滚: {rollback_error}"
                ) from save_error
            self._cleanup(unit)
            raise
        self._cleanup(unit)

    def recover_all(self) -> list[str]:
        if not self.journal_dir.exists():
            return []
        recovered = []
        for path in sorted(self.journal_dir.glob("strm-commit-*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            version = int(data.get("version") or 1)
            unit = self._decode_unit(data["unit"], version=version)
            stage = str(data["stage"])
            if stage == "blocked":
                raise StrmRecoveryBlockedError(
                    f"CommitUnit {unit.id} 已标记 blocked，需要人工处理"
                )
            states = self._container_states(unit)
            rollback = (
                stage in {"prepared", "files_applied"}
                and all(value == "before" for value in states.values())
            )
            if rollback:
                try:
                    self._rollback_files(unit)
                    self._verify_before(unit)
                except StrmRecoveryBlockedError as error:
                    self._write_blocked(unit, str(error))
                    raise
            else:
                if any(value == "conflict" for value in states.values()):
                    raise RuntimeError(f"CommitUnit {unit.id} 记录状态无法验证")
                if stage in {"prepared", "files_applied"}:
                    self._verify_files_applied(unit)
                snapshots = self._after_snapshots(unit)
                for container, state in states.items():
                    if state == "before":
                        self._save_container(container, snapshots[container])
                self._verify_after(unit)
            self._write(unit, "committed")
            self._cleanup(unit)
            recovered.append(unit.id)
        return recovered

    def _fault(self, stage: JournalStage) -> None:
        if self.fault_injector:
            self.fault_injector(stage)

    def _records(self, container: Container) -> dict[str, dict[str, Any]]:
        return self.adapters[container].snapshot()

    def _save_container(self, container: Container, records: Mapping[str, Mapping[str, Any]]) -> None:
        self.adapters[container].save(records)

    def _compare_before(self, unit: CommitUnit) -> None:
        snapshots = {container: self._records(container) for container in ("strm", "upload")}
        for mutation in unit.mutations:
            current = snapshots[mutation.container].get(mutation.key)
            expected = dict(mutation.before) if mutation.before is not None else None
            if current != expected:
                raise RuntimeError(f"CommitUnit {unit.id} compare-before-apply 失败: {mutation.container}/{mutation.key}")

    def _apply_mutations(self, unit: CommitUnit) -> dict[Container, dict[str, dict[str, Any]]]:
        snapshots = {container: self._records(container) for container in ("strm", "upload")}
        for mutation in unit.mutations:
            if mutation.after is None:
                snapshots[mutation.container].pop(mutation.key, None)
            else:
                snapshots[mutation.container][mutation.key] = dict(mutation.after)
        return snapshots

    def _restore_before_records(self, unit: CommitUnit) -> None:
        """尽力把已保存 container 恢复为本 CommitUnit 的 before 快照。"""

        snapshots = {container: self._records(container) for container in ("strm", "upload")}
        for mutation in unit.mutations:
            if mutation.before is None:
                snapshots[mutation.container].pop(mutation.key, None)
            else:
                snapshots[mutation.container][mutation.key] = dict(mutation.before)
        for container in ("strm", "upload"):
            if any(m.container == container for m in unit.mutations):
                self._save_container(container, snapshots[container])

    def _after_snapshots(self, unit: CommitUnit) -> dict[Container, dict[str, dict[str, Any]]]:
        result = {container: self._records(container) for container in ("strm", "upload")}
        for mutation in unit.mutations:
            if mutation.after is None:
                result[mutation.container].pop(mutation.key, None)
            else:
                result[mutation.container][mutation.key] = dict(mutation.after)
        return result

    def _save_changed(self, snapshots: Mapping[Container, Mapping[str, Mapping[str, Any]]], unit: CommitUnit) -> None:
        for container in ("strm", "upload"):
            if any(m.container == container for m in unit.mutations):
                self._save_container(container, snapshots[container])

    def _with_backups(self, unit: CommitUnit) -> CommitUnit:
        ops = []
        for index, operation in enumerate(unit.file_ops):
            existed = operation.target.exists() or operation.target.is_symlink()
            if (
                operation.target_existed_before is not None
                and operation.target_existed_before != existed
            ):
                raise RuntimeError("FileOperation incumbent 状态漂移")
            backup = operation.backup or operation.target.with_name(
                f".{operation.target.name}.{unit.id}.{index}.bak"
            )
            before_sha256 = operation.before_sha256
            if existed and not before_sha256 and operation.target.is_file() and not operation.target.is_symlink():
                before_sha256 = _file_sha256(operation.target)
            after_sha256 = operation.after_sha256
            if (
                operation.action == "replace"
                and not after_sha256
                and operation.temp is not None
                and operation.temp.is_file()
                and not operation.temp.is_symlink()
            ):
                after_sha256 = _file_sha256(operation.temp)
            ops.append(
                replace(
                    operation,
                    backup=backup,
                    before_sha256=before_sha256,
                    after_sha256=after_sha256,
                    target_existed_before=existed,
                )
            )
        return replace(unit, file_ops=tuple(ops))

    def _apply_files(self, unit: CommitUnit) -> None:
        applied: list[FileOperation] = []
        try:
            for operation in unit.file_ops:
                target, backup = operation.target, operation.backup
                target.parent.mkdir(parents=True, exist_ok=True)
                exists_now = target.exists() or target.is_symlink()
                if operation.target_existed_before is None:
                    raise RuntimeError("FileOperation 缺少 target_existed_before")
                if exists_now != operation.target_existed_before:
                    raise RuntimeError("FileOperation incumbent 状态漂移")
                if operation.target_existed_before:
                    if target.is_symlink() or not target.is_file():
                        raise RuntimeError("FileOperation incumbent 不是普通文件")
                    if (
                        operation.before_sha256
                        and _file_sha256(target) != operation.before_sha256
                    ):
                        raise RuntimeError(
                            f"FileOperation {operation.action} incumbent 摘要漂移"
                        )
                    assert backup is not None
                    try:
                        os.link(target, backup)
                    except OSError:
                        shutil.copy2(target, backup)
                        with backup.open("rb") as handle:
                            os.fsync(handle.fileno())
                applied.append(operation)
                if operation.action == "replace":
                    if (
                        operation.temp is None
                        or operation.temp.is_symlink()
                        or not operation.temp.is_file()
                    ):
                        raise OSError(f"替换 temp 不可用: {operation.temp}")
                    os.replace(operation.temp, target)
                elif exists_now:
                    target.unlink()
            _fsync_parent_dirs(
                path
                for operation in unit.file_ops
                for path in (operation.target, operation.backup, operation.temp)
                if path is not None
            )
        except Exception:
            applied_unit = replace(unit, file_ops=tuple(applied))
            self._rollback_files(applied_unit)
            self._cleanup_files(unit)
            raise

    def _rollback_files(self, unit: CommitUnit) -> None:
        changed: list[Path] = []
        for operation in reversed(unit.file_ops):
            backup = operation.backup
            if operation.target_existed_before is True:
                if operation.action == "replace":
                    replace_applied = bool(
                        operation.temp is not None and not operation.temp.exists()
                    )
                    if replace_applied:
                        if not operation.after_sha256:
                            raise StrmRecoveryBlockedError(
                                "已有目标回滚缺少 after_sha256，拒绝用 backup 覆盖"
                            )
                        if operation.target.is_symlink() or not operation.target.is_file():
                            raise StrmRecoveryBlockedError(
                                "已有目标回滚时输出已不是普通文件，拒绝用 backup 覆盖"
                            )
                        if _file_sha256(operation.target) != operation.after_sha256:
                            raise StrmRecoveryBlockedError(
                                "已有目标回滚时输出已被外部替换，拒绝用 backup 覆盖"
                            )
                        if not backup or not backup.exists():
                            raise RuntimeError("incumbent backup 缺失")
                        os.replace(backup, operation.target)
                        changed.extend((backup, operation.target))
                    elif operation.before_sha256:
                        if operation.target.is_symlink() or not operation.target.is_file():
                            raise StrmRecoveryBlockedError(
                                "已有目标回滚前 incumbent 已被外部替换"
                            )
                        if _file_sha256(operation.target) != operation.before_sha256:
                            raise StrmRecoveryBlockedError(
                                "已有目标回滚前 incumbent 摘要已漂移"
                            )
                elif operation.action == "unlink":
                    if operation.target.exists() or operation.target.is_symlink():
                        if (
                            operation.target.is_symlink()
                            or not operation.target.is_file()
                            or (
                                operation.before_sha256
                                and _file_sha256(operation.target)
                                != operation.before_sha256
                            )
                        ):
                            raise StrmRecoveryBlockedError(
                                "已有目标删除回滚时出现外部文件，拒绝用 backup 覆盖"
                            )
                    else:
                        if not backup or not backup.exists():
                            raise RuntimeError("incumbent backup 缺失")
                        os.replace(backup, operation.target)
                        changed.extend((backup, operation.target))
                else:
                    raise RuntimeError("未知 FileOperation action")
            elif operation.target_existed_before is False:
                # temp 消失只证明 replace 曾发生；删除前还必须证明目标仍是本事务 after。
                if (
                    operation.action == "replace"
                    and operation.temp is not None
                    and not operation.temp.exists()
                ):
                    if not operation.after_sha256:
                        raise StrmRecoveryBlockedError(
                            "新目标回滚缺少 after_sha256，拒绝删除"
                        )
                    if operation.target.is_symlink() or not operation.target.is_file():
                        raise StrmRecoveryBlockedError(
                            "新目标回滚时输出已不是普通文件，拒绝删除"
                        )
                    if _file_sha256(operation.target) != operation.after_sha256:
                        raise StrmRecoveryBlockedError(
                            "新目标回滚时输出已被外部替换，拒绝删除"
                        )
                    operation.target.unlink()
                    changed.append(operation.target)
            else:
                raise RuntimeError("FileOperation 缺少 target_existed_before")
        _fsync_parent_dirs(changed)

    def _verify_before(self, unit: CommitUnit) -> None:
        states = self._container_states(unit)
        if any(value != "before" for value in states.values()):
            raise RuntimeError(f"CommitUnit {unit.id} before 记录校验失败: {states}")
        for operation in unit.file_ops:
            exists = operation.target.exists() or operation.target.is_symlink()
            if operation.target_existed_before is True:
                if not operation.target.is_file() or operation.target.is_symlink():
                    raise RuntimeError(f"CommitUnit {unit.id} 回滚文件不存在")
                if (
                    operation.before_sha256
                    and _file_sha256(operation.target) != operation.before_sha256
                ):
                    raise RuntimeError(f"CommitUnit {unit.id} 回滚文件摘要不匹配")
            elif operation.target_existed_before is False:
                if exists:
                    raise RuntimeError(f"CommitUnit {unit.id} 回滚目标本应不存在")
            else:
                raise RuntimeError("FileOperation 缺少 target_existed_before")

    def _verify_files_applied(self, unit: CommitUnit) -> None:
        """在补写记录前证明文件阶段已经落盘，避免恢复时误认外来 incumbent。"""

        for operation in unit.file_ops:
            if operation.action == "unlink":
                if operation.target.exists() or operation.target.is_symlink():
                    raise RuntimeError(
                        f"CommitUnit {unit.id} 文件阶段无法验证：删除目标仍存在"
                    )
                continue
            if operation.temp is None or operation.temp.exists():
                raise RuntimeError(
                    f"CommitUnit {unit.id} 文件阶段无法验证：replace 尚未完成"
                )
            if operation.target.is_symlink() or not operation.target.is_file():
                raise RuntimeError(
                    f"CommitUnit {unit.id} 文件阶段无法验证：输出不存在"
                )
            if (
                operation.after_sha256
                and _file_sha256(operation.target) != operation.after_sha256
            ):
                raise RuntimeError(
                    f"CommitUnit {unit.id} 文件阶段无法验证：输出摘要不匹配"
                )

    def _verify_after(self, unit: CommitUnit) -> None:
        states = self._container_states(unit)
        if any(value != "after" for value in states.values()):
            raise RuntimeError(f"CommitUnit {unit.id} after 记录校验失败: {states}")
        for operation in unit.file_ops:
            if operation.action == "unlink":
                if operation.target.exists() or operation.target.is_symlink():
                    raise RuntimeError(f"CommitUnit {unit.id} 删除目标仍存在")
            else:
                if operation.target.is_symlink() or not operation.target.is_file():
                    raise RuntimeError(
                        f"CommitUnit {unit.id} 输出不存在或是符号链接"
                    )
                if operation.after_sha256 and _file_sha256(operation.target) != operation.after_sha256:
                    raise RuntimeError(f"CommitUnit {unit.id} 输出摘要不匹配")

    def _container_states(self, unit: CommitUnit) -> dict[Container, str]:
        result: dict[Container, str] = {}
        for container in {mutation.container for mutation in unit.mutations}:
            records = self._records(container)
            states = set()
            for mutation in (item for item in unit.mutations if item.container == container):
                current = records.get(mutation.key)
                before = dict(mutation.before) if mutation.before is not None else None
                after = dict(mutation.after) if mutation.after is not None else None
                states.add(
                    "after" if current == after
                    else "before" if current == before
                    else "conflict"
                )
            result[container] = states.pop() if len(states) == 1 else "conflict"
        return result

    def _journal_path(self, unit_id: str) -> Path:
        return self.journal_dir / f"strm-commit-{unit_id}.json"

    def _write(self, unit: CommitUnit, stage: JournalStage) -> None:
        path = self._journal_path(unit.id)
        temp = path.with_suffix(".json.tmp")
        payload = {"version": 2, "stage": stage, "unit": self._encode_unit(unit)}
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        _fsync_dir(self.journal_dir)

    def _write_blocked(self, unit: CommitUnit, reason: str) -> None:
        """尽最大努力留下可诊断的阻断 journal；reason 不参与恢复解码。"""

        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self._write(unit, "blocked")
        path = self._journal_path(unit.id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["blocked_reason"] = str(reason)
            temp = path.with_suffix(".json.tmp")
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
            _fsync_dir(self.journal_dir)
        except (OSError, ValueError, TypeError):
            pass

    @staticmethod
    def _cleanup_files(unit: CommitUnit) -> None:
        changed: list[Path] = []
        for operation in unit.file_ops:
            if operation.backup:
                existed = operation.backup.exists() or operation.backup.is_symlink()
                operation.backup.unlink(missing_ok=True)
                if existed:
                    changed.append(operation.backup)
            if operation.temp:
                existed = operation.temp.exists() or operation.temp.is_symlink()
                operation.temp.unlink(missing_ok=True)
                if existed:
                    changed.append(operation.temp)
        _fsync_parent_dirs(changed)

    def _cleanup(self, unit: CommitUnit) -> None:
        self._cleanup_files(unit)
        journal_path = self._journal_path(unit.id)
        journal_path.unlink(missing_ok=True)
        _fsync_dir(self.journal_dir)

    @staticmethod
    def _encode_unit(unit: CommitUnit) -> dict[str, Any]:
        return {
            "id": unit.id,
            "journal_required": unit.journal_required,
            "mutations": [asdict(item) for item in unit.mutations],
            "file_ops": [
                {
                    **asdict(item),
                    "target": str(item.target),
                    "temp": str(item.temp) if item.temp else None,
                    "backup": str(item.backup) if item.backup else None,
                }
                for item in unit.file_ops
            ],
        }

    @staticmethod
    def _decode_unit(
        data: Mapping[str, Any],
        *,
        version: int = 2,
    ) -> CommitUnit:
        file_ops = []
        for item in data.get("file_ops", ()):
            before_sha256 = str(item.get("before_sha256") or "")
            if version == 1:
                if not before_sha256:
                    raise RuntimeError(
                        "version 1 journal 缺少 before_sha256，无法安全恢复"
                    )
                target_existed_before: bool | None = True
            elif version == 2:
                raw_existed = item.get("target_existed_before")
                if raw_existed is None:
                    raise RuntimeError(
                        "version 2 journal 缺少 target_existed_before"
                    )
                target_existed_before = bool(raw_existed)
            else:
                raise RuntimeError(f"不支持的 STRM journal version: {version}")
            file_ops.append(
                FileOperation(
                    action=item["action"],
                    target=Path(item["target"]),
                    temp=Path(item["temp"]) if item.get("temp") else None,
                    backup=Path(item["backup"]) if item.get("backup") else None,
                    before_sha256=before_sha256,
                    after_sha256=str(item.get("after_sha256") or ""),
                    target_existed_before=target_existed_before,
                )
            )
        return CommitUnit(
            id=str(data["id"]),
            mutations=tuple(
                RecordMutation(**item) for item in data.get("mutations", ())
            ),
            file_ops=tuple(file_ops),
            journal_required=bool(data.get("journal_required")),
        )
