"""仅测试使用的严格事务 helper；生产模块不暴露直接落盘 facade。"""
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from app.plugins.p115liteassistant.strm_core import (
    CommitJournal,
    RecordClaims,
    SessionClaim,
    SessionReservations,
    StrmMaterializer,
)


def make_test_journal(store: Any, root: Path | None = None) -> CommitJournal:
    """为调用方构造真实、彼此隔离的 CommitJournal。"""
    configured = getattr(store, "_test_journal_dir", None)
    if not isinstance(configured, (str, Path)):
        configured = None
    if root is not None:
        base = Path(root)
    elif configured:
        base = Path(configured)
    else:
        holder = getattr(store, "_test_journal_holder", None)
        if not isinstance(holder, TemporaryDirectory):
            holder = TemporaryDirectory(prefix="p115-test-journal-")
            store._test_journal_holder = holder
        base = Path(holder.name)
    return CommitJournal(store, base / "journal", enabled=True)


def write_uploaded_strm_for_test(
    local_path: Path,
    source_root: Path,
    target_root: Path,
    pickcode: str,
    moviepilot_url: str,
    redirect_secret: str,
    *,
    store: Any | None = None,
) -> Path:
    """仅供测试准备上传侧 STRM；走严格 prepare/commit，不提供生产 facade。"""
    from hashlib import sha256

    from app.plugins.p115liteassistant.strm import (
        build_strm_content,
        uploaded_strm_path,
    )
    from app.plugins.p115liteassistant.strm_core import (
        CloudIdentity,
        MaterializeRequest,
    )

    class Store:
        def __init__(self):
            self.strm = {}
            self.upload = {}

        def get_strm_records(self):
            return dict(self.strm)

        def save_strm_records(self, records):
            self.strm = dict(records)

        def get_upload_records(self):
            return dict(self.upload)

        def save_upload_records(self, records):
            self.upload = dict(records)

    backing = store or Store()
    local_path = Path(local_path).resolve()
    source_root = Path(source_root).resolve()
    target_root = Path(target_root).resolve()
    output = uploaded_strm_path(local_path, source_root, target_root)
    content = build_strm_content(
        moviepilot_url, pickcode, redirect_secret, local_path.name
    )
    request = MaterializeRequest(
        source_id="test-upload",
        container="upload",
        key=str(local_path),
        kind="strm",
        target_root=target_root,
        owner_id=str(source_root),
        relative_path=local_path.relative_to(source_root).as_posix(),
        output=output,
        cloud_identity=CloudIdentity(pickcode=pickcode),
        fingerprint=sha256(content.encode("utf-8")).hexdigest(),
        content=content,
        producer="test",
    )
    materializer = StrmMaterializer(backing)
    result = materialize_for_test(
        materializer, request, RecordClaims(), store=backing
    )
    return result.output


def materialize_for_test(
    materializer: StrmMaterializer,
    request,
    claims: RecordClaims,
    *,
    journal: CommitJournal | None = None,
    store: Any | None = None,
    **kwargs,
):
    """为旧内核单测补齐 reserve/confirm/prepare/execute/commit。"""
    kwargs.pop("require_reservation", None)
    reservations = kwargs.pop("session_reservations", None) or SessionReservations()
    decision = kwargs.get("decision") or materializer.validate_collision(
        request, claims, previous=kwargs.get("previous")
    )
    token = kwargs.pop("reservation", None)
    if token is None:
        reservation = materializer.reserve(request, decision, reservations)
        token = materializer.confirm(reservations, reservation)
    prepared = materializer.prepare(
        request,
        claims,
        decision=decision,
        previous=kwargs.get("previous"),
        incremental=kwargs.get("incremental", True),
        reservation=token,
        session_reservations=reservations,
    )
    if journal is None:
        backing = store or materializer._store
        if backing is None:
            class Store:
                strm = {}
                upload = {}
                def get_strm_records(self): return dict(self.strm)
                def save_strm_records(self, records): self.strm = dict(records)
                def get_upload_records(self): return dict(self.upload)
                def save_upload_records(self, records): self.upload = dict(records)
            backing = Store()
        previous = kwargs.get("previous")
        if previous is not None:
            if request.container == "strm":
                backing.strm = {request.key: dict(previous)}
            else:
                backing.upload = {request.key: dict(previous)}
        journal = make_test_journal(backing, request.target_root)
    try:
        return materializer.commit(prepared, journal)
    except Exception:
        prepared.discard()
        raise
