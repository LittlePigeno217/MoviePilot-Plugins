from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import Request
from plugins.p115liteassistant.api import Api
from plugins.p115liteassistant.client import UploadResult
from plugins.p115liteassistant.records import IncrementalRecordStore
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
    def iter_files(self, cid):
        assert cid == "115-root"
        return iter(
            [
                {"name": "Film.mkv", "pickcode": "pick", "size": 10, "rel_path": "Movies/Film.mkv"},
                {"name": "readme.txt", "pickcode": "ignored", "size": 1, "rel_path": "readme.txt"},
            ]
        )


class FakeUploadClient:
    def __init__(self):
        self.uploaded = []

    def ensure_remote_dir(self, path):
        return {"fileid": "1", "path": path}

    def upload_file(self, target, local_path):
        self.uploaded.append((target["path"], Path(local_path).name))
        return UploadResult(success=True, reused=Path(local_path).suffix == ".mkv")


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

            changed = StrmGenerator(FakeStrmClient(), store, "https://media.example/", "api-token", incremental=True)
            changed_result = changed.run_mapping(
                {"id": "movies", "source_cid": "115-root", "source_path": "/Movies", "target_dir": str(target)}
            )
            self.assertEqual(changed_result["updated"], 1)
            self.assertEqual(
                generated.read_text(encoding="utf-8"),
                "https://media.example/api/v1/plugin/P115LiteAssistant/redirect?pickcode=pick&apikey=api-token\n",
            )

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

            first = DirectoryUploader(client, store, config).run(incremental=True)
            second = DirectoryUploader(client, store, config).run(incremental=True)

            self.assertEqual(first["instant"], 1)
            self.assertEqual(first["uploaded"], 1)
            self.assertEqual(first["errors"], 0)
            self.assertEqual(client.uploaded, [("/Cloud/Movies", "Film.mkv"), ("/Cloud/Movies", "Film.nfo")])
            self.assertEqual(second["skipped"], 2)
            self.assertTrue(store.upload_records.has_changed(source / "Film.mkv", "/Cloud/New/Film.mkv"))

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

            result = DirectoryUploader(FailingSidecarUploadClient(), FakeStore(), config).run(incremental=True)

            self.assertEqual(result["deleted"], 0)
            self.assertEqual(result["errors"], 1)
            self.assertTrue(movie.exists())
            self.assertTrue(sidecar.exists())

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
