from __future__ import annotations

import json
import os
import sys
import threading
import time
import types
import unittest
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

# 该内核本身不依赖 MoviePilot；后端缺失时仍以生产包名装载独立模块。
try:
    import app.plugins.p115liteassistant.strm_core as strm_core_module
    from app.plugins.p115liteassistant.strm_core import (
        CloudIdentity, CollisionDecision, CommitJournal, CommitUnit, FileOperation,
        MaterializeRequest, RecordClaim, RecordClaims, RecordMutation,
        ReservationToken, SessionClaim, SessionReservations, SiblingCandidate,
        StrmMaterializer, StrmOwnershipConflict, StrmRecoveryBlockedError,
        build_record_mutation as module_build_record_mutation,
        resolve_legacy_strm_owner, resolve_legacy_upload_owner,
        stable_materialization_order, strm_journal_enabled,
    )
except ModuleNotFoundError:
    import importlib.util
    repository = Path(__file__).resolve().parents[2]
    package = types.ModuleType("app.plugins.p115liteassistant")
    package.__path__ = [str(repository / "plugins" / "p115liteassistant")]
    sys.modules["app.plugins.p115liteassistant"] = package
    spec = importlib.util.spec_from_file_location(
        "app.plugins.p115liteassistant.strm_core",
        repository / "plugins" / "p115liteassistant" / "strm_core.py",
    )
    module = importlib.util.module_from_spec(spec)
    strm_core_module = module
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    CloudIdentity = module.CloudIdentity
    CollisionDecision = module.CollisionDecision
    CommitJournal = module.CommitJournal
    CommitUnit = module.CommitUnit
    FileOperation = module.FileOperation
    MaterializeRequest = module.MaterializeRequest
    RecordClaim = module.RecordClaim
    RecordClaims = module.RecordClaims
    RecordMutation = module.RecordMutation
    ReservationToken = module.ReservationToken
    SessionClaim = module.SessionClaim
    SessionReservations = module.SessionReservations
    SiblingCandidate = module.SiblingCandidate
    StrmMaterializer = module.StrmMaterializer
    StrmOwnershipConflict = module.StrmOwnershipConflict
    StrmRecoveryBlockedError = module.StrmRecoveryBlockedError
    module_build_record_mutation = module.build_record_mutation
    resolve_legacy_strm_owner = module.resolve_legacy_strm_owner
    resolve_legacy_upload_owner = module.resolve_legacy_upload_owner
    stable_materialization_order = module.stable_materialization_order
    strm_journal_enabled = module.strm_journal_enabled



from tests.p115liteassistant.helpers import materialize_for_test


class DictStore:
    def __init__(self, strm=None, upload=None):
        self.strm = dict(strm or {})
        self.upload = dict(upload or {})

    def get_strm_records(self):
        return {key: dict(value) for key, value in self.strm.items()}

    def save_strm_records(self, records):
        self.strm = {key: dict(value) for key, value in records.items()}

    def get_upload_records(self):
        return {key: dict(value) for key, value in self.upload.items()}

    def save_upload_records(self, records):
        self.upload = {key: dict(value) for key, value in records.items()}


class CrashAt(RuntimeError):
    pass


class StrmCoreTest(unittest.TestCase):
    def request(self, root: Path, **overrides):
        values = {
            "source_id": "scan",
            "container": "strm",
            "key": "map:movie.mkv",
            "kind": "strm",
            "target_root": root,
            "owner_id": "map",
            "relative_path": "movie.mkv",
            "cloud_identity": CloudIdentity(pickcode="abc"),
            "fingerprint": "fp",
            "content": b"https://example/abc\n",
            "producer": "strm_sync",
        }
        values.update(overrides)
        return MaterializeRequest(**values)

    def test_naming_regular_iso_and_same_stem(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            materializer = StrmMaterializer()
            regular = self.request(root)
            iso = self.request(root, key="map:disc.iso", relative_path="disc.iso")
            self.assertEqual(materializer.validate_collision(regular, RecordClaims()).output, root / "movie.strm")
            self.assertEqual(materializer.validate_collision(iso, RecordClaims()).output, root / "disc.iso.strm")
            decision = materializer.validate_collision(
                regular,
                RecordClaims(),
                sibling_candidates=(SiblingCandidate("movie.mp4", "map:movie.mp4"),),
            )
            self.assertEqual(decision.status, "same_stem")
            self.assertEqual(decision.output, root / "movie.mkv.strm")

    def test_materialize_exact_bytes_incremental_and_atomic_temp_cleanup(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            request = self.request(root)
            materializer = StrmMaterializer()
            decision = materializer.validate_collision(request, RecordClaims())
            first = materialize_for_test(materializer, request, RecordClaims(), decision=decision)
            self.assertEqual(first.action, "created")
            self.assertEqual(first.output.read_bytes(), request.content)
            previous = first.mutations[0].after
            second = materialize_for_test(materializer, request, RecordClaims(), decision=decision, previous=previous)
            self.assertEqual(second.action, "skipped")
            first.output.write_bytes(b"wrong")
            third = materialize_for_test(materializer, request, RecordClaims(), decision=decision, previous=previous)
            self.assertEqual(third.action, "updated")
            self.assertEqual(first.output.read_bytes(), request.content)
            self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_output_boundary_and_symlink_refused(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            root, outside = base / "root", base / "outside"
            root.mkdir(); outside.mkdir()
            request = self.request(root, output=outside / "bad.strm")
            decision = StrmMaterializer().validate_collision(request, RecordClaims())
            self.assertEqual(decision.status, "occupied")
            link = root / "linked"
            link.symlink_to(outside, target_is_directory=True)
            request = self.request(root, output=link / "bad.strm")
            self.assertEqual(StrmMaterializer().validate_collision(request, RecordClaims()).status, "occupied")

    def test_unclaimed_existing_regular_file_is_occupied(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); output = root / "movie.strm"
            output.write_bytes(b"incumbent")
            request = self.request(root)
            decision = StrmMaterializer().validate_collision(request, RecordClaims())
            self.assertEqual(decision.status, "occupied")
            self.assertEqual(output.read_bytes(), b"incumbent")

            previous = {
                "path": str(output), "fingerprint": "old",
                "cloud_identity": {"pickcode": "abc"},
            }
            owned = StrmMaterializer().validate_collision(
                request, RecordClaims(), previous=previous
            )
            self.assertTrue(owned.writable)

    def test_unclaimed_exact_strm_is_same_content_and_claimed_by_replace(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "movie.strm"
            request = self.request(root)
            output.write_bytes(request.content)
            before_inode = output.stat().st_ino
            store = DictStore()
            materializer = StrmMaterializer(store)

            decision = materializer.validate_collision(request, RecordClaims())
            self.assertEqual(decision.status, "same_content")
            self.assertTrue(decision.writable)
            reservations = SessionReservations()
            token = materializer.confirm(
                reservations, materializer.reserve(request, decision, reservations)
            )
            prepared = materializer.prepare(
                request, RecordClaims(), decision=decision, previous=None,
                reservation=token, session_reservations=reservations,
            )
            self.assertEqual(prepared.result.action, "updated")
            self.assertTrue(prepared.result.content_matched)
            self.assertEqual(prepared.result.mutations[0].before, None)
            self.assertEqual(len(prepared.unit.file_ops), 1)
            operation = prepared.unit.file_ops[0]
            self.assertEqual(operation.action, "replace")
            self.assertEqual(operation.before_sha256, sha256(request.content).hexdigest())

            result = materializer.commit(
                prepared, CommitJournal(store, root / "journal", enabled=True)
            )
            self.assertEqual(output.read_bytes(), request.content)
            self.assertNotEqual(output.stat().st_ino, before_inode)
            self.assertEqual(store.strm[request.key], result.mutations[0].after)

    def test_exact_content_path_types_and_other_claims_still_refuse(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            root, outside = base / "root", base / "outside"
            root.mkdir(); outside.mkdir()
            request = self.request(root)
            exact = root / "exact.strm"
            exact.write_bytes(request.content)

            link = root / "movie.strm"
            link.symlink_to(exact)
            self.assertEqual(
                StrmMaterializer().validate_collision(request, RecordClaims()).status,
                "occupied",
            )
            link.unlink(); link.mkdir()
            self.assertEqual(
                StrmMaterializer().validate_collision(request, RecordClaims()).status,
                "occupied",
            )
            outside_exact = outside / "exact.strm"
            outside_exact.write_bytes(request.content)
            outside_request = self.request(root, output=outside_exact)
            self.assertEqual(
                StrmMaterializer().validate_collision(outside_request, RecordClaims()).status,
                "occupied",
            )

            link.rmdir(); link.write_bytes(request.content)
            conflict = RecordClaim(
                "upload", "other", link, "strm", "upload:other",
                CloudIdentity(pickcode="different"), "explicit",
            )
            ambiguous = replace(conflict, key="ambiguous", owner="", owner_confidence="ambiguous")
            for incumbent in (conflict, ambiguous):
                self.assertEqual(
                    StrmMaterializer().validate_collision(
                        request, RecordClaims((incumbent,))
                    ).status,
                    "occupied",
                )

    def test_previous_identity_mismatch_can_claim_only_exact_content(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "movie.strm"
            request = self.request(root)
            previous = {
                "path": str(output), "fingerprint": "old", "owner_id": "other",
                "cloud_identity": {"pickcode": "different"},
            }
            output.write_bytes(request.content)
            decision = StrmMaterializer().validate_collision(
                request, RecordClaims(), previous=previous
            )
            self.assertEqual(decision.status, "same_content")
            result = materialize_for_test(
                StrmMaterializer(), request, RecordClaims(), decision=decision,
                previous=previous,
            )
            self.assertEqual(result.action, "updated")
            self.assertTrue(result.content_matched)
            self.assertEqual(result.mutations[0].before, previous)

            output.write_bytes(b"different")
            self.assertEqual(
                StrmMaterializer().validate_collision(
                    request, RecordClaims(), previous=previous
                ).status,
                "occupied",
            )

    def test_same_content_drift_between_validate_and_prepare_is_refused(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "movie.strm"
            request = self.request(root)
            output.write_bytes(request.content)
            materializer = StrmMaterializer()
            decision = materializer.validate_collision(request, RecordClaims())
            reservations = SessionReservations()
            token = materializer.confirm(
                reservations, materializer.reserve(request, decision, reservations)
            )
            output.write_bytes(b"external")

            with self.assertRaisesRegex(StrmOwnershipConflict, "same_content"):
                materializer.prepare(
                    request, RecordClaims(), decision=decision, previous=None,
                    reservation=token, session_reservations=reservations,
                )
            self.assertEqual(output.read_bytes(), b"external")
            self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_content_none_uses_same_payload_for_collision_and_prepare(self):
        from app.plugins.p115liteassistant.strm import build_strm_content
        from p115pickcode import id_to_pickcode

        with TemporaryDirectory() as directory:
            root = Path(directory)
            pickcode = id_to_pickcode(101)
            request = self.request(
                root, content=None, pickcode=pickcode, file_name="movie.mkv"
            )
            materializer = StrmMaterializer(
                moviepilot_url="https://moviepilot.example/",
                redirect_secret="payload-secret-0123456789",
            )
            expected = build_strm_content(
                "https://moviepilot.example", pickcode,
                "payload-secret-0123456789", "movie.mkv",
            ).encode("utf-8")
            output = root / "movie.strm"
            output.write_bytes(expected)
            decision = materializer.validate_collision(request, RecordClaims())
            self.assertEqual(decision.status, "same_content")
            result = materialize_for_test(
                materializer, request, RecordClaims(), decision=decision
            )
            self.assertTrue(result.content_matched)
            self.assertEqual(output.read_bytes(), expected)

    def test_claim_same_owner_shared_and_cross_container_occupied(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            request = self.request(root)
            output = root / "movie.strm"
            same = RecordClaim("strm", "old", output, "strm", "strm:map", CloudIdentity(pickcode="old"), "explicit")
            self.assertEqual(StrmMaterializer().validate_collision(request, RecordClaims((same,))).status, "same_owner")
            shared = replace(same, owner="strm:other", cloud_identity=CloudIdentity(pickcode="abc"))
            self.assertEqual(StrmMaterializer().validate_collision(request, RecordClaims((shared,))).status, "same_identity_shared")
            cross = replace(same, container="upload", owner="upload:source", cloud_identity=CloudIdentity(pickcode="different"))
            self.assertEqual(StrmMaterializer().validate_collision(request, RecordClaims((cross,))).status, "occupied")

    def test_collision_checks_all_claims_independent_of_order(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            request = self.request(root)
            output = root / "movie.strm"
            same = RecordClaim("strm", "same", output, "strm", "strm:map", CloudIdentity(pickcode="abc"), "explicit")
            conflict = replace(same, key="conflict", owner="strm:other", cloud_identity=CloudIdentity(pickcode="different"))
            ambiguous = replace(same, key="ambiguous", owner="", owner_confidence="ambiguous")
            for claims in ((same, conflict), (conflict, same), (same, ambiguous), (ambiguous, same)):
                self.assertEqual(
                    StrmMaterializer().validate_collision(request, RecordClaims(claims)).status,
                    "occupied",
                )
            all_same = (same, replace(same, key="same-2"))
            self.assertEqual(
                StrmMaterializer().validate_collision(request, RecordClaims(all_same)).status,
                "same_owner",
            )
            shared = replace(same, owner="strm:other")
            all_identity = (shared, replace(shared, key="shared-2", owner="upload:source"))
            self.assertEqual(
                StrmMaterializer().validate_collision(request, RecordClaims(all_identity)).status,
                "same_identity_shared",
            )

    def test_stable_order_and_session_winner_is_input_order_independent(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            one = self.request(root, key="z", relative_path="same.mkv")
            two = self.request(root, key="a", relative_path="same.mp4")
            decision = CollisionDecision("free", root / "same.strm")
            for items in (((one, decision), (two, decision)), ((two, decision), (one, decision))):
                ordered = stable_materialization_order(items)
                self.assertEqual([item[0].key for item in ordered], ["a", "z"])
                reservations = SessionReservations()
                for request, item_decision in items:  # 刻意不依赖预排序。
                    reservations.reserve(
                        item_decision.output,
                        SessionClaim(
                            request.container, request.key, f"strm:{request.owner_id}",
                            request.cloud_identity, request.kind,
                        ),
                    )
                self.assertEqual(reservations.get(decision.output).winner.key, "a")

    def test_session_preemption_rejects_loser_materialization(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "same.strm"
            loser_request = self.request(root, key="z", relative_path="same.mkv")
            winner_request = self.request(root, key="a", relative_path="same.mp4")
            loser = SessionClaim("strm", "z", "strm:map", loser_request.cloud_identity)
            winner = SessionClaim("strm", "a", "strm:map", winner_request.cloud_identity)
            reservations = SessionReservations()
            stale = reservations.reserve(output, loser)
            current = reservations.reserve(output, winner)

            self.assertEqual(current.status, "preempted")
            self.assertEqual(current.preempted, loser)
            self.assertFalse(reservations.confirm(stale.token))
            self.assertTrue(reservations.confirm(current.token))
            with self.assertRaisesRegex(StrmOwnershipConflict, "generation"):
                materialize_for_test(StrmMaterializer(), 
                    loser_request,
                    RecordClaims(),
                    decision=CollisionDecision("free", output),
                    reservation=stale.token,
                    session_reservations=reservations,
                )
            self.assertFalse(output.exists())

    def test_finalize_rechecks_after_blocked_download_and_preemption(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "movie.nfo"
            started = threading.Event()
            resume = threading.Event()
            reservations = SessionReservations()
            request_a = self.request(
                root, key="z", kind="sidecar", output=output,
                relative_path="movie.nfo", content=None, size=1,
                downloader=lambda _pickcode, temp: (
                    temp.write_bytes(b"A"), started.set(), resume.wait(2)
                ),
            )
            request_b = replace(request_a, key="a", downloader=None)
            token_a = reservations.reserve(
                output, SessionClaim("strm", "z", "strm:map", request_a.cloud_identity, "sidecar")
            ).token
            self.assertTrue(reservations.confirm(token_a))
            errors = []

            def materialize_a():
                try:
                    materialize_for_test(StrmMaterializer(), 
                        request_a, RecordClaims(), decision=CollisionDecision("free", output),
                        reservation=token_a, session_reservations=reservations,
                        require_reservation=True, incremental=False,
                    )
                except Exception as error:
                    errors.append(error)

            worker = threading.Thread(target=materialize_a)
            worker.start()
            self.assertTrue(started.wait(1))
            winner_b = reservations.reserve(
                output, SessionClaim("strm", "a", "strm:map", request_b.cloud_identity, "sidecar")
            )
            self.assertEqual(winner_b.status, "preempted")
            resume.set(); worker.join(2)
            self.assertFalse(worker.is_alive())
            self.assertFalse(output.exists())
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], StrmOwnershipConflict)
            self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_new_target_created_during_download_is_not_overwritten(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "movie.nfo"
            started = threading.Event()
            resume = threading.Event()
            errors = []

            def download(_pickcode, temp):
                temp.write_bytes(b"transaction")
                started.set()
                self.assertTrue(resume.wait(2))

            request = self.request(
                root, key="map:sidecar:movie.nfo", kind="sidecar",
                output=output, relative_path="movie.nfo", content=None,
                size=len(b"transaction"), downloader=download,
            )
            reservations = SessionReservations()
            token = reservations.reserve(
                output,
                SessionClaim(
                    "strm", request.key, "strm:map",
                    request.cloud_identity, "sidecar",
                ),
            ).token
            self.assertTrue(reservations.confirm(token))

            def run():
                try:
                    materialize_for_test(StrmMaterializer(), 
                        request, RecordClaims(),
                        decision=CollisionDecision("free", output),
                        reservation=token,
                        session_reservations=reservations,
                        require_reservation=True,
                        incremental=False,
                    )
                except Exception as error:
                    errors.append(error)

            worker = threading.Thread(target=run)
            worker.start()
            self.assertTrue(started.wait(1))
            output.write_bytes(b"external")
            resume.set()
            worker.join(2)
            self.assertFalse(worker.is_alive())
            self.assertEqual(output.read_bytes(), b"external")
            self.assertEqual(len(errors), 1)
            self.assertRegex(str(errors[0]), "occupied/refused|漂移")
            self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_existing_incumbent_drift_after_collision_before_replace_is_refused(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "movie.nfo"
            output.write_bytes(b"owned-before")
            downloaded = threading.Event()
            resume = threading.Event()
            errors = []

            def download(_pickcode, temp):
                temp.write_bytes(b"transaction")
                downloaded.set()
                self.assertTrue(resume.wait(2))

            request = self.request(
                root, key="map:sidecar:movie.nfo", kind="sidecar", output=output,
                relative_path="movie.nfo", content=None, size=len(b"transaction"),
                downloader=download,
            )
            previous = {
                "path": str(output), "owner_id": "map",
                "cloud_identity": {"pickcode": "abc"}, "fingerprint": "old",
            }
            claims = RecordClaims.from_records({request.key: previous}, mapping_ids={"map"})
            materializer = StrmMaterializer()
            decision = materializer.validate_collision(request, claims, previous=previous)
            reservations = SessionReservations()
            reservation = materializer.reserve(request, decision, reservations)
            token = materializer.confirm(reservations, reservation)

            def run():
                try:
                    materialize_for_test(materializer, 
                        request, claims, decision=decision, previous=previous,
                        incremental=False, reservation=token,
                        session_reservations=reservations, require_reservation=True,
                    )
                except Exception as error:
                    errors.append(error)

            worker = threading.Thread(target=run)
            worker.start()
            self.assertTrue(downloaded.wait(1))
            output.write_bytes(b"external-drift")
            resume.set()
            worker.join(2)

            self.assertEqual(output.read_bytes(), b"external-drift")
            self.assertEqual(len(errors), 1)
            self.assertRegex(str(errors[0]), "incumbent|漂移")
            self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_parent_replaced_with_symlink_after_temp_creation_is_refused(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "root"
            parent = root / "media"
            outside = base / "outside"
            parent.mkdir(parents=True)
            outside.mkdir()
            output = parent / "movie.nfo"
            downloaded = threading.Event()
            resume = threading.Event()
            errors = []

            def download(_pickcode, temp):
                temp.write_bytes(b"transaction")
                downloaded.set()
                self.assertTrue(resume.wait(2))

            request = self.request(
                root,
                key="map:sidecar:movie.nfo",
                kind="sidecar",
                output=output,
                relative_path="media/movie.nfo",
                content=None,
                size=len(b"transaction"),
                downloader=download,
            )
            materializer = StrmMaterializer()
            decision = materializer.validate_collision(request, RecordClaims())
            reservations = SessionReservations()
            reservation = materializer.reserve(request, decision, reservations)
            token = materializer.confirm(reservations, reservation)

            def run():
                try:
                    materialize_for_test(materializer, 
                        request, RecordClaims(), decision=decision,
                        incremental=False, reservation=token,
                        session_reservations=reservations,
                        require_reservation=True,
                    )
                except Exception as error:
                    errors.append(error)

            worker = threading.Thread(target=run)
            worker.start()
            self.assertTrue(downloaded.wait(1))
            temp = next(parent.glob(".*.tmp"))
            parked = root / "parked"
            parent.rename(parked)
            parent.symlink_to(outside, target_is_directory=True)
            resume.set()
            worker.join(2)

            self.assertFalse(worker.is_alive())
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], StrmOwnershipConflict)
            self.assertIn("父目录", str(errors[0]))
            self.assertFalse((outside / "movie.nfo").exists())
            self.assertTrue((parked / temp.name).exists())

    def test_parent_replaced_with_symlink_before_temp_creation_is_refused(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "root"
            outside = base / "outside"
            parent = root / "media"
            parent.mkdir(parents=True)
            outside.mkdir()
            output = parent / "movie.strm"
            request = self.request(root, output=output, content=b"new")
            materializer = StrmMaterializer()
            decision = materializer.validate_collision(request, RecordClaims())
            reservations = SessionReservations()
            token = reservations.reserve(
                output,
                SessionClaim("strm", request.key, "strm:map", request.cloud_identity),
            ).token
            self.assertTrue(reservations.confirm(token))

            parent.rmdir()
            parent.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(StrmOwnershipConflict, "父目录"):
                materialize_for_test(materializer, 
                    request, RecordClaims(), decision=decision,
                    reservation=token, session_reservations=reservations,
                    require_reservation=True, incremental=False,
                )
            self.assertFalse((outside / "movie.strm").exists())
            self.assertEqual(list(outside.glob(".*.tmp")), [])

    def test_preempt_waits_while_finalize_lock_contains_replace(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "same.strm"
            reservations = SessionReservations()
            request_a = self.request(root, key="z", output=output, content=b"A")
            request_b = self.request(root, key="a", output=output, content=b"B")
            token_a = reservations.reserve(
                output, SessionClaim("strm", "z", "strm:map", request_a.cloud_identity)
            ).token
            self.assertTrue(reservations.confirm(token_a))
            entered_replace = threading.Event()
            release_replace = threading.Event()
            preempt_done = threading.Event()
            real_replace = os.replace

            def blocking_replace(source, target):
                if Path(target) == output:
                    entered_replace.set()
                    self.assertTrue(release_replace.wait(2))
                return real_replace(source, target)

            def run_a():
                materialize_for_test(StrmMaterializer(), 
                    request_a, RecordClaims(), decision=CollisionDecision("free", output),
                    reservation=token_a, session_reservations=reservations,
                    require_reservation=True, incremental=False,
                )

            def preempt_b():
                reservations.reserve(
                    output, SessionClaim("strm", "a", "strm:map", request_b.cloud_identity)
                )
                preempt_done.set()

            with patch.object(strm_core_module.os, "replace", side_effect=blocking_replace):
                writer = threading.Thread(target=run_a)
                writer.start(); self.assertTrue(entered_replace.wait(1))
                preemptor = threading.Thread(target=preempt_b)
                preemptor.start(); time.sleep(0.05)
                self.assertFalse(preempt_done.is_set())
                release_replace.set(); writer.join(2); preemptor.join(2)
            self.assertTrue(preempt_done.is_set())
            self.assertEqual(output.read_bytes(), b"A")
            self.assertEqual(reservations.get(output).winner.key, "a")

    def test_strict_prepare_requires_reservation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            request = self.request(root)
            with self.assertRaisesRegex(TypeError, "reservation"):
                StrmMaterializer().prepare(
                    request, RecordClaims(),
                    decision=CollisionDecision("free", root / "movie.strm"),
                )

    def test_session_reservations_multithread_stress(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            reservations = SessionReservations()
            barrier = threading.Barrier(8)
            errors = []

            def churn(index):
                try:
                    barrier.wait()
                    claim = SessionClaim(
                        "strm", f"{index:02d}", "strm:map",
                        CloudIdentity(pickcode=f"pc{index}"),
                    )
                    for round_no in range(100):
                        output = root / f"{round_no % 4}.strm"
                        moved = root / f"moved-{index}-{round_no}.strm"
                        decision = reservations.reserve(output, claim)
                        if decision.token:
                            reservations.confirm(decision.token)
                        relocated = reservations.relocate(claim, output, moved)
                        if relocated.token:
                            reservations.confirm(relocated.token)
                            reservations.release(relocated.token)
                        reservations.release(claim, output)
                except Exception as error:
                    errors.append(error)

            workers = [threading.Thread(target=churn, args=(index,)) for index in range(8)]
            for worker in workers: worker.start()
            for worker in workers: worker.join(5)
            self.assertFalse(any(worker.is_alive() for worker in workers))
            self.assertEqual(errors, [])
            for output, reservation in reservations.snapshot().items():
                self.assertEqual(output, reservation.output)
                self.assertNotIn(reservation.winner.ref, {item.ref for item in reservation.losers})

    def test_session_confirm_release_relocate_and_generation_expiry(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            old_output = root / "same.strm"
            new_output = root / "same.mkv.strm"
            winner = SessionClaim("strm", "a", "strm:map", CloudIdentity(pickcode="a"))
            loser = SessionClaim("strm", "z", "strm:map", CloudIdentity(pickcode="z"))
            reservations = SessionReservations()
            first = reservations.reserve(old_output, winner)
            lost = reservations.reserve(old_output, loser)
            self.assertTrue(reservations.confirm(first.token))
            self.assertFalse(lost.confirmed_candidate)

            relocated = reservations.relocate(loser, old_output, new_output)
            self.assertEqual(relocated.status, "relocated")
            self.assertEqual(reservations.get(new_output).winner.ref, loser.ref)
            self.assertNotIn(loser, reservations.get(old_output).losers)
            self.assertTrue(reservations.confirm(relocated.token))

            self.assertTrue(reservations.release(first.token))
            self.assertFalse(reservations.confirm(first.token))
            second = reservations.reserve(old_output, winner)
            self.assertGreater(second.generation, first.generation)
            self.assertFalse(reservations.confirm(first.token))
            self.assertTrue(reservations.confirm(second.token))
            self.assertFalse(reservations.release(first.token))
            self.assertTrue(reservations.confirm(second.token))
            self.assertTrue(reservations.release(loser, new_output))
            self.assertIsNone(reservations.get(new_output))

    def test_sidecar_first_materialize_records_metadata_then_second_skips(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "movie.nfo"
            payload = b"1234"
            digest = "03ac674216f3e15c761ee1a5e255f067953623c8b388b4459e13f978d7c846f4"
            calls = []
            request = self.request(
                root, key="map:sidecar:movie.nfo", kind="sidecar",
                relative_path="movie.nfo", output=output, content=None,
                size=len(payload), sha256=digest,
                pickcode="abc",
                downloader=lambda pickcode, temp: (calls.append(pickcode), temp.write_bytes(payload)),
            )
            materializer = StrmMaterializer()
            first = materialize_for_test(materializer, 
                request, RecordClaims(), decision=CollisionDecision("free", output)
            )
            after = first.mutations[0].after
            self.assertEqual(
                {key: after[key] for key in ("size", "sha256")},
                {"size": 4, "sha256": digest},
            )
            self.assertNotIn("mtime", after)
            self.assertNotIn("etag", after)
            second = materialize_for_test(materializer, 
                request, RecordClaims(), decision=CollisionDecision("free", output),
                previous=after,
            )
            self.assertEqual(second.action, "skipped")
            self.assertEqual(calls, ["abc"])

    def test_sidecar_missing_or_unreliable_metadata_does_not_false_skip_or_persist(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "movie.nfo"
            output.write_bytes(b"1234")
            calls = []
            reliable = self.request(
                root, key="map:sidecar:movie.nfo", kind="sidecar",
                relative_path="movie.nfo", output=output, content=None,
                size=4, mtime=123, etag="etag-1", pickcode="abc",
                downloader=lambda pickcode, temp: (calls.append(pickcode), temp.write_bytes(b"1234")),
            )
            incomplete = {
                "fingerprint": "fp", "path": str(output),
                "cloud_identity": {"pickcode": "abc"},
            }
            skipped = materialize_for_test(StrmMaterializer(), 
                replace(reliable, mtime=None, etag=""), RecordClaims(),
                decision=CollisionDecision("free", output), previous=incomplete,
            )
            self.assertEqual(skipped.action, "updated")
            self.assertEqual(calls, ["abc"])

            unreliable = replace(reliable, cloud_identity=CloudIdentity(), size=99)
            mutation = module_build_record_mutation(
                unreliable, before=incomplete, output=output, reason="test"
            )
            self.assertNotIn("size", mutation.after)
            result = materialize_for_test(StrmMaterializer(), 
                replace(unreliable, size=4), RecordClaims(),
                decision=CollisionDecision("free", output), previous=incomplete,
            )
            self.assertEqual(result.action, "updated")
            self.assertEqual(calls, ["abc", "abc"])

    def test_unreliable_sidecar_actual_materialize_never_persists_metadata(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); output = root / "movie.nfo"
            digest = sha256(b"data").hexdigest()
            request = self.request(
                root, key="map:sidecar:movie.nfo", kind="sidecar",
                relative_path="movie.nfo", output=output, content=None,
                cloud_identity=CloudIdentity(path="/movie.nfo"),
                size=4, mtime=123, etag="etag", sha256=digest,
                downloader=lambda _pickcode, temp: temp.write_bytes(b"data"),
            )
            previous = {
                "path": str(output), "fingerprint": "old",
                "cloud_identity": {"path": "/movie.nfo"},
                "size": 999, "mtime": 999, "etag": "stale", "sha256": "stale",
            }
            result = materialize_for_test(StrmMaterializer(), 
                request, RecordClaims(), decision=CollisionDecision("free", output),
                previous=previous, incremental=False,
            )
            self.assertEqual(output.read_bytes(), b"data")
            for field in ("size", "mtime", "etag", "sha256"):
                self.assertNotIn(field, result.mutations[0].after)

    def test_sidecar_without_any_metadata_redownloads_damaged_file(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); output = root / "movie.nfo"
            output.write_bytes(b"damaged")
            calls = []
            previous = {
                "fingerprint": "fp", "path": str(output),
                "cloud_identity": {"pickcode": "abc"},
            }
            request = self.request(
                root, key="map:sidecar:movie.nfo", kind="sidecar",
                relative_path="movie.nfo", output=output, content=None,
                downloader=lambda _pickcode, temp: (calls.append(1), temp.write_bytes(b"fresh")),
            )
            result = materialize_for_test(StrmMaterializer(), 
                request, RecordClaims(), decision=CollisionDecision("free", output),
                previous=previous,
            )
            self.assertEqual(result.action, "updated")
            self.assertEqual(calls, [1])
            self.assertEqual(output.read_bytes(), b"fresh")

    def test_sidecar_failure_preserves_old_file(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); output = root / "movie.nfo"; output.write_bytes(b"old")
            def bad(_pickcode, temp):
                temp.write_bytes(b"x")
            request = self.request(
                root, key="map:sidecar:movie.nfo", kind="sidecar", relative_path="movie.nfo",
                output=output, content=None, size=4, downloader=bad,
            )
            with self.assertRaisesRegex(OSError, "大小"):
                materialize_for_test(StrmMaterializer(), request, RecordClaims(), decision=CollisionDecision("free", output), incremental=False)
            self.assertEqual(output.read_bytes(), b"old")
            self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_remove_result_four_core_states_and_refusals(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); output = root / "movie.strm"; output.write_text("x")
            record = {"path": str(output), "owner_id": "map"}
            own = RecordClaim("strm", "key", output, "strm", "strm:map", CloudIdentity(pickcode="abc"), "explicit", record)
            materializer = StrmMaterializer()
            shared = replace(own, key="other", owner="strm:other")
            result = materializer.remove_if_owned(record_ref=("strm", "key"), record=record, claims=RecordClaims((own, shared)), target_root=root, expected_owner_id="map")
            self.assertEqual((result.disposition, result.may_drop_record), ("shared_claim", True))
            result = materializer.remove_if_owned(record_ref=("strm", "key"), record=record, claims=RecordClaims((own,)), target_root=root, expected_owner_id="wrong")
            self.assertEqual((result.disposition, result.may_drop_record), ("owner_mismatch", False))
            result = materializer.remove_if_owned(record_ref=("strm", "key"), record=record, claims=RecordClaims((own,)), target_root=root, expected_owner_id="map")
            self.assertEqual((result.disposition, result.may_drop_record), ("unlinked", True))
            self.assertIsNotNone(result.unit)
            self.assertTrue(output.exists())
            output.unlink()
            result = materializer.remove_if_owned(record_ref=("strm", "key"), record=record, claims=RecordClaims((own,)), target_root=root, expected_owner_id="map")
            self.assertEqual((result.disposition, result.may_drop_record), ("already_missing", True))

            ambiguous = replace(own, owner="", owner_confidence="ambiguous")
            result = materializer.remove_if_owned(
                record_ref=("strm", "key"), record=record,
                claims=RecordClaims((ambiguous,)), target_root=root,
                expected_owner_id="map",
            )
            self.assertEqual(
                (result.disposition, result.may_drop_record),
                ("ambiguous_legacy_owner", False),
            )
            conflict = replace(own, key="ambiguous-other", owner="", owner_confidence="ambiguous")
            result = materializer.remove_if_owned(
                record_ref=("strm", "key"), record=record,
                claims=RecordClaims((own, conflict)), target_root=root,
                expected_owner_id="map",
            )
            self.assertEqual(
                (result.disposition, result.may_drop_record),
                ("claim_conflict", False),
            )
            result = materializer.remove_if_owned(
                record_ref=("strm", "key"),
                record={"path": str(root.parent / "outside.strm")},
                claims=RecordClaims((own,)), target_root=root,
                expected_owner_id="map",
            )
            self.assertEqual(
                (result.disposition, result.may_drop_record),
                ("unsafe_path", False),
            )
            output.write_text("x")
            with patch("app.plugins.p115liteassistant.strm_core._file_sha256", side_effect=OSError("read-only")):
                result = materializer.remove_if_owned(
                    record_ref=("strm", "key"), record=record,
                    claims=RecordClaims((own,)), target_root=root,
                    expected_owner_id="map",
                )
            self.assertEqual(
                (result.disposition, result.may_drop_record),
                ("io_error", False),
            )

    def test_mapping_id_with_colon_uses_longest_prefix_and_mismatch_is_ambiguous(self):
        resolved = resolve_legacy_strm_owner("team:movies:sidecar:a.nfo", ("team", "team:movies"))
        self.assertEqual((resolved.mapping_id, resolved.kind, resolved.confidence), ("team:movies", "sidecar", "inferred"))
        mismatch = resolve_legacy_strm_owner("team:movies:a.mkv", ("team:movies",), record_mapping_id="team")
        self.assertEqual(mismatch.confidence, "ambiguous")
        missing = resolve_legacy_strm_owner("unknown:a.mkv", ("team",))
        self.assertEqual(missing.confidence, "ambiguous")

    def test_record_claims_marks_zero_match_legacy_owner_ambiguous(self):
        claims = RecordClaims.from_records(
            {"unknown:movie.mkv": {"path": "/tmp/movie.strm"}},
            mapping_ids=("known",),
        )
        claim = next(iter(claims))
        self.assertEqual(claim.owner_confidence, "ambiguous")

    def test_upload_legacy_owner_checks_all_three_roots(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            outer_source = root / "media"
            nested_source = outer_source / "nested"
            outer_strm = root / "strm"
            nested_strm = outer_strm / "nested"
            record = {
                "target": "/Cloud/Nested/movie.mkv",
                "output_path": str(nested_strm / "movie.strm"),
            }
            mappings = (
                {"id": "outer", "source": str(outer_source), "target": "/Cloud", "strm_target": str(outer_strm)},
                {"id": "nested", "source": str(nested_source), "target": "/Cloud/Nested", "strm_target": str(nested_strm)},
            )
            resolved = resolve_legacy_upload_owner(
                str(nested_source / "movie.mkv"), record, mappings
            )
            self.assertEqual((resolved.mapping_id, resolved.confidence), ("nested", "inferred"))

            outside = {**record, "output_path": str(root / "outside" / "movie.strm")}
            self.assertEqual(
                resolve_legacy_upload_owner(str(nested_source / "movie.mkv"), outside, mappings).confidence,
                "ambiguous",
            )
            missing_output = {"target": record["target"]}
            self.assertEqual(
                resolve_legacy_upload_owner(str(nested_source / "movie.mkv"), missing_output, mappings).confidence,
                "ambiguous",
            )
            missing_strm_root = ({
                "id": "nested", "source": str(nested_source),
                "target": "/Cloud/Nested",
            },)
            self.assertEqual(
                resolve_legacy_upload_owner(
                    str(nested_source / "movie.mkv"), record, missing_strm_root
                ).confidence,
                "ambiguous",
            )
            prefix_spoof = {
                **record, "output_path": str(root / "strm-ab" / "movie.strm")
            }
            prefix_mapping = ({
                "id": "prefix", "source": str(nested_source),
                "target": "/Cloud/Nested", "strm_target": str(root / "strm-a"),
            },)
            self.assertEqual(
                resolve_legacy_upload_owner(
                    str(nested_source / "movie.mkv"), prefix_spoof, prefix_mapping
                ).confidence,
                "ambiguous",
            )

            # 较深 mapping 的 STRM 根越界时，较浅且三条件合法的 mapping 仍可胜出。
            nested_bad = {**mappings[1], "strm_target": str(root / "other")}
            fallback = resolve_legacy_upload_owner(
                str(nested_source / "movie.mkv"), record, (mappings[0], nested_bad)
            )
            self.assertEqual(fallback.mapping_id, "outer")

    def test_feature_flag_defaults_off(self):
        with patch.dict(os.environ, {"P115_STRM_JOURNAL_ENABLED": "true"}):
            self.assertFalse(strm_journal_enabled({}))
        self.assertTrue(strm_journal_enabled({"P115_STRM_JOURNAL_ENABLED": "true"}))

    def journal_fixture(self, root: Path):
        target = root / "movie.strm"; target.write_bytes(b"old")
        temp = root / ".movie.new.tmp"; temp.write_bytes(b"new")
        before_s = {"path": str(target), "fingerprint": "old"}
        after_s = {"path": str(target), "fingerprint": "new"}
        before_u = {"output_path": str(target), "fingerprint": "old"}
        after_u = {"output_path": str(target), "fingerprint": "new"}
        store = DictStore({"s": before_s}, {"u": before_u})
        unit = CommitUnit(
            "case", (
                RecordMutation("test", "strm", "s", before_s, after_s, "strm", "test"),
                RecordMutation("test", "upload", "u", before_u, after_u, "strm", "test"),
            ),
            (FileOperation("replace", target, temp=temp, after_sha256="11507a0e2f5e69d5dfa40a62a1bd7b6ee57e6bcd85c67c9b8431b36fff21c437"),),
            True,
        )
        return store, unit, target

    def test_journal_required_rejected_when_feature_off(self):
        with TemporaryDirectory() as directory:
            store, unit, _target = self.journal_fixture(Path(directory))
            with self.assertRaisesRegex(RuntimeError, "默认关闭"):
                CommitJournal(store, Path(directory) / "journal", enabled=False).execute(unit)

    def test_journal_compare_before_apply_refuses_drift(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); store, unit, target = self.journal_fixture(root)
            store.strm["s"] = {**store.strm["s"], "fingerprint": "drift"}
            with self.assertRaisesRegex(RuntimeError, "compare-before-apply"):
                CommitJournal(store, root / "journal", enabled=True).execute(unit)
            self.assertEqual(target.read_bytes(), b"old")

    def test_replace_apply_refuses_preimage_digest_drift_and_cleans_artifacts(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            request = self.request(root)
            output = root / "movie.strm"
            output.write_bytes(request.content)
            store = DictStore()
            materializer = StrmMaterializer(store)
            decision = materializer.validate_collision(request, RecordClaims())
            reservations = SessionReservations()
            token = materializer.confirm(
                reservations, materializer.reserve(request, decision, reservations)
            )
            prepared = materializer.prepare(
                request, RecordClaims(), decision=decision, previous=None,
                reservation=token, session_reservations=reservations,
            )
            output.write_bytes(b"external after prepare")

            with self.assertRaisesRegex(RuntimeError, "replace incumbent 摘要漂移"):
                materializer.commit(
                    prepared, CommitJournal(store, root / "journal", enabled=True)
                )

            self.assertEqual(output.read_bytes(), b"external after prepare")
            self.assertNotIn(request.key, store.strm)
            self.assertEqual(list(root.glob(".*.tmp")), [])
            self.assertEqual(list(root.glob(".*.bak")), [])

    def test_version_one_journal_without_digest_is_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store, unit, _target = self.journal_fixture(root)
            journal = CommitJournal(store, root / "journal", enabled=True)
            journal.journal_dir.mkdir()
            payload = {
                "version": 1,
                "stage": "prepared",
                "unit": journal._encode_unit(unit),
            }
            payload["unit"]["file_ops"][0].pop("before_sha256", None)
            journal._journal_path(unit.id).write_text(
                json.dumps(payload), encoding="utf-8"
            )

            with self.assertRaisesRegex(RuntimeError, "version 1 journal 缺少 before_sha256"):
                journal.recover_all()

    def test_journal_recovery_refuses_unknown_record_state(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); store, unit, _target = self.journal_fixture(root)
            journal = CommitJournal(
                store, root / "journal", enabled=True,
                fault_injector=lambda stage: (_ for _ in ()).throw(CrashAt(stage)) if stage == "files_applied" else None,
            )
            with self.assertRaises(CrashAt):
                journal.execute(unit)
            store.strm["s"] = {"fingerprint": "neither"}
            with self.assertRaisesRegex(RuntimeError, "无法验证"):
                CommitJournal(store, root / "journal", enabled=True).recover_all()

    def test_prepared_new_target_recovery_does_not_delete_later_incumbent(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "new.strm"
            temp = root / ".new.tmp"
            temp.write_bytes(b"new")
            before = None
            after = {"path": str(target), "fingerprint": "new"}
            store = DictStore()
            unit = CommitUnit(
                "new-target",
                (RecordMutation("test", "strm", "s", before, after, "strm"),),
                (FileOperation("replace", target, temp=temp),),
                True,
            )
            journal = CommitJournal(
                store, root / "journal", enabled=True,
                fault_injector=lambda stage: (_ for _ in ()).throw(CrashAt(stage)) if stage == "prepared" else None,
            )
            with self.assertRaises(CrashAt):
                journal.execute(unit)
            target.write_bytes(b"incumbent")
            with self.assertRaisesRegex(RuntimeError, "本应不存在"):
                CommitJournal(store, root / "journal", enabled=False).recover_all()
            self.assertEqual(target.read_bytes(), b"incumbent")

            # 即使记录意外已到 after，也不能把后来出现的 incumbent 当作本事务文件。
            store.strm["s"] = dict(after)
            with self.assertRaisesRegex(RuntimeError, "replace 尚未完成"):
                CommitJournal(store, root / "journal", enabled=False).recover_all()
            self.assertEqual(target.read_bytes(), b"incumbent")

    def test_files_applied_new_target_recovery_removes_transaction_file(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "new.strm"
            temp = root / ".new.tmp"
            temp.write_bytes(b"new")
            store = DictStore()
            unit = CommitUnit(
                "new-target-applied",
                (RecordMutation("test", "strm", "s", None, {"path": str(target)}, "strm"),),
                (FileOperation("replace", target, temp=temp),),
                True,
            )
            journal = CommitJournal(
                store, root / "journal", enabled=True,
                fault_injector=lambda stage: (_ for _ in ()).throw(CrashAt(stage)) if stage == "files_applied" else None,
            )
            with self.assertRaises(CrashAt):
                journal.execute(unit)
            self.assertTrue(target.exists())
            CommitJournal(store, root / "journal", enabled=False).recover_all()
            self.assertFalse(target.exists())

    def test_files_applied_new_target_external_replacement_blocks_recovery(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); target = root / "new.strm"; temp = root / ".new.tmp"
            temp.write_bytes(b"transaction")
            digest = sha256(b"transaction").hexdigest()
            store = DictStore()
            unit = CommitUnit(
                "external-replacement",
                (RecordMutation("test", "strm", "s", None, {"path": str(target)}, "strm"),),
                (FileOperation("replace", target, temp=temp, after_sha256=digest),), True,
            )
            journal = CommitJournal(
                store, root / "journal", enabled=True,
                fault_injector=lambda stage: (_ for _ in ()).throw(CrashAt(stage))
                if stage == "files_applied" else None,
            )
            with self.assertRaises(CrashAt): journal.execute(unit)
            target.write_bytes(b"external")
            with self.assertRaisesRegex(StrmRecoveryBlockedError, "外部替换"):
                CommitJournal(store, root / "journal", enabled=False).recover_all()
            self.assertEqual(target.read_bytes(), b"external")
            payload = json.loads(
                next((root / "journal").glob("strm-commit-*.json")).read_text()
            )
            self.assertEqual(payload["stage"], "blocked")

    def test_journal_save_failure_rolls_back_file_and_records(self):
        class FailOnceStore(DictStore):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs); self.failed = False
            def save_strm_records(self, records):
                if not self.failed:
                    self.failed = True
                    raise OSError("save failed")
                super().save_strm_records(records)

        with TemporaryDirectory() as directory:
            root = Path(directory); target = root / "movie.strm"; target.write_bytes(b"old")
            temp = root / ".movie.tmp"; temp.write_bytes(b"new")
            before = {"path": str(target), "fingerprint": "old"}
            after = {"path": str(target), "fingerprint": "new"}
            store = FailOnceStore({"s": before})
            unit = CommitUnit(
                "save-failure",
                (RecordMutation("test", "strm", "s", before, after, "strm"),),
                (FileOperation(
                    "replace", target, temp=temp,
                    before_sha256=sha256(b"old").hexdigest(),
                    after_sha256=sha256(b"new").hexdigest(),
                ),), True,
            )
            with self.assertRaisesRegex(OSError, "save failed"):
                CommitJournal(store, root / "journal", enabled=True).execute(unit)
            self.assertEqual(target.read_bytes(), b"old")
            self.assertEqual(store.strm["s"], before)
            self.assertEqual(list(root.glob("*.bak")), [])

    def test_journal_save_failure_does_not_overwrite_external_replacement(self):
        class ReplaceThenFailStore(DictStore):
            def __init__(self, target, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.target = target
                self.failed = False

            def save_strm_records(self, records):
                if not self.failed:
                    self.failed = True
                    self.target.write_bytes(b"external")
                    raise OSError("save failed")
                super().save_strm_records(records)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "movie.strm"
            target.write_bytes(b"old")
            temp = root / ".movie.tmp"
            temp.write_bytes(b"new")
            before = {"path": str(target), "fingerprint": "old"}
            after = {"path": str(target), "fingerprint": "new"}
            store = ReplaceThenFailStore(target, {"s": before})
            unit = CommitUnit(
                "external-after-apply",
                (RecordMutation("test", "strm", "s", before, after, "strm"),),
                (FileOperation(
                    "replace", target, temp=temp,
                    before_sha256=sha256(b"old").hexdigest(),
                    after_sha256=sha256(b"new").hexdigest(),
                ),),
                True,
            )

            with self.assertRaisesRegex(StrmRecoveryBlockedError, "外部替换"):
                CommitJournal(store, root / "journal", enabled=True).execute(unit)
            self.assertEqual(target.read_bytes(), b"external")
            payload = json.loads(
                next((root / "journal").glob("strm-commit-*.json")).read_text()
            )
            self.assertEqual(payload["stage"], "blocked")

    def test_journal_existing_target_external_replacement_blocks_recovery(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store, unit, target = self.journal_fixture(root)
            journal = CommitJournal(
                store, root / "journal", enabled=True,
                fault_injector=lambda stage: (_ for _ in ()).throw(CrashAt(stage))
                if stage == "files_applied" else None,
            )
            with self.assertRaises(CrashAt):
                journal.execute(unit)
            target.write_bytes(b"external")

            with self.assertRaisesRegex(StrmRecoveryBlockedError, "外部替换"):
                CommitJournal(store, root / "journal", enabled=False).recover_all()
            self.assertEqual(target.read_bytes(), b"external")
            payload = json.loads(
                next((root / "journal").glob("strm-commit-*.json")).read_text()
            )
            self.assertEqual(payload["stage"], "blocked")

    def test_verify_after_explicitly_rejects_symlink_to_regular_file(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real.strm"
            real.write_bytes(b"new")
            target = root / "movie.strm"
            target.symlink_to(real)
            after = {"path": str(target), "fingerprint": "new"}
            store = DictStore({"s": after})
            unit = CommitUnit(
                "symlink-after",
                (RecordMutation("test", "strm", "s", None, after, "strm"),),
                (FileOperation(
                    "replace", target,
                    after_sha256=sha256(b"new").hexdigest(),
                    target_existed_before=False,
                ),),
                True,
            )

            with self.assertRaisesRegex(RuntimeError, "符号链接"):
                CommitJournal(store, root / "journal", enabled=True)._verify_after(unit)

    def test_journal_fault_recovery_at_every_stage(self):
        for stage in ("prepared", "files_applied", "strm_saved", "upload_saved", "committed"):
            with self.subTest(stage=stage), TemporaryDirectory() as directory:
                root = Path(directory); store, unit, target = self.journal_fixture(root)
                def crash(current):
                    if current == stage:
                        raise CrashAt(stage)
                journal = CommitJournal(store, root / "journal", enabled=True, fault_injector=crash)
                with self.assertRaises(CrashAt):
                    journal.execute(unit)
                CommitJournal(store, root / "journal", enabled=True).recover_all()
                if stage in {"prepared", "files_applied"}:
                    self.assertEqual(target.read_bytes(), b"old")
                    self.assertEqual(store.strm["s"]["fingerprint"], "old")
                    self.assertEqual(store.upload["u"]["fingerprint"], "old")
                else:
                    self.assertEqual(target.read_bytes(), b"new")
                    self.assertEqual(store.strm["s"]["fingerprint"], "new")
                    self.assertEqual(store.upload["u"]["fingerprint"], "new")
                self.assertEqual(list((root / "journal").glob("strm-commit-*.json")), [])


if __name__ == "__main__":
    unittest.main()

class TransactionalRemovalContractTest(unittest.TestCase):
    def test_prepare_unique_has_mutation_and_unlink_without_side_effect(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); output = root / "a.strm"; output.write_text("x")
            record = {"path": str(output), "owner_id": "m"}
            claim = RecordClaim("strm", "k", output, "strm", "strm:m", CloudIdentity(), "explicit", record)
            result = StrmMaterializer().remove_if_owned(
                record_ref=("strm", "k"), record=record, claims=RecordClaims((claim,)),
                target_root=root, expected_owner_id="m",
            )
            self.assertTrue(output.exists())
            self.assertEqual(len(result.unit.mutations), 1)
            self.assertEqual(len(result.unit.file_ops), 1)
            self.assertEqual(result.unit.file_ops[0].action, "unlink")

    def test_prepare_shared_has_mutation_only(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); output = root / "a.strm"; output.write_text("x")
            record = {"path": str(output), "owner_id": "m"}
            own = RecordClaim("strm", "k", output, "strm", "strm:m", CloudIdentity(), "explicit", record)
            other = replace(own, key="other", owner="strm:o")
            result = StrmMaterializer().remove_if_owned(
                record_ref=("strm", "k"), record=record, claims=RecordClaims((own, other)),
                target_root=root, expected_owner_id="m",
            )
            self.assertEqual(result.disposition, "shared_claim")
            self.assertEqual(result.unit.file_ops, ())

    def test_prepare_missing_has_mutation_only(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); output = root / "missing.strm"
            record = {"path": str(output), "owner_id": "m"}
            claim = RecordClaim("strm", "k", output, "strm", "strm:m", CloudIdentity(), "explicit", record)
            result = StrmMaterializer().remove_if_owned(
                record_ref=("strm", "k"), record=record, claims=RecordClaims((claim,)),
                target_root=root, expected_owner_id="m",
            )
            self.assertEqual(result.disposition, "already_missing")
            self.assertEqual(result.unit.file_ops, ())

    def test_batch_same_output_has_two_mutations_one_unlink(self):
        from app.plugins.p115liteassistant.strm_core import OwnedRemovalRequest
        with TemporaryDirectory() as directory:
            root = Path(directory); output = root / "a.strm"; output.write_text("x")
            a = {"path": str(output), "owner_id": "a"}; b = {"path": str(output), "owner_id": "b"}
            ca = RecordClaim("strm", "a", output, "strm", "strm:a", CloudIdentity(), "explicit", a)
            cb = RecordClaim("strm", "b", output, "strm", "strm:b", CloudIdentity(), "explicit", b)
            result = StrmMaterializer().prepare_owned_removals((
                OwnedRemovalRequest(("strm", "a"), a, root, "a"),
                OwnedRemovalRequest(("strm", "b"), b, root, "b"),
            ), RecordClaims((ca, cb)))[0]
            self.assertEqual(len(result.unit.mutations), 2)
            self.assertEqual(len(result.unit.file_ops), 1)

    def test_refusal_has_no_unit(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); output = root / "a.strm"; output.write_text("x")
            record = {"path": str(output)}
            claim = RecordClaim("strm", "k", output, "strm", "", CloudIdentity(), "ambiguous", record)
            result = StrmMaterializer().remove_if_owned(
                record_ref=("strm", "k"), record=record, claims=RecordClaims((claim,)),
                target_root=root, expected_owner_id="m",
            )
            self.assertFalse(result.may_drop_record)
            self.assertIsNone(result.unit)

    def test_apply_directory_fsync_precedes_files_applied_stage(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); target = root / "a.strm"; target.write_text("x")
            before = {"path": str(target)}; store = DictStore({"k": before})
            result = StrmMaterializer().remove_if_owned(
                record_ref=("strm", "k"), record=before,
                claims=RecordClaims((RecordClaim("strm", "k", target, "strm", "strm:m", CloudIdentity(), "explicit", before),)),
                target_root=root, expected_owner_id="m",
            )
            events = []
            with patch("app.plugins.p115liteassistant.strm_core._fsync_parent_dirs", side_effect=lambda _p: events.append("dir")):
                journal = CommitJournal(store, root / "journal", enabled=True,
                    fault_injector=lambda stage: events.append(stage))
                journal.execute(result.unit)
            self.assertLess(events.index("dir"), events.index("files_applied"))

    def test_production_constructors_reject_missing_journal(self):
        from app.plugins.p115liteassistant.api import Api as ProductionApi
        from app.plugins.p115liteassistant.life_monitor import LifeMonitor as ProductionLifeMonitor
        from app.plugins.p115liteassistant.strm import StrmGenerator as ProductionStrmGenerator
        from app.plugins.p115liteassistant.uploader import DirectoryUploader as ProductionDirectoryUploader
        class Store:
            def get_redirect_secret(self): return "x"
            def get_config(self): return {}
        store = Store()
        with self.assertRaises(ValueError): ProductionStrmGenerator(object(), store, "", False, journal=None)
        with self.assertRaises(ValueError): ProductionLifeMonitor(lambda: object(), store, journal=None)
        with self.assertRaises(ValueError): ProductionDirectoryUploader(object(), store, {}, journal=None)
        with self.assertRaises(ValueError): ProductionApi(lambda: object(), store, journal=None)

class RemovalJournalExecutionTest(unittest.TestCase):
    @staticmethod
    def prepared(root, store, *, extra_claim=None):
        target = root / "movie.strm"; target.write_text("x")
        record = {"path": str(target), "owner_id": "m"}; store.strm["k"] = record
        own = RecordClaim("strm", "k", target, "strm", "strm:m", CloudIdentity(), "explicit", record)
        claims = RecordClaims((own,) if extra_claim is None else (own, extra_claim(own)))
        result = StrmMaterializer(store).remove_if_owned(
            record_ref=("strm", "k"), record=record, claims=claims,
            target_root=root, expected_owner_id="m",
        )
        return target, result

    def test_execute_unique_removes_file_and_record(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); store = DictStore()
            target, result = self.prepared(root, store)
            CommitJournal(store, root / "journal", enabled=True).execute(result.unit)
            self.assertFalse(target.exists()); self.assertNotIn("k", store.strm)

    def test_unlink_apply_refuses_target_digest_drift(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); store = DictStore()
            target, result = self.prepared(root, store)
            target.write_text("external replacement", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "unlink incumbent 摘要漂移"):
                CommitJournal(store, root / "journal", enabled=True).execute(result.unit)

            self.assertEqual(target.read_text(encoding="utf-8"), "external replacement")
            self.assertIn("k", store.strm)
            journal = next((root / "journal").glob("strm-commit-*.json"))
            self.assertEqual(json.loads(journal.read_text(encoding="utf-8"))["stage"], "prepared")

    def test_copy_backup_is_fsynced_before_unlink(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); store = DictStore()
            target, result = self.prepared(root, store)
            journal = CommitJournal(store, root / "journal", enabled=True)
            unit = journal._with_backups(result.unit)
            backup = unit.file_ops[0].backup
            fsynced = []
            real_fsync = os.fsync

            def track_fsync(fd):
                fsynced.append(Path(os.readlink(f"/proc/self/fd/{fd}")))
                real_fsync(fd)

            with patch(
                "app.plugins.p115liteassistant.strm_core.os.link",
                side_effect=OSError("cross-device"),
            ), patch(
                "app.plugins.p115liteassistant.strm_core.os.fsync",
                side_effect=track_fsync,
            ):
                journal._apply_files(unit)

            self.assertFalse(target.exists())
            self.assertEqual(backup.read_text(encoding="utf-8"), "x")
            self.assertIn(backup, fsynced)

    def test_copy_backup_fsync_failure_preserves_before(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); store = DictStore()
            target, result = self.prepared(root, store)
            real_fsync = os.fsync

            def fail_backup_fsync(fd):
                opened = Path(os.readlink(f"/proc/self/fd/{fd}"))
                if opened.suffix == ".bak":
                    raise OSError("fsync failed")
                real_fsync(fd)

            with patch(
                "app.plugins.p115liteassistant.strm_core.os.link",
                side_effect=OSError("cross-device"),
            ), patch(
                "app.plugins.p115liteassistant.strm_core.os.fsync",
                side_effect=fail_backup_fsync,
            ), self.assertRaisesRegex(OSError, "fsync failed"):
                CommitJournal(store, root / "journal", enabled=True).execute(result.unit)

            self.assertEqual(target.read_text(encoding="utf-8"), "x")
            self.assertIn("k", store.strm)

    def test_execute_shared_removes_record_but_keeps_file(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); store = DictStore()
            target, result = self.prepared(
                root, store, extra_claim=lambda own: replace(own, key="other", owner="strm:o")
            )
            CommitJournal(store, root / "journal", enabled=True).execute(result.unit)
            self.assertTrue(target.exists()); self.assertNotIn("k", store.strm)

    def test_execute_missing_removes_record(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); store = DictStore()
            target = root / "missing.strm"; record = {"path": str(target), "owner_id": "m"}
            store.strm["k"] = record
            claim = RecordClaim("strm", "k", target, "strm", "strm:m", CloudIdentity(), "explicit", record)
            result = StrmMaterializer(store).remove_if_owned(
                record_ref=("strm", "k"), record=record, claims=RecordClaims((claim,)),
                target_root=root, expected_owner_id="m",
            )
            CommitJournal(store, root / "journal", enabled=True).execute(result.unit)
            self.assertNotIn("k", store.strm)

    def test_batch_with_external_claim_has_no_unlink(self):
        from app.plugins.p115liteassistant.strm_core import OwnedRemovalRequest
        with TemporaryDirectory() as directory:
            root = Path(directory); target = root / "a.strm"; target.write_text("x")
            record = {"path": str(target), "owner_id": "m"}
            own = RecordClaim("strm", "k", target, "strm", "strm:m", CloudIdentity(), "explicit", record)
            external = replace(own, key="external", owner="strm:e")
            result = StrmMaterializer().prepare_owned_removals((
                OwnedRemovalRequest(("strm", "k"), record, root, "m"),
            ), RecordClaims((own, external)))[0]
            self.assertEqual(result.disposition, "shared_claim"); self.assertEqual(result.unit.file_ops, ())

    def test_batch_ambiguous_external_claim_rejects_whole_group(self):
        from app.plugins.p115liteassistant.strm_core import OwnedRemovalRequest
        with TemporaryDirectory() as directory:
            root = Path(directory); target = root / "a.strm"; target.write_text("x")
            record = {"path": str(target), "owner_id": "m"}
            own = RecordClaim("strm", "k", target, "strm", "strm:m", CloudIdentity(), "explicit", record)
            ambiguous = replace(own, key="external", owner="", owner_confidence="ambiguous")
            result = StrmMaterializer().prepare_owned_removals((
                OwnedRemovalRequest(("strm", "k"), record, root, "m"),
            ), RecordClaims((own, ambiguous)))[0]
            self.assertEqual(result.disposition, "claim_conflict"); self.assertIsNone(result.unit)

    def test_rollback_fsyncs_restored_parent(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); store, unit, _target = StrmCoreTest().journal_fixture(root)
            journal = CommitJournal(store, root / "journal", enabled=True)
            unit = journal._with_backups(unit); journal._apply_files(unit)
            calls = []
            with patch("app.plugins.p115liteassistant.strm_core._fsync_parent_dirs", side_effect=lambda paths: calls.append(tuple(paths))):
                journal._rollback_files(unit)
            self.assertTrue(calls)

    def test_cleanup_fsyncs_files_before_journal_dir(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); store, unit, _target = StrmCoreTest().journal_fixture(root)
            journal = CommitJournal(store, root / "journal", enabled=True)
            journal.journal_dir.mkdir(parents=True, exist_ok=True)
            unit = journal._with_backups(unit); journal._write(unit, "prepared")
            events = []
            with patch("app.plugins.p115liteassistant.strm_core._fsync_parent_dirs", side_effect=lambda _p: events.append("files")), patch("app.plugins.p115liteassistant.strm_core._fsync_dir", side_effect=lambda _p: events.append("journal")):
                journal._cleanup(unit)
            self.assertEqual(events[-2:], ["files", "journal"])

    def test_write_blocked_fsyncs_second_replace(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); store = DictStore(); journal = CommitJournal(store, root / "journal", enabled=True)
            unit = CommitUnit.create(())
            calls = []
            with patch("app.plugins.p115liteassistant.strm_core._fsync_dir", side_effect=lambda path: calls.append(Path(path))):
                journal._write_blocked(unit, "reason")
            self.assertGreaterEqual(calls.count(journal.journal_dir), 2)

    def test_parent_fsync_deduplicates_and_orders(self):
        from app.plugins.p115liteassistant.strm_core import _fsync_parent_dirs
        with TemporaryDirectory() as directory:
            root = Path(directory); (root / "b").mkdir(); (root / "a").mkdir()
            calls = []
            with patch("app.plugins.p115liteassistant.strm_core._fsync_dir", side_effect=lambda path: calls.append(Path(path))):
                _fsync_parent_dirs((root / "b" / "1", root / "a" / "1", root / "b" / "2"))
            self.assertEqual(calls, [root / "a", root / "b"])
