from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch

from fastapi import Request
from plugins.p115liteassistant.api import Api
from plugins.p115liteassistant.client import U115AuthError, U115Client, UploadResult
from plugins.p115liteassistant.records import IncrementalRecordStore
from plugins.p115liteassistant.resilience import retry_call as real_retry_call
from plugins.p115liteassistant.strm import StrmGenerator
from plugins.p115liteassistant.uploader import DirectoryUploader


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
                {"name": "Film.mkv", "pickcode": "pick", "size": 10, "rel_path": "Movies/Film.mkv"},
                {"name": "Film.nfo", "pickcode": "sidecar-pick", "size": 4, "rel_path": "Movies/Film.nfo"},
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
            "pickcode": "abcdefghijklmnopq",
        }
        return result

    @staticmethod
    def get_item(_target_path):
        return {"name": "Film.mkv", "pickcode": "abcdefghijklmnopq"}


class DelayedStrmUploadClient(FakeUploadClient):
    def __init__(self):
        super().__init__()
        self.item_checks = 0

    def get_item(self, _target_path):
        self.item_checks += 1
        return {"name": "Film.mkv", "pickcode": "abcdefghijklmnopq"}


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
    def test_moviepilot_url_uses_the_request_address(self):
        request = Request(
            {
                "type": "http",
                "scheme": "http",
                "server": ("127.0.0.1", 3001),
                "headers": [(b"x-forwarded-proto", b"https"), (b"x-forwarded-host", b"moviepilot.example")],
            }
        )

        self.assertEqual(Api._moviepilot_url(request), "https://moviepilot.example")

    def test_strm_address_prefers_config_and_falls_back_to_request(self):
        request = Request(
            {
                "type": "http",
                "scheme": "http",
                "server": ("127.0.0.1", 3001),
                "path": "/api/v1/plugin/P115LiteAssistant/strm/sync",
                "query_string": b"",
                "headers": [(b"host", b"127.0.0.1:3001")],
            }
        )

        configured = Api(lambda: None, FakeStore({"moviepilot_address": "https://media.example/"}), lambda: "")
        fallback = Api(lambda: None, FakeStore(), lambda: "")

        self.assertEqual(configured._strm_moviepilot_url(request), "https://media.example")
        self.assertEqual(fallback._strm_moviepilot_url(request), "http://127.0.0.1:3001")

    def test_strm_generator_writes_unique_plugin_redirect_url(self):
        with TemporaryDirectory() as directory:
            target = Path(directory)
            store = FakeStore()
            generator = StrmGenerator(FakeStrmClient(), store, "http://mp:3000", "api-token", incremental=True)

            with patch("plugins.p115liteassistant.strm.logger") as strm_logger:
                result = generator.run_mapping(
                    {"id": "movies", "source_cid": "115-root", "source_path": "/Movies", "target_dir": str(target)}
                )

            generated = target / "Movies" / "Film.strm"
            self.assertEqual(result["added"], 1)
            self.assertEqual(
                generated.read_text(encoding="utf-8"),
                "http://mp:3000/api/v1/plugin/P115LiteAssistant/redirect?pickcode=pick&apikey=api-token\n",
            )
            self.assertFalse(list(generated.parent.glob(".*.tmp")))
            self.assertTrue(any("生成 STRM 成功" in call.args[0] for call in strm_logger.debug.call_args_list))

            changed = StrmGenerator(FakeStrmClient(), store, "https://media.example/", "api-token", incremental=True)
            changed_result = changed.run_mapping(
                {"id": "movies", "source_cid": "115-root", "source_path": "/Movies", "target_dir": str(target)}
            )
            self.assertEqual(changed_result["updated"], 1)
            self.assertEqual(
                generated.read_text(encoding="utf-8"),
                "https://media.example/api/v1/plugin/P115LiteAssistant/redirect?pickcode=pick&apikey=api-token\n",
            )
            unchanged_result = changed.run_mapping(
                {"id": "movies", "source_cid": "115-root", "source_path": "/Movies", "target_dir": str(target)}
            )
            self.assertEqual(unchanged_result["skipped"], 1)

            rotated = StrmGenerator(
                FakeStrmClient(),
                store,
                "https://media.example/",
                "rotated-token",
                incremental=True,
            )
            rotated_result = rotated.run_mapping(
                {"id": "movies", "source_cid": "115-root", "source_path": "/Movies", "target_dir": str(target)}
            )
            self.assertEqual(rotated_result["updated"], 1)
            self.assertEqual(
                generated.read_text(encoding="utf-8"),
                "https://media.example/api/v1/plugin/P115LiteAssistant/redirect"
                "?pickcode=pick&apikey=rotated-token\n",
            )
            self.assertNotIn(
                "rotated-token",
                store.strm_records["movies:Movies/Film.mkv"]["fingerprint"],
            )

    def test_strm_generator_writes_files_concurrently(self):
        class ManyStrmClient:
            @staticmethod
            def iter_files(_cid):
                return iter(
                    {
                        "name": f"Film{index}.mkv",
                        "pickcode": f"pick-{index}",
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
            generator = TrackingGenerator(ManyStrmClient(), FakeStore(), "http://mp:3000", "api-token", False)
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
                        {"name": "Film1.mkv", "pickcode": "pick-1", "size": 1, "rel_path": "Movies/Film1.mkv"},
                        {"name": "Film2.mkv", "pickcode": "pick-2", "size": 2, "rel_path": "Movies/Film2.mkv"},
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
                    "api-token",
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
                "api-token",
                incremental=True,
                download_sidecars=True,
                sidecar_extensions=".nfo",
            )

            result = generator.run_mapping(
                {"id": "movies", "source_cid": "115-root", "target_dir": str(target)}
            )

            self.assertEqual(result["sidecars"], 1)
            self.assertEqual((target / "Movies" / "Film.nfo").read_text(encoding="utf-8"), "sidecar")
            self.assertEqual(client.downloaded[0][0], "sidecar-pick")

    def test_strm_generator_does_not_download_sidecars_when_disabled(self):
        with TemporaryDirectory() as directory:
            client = FakeStrmClient()
            result = StrmGenerator(
                client,
                FakeStore(),
                "http://mp:3000",
                "api-token",
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
                "api-token",
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

    def test_strm_generator_rejects_same_stem_output_collisions(self):
        class ConflictingMediaClient:
            @staticmethod
            def iter_files(_cid):
                return iter(
                    [
                        {"name": "Film.mkv", "pickcode": "first", "size": 1, "rel_path": "Film.mkv"},
                        {"name": "Film.mp4", "pickcode": "second", "size": 2, "rel_path": "Film.mp4"},
                    ]
                )

        with TemporaryDirectory() as directory:
            result = StrmGenerator(
                ConflictingMediaClient(),
                FakeStore(),
                "http://mp:3000",
                "api-token",
                incremental=False,
            ).run_mapping({"id": "movies", "source_cid": "root", "target_dir": directory})

            self.assertEqual(result["added"], 1)
            self.assertEqual(result["errors"], 1)
            self.assertIn("pickcode=first", (Path(directory) / "Film.strm").read_text(encoding="utf-8"))

    def test_strm_generator_persists_completed_writes_when_scan_fails(self):
        class InterruptedScanClient:
            @staticmethod
            def iter_files(_cid):
                yield {"name": "Film.mkv", "pickcode": "pick", "size": 1, "rel_path": "Film.mkv"}
                raise RuntimeError("remote scan failed")

        with TemporaryDirectory() as directory:
            store = FakeStore()
            generator = StrmGenerator(
                InterruptedScanClient(),
                store,
                "http://mp:3000",
                "api-token",
                incremental=True,
            )

            with self.assertRaisesRegex(RuntimeError, "remote scan failed"):
                generator.run_mapping(
                    {"id": "movies", "source_cid": "root", "target_dir": directory}
                )

            self.assertTrue((Path(directory) / "Film.strm").is_file())
            self.assertIn("movies:Film.mkv", store.strm_records)

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

            result = DirectoryUploader(
                StrmUploadClient(),
                FakeStore(),
                config,
                "https://moviepilot.example",
                "api-token",
            ).run(incremental=True)

            generated = output / "Movies" / "Film.strm"
            self.assertEqual(result["strm_generated"], 1)
            self.assertEqual(result["strm_errors"], 0)
            self.assertEqual(
                generated.read_text(encoding="utf-8"),
                "https://moviepilot.example/api/v1/plugin/P115LiteAssistant/redirect"
                "?pickcode=abcdefghijklmnopq&apikey=api-token\n",
            )

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
                "api-token",
            )

            with self.assertRaisesRegex(ValueError, "未配置输出目录"):
                uploader.run(incremental=True)

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
                "api-token",
            ).run(incremental=True)

            self.assertEqual(result["strm_generated"], 1)
            self.assertEqual(client.item_checks, 1)
            sleeper.assert_called_once_with(5)

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
                metadata={"pickcode": "abcdefghijklmnopq"},
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
                "api-token",
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
                        "pick_code": "abcdefghijklmnopq",
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
                    "api-token",
                ).run(incremental=True)

            record = store.upload_records.to_dict()[str(movie)]
            self.assertEqual(result["strm_generated"], 1)
            self.assertEqual(result["strm_errors"], 0)
            self.assertEqual(client.uploaded, [])
            self.assertEqual(record["pickcode"], "abcdefghijklmnopq")
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
                        "pick_code": "abcdefghijklmnopq",
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
                "api-token",
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
                "api-token",
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
                metadata={"pickcode": "abcdefghijklmnopq"},
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
                "api-token",
            ).run(incremental=True)

            self.assertEqual(result["strm_errors"], 1)
            self.assertEqual(client.uploaded, [])
            self.assertTrue(movie.is_file())
            self.assertFalse((output / "Film.strm").exists())
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
                "api-token",
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
                "api-token",
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
                "api-token",
            ).run(incremental=True)
            second = DirectoryUploader(
                client,
                store,
                config,
                "https://moviepilot.example",
                "api-token",
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
