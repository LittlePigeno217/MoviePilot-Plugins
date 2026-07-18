from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch

from p115pickcode import id_to_pickcode

from plugins.p115liteassistant.api import Api
from plugins.p115liteassistant.client import U115AuthError, U115Client, UploadResult
from plugins.p115liteassistant.records import IncrementalRecordStore
from plugins.p115liteassistant.resilience import retry_call as real_retry_call
from plugins.p115liteassistant.strm import (
    StrmGenerator,
    build_redirect_signature,
    build_strm_url,
    normalize_pickcode,
    write_uploaded_strm,
)
from plugins.p115liteassistant.uploader import DirectoryUploader


VALID_PICKCODE = id_to_pickcode(1)
SIDECAR_PICKCODE = id_to_pickcode(2)
SECOND_PICKCODE = id_to_pickcode(3)
TEST_REDIRECT_SECRET = "test-redirect-secret-0123456789abcdef"
VALID_SIGNATURE = build_redirect_signature(TEST_REDIRECT_SECRET, VALID_PICKCODE)


class FakeStore:
    def __init__(self, config=None):
        self.strm_records = {}
        self.upload_records = IncrementalRecordStore()
        self.config = dict(config or {})

    def get_config(self):
        return dict(self.config)

    def get_strm_records(self):
        return dict(self.strm_records)

    def save_strm_records(self, records):
        self.strm_records = dict(records)

    @staticmethod
    def get_redirect_secret():
        return TEST_REDIRECT_SECRET

    def get_upload_records(self):
        return self.upload_records

    def save_upload_records(self, records):
        self.upload_records = records


class FakeStrmClient:
    def __init__(self):
        self.downloaded = []

    def iter_files(self, cid):
        assert cid == "115-root"
        return iter(
            [
                {"name": "Film.mkv", "pickcode": VALID_PICKCODE, "size": 10, "rel_path": "Movies/Film.mkv"},
                {"name": "Film.nfo", "pickcode": SIDECAR_PICKCODE, "size": 4, "rel_path": "Movies/Film.nfo"},
                {"name": "readme.txt", "pickcode": "ignored", "size": 1, "rel_path": "readme.txt"},
            ]
        )

    def download_file(self, pickcode, output, create_parent=True):
        if create_parent:
            Path(output).parent.mkdir(parents=True, exist_ok=True)
        self.downloaded.append((pickcode, Path(output)))
        Path(output).write_text("sidecar", encoding="utf-8")


class FakeUploadClient:
    def __init__(self):
        self.uploaded = []
        self.ready_checks = 0

    def ensure_upload_ready(self):
        self.ready_checks += 1

    def ensure_remote_dir(self, path):
        return {"fileid": "1", "path": path}

    def upload_file(self, target, local_path):
        self.uploaded.append((target["path"], Path(local_path).name))
        return UploadResult(success=True, reused=Path(local_path).suffix == ".mkv")


class StrmUploadClient(FakeUploadClient):
    def upload_file(self, target, local_path):
        result = super().upload_file(target, local_path)
        result.file_item = {
            "name": Path(local_path).name,
            "pickcode": VALID_PICKCODE,
        }
        return result

    @staticmethod
    def get_item(_target_path):
        return {"name": "Film.mkv", "pickcode": VALID_PICKCODE}


class DelayedStrmUploadClient(FakeUploadClient):
    def __init__(self):
        super().__init__()
        self.item_checks = 0

    def get_item(self, _target_path):
        self.item_checks += 1
        return {"name": "Film.mkv", "pickcode": VALID_PICKCODE}


class FailingSidecarUploadClient(FakeUploadClient):
    def upload_file(self, target, local_path):
        if Path(local_path).suffix == ".nfo":
            self.uploaded.append((target["path"], Path(local_path).name))
            return UploadResult(success=False, message="附属文件上传失败")
        return super().upload_file(target, local_path)


class FlakyUploadClient(FakeUploadClient):
    def __init__(self):
        super().__init__()
        self.attempts = 0

    def upload_file(self, target, local_path):
        self.attempts += 1
        if self.attempts == 1:
            raise RuntimeError("temporary upload failure")
        return super().upload_file(target, local_path)


class StrmAndUploaderTest(unittest.TestCase):
    def test_strm_address_requires_explicit_config(self):
        configured = Api(lambda: None, FakeStore({"moviepilot_address": "https://media.example/"}))
        missing = Api(lambda: None, FakeStore())

        self.assertEqual(configured._strm_moviepilot_url(), "https://media.example")
        self.assertEqual(missing._strm_moviepilot_url(), "")
        with TemporaryDirectory() as directory, self.assertRaisesRegex(
            ValueError,
            "MoviePilot HTTP",
        ):
            StrmGenerator(FakeStrmClient(), FakeStore(), "", True).run_mapping(
                {"id": "movies", "source_cid": "115-root", "target_dir": directory}
            )

    def test_strm_url_contains_filename_without_global_apikey(self):
        url = build_strm_url(
            "https://moviepilot.example/mp",
            VALID_PICKCODE,
            TEST_REDIRECT_SECRET,
            "电影 ISO.iso",
        )

        self.assertEqual(
            url,
            "https://moviepilot.example/mp/api/v1/plugin/P115LiteAssistant/redirect"
            f"?pickcode={VALID_PICKCODE}&file_name=%E7%94%B5%E5%BD%B1+ISO.iso"
            f"&sign={VALID_SIGNATURE}",
        )
        self.assertNotIn("apikey", url)
        self.assertLess(len(VALID_PICKCODE), 17)

    def test_pickcode_validation_accepts_real_variable_lengths(self):
        pickcodes = [id_to_pickcode(value) for value in (1, 2**31, 2**63 - 1)]

        self.assertGreater(len({len(value) for value in pickcodes}), 1)
        for pickcode in pickcodes:
            self.assertEqual(normalize_pickcode(pickcode.upper()), pickcode)
        with self.assertRaisesRegex(ValueError, "无效 pickcode"):
            normalize_pickcode("abcdefghijklmnopq")

    def test_strm_generator_requires_source_directory(self):
        with TemporaryDirectory() as directory, self.assertRaisesRegex(
            ValueError,
            "115 源目录不能为空",
        ):
            StrmGenerator(FakeStrmClient(), FakeStore(), "https://moviepilot.example", False).run_mapping(
                {"id": "movies", "source_cid": "", "target_dir": directory}
            )

    def test_strm_generator_rejects_invalid_pickcode(self):
        class InvalidPickcodeClient:
            @staticmethod
            def iter_files(_cid):
                return iter(
                    [{"name": "Film.mkv", "pickcode": "pick", "size": 1, "rel_path": "Film.mkv"}]
                )

        with TemporaryDirectory() as directory:
            result = StrmGenerator(
                InvalidPickcodeClient(),
                FakeStore(),
                "https://moviepilot.example",
                False,
            ).run_mapping({"id": "movies", "source_cid": "root", "target_dir": directory})

            self.assertEqual(result["added"], 0)
            self.assertEqual(result["errors"], 1)
            self.assertFalse((Path(directory) / "Film.strm").exists())

    def test_strm_generator_keeps_existing_output_when_present_pickcode_is_invalid(self):
        class InvalidPickcodeClient:
            @staticmethod
            def iter_files(_cid):
                return iter(
                    [{"name": "Film.mkv", "pickcode": "pick", "size": 1, "rel_path": "Film.mkv"}]
                )

        with TemporaryDirectory() as directory:
            output = Path(directory) / "Film.strm"
            output.write_text("existing\n", encoding="utf-8")
            store = FakeStore()
            store.strm_records["movies:Film.mkv"] = {
                "fingerprint": "existing",
                "path": str(output),
            }

            result = StrmGenerator(
                InvalidPickcodeClient(),
                store,
                "https://moviepilot.example",
                True,
            ).run_mapping({"id": "movies", "source_cid": "root", "target_dir": directory})

            self.assertEqual(result["removed"], 0)
            self.assertEqual(result["errors"], 1)
            self.assertEqual(output.read_text(encoding="utf-8"), "existing\n")
            self.assertIn("movies:Film.mkv", store.strm_records)

    def test_iso_generation_preserves_media_extension(self):
        class IsoClient:
            @staticmethod
            def iter_files(_cid):
                return iter(
                    [{"name": "Disc.iso", "pickcode": VALID_PICKCODE, "size": 1, "rel_path": "Disc.iso"}]
                )

        with TemporaryDirectory() as directory:
            target = Path(directory)
            legacy_output = target / "Disc.strm"
            legacy_output.write_text("legacy", encoding="utf-8")
            store = FakeStore()
            store.strm_records["iso:Disc.iso"] = {
                "fingerprint": "legacy",
                "path": str(legacy_output),
            }
            result = StrmGenerator(
                IsoClient(),
                store,
                "https://moviepilot.example",
                False,
            ).run_mapping({"id": "iso", "source_cid": "root", "target_dir": directory})
            local_source = target / "source"
            upload_target = target / "upload-strm"
            local_source.mkdir()
            iso_file = local_source / "Upload.iso"
            iso_file.write_bytes(b"iso")
            uploaded = write_uploaded_strm(
                iso_file,
                local_source,
                upload_target,
                VALID_PICKCODE,
                "https://moviepilot.example",
                TEST_REDIRECT_SECRET,
            )

            self.assertEqual(result["updated"], 1)
            self.assertTrue((target / "Disc.iso.strm").is_file())
            self.assertFalse(legacy_output.exists())
            self.assertEqual(uploaded.name, "Upload.iso.strm")
            self.assertIn("file_name=Upload.iso", uploaded.read_text(encoding="utf-8"))

    def test_iso_migration_keeps_legacy_path_owned_by_another_mapping(self):
        class IsoClient:
            @staticmethod
            def iter_files(_cid):
                return iter(
                    [{"name": "Disc.iso", "pickcode": VALID_PICKCODE, "size": 1, "rel_path": "Disc.iso"}]
                )

        with TemporaryDirectory() as directory:
            legacy_output = Path(directory) / "Disc.strm"
            legacy_output.write_text("other mapping", encoding="utf-8")
            store = FakeStore()
            store.strm_records = {
                "iso:Disc.iso": {"fingerprint": "legacy", "path": str(legacy_output)},
                "other:Disc.mkv": {"fingerprint": "current", "path": str(legacy_output)},
            }

            StrmGenerator(
                IsoClient(),
                store,
                "https://moviepilot.example",
                False,
            ).run_mapping({"id": "iso", "source_cid": "root", "target_dir": directory})

            self.assertTrue((Path(directory) / "Disc.iso.strm").is_file())
            self.assertEqual(legacy_output.read_text(encoding="utf-8"), "other mapping")

    def test_strm_generator_writes_unique_plugin_redirect_url(self):
        with TemporaryDirectory() as directory:
            target = Path(directory)
            store = FakeStore()
            generator = StrmGenerator(FakeStrmClient(), store, "http://mp:3000", incremental=True)

            with patch("plugins.p115liteassistant.strm.logger") as strm_logger:
                result = generator.run_mapping(
                    {"id": "movies", "source_cid": "115-root", "source_path": "/Movies", "target_dir": str(target)}
                )

            generated = target / "Movies" / "Film.strm"
            self.assertEqual(result["added"], 1)
            self.assertEqual(
                generated.read_text(encoding="utf-8"),
                "http://mp:3000/api/v1/plugin/P115LiteAssistant/redirect"
                f"?pickcode={VALID_PICKCODE}&file_name=Film.mkv&sign={VALID_SIGNATURE}\n",
            )
            self.assertFalse(list(generated.parent.glob(".*.tmp")))
            self.assertTrue(any("生成 STRM 成功" in call.args[0] for call in strm_logger.debug.call_args_list))

            changed = StrmGenerator(FakeStrmClient(), store, "https://media.example/", incremental=True)
            changed_result = changed.run_mapping(
                {"id": "movies", "source_cid": "115-root", "source_path": "/Movies", "target_dir": str(target)}
            )
            self.assertEqual(changed_result["updated"], 1)
            self.assertEqual(
                generated.read_text(encoding="utf-8"),
                "https://media.example/api/v1/plugin/P115LiteAssistant/redirect"
                f"?pickcode={VALID_PICKCODE}&file_name=Film.mkv&sign={VALID_SIGNATURE}\n",
            )
            unchanged_result = changed.run_mapping(
                {"id": "movies", "source_cid": "115-root", "source_path": "/Movies", "target_dir": str(target)}
            )
            self.assertEqual(unchanged_result["skipped"], 1)

            generated.write_text("broken\n", encoding="utf-8")
            repaired_result = changed.run_mapping(
                {"id": "movies", "source_cid": "115-root", "source_path": "/Movies", "target_dir": str(target)}
            )
            self.assertEqual(repaired_result["updated"], 1)
            self.assertIn(f"pickcode={VALID_PICKCODE}", generated.read_text(encoding="utf-8"))

            store.strm_records["movies:Movies/Film.mkv"]["fingerprint"] = "legacy-token-fingerprint"
            generated.write_text("https://media.example/old?apikey=legacy\n", encoding="utf-8")
            migrated_result = changed.run_mapping(
                {"id": "movies", "source_cid": "115-root", "source_path": "/Movies", "target_dir": str(target)}
            )
            self.assertEqual(migrated_result["updated"], 1)
            self.assertNotIn("apikey", generated.read_text(encoding="utf-8"))

    def test_strm_generator_writes_files_concurrently(self):
        class ManyStrmClient:
            @staticmethod
            def iter_files(_cid):
                return iter(
                    {
                        "name": f"Film{index}.mkv",
                        "pickcode": id_to_pickcode(index + 1),
                        "size": index,
                        "rel_path": f"Movies/Film{index}.mkv",
                    }
                    for index in range(32)
                )

        class TrackingGenerator(StrmGenerator):
            _state_lock = threading.Lock()
            active_writes = 0
            max_active_writes = 0

            def _write_strm(self, *args):
                with self._state_lock:
                    self.active_writes += 1
                    self.max_active_writes = max(self.max_active_writes, self.active_writes)
                try:
                    time.sleep(0.01)
                    return super()._write_strm(*args)
                finally:
                    with self._state_lock:
                        self.active_writes -= 1

        with TemporaryDirectory() as directory, patch("plugins.p115liteassistant.strm.logger"):
            generator = TrackingGenerator(ManyStrmClient(), FakeStore(), "http://mp:3000", False)
            result = generator.run_mapping(
                {"id": "many", "source_cid": "115-root", "target_dir": directory}
            )

        self.assertEqual(result["added"], 32)
        self.assertGreaterEqual(generator.max_active_writes, 2)

    def test_strm_generator_prepares_each_output_directory_once(self):
        class SharedDirectoryClient:
            @staticmethod
            def iter_files(_cid):
                return iter(
                    [
                        {"name": "Film1.mkv", "pickcode": VALID_PICKCODE, "size": 1, "rel_path": "Movies/Film1.mkv"},
                        {"name": "Film2.mkv", "pickcode": SECOND_PICKCODE, "size": 2, "rel_path": "Movies/Film2.mkv"},
                    ]
                )

        with TemporaryDirectory() as directory:
            target = Path(directory)
            output_parent = target / "Movies"
            mkdir_calls = []
            real_mkdir = Path.mkdir

            def tracking_mkdir(path, *args, **kwargs):
                if path == output_parent:
                    mkdir_calls.append(path)
                return real_mkdir(path, *args, **kwargs)

            with patch.object(Path, "mkdir", tracking_mkdir):
                result = StrmGenerator(
                    SharedDirectoryClient(),
                    FakeStore(),
                    "http://mp:3000",
                    incremental=False,
                ).run_mapping({"id": "movies", "source_cid": "root", "target_dir": directory})

            self.assertEqual(result["added"], 2)
            self.assertEqual(mkdir_calls, [output_parent])

    def test_strm_generator_downloads_sidecars_into_output_tree_when_enabled(self):
        with TemporaryDirectory() as directory:
            target = Path(directory)
            client = FakeStrmClient()
            generator = StrmGenerator(
                client,
                FakeStore(),
                "http://mp:3000",
                incremental=True,
                download_sidecars=True,
                sidecar_extensions=".nfo",
            )

            result = generator.run_mapping(
                {"id": "movies", "source_cid": "115-root", "target_dir": str(target)}
            )

            self.assertEqual(result["sidecars"], 1)
            self.assertEqual((target / "Movies" / "Film.nfo").read_text(encoding="utf-8"), "sidecar")
            self.assertEqual(client.downloaded[0][0], SIDECAR_PICKCODE)

    def test_strm_generator_does_not_download_sidecars_when_disabled(self):
        with TemporaryDirectory() as directory:
            client = FakeStrmClient()
            result = StrmGenerator(
                client,
                FakeStore(),
                "http://mp:3000",
                incremental=True,
                download_sidecars=False,
                sidecar_extensions=".nfo",
            ).run_mapping(
                {"id": "movies", "source_cid": "115-root", "target_dir": directory}
            )

            self.assertEqual(result["sidecars"], 0)
            self.assertEqual(client.downloaded, [])

    def test_strm_generator_retries_a_failed_sidecar_download(self):
        class FlakySidecarClient(FakeStrmClient):
            def __init__(self):
                super().__init__()
                self.attempts = 0

            def download_file(self, pickcode, output, create_parent=True):
                self.attempts += 1
                if self.attempts < 3:
                    raise RuntimeError("temporary download failure")
                super().download_file(pickcode, output, create_parent=create_parent)

        with TemporaryDirectory() as directory:
            client = FlakySidecarClient()
            generator = StrmGenerator(
                client,
                FakeStore(),
                "http://mp:3000",
                incremental=True,
                download_sidecars=True,
                sidecar_extensions=".nfo",
            )

            with patch(
                "plugins.p115liteassistant.strm.retry_call",
                side_effect=lambda operation, **kwargs: real_retry_call(
                    operation,
                    sleeper=lambda _seconds: None,
                    **kwargs,
                ),
            ):
                result = generator.run_mapping(
                    {"id": "movies", "source_cid": "115-root", "target_dir": directory}
                )

            self.assertEqual(client.attempts, 3)
            self.assertEqual(result["sidecars"], 1)
            self.assertEqual(result["errors"], 0)

    def test_strm_generator_keeps_first_same_stem_item(self):
        class ConflictingMediaClient:
            @staticmethod
            def iter_files(_cid):
                return iter(
                    [
                        {"name": "Film.mkv", "pickcode": VALID_PICKCODE, "size": 1, "rel_path": "Film.mkv"},
                        {"name": "Film.mp4", "pickcode": SECOND_PICKCODE, "size": 2, "rel_path": "Film.mp4"},
                    ]
                )

        with TemporaryDirectory() as directory:
            store = FakeStore()
            stale_output = Path(directory) / "Film.mp4.strm"
            stale_output.write_text("stale\n", encoding="utf-8")
            store.strm_records["movies:Film.mp4"] = {
                "fingerprint": "stale",
                "path": str(stale_output),
            }
            result = StrmGenerator(
                ConflictingMediaClient(),
                store,
                "http://mp:3000",
                incremental=False,
            ).run_mapping({"id": "movies", "source_cid": "root", "target_dir": directory})

            output = Path(directory) / "Film.strm"
            self.assertEqual(result["added"], 1)
            self.assertEqual(result["skipped"], 1)
            self.assertEqual(result["removed"], 1)
            self.assertEqual(result["errors"], 0)
            self.assertIn(f"pickcode={VALID_PICKCODE}", output.read_text(encoding="utf-8"))
            self.assertNotIn(f"pickcode={SECOND_PICKCODE}", output.read_text(encoding="utf-8"))
            self.assertFalse(stale_output.exists())
            self.assertIn("movies:Film.mkv", store.strm_records)
            self.assertNotIn("movies:Film.mp4", store.strm_records)

    def test_strm_generator_keeps_first_exact_duplicate_path(self):
        class DuplicateMediaClient:
            @staticmethod
            def iter_files(_cid):
                return iter(
                    [
                        {"name": "Film.mkv", "pickcode": VALID_PICKCODE, "size": 1, "rel_path": "Film.mkv"},
                        {"name": "Film.mkv", "pickcode": SECOND_PICKCODE, "size": 2, "rel_path": "Film.mkv"},
                    ]
                )

        with TemporaryDirectory() as directory:
            store = FakeStore()
            result = StrmGenerator(
                DuplicateMediaClient(),
                store,
                "http://mp:3000",
                incremental=False,
            ).run_mapping({"id": "movies", "source_cid": "root", "target_dir": directory})

            output = Path(directory) / "Film.strm"
            self.assertEqual(result["added"], 1)
            self.assertEqual(result["skipped"], 1)
            self.assertEqual(result["errors"], 0)
            self.assertIn(f"pickcode={VALID_PICKCODE}", output.read_text(encoding="utf-8"))
            self.assertNotIn(f"pickcode={SECOND_PICKCODE}", output.read_text(encoding="utf-8"))
            self.assertIn("movies:Film.mkv", store.strm_records)

    def test_strm_generator_keeps_latest_115_modified_duplicate(self):
        class DuplicateMediaClient:
            @staticmethod
            def iter_files(_cid):
                return iter(
                    [
                        {
                            "name": "Film.mkv",
                            "pickcode": VALID_PICKCODE,
                            "size": 1,
                            "mtime": 100,
                            "rel_path": "Film.mkv",
                        },
                        {
                            "name": "Film.mp4",
                            "pickcode": SECOND_PICKCODE,
                            "size": 2,
                            "mtime": 200,
                            "rel_path": "Film.mp4",
                        },
                    ]
                )

        with TemporaryDirectory() as directory:
            store = FakeStore()
            result = StrmGenerator(
                DuplicateMediaClient(),
                store,
                "http://mp:3000",
                incremental=False,
            ).run_mapping({"id": "movies", "source_cid": "root", "target_dir": directory})

            output = Path(directory) / "Film.strm"
            self.assertEqual(result["added"], 1)
            self.assertEqual(result["skipped"], 1)
            self.assertEqual(result["errors"], 0)
            self.assertIn(f"pickcode={SECOND_PICKCODE}", output.read_text(encoding="utf-8"))
            self.assertNotIn(f"pickcode={VALID_PICKCODE}", output.read_text(encoding="utf-8"))

    def test_strm_generator_rejects_output_owned_by_another_mapping(self):
        class SingleMediaClient:
            @staticmethod
            def iter_files(_cid):
                return iter(
                    [
                        {
                            "name": "Film.mkv",
                            "pickcode": VALID_PICKCODE,
                            "size": 1,
                            "rel_path": "Film.mkv",
                        }
                    ]
                )

        with TemporaryDirectory() as directory:
            output = Path(directory) / "Film.strm"
            output.write_text("owned by other mapping\n", encoding="utf-8")
            store = FakeStore()
            store.strm_records["other:Film.mkv"] = {
                "fingerprint": "other",
                "path": str(output),
            }

            result = StrmGenerator(
                SingleMediaClient(),
                store,
                "http://mp:3000",
                incremental=False,
            ).run_mapping({"id": "movies", "source_cid": "root", "target_dir": directory})

            self.assertEqual(result["added"], 0)
            self.assertEqual(result["errors"], 1)
            self.assertEqual(output.read_text(encoding="utf-8"), "owned by other mapping\n")
            self.assertIn("other:Film.mkv", store.strm_records)
            self.assertNotIn("movies:Film.mkv", store.strm_records)

    def test_strm_generator_removes_outputs_missing_after_complete_scan(self):
        class EmptyScanClient:
            @staticmethod
            def iter_files(_cid):
                return iter([])

        with TemporaryDirectory() as directory:
            output = Path(directory) / "Film.strm"
            output.write_text("stale\n", encoding="utf-8")
            store = FakeStore()
            store.strm_records["movies:Film.mkv"] = {
                "fingerprint": "stale",
                "path": str(output),
            }

            result = StrmGenerator(
                EmptyScanClient(),
                store,
                "http://mp:3000",
                incremental=True,
            ).run_mapping({"id": "movies", "source_cid": "root", "target_dir": directory})

            self.assertEqual(result["removed"], 1)
            self.assertFalse(output.exists())
            self.assertNotIn("movies:Film.mkv", store.strm_records)

    def test_strm_generator_preserves_stale_output_owned_by_another_mapping(self):
        class EmptyScanClient:
            @staticmethod
            def iter_files(_cid):
                return iter([])

        with TemporaryDirectory() as directory:
            output = Path(directory) / "Film.strm"
            output.write_text("shared\n", encoding="utf-8")
            store = FakeStore()
            store.strm_records.update(
                {
                    "movies:Film.mkv": {"fingerprint": "stale", "path": str(output)},
                    "other:Film.mkv": {"fingerprint": "current", "path": str(output)},
                }
            )

            result = StrmGenerator(
                EmptyScanClient(),
                store,
                "http://mp:3000",
                incremental=True,
            ).run_mapping({"id": "movies", "source_cid": "root", "target_dir": directory})

            self.assertEqual(result["removed"], 1)
            self.assertTrue(output.is_file())
            self.assertNotIn("movies:Film.mkv", store.strm_records)
            self.assertIn("other:Film.mkv", store.strm_records)

    def test_strm_generator_persists_completed_writes_when_scan_fails(self):
        class InterruptedScanClient:
            @staticmethod
            def iter_files(_cid):
                yield {"name": "Film.mkv", "pickcode": VALID_PICKCODE, "size": 1, "rel_path": "Film.mkv"}
                raise RuntimeError("remote scan failed")

        with TemporaryDirectory() as directory:
            store = FakeStore()
            stale_output = Path(directory) / "Old.strm"
            stale_output.write_text("stale\n", encoding="utf-8")
            store.strm_records["movies:Old.mkv"] = {
                "fingerprint": "stale",
                "path": str(stale_output),
            }
            generator = StrmGenerator(
                InterruptedScanClient(),
                store,
                "http://mp:3000",
                incremental=True,
            )

            with self.assertRaisesRegex(RuntimeError, "remote scan failed"):
                generator.run_mapping(
                    {"id": "movies", "source_cid": "root", "target_dir": directory}
                )

            self.assertTrue((Path(directory) / "Film.strm").is_file())
            self.assertIn("movies:Film.mkv", store.strm_records)
            self.assertTrue(stale_output.is_file())
            self.assertIn("movies:Old.mkv", store.strm_records)

    def test_directory_uploader_includes_sidecars_and_skips_unchanged_files(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "Movies"
            source.mkdir()
            (source / "Film.mkv").write_bytes(b"media")
            (source / "Film.nfo").write_text("nfo", encoding="utf-8")
            (source / "ignored.txt").write_text("ignored", encoding="utf-8")
            store = FakeStore()
            client = FakeUploadClient()
            config = {
                "upload_mappings": [{"enabled": True, "source": str(source), "target": "/Cloud/Movies"}],
                "upload_include_sidecars": True,
                "upload_media_extensions": ".mkv",
                "upload_sidecar_extensions": ".nfo",
            }

            with patch("plugins.p115liteassistant.uploader.logger") as upload_logger:
                first = DirectoryUploader(client, store, config).run(incremental=True)
            second = DirectoryUploader(client, store, config).run(incremental=True)

            self.assertEqual(first["instant"], 1)
            self.assertEqual(first["uploaded"], 1)
            self.assertEqual(first["errors"], 0)
            self.assertEqual(client.uploaded, [("/Cloud/Movies", "Film.mkv"), ("/Cloud/Movies", "Film.nfo")])
            self.assertEqual(second["skipped"], 2)
            self.assertTrue(store.upload_records.has_changed(source / "Film.mkv", "/Cloud/New/Film.mkv"))
            success_messages = [call.args[0] for call in upload_logger.info.call_args_list]
            self.assertTrue(any("秒传成功" in message for message in success_messages))
            self.assertTrue(any("上传成功" in message for message in success_messages))

    def test_directory_uploader_generates_strm_after_media_upload(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            output = Path(directory) / "output"
            nested = source / "Movies"
            nested.mkdir(parents=True)
            (nested / "Film.mkv").write_bytes(b"media")
            config = {
                "upload_mappings": [
                    {
                        "enabled": True,
                        "source": str(source),
                        "target": "/Cloud",
                        "strm_target": str(output),
                    }
                ],
                "upload_generate_strm": True,
                "upload_include_sidecars": False,
                "upload_media_extensions": ".mkv",
            }

            client = StrmUploadClient()
            store = FakeStore()
            result = DirectoryUploader(
                client,
                store,
                config,
                "https://moviepilot.example",
            ).run(incremental=True)

            generated = output / "Movies" / "Film.strm"
            self.assertEqual(result["strm_generated"], 1)
            self.assertEqual(result["strm_errors"], 0)
            self.assertEqual(
                generated.read_text(encoding="utf-8"),
                "https://moviepilot.example/api/v1/plugin/P115LiteAssistant/redirect"
                f"?pickcode={VALID_PICKCODE}&file_name=Film.mkv&sign={VALID_SIGNATURE}\n",
            )
            generated.write_text("broken\n", encoding="utf-8")

            repaired = DirectoryUploader(
                client,
                store,
                config,
                "https://moviepilot.example",
            ).run(incremental=True)

            self.assertEqual(repaired["strm_generated"], 1)
            self.assertEqual(len(client.uploaded), 1)
            self.assertIn(f"pickcode={VALID_PICKCODE}", generated.read_text(encoding="utf-8"))

    def test_directory_uploader_requires_strm_target_when_generation_enabled(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            (source / "Film.mkv").write_bytes(b"media")
            uploader = DirectoryUploader(
                StrmUploadClient(),
                FakeStore(),
                {
                    "upload_mappings": [
                        {"enabled": True, "source": str(source), "target": "/Cloud"}
                    ],
                    "upload_generate_strm": True,
                    "upload_media_extensions": ".mkv",
                },
                "https://moviepilot.example",
            )

            with self.assertRaisesRegex(ValueError, "未配置输出目录"):
                uploader.run(incremental=True)

    def test_directory_uploader_rejects_conflicting_strm_outputs_before_upload(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            output = Path(directory) / "output"
            source.mkdir()
            (source / "Film.mkv").write_bytes(b"mkv")
            (source / "Film.mp4").write_bytes(b"mp4")
            client = StrmUploadClient()
            uploader = DirectoryUploader(
                client,
                FakeStore(),
                {
                    "upload_mappings": [
                        {
                            "enabled": True,
                            "source": str(source),
                            "target": "/Cloud",
                            "strm_target": str(output),
                        }
                    ],
                    "upload_generate_strm": True,
                    "upload_include_sidecars": False,
                    "upload_media_extensions": ".mkv,.mp4",
                },
                "https://moviepilot.example",
            )

            with self.assertRaisesRegex(ValueError, "STRM 输出路径冲突"):
                uploader.run(incremental=True)

            self.assertEqual(client.uploaded, [])

    def test_directory_uploader_rechecks_uploaded_item_before_generating_strm(self):
        with TemporaryDirectory() as directory, patch(
            "plugins.p115liteassistant.uploader.sleep"
        ) as sleeper:
            source = Path(directory) / "source"
            output = Path(directory) / "output"
            source.mkdir()
            (source / "Film.mkv").write_bytes(b"media")
            client = DelayedStrmUploadClient()
            result = DirectoryUploader(
                client,
                FakeStore(),
                {
                    "upload_mappings": [
                        {
                            "enabled": True,
                            "source": str(source),
                            "target": "/Cloud",
                            "strm_target": str(output),
                        }
                    ],
                    "upload_generate_strm": True,
                    "upload_include_sidecars": False,
                    "upload_media_extensions": ".mkv",
                },
                "https://moviepilot.example",
            ).run(incremental=True)

            self.assertEqual(result["strm_generated"], 1)
            self.assertEqual(client.item_checks, 1)
            sleeper.assert_called_once_with(5)

    def test_directory_uploader_does_not_retry_expired_cookie_errors(self):
        class ExpiredCookieClient(FakeUploadClient):
            def __init__(self):
                super().__init__()
                self.item_checks = 0

            def get_item(self, _target_path):
                self.item_checks += 1
                raise U115AuthError("115 Cookie 已失效，请重新扫码登录")

        client = ExpiredCookieClient()
        uploader = DirectoryUploader(client, FakeStore(), {})

        with patch("plugins.p115liteassistant.uploader.sleep") as sleeper, self.assertRaisesRegex(
            U115AuthError,
            "Cookie 已失效",
        ):
            uploader._resolve_uploaded_file_item(
                None,
                "/Cloud/Film.mkv",
                wait_for_upload=False,
            )

        self.assertEqual(client.item_checks, 1)
        sleeper.assert_not_called()

    def test_directory_uploader_reprocesses_old_record_when_strm_is_enabled(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            output = Path(directory) / "output"
            source.mkdir()
            movie = source / "Film.mkv"
            movie.write_bytes(b"media")
            store = FakeStore()
            store.upload_records.mark_uploaded(
                movie,
                "/Cloud/Film.mkv",
                metadata={"pickcode": VALID_PICKCODE},
            )
            client = StrmUploadClient()

            result = DirectoryUploader(
                client,
                store,
                {
                    "upload_mappings": [
                        {
                            "enabled": True,
                            "source": str(source),
                            "target": "/Cloud",
                            "strm_target": str(output),
                        }
                    ],
                    "upload_generate_strm": True,
                    "upload_include_sidecars": False,
                    "upload_media_extensions": ".mkv",
                },
                "https://moviepilot.example",
            ).run(incremental=True)

            self.assertEqual(result["strm_generated"], 1)
            self.assertEqual(len(client.uploaded), 0)
            self.assertTrue((output / "Film.strm").is_file())

    def test_directory_uploader_migrates_legacy_record_identity_before_strm(self):
        class LegacyRecordClient(FakeUploadClient):
            @staticmethod
            def get_item(target_path):
                return U115Client._item_from_info(
                    {
                        "file_id": "remote-file-id",
                        "file_category": "1",
                        "file_name": "Film.mkv",
                        "pick_code": VALID_PICKCODE,
                        "size_byte": "5",
                    },
                    target_path,
                )

        with TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            output = Path(directory) / "output"
            source.mkdir()
            movie = source / "Film.mkv"
            movie.write_bytes(b"media")
            store = FakeStore()
            store.upload_records.mark_uploaded(movie, "/Cloud/Film.mkv")
            client = LegacyRecordClient()

            with patch("plugins.p115liteassistant.uploader.logger") as upload_logger:
                result = DirectoryUploader(
                    client,
                    store,
                    {
                        "upload_mappings": [
                            {
                                "enabled": True,
                                "source": str(source),
                                "target": "/Cloud",
                                "strm_target": str(output),
                            }
                        ],
                        "upload_generate_strm": True,
                        "upload_include_sidecars": False,
                        "upload_media_extensions": ".mkv",
                    },
                    "https://moviepilot.example",
                ).run(incremental=True)

            record = store.upload_records.to_dict()[str(movie)]
            self.assertEqual(result["strm_generated"], 1)
            self.assertEqual(result["strm_errors"], 0)
            self.assertEqual(client.uploaded, [])
            self.assertEqual(record["pickcode"], VALID_PICKCODE)
            self.assertEqual(record["pickcode_identity_source"], "verified_target_path")
            self.assertEqual(record["pickcode_identity_target"], "/Cloud/Film.mkv")
            self.assertEqual(record["pickcode_identity_fileid"], "remote-file-id")
            self.assertIn("pickcode_identity_migrated_at", record)
            self.assertTrue((output / "Film.strm").is_file())
            self.assertTrue(
                any("旧上传记录身份迁移成功" in call.args[0] for call in upload_logger.info.call_args_list)
            )

    def test_directory_uploader_rejects_legacy_identity_without_remote_size(self):
        class MissingSizeLegacyRecordClient(FakeUploadClient):
            @staticmethod
            def get_item(target_path):
                return U115Client._item_from_info(
                    {
                        "file_id": "remote-file-id",
                        "file_category": "1",
                        "file_name": "Film.mkv",
                        "pick_code": VALID_PICKCODE,
                    },
                    target_path,
                )

        with TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            output = Path(directory) / "output"
            source.mkdir()
            movie = source / "Film.mkv"
            movie.write_bytes(b"media")
            store = FakeStore()
            store.upload_records.mark_uploaded(movie, "/Cloud/Film.mkv")
            client = MissingSizeLegacyRecordClient()

            result = DirectoryUploader(
                client,
                store,
                {
                    "upload_mappings": [
                        {
                            "enabled": True,
                            "source": str(source),
                            "target": "/Cloud",
                            "strm_target": str(output),
                        }
                    ],
                    "upload_generate_strm": True,
                    "upload_delete_source": True,
                    "upload_include_sidecars": False,
                    "upload_media_extensions": ".mkv",
                },
                "https://moviepilot.example",
            ).run(incremental=True)

            record = store.upload_records.to_dict()[str(movie)]
            self.assertEqual(result["strm_errors"], 1)
            self.assertEqual(result["strm_generated"], 0)
            self.assertEqual(client.uploaded, [])
            self.assertNotIn("pickcode", record)
            self.assertTrue(movie.is_file())
            self.assertFalse((output / "Film.strm").exists())
            self.assertIn("缺少大小", result["errors_detail"][0]["message"])

    def test_directory_uploader_rejects_legacy_identity_path_mismatch(self):
        class MismatchedLegacyRecordClient(FakeUploadClient):
            @staticmethod
            def get_item(_target_path):
                return {
                    "fileid": "other-file-id",
                    "path": "/Other/Film.mkv",
                    "type": "file",
                    "name": "Film.mkv",
                    "pickcode": "qrstuvwxyzabcdefg",
                    "size": 5,
                }

        with TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            output = Path(directory) / "output"
            source.mkdir()
            movie = source / "Film.mkv"
            movie.write_bytes(b"media")
            store = FakeStore()
            store.upload_records.mark_uploaded(movie, "/Cloud/Film.mkv")
            client = MismatchedLegacyRecordClient()

            result = DirectoryUploader(
                client,
                store,
                {
                    "upload_mappings": [
                        {
                            "enabled": True,
                            "source": str(source),
                            "target": "/Cloud",
                            "strm_target": str(output),
                        }
                    ],
                    "upload_generate_strm": True,
                    "upload_delete_source": True,
                    "upload_include_sidecars": False,
                    "upload_media_extensions": ".mkv",
                },
                "https://moviepilot.example",
            ).run(incremental=True)

            record = store.upload_records.to_dict()[str(movie)]
            self.assertEqual(result["strm_errors"], 1)
            self.assertEqual(result["strm_generated"], 0)
            self.assertEqual(client.uploaded, [])
            self.assertNotIn("pickcode", record)
            self.assertTrue(movie.is_file())
            self.assertFalse((output / "Film.strm").exists())
            self.assertIn("远端文件路径", result["errors_detail"][0]["message"])

    def test_directory_uploader_rejects_pending_strm_when_remote_pickcode_changed(self):
        class ReplacedRemoteClient(FakeUploadClient):
            @staticmethod
            def get_item(_target_path):
                return {"name": "Film.mkv", "pickcode": "qrstuvwxyzabcdefg"}

        with TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            output = Path(directory) / "output"
            source.mkdir()
            movie = source / "Film.mkv"
            movie.write_bytes(b"media")
            store = FakeStore()
            store.upload_records.mark_uploaded(
                movie,
                "/Cloud/Film.mkv",
                metadata={"pickcode": VALID_PICKCODE},
            )
            client = ReplacedRemoteClient()

            result = DirectoryUploader(
                client,
                store,
                {
                    "upload_mappings": [
                        {
                            "enabled": True,
                            "source": str(source),
                            "target": "/Cloud",
                            "strm_target": str(output),
                        }
                    ],
                    "upload_generate_strm": True,
                    "upload_delete_source": True,
                    "upload_include_sidecars": False,
                    "upload_media_extensions": ".mkv",
                },
                "https://moviepilot.example",
            ).run(incremental=True)

            self.assertEqual(result["strm_errors"], 1)
            self.assertEqual(client.uploaded, [])
            self.assertTrue(movie.is_file())
            self.assertFalse((output / "Film.strm").exists())
            self.assertIn("Pickcode 与当前远端文件不一致", result["errors_detail"][0]["message"])

    def test_directory_uploader_revalidates_remote_pickcode_before_incremental_skip(self):
        class ReplacedRemoteClient(FakeUploadClient):
            @staticmethod
            def get_item(_target_path):
                return {"name": "Film.mkv", "pickcode": SECOND_PICKCODE}

        with TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            output = Path(directory) / "output"
            source.mkdir()
            movie = source / "Film.mkv"
            movie.write_bytes(b"media")
            store = FakeStore()
            client = ReplacedRemoteClient()
            config = {
                "upload_mappings": [
                    {
                        "enabled": True,
                        "source": str(source),
                        "target": "/Cloud",
                        "strm_target": str(output),
                    }
                ],
                "upload_generate_strm": True,
                "upload_include_sidecars": False,
                "upload_media_extensions": ".mkv",
            }
            uploader = DirectoryUploader(
                client,
                store,
                config,
                "https://moviepilot.example",
            )
            store.upload_records.mark_uploaded(
                movie,
                "/Cloud/Film.mkv",
                metadata={
                    "pickcode": VALID_PICKCODE,
                    **uploader._strm_record_metadata(str(output)),
                },
            )
            generated = write_uploaded_strm(
                movie,
                source,
                output,
                VALID_PICKCODE,
                "https://moviepilot.example",
                TEST_REDIRECT_SECRET,
            )

            result = uploader.run(incremental=True)

            self.assertEqual(result["skipped"], 1)
            self.assertEqual(result["strm_errors"], 1)
            self.assertEqual(result["strm_generated"], 0)
            self.assertEqual(client.uploaded, [])
            self.assertIn(VALID_PICKCODE, generated.read_text(encoding="utf-8"))
            self.assertIn("Pickcode 与当前远端文件不一致", result["errors_detail"][0]["message"])

    def test_directory_uploader_keeps_source_when_strm_generation_fails(self):
        class MissingItemClient(FakeUploadClient):
            @staticmethod
            def get_item(_target_path):
                return None

        with TemporaryDirectory() as directory, patch(
            "plugins.p115liteassistant.uploader.sleep"
        ):
            source = Path(directory) / "source"
            output = Path(directory) / "output"
            source.mkdir()
            movie = source / "Film.mkv"
            movie.write_bytes(b"media")
            store = FakeStore()
            client = MissingItemClient()
            result = DirectoryUploader(
                client,
                store,
                {
                    "upload_mappings": [
                        {
                            "enabled": True,
                            "source": str(source),
                            "target": "/Cloud",
                            "strm_target": str(output),
                        }
                    ],
                    "upload_generate_strm": True,
                    "upload_delete_source": True,
                    "upload_include_sidecars": False,
                    "upload_media_extensions": ".mkv",
                },
                "https://moviepilot.example",
            ).run(incremental=True)

            self.assertEqual(result["strm_errors"], 1)
            self.assertTrue(movie.is_file())
            self.assertFalse(store.upload_records.has_changed(movie, "/Cloud/Film.mkv"))

            repeated = DirectoryUploader(
                client,
                store,
                {
                    "upload_mappings": [
                        {
                            "enabled": True,
                            "source": str(source),
                            "target": "/Cloud",
                            "strm_target": str(output),
                        }
                    ],
                    "upload_generate_strm": True,
                    "upload_delete_source": True,
                    "upload_include_sidecars": False,
                    "upload_media_extensions": ".mkv",
                },
                "https://moviepilot.example",
            ).run(incremental=True)

            self.assertEqual(repeated["skipped"], 1)
            self.assertEqual(len(client.uploaded), 1)

    def test_directory_uploader_rejects_enabled_empty_mapping(self):
        uploader = DirectoryUploader(
            FakeUploadClient(),
            FakeStore(),
            {"upload_mappings": [{"enabled": True, "source": "", "target": ""}]},
        )

        with self.assertRaisesRegex(ValueError, "必须同时配置"):
            uploader.run(incremental=True)

    def test_directory_uploader_rejects_same_or_nested_sources_before_upload(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            nested = source / "nested"
            nested.mkdir(parents=True)
            (nested / "Film.mkv").write_bytes(b"media")

            for sources in ((source, source), (source, nested)):
                with self.subTest(sources=sources):
                    client = FakeUploadClient()
                    uploader = DirectoryUploader(
                        client,
                        FakeStore(),
                        {
                            "upload_mappings": [
                                {"enabled": True, "source": str(sources[0]), "target": "/Cloud/A"},
                                {"enabled": True, "source": str(sources[1]), "target": "/Cloud/B"},
                            ],
                            "upload_include_sidecars": False,
                            "upload_media_extensions": ".mkv",
                        },
                    )

                    with self.assertRaisesRegex(ValueError, "不能相同或互为父子目录"):
                        uploader.run(incremental=True)

                    self.assertEqual(client.uploaded, [])

    def test_directory_uploader_rejects_source_symlink_before_upload(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "Film.mkv").write_bytes(b"media")
            symlink = source / "Linked.mkv"
            symlink.write_bytes(b"linked")
            client = FakeUploadClient()

            uploader = DirectoryUploader(
                client,
                FakeStore(),
                {
                    "upload_mappings": [
                        {"enabled": True, "source": str(source), "target": "/Cloud"}
                    ],
                    "upload_include_sidecars": False,
                    "upload_media_extensions": ".mkv",
                },
            )

            with patch.object(Path, "is_symlink", autospec=True) as is_symlink:
                is_symlink.side_effect = lambda path: path == symlink
                with self.assertRaisesRegex(ValueError, "不允许包含符号链接"):
                    uploader.run(incremental=True)

            self.assertEqual(client.uploaded, [])

    def test_directory_uploader_checks_auth_before_scanning(self):
        class UnauthorizedClient(FakeUploadClient):
            def ensure_upload_ready(self):
                raise U115AuthError("Open 授权失败")

        uploader = DirectoryUploader(
            UnauthorizedClient(),
            FakeStore(),
            {"upload_mappings": [{"enabled": True, "source": "/missing", "target": "/Cloud"}]},
        )

        with patch.object(uploader, "_iter_files") as iter_files:
            with self.assertRaisesRegex(U115AuthError, "Open 授权失败"):
                uploader.run(incremental=True)

        iter_files.assert_not_called()

    def test_directory_uploader_retries_transient_upload_failures(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "Movies"
            source.mkdir()
            (source / "Film.mkv").write_bytes(b"media")
            client = FlakyUploadClient()
            config = {
                "upload_mappings": [{"enabled": True, "source": str(source), "target": "/Cloud/Movies"}],
                "upload_include_sidecars": False,
                "upload_media_extensions": ".mkv",
                "upload_sidecar_extensions": ".nfo",
            }

            result = DirectoryUploader(client, FakeStore(), config).run(incremental=True)

            self.assertEqual(client.attempts, 2)
            self.assertEqual(result["instant"], 1)
            self.assertEqual(result["errors"], 0)

    def test_directory_uploader_deletes_source_only_after_success(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "Movies"
            source.mkdir()
            movie = source / "Film.mkv"
            movie.write_bytes(b"media")
            config = {
                "upload_mappings": [{"enabled": True, "source": str(source), "target": "/Cloud/Movies"}],
                "upload_include_sidecars": False,
                "upload_delete_source": True,
                "upload_media_extensions": ".mkv",
                "upload_sidecar_extensions": ".nfo",
            }

            result = DirectoryUploader(FakeUploadClient(), FakeStore(), config).run(incremental=True)

            self.assertEqual(result["errors"], 0)
            self.assertFalse(movie.exists())
            self.assertTrue(source.is_dir())

    def test_directory_uploader_deletes_media_and_sidecars_as_a_group(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "Movies"
            source.mkdir()
            movie = source / "Film.mkv"
            sidecar = source / "Film.nfo"
            movie.write_bytes(b"media")
            sidecar.write_text("nfo", encoding="utf-8")
            config = {
                "upload_mappings": [{"enabled": True, "source": str(source), "target": "/Cloud/Movies"}],
                "upload_include_sidecars": True,
                "upload_delete_source": True,
                "upload_media_extensions": ".mkv",
                "upload_sidecar_extensions": ".nfo",
            }

            result = DirectoryUploader(FakeUploadClient(), FakeStore(), config).run(incremental=True)

            self.assertEqual(result["deleted"], 2)
            self.assertFalse(movie.exists())
            self.assertFalse(sidecar.exists())

    def test_directory_uploader_deletes_an_orphan_sidecar_after_upload(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "Movies"
            source.mkdir()
            sidecar = source / "poster.jpg"
            sidecar.write_bytes(b"poster")
            config = {
                "upload_mappings": [{"enabled": True, "source": str(source), "target": "/Cloud/Movies"}],
                "upload_include_sidecars": True,
                "upload_delete_source": True,
                "upload_media_extensions": ".mkv",
                "upload_sidecar_extensions": ".jpg",
            }

            result = DirectoryUploader(FakeUploadClient(), FakeStore(), config).run(incremental=True)

            self.assertEqual(result["deleted"], 1)
            self.assertFalse(sidecar.exists())

    def test_directory_uploader_does_not_retry_upload_when_strm_lookup_fails(self):
        class LookupFailureClient(FakeUploadClient):
            @staticmethod
            def get_item(_target_path):
                raise RuntimeError("temporary lookup failure")

        with TemporaryDirectory() as directory, patch(
            "plugins.p115liteassistant.uploader.sleep"
        ):
            source = Path(directory) / "Movies"
            output = Path(directory) / "strm"
            source.mkdir()
            movie = source / "Film.mkv"
            movie.write_bytes(b"media")
            client = LookupFailureClient()
            store = FakeStore()
            config = {
                "upload_mappings": [
                    {
                        "enabled": True,
                        "source": str(source),
                        "target": "/Cloud/Movies",
                        "strm_target": str(output),
                    }
                ],
                "upload_generate_strm": True,
                "upload_include_sidecars": False,
                "upload_media_extensions": ".mkv",
            }

            first = DirectoryUploader(
                client,
                store,
                config,
                "https://moviepilot.example",
            ).run(incremental=True)
            second = DirectoryUploader(
                client,
                store,
                config,
                "https://moviepilot.example",
            ).run(incremental=True)

            self.assertEqual(first["instant"], 1)
            self.assertEqual(first["strm_errors"], 1)
            self.assertEqual(second["skipped"], 1)
            self.assertEqual(len(client.uploaded), 1)
            self.assertFalse(store.upload_records.has_changed(movie, "/Cloud/Movies/Film.mkv"))

    def test_directory_uploader_keeps_media_when_sidecar_upload_fails(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "Movies"
            source.mkdir()
            movie = source / "Film.mkv"
            sidecar = source / "Film.nfo"
            movie.write_bytes(b"media")
            sidecar.write_text("nfo", encoding="utf-8")
            config = {
                "upload_mappings": [{"enabled": True, "source": str(source), "target": "/Cloud/Movies"}],
                "upload_include_sidecars": True,
                "upload_delete_source": True,
                "upload_media_extensions": ".mkv",
                "upload_sidecar_extensions": ".nfo",
            }

            with patch("plugins.p115liteassistant.uploader.logger") as upload_logger:
                result = DirectoryUploader(FailingSidecarUploadClient(), FakeStore(), config).run(incremental=True)

            self.assertEqual(result["deleted"], 0)
            self.assertEqual(result["errors"], 1)
            self.assertTrue(movie.exists())
            self.assertTrue(sidecar.exists())
            self.assertTrue(any("上传失败" in call.args[0] for call in upload_logger.error.call_args_list))

    def test_directory_uploader_removes_empty_child_directories(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "Movies"
            nested = source / "Season 1"
            nested.mkdir(parents=True)
            movie = nested / "Film.mkv"
            movie.write_bytes(b"media")
            config = {
                "upload_mappings": [{"enabled": True, "source": str(source), "target": "/Cloud/Movies"}],
                "upload_include_sidecars": False,
                "upload_delete_source": True,
                "upload_media_extensions": ".mkv",
                "upload_sidecar_extensions": ".nfo",
            }

            result = DirectoryUploader(FakeUploadClient(), FakeStore(), config).run(incremental=True)

            self.assertEqual(result["deleted"], 1)
            self.assertFalse(nested.exists())
            self.assertTrue(source.is_dir())
