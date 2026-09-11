from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.plugins.p115liteassistant import P115LiteAssistant
from app.plugins.p115liteassistant.api import Api as ProductionApi


from tests.p115liteassistant.helpers import make_test_journal


def Api(client_provider, store, *args, journal=None, **kwargs):
    return ProductionApi(
        client_provider, store, *args,
        journal=journal or make_test_journal(store), **kwargs
    )


class FakeStore:
    def __init__(self, config=None):
        self.config = dict(config or {})
        self.update_calls = []
        self.strm_records = {}
        self.history = []

    def get_config(self):
        return dict(self.config)

    def update_config(self, updates):
        self.update_calls.append(dict(updates))
        self.config.update(dict(updates))
        return dict(self.config)

    def get_strm_records(self):
        return dict(self.strm_records)

    def save_strm_records(self, records):
        self.strm_records = dict(records)

    def get_upload_records(self):
        return {}

    def save_upload_records(self, records):
        pass

    def append_history(self, entry):
        self.history.append(dict(entry))


class LocalPathBoundaryTest(unittest.TestCase):
    def build_api(self, config=None):
        store = FakeStore(config)
        return Api(lambda: object(), store), store

    @staticmethod
    def build_plugin(config):
        store = FakeStore(config)
        plugin = object.__new__(P115LiteAssistant)
        plugin._store = store
        plugin._api = Api(lambda: object(), store)
        plugin._client = None
        plugin._client_signature = None
        plugin._strm_journal = Mock()
        plugin._strm_journal.recover_all.return_value = []
        plugin._strm_recovery_alerted = False
        plugin._sync_life_monitor = Mock()
        plugin._sync_strm_watch = Mock()
        plugin._sync_upload_watch = Mock()
        return plugin, store

    def test_init_plugin_migrates_enabled_legacy_mapping_before_services_start(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            plugin, store = self.build_plugin(
                {
                    "enabled": True,
                    "local_path_allowlist": [],
                    "upload_mappings": [
                        {"source": str(source), "target": "/115", "enabled": True}
                    ],
                }
            )
            order = []
            migrate = plugin._api.migrate_legacy_allowlist

            def migrate_before_services():
                order.append("migrate")
                return migrate()

            plugin._api.migrate_legacy_allowlist = Mock(side_effect=migrate_before_services)
            plugin._sync_life_monitor.side_effect = lambda: order.append("life")
            plugin._sync_strm_watch.side_effect = lambda: order.append("strm")
            plugin._sync_upload_watch.side_effect = lambda: order.append("upload")

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                plugin.init_plugin()

            self.assertEqual(store.config["local_path_allowlist"], [str(source.resolve())])
            self.assertEqual(plugin._api._authorized_local_path(source), source.resolve())
            self.assertEqual(order, ["migrate", "life", "strm", "upload"])
            plugin._sync_life_monitor.assert_called_once_with()
            plugin._sync_strm_watch.assert_called_once_with()
            plugin._sync_upload_watch.assert_called_once_with()

    def test_init_plugin_legacy_migration_is_idempotent(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            plugin, store = self.build_plugin(
                {"upload_mappings": [{"source": str(source), "target": "/115"}]}
            )

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                plugin.init_plugin()
                plugin.init_plugin()

            self.assertEqual(store.update_calls, [{"local_path_allowlist": [str(source.resolve())]}])

    def test_init_plugin_does_not_replace_existing_allowlist(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            allowed = base / "allowed"
            source = base / "source"
            allowed.mkdir()
            source.mkdir()
            plugin, store = self.build_plugin(
                {
                    "local_path_allowlist": [str(allowed)],
                    "upload_mappings": [{"source": str(source), "target": "/115"}],
                }
            )

            plugin.init_plugin()

            self.assertEqual(store.config["local_path_allowlist"], [str(allowed)])
            self.assertEqual(store.update_calls, [])

    def test_init_plugin_logs_failed_migration_and_starts_services_fail_closed(self):
        with TemporaryDirectory() as temp:
            missing = Path(temp) / "missing"
            plugin, store = self.build_plugin(
                {
                    "local_path_allowlist": [],
                    "upload_mappings": [{"source": str(missing), "target": "/115"}],
                }
            )

            with (
                patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]),
                patch("app.plugins.p115liteassistant.logger.error") as log_error,
            ):
                plugin.init_plugin()

            self.assertEqual(store.config["local_path_allowlist"], [])
            self.assertIsNone(plugin._api._authorized_local_path(missing))
            log_error.assert_called_once()
            self.assertIn("启动迁移 allowlist 失败", log_error.call_args.args[0])
            plugin._sync_upload_watch.assert_called_once_with()

    def test_init_plugin_ignores_disabled_legacy_mapping(self):
        with TemporaryDirectory() as temp:
            missing = Path(temp) / "missing"
            plugin, store = self.build_plugin(
                {
                    "local_path_allowlist": [],
                    "upload_mappings": [
                        {"source": str(missing), "target": "/115", "enabled": False}
                    ],
                }
            )

            plugin.init_plugin()

            self.assertEqual(store.config["local_path_allowlist"], [])
            self.assertEqual(store.update_calls, [])
            plugin._sync_upload_watch.assert_called_once_with()

    def test_init_plugin_merges_startup_config_before_migration(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            plugin, store = self.build_plugin(
                {"local_path_allowlist": [], "upload_mappings": []}
            )
            startup_config = {
                "upload_mappings": [{"source": str(source), "target": "/115"}]
            }

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                plugin.init_plugin(startup_config)

            self.assertEqual(
                store.update_calls,
                [startup_config, {"local_path_allowlist": [str(source.resolve())]}],
            )

    def test_config_save_restarts_upload_watch_only_when_mapping_changes(self):
        plugin, store = self.build_plugin(
            {
                "enabled": True,
                "upload_mappings": [
                    {"id": "movies", "source": "/media/movies", "enabled": True}
                ],
            }
        )
        plugin._upload_watch_signature = plugin._upload_watch_config_signature(
            store.get_config()
        )

        plugin._on_config_saved()
        plugin._sync_upload_watch.assert_not_called()

        store.config["upload_mappings"] = [
            {"id": "movies", "source": "/media/movies-2", "enabled": True}
        ]
        plugin._on_config_saved()
        plugin._sync_upload_watch.assert_called_once_with()

    def test_local_roots_use_host_directories_and_explicit_allowlist_but_never_root(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            download = base / "downloads"
            library = base / "library"
            extra = base / "extra"
            remote = base / "remote"
            for path in (download, library, extra, remote):
                path.mkdir()
            api, _store = self.build_api({"local_path_allowlist": [str(extra)]})
            directories = [
                SimpleNamespace(
                    storage="local",
                    download_path=str(download),
                    library_storage="local",
                    library_path=str(library),
                ),
                SimpleNamespace(
                    storage="u115",
                    download_path=str(remote),
                    library_storage="u115",
                    library_path=str(remote),
                ),
            ]

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=directories):
                roots = api._local_roots()

            self.assertEqual(roots, [download.resolve(), library.resolve(), extra.resolve()])
            self.assertNotIn(Path("/"), roots)

    def test_save_config_rejects_filesystem_root_in_explicit_allowlist(self):
        api, _store = self.build_api()

        with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
            result = api.save_config({"local_path_allowlist": ["/"]})

        self.assertFalse(result["success"])
        self.assertIn("allowlist", result["message"])

    def test_save_config_rejects_non_path_allowlist_entries(self):
        api, _store = self.build_api()

        with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
            result = api.save_config({"local_path_allowlist": [{"path": "/media"}]})

        self.assertFalse(result["success"])
        self.assertIn("allowlist", result["message"])

    def test_save_config_rejects_mapping_paths_outside_allowlist(self):
        with TemporaryDirectory() as temp:
            allowed = Path(temp) / "allowed"
            outside = Path(temp) / "outside"
            allowed.mkdir()
            outside.mkdir()
            api, store = self.build_api({"local_path_allowlist": [str(allowed)]})

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                refused = api.save_config(
                    {"strm_mappings": [{"target_dir": str(outside), "source_cid": "1"}]}
                )
                accepted = api.save_config(
                    {
                        "strm_mappings": [
                            {"target_dir": str(allowed / "strm"), "source_cid": "1"}
                        ],
                        "upload_mappings": [
                            {
                                "source": str(allowed / "source"),
                                "target": "/115",
                                "strm_target": str(allowed / "strm"),
                            }
                        ],
                    }
                )

            self.assertFalse(refused["success"])
            self.assertIn("allowlist", refused["message"])
            self.assertTrue(accepted["success"])
            self.assertEqual(store.config["strm_mappings"][0]["target_dir"], str(allowed / "strm"))

    def test_save_config_accepts_host_roots_and_does_not_persist_a_rejected_update(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            host_root = base / "media"
            outside = base / "outside"
            host_root.mkdir()
            outside.mkdir()
            original = [{"target_dir": str(host_root / "old"), "source_cid": "1"}]
            api, store = self.build_api({"strm_mappings": original})
            directories = [
                SimpleNamespace(
                    storage="local",
                    download_path=str(host_root),
                    library_storage="local",
                    library_path=str(host_root),
                )
            ]

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=directories):
                accepted = api.save_config(
                    {"strm_mappings": [{"target_dir": str(host_root / "new"), "source_cid": "1"}]}
                )
                refused = api.save_config(
                    {"strm_mappings": [{"target_dir": str(outside), "source_cid": "1"}]}
                )

            self.assertTrue(accepted["success"])
            self.assertFalse(refused["success"])
            self.assertEqual(store.config["strm_mappings"][0]["target_dir"], str(host_root / "new"))

    def test_save_config_resolves_symlinks_before_allowlist_check(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            allowed = base / "allowed"
            outside = base / "outside"
            allowed.mkdir()
            outside.mkdir()
            (allowed / "escape").symlink_to(outside, target_is_directory=True)
            api, _store = self.build_api({"local_path_allowlist": [str(allowed)]})

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                result = api.save_config(
                    {"upload_mappings": [{"source": str(allowed / "escape"), "target": "/115"}]}
                )

            self.assertFalse(result["success"])
            self.assertIn("allowlist", result["message"])

    def test_save_config_migrates_exact_legacy_mapping_directories_once(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            strm = base / "media" / "Strm"
            source = base / "media" / "link - other"
            generated = base / "generated"
            narrow_host_root = source / "library"
            for path in (strm, narrow_host_root, generated):
                path.mkdir(parents=True)
            config = {
                "local_path_allowlist": [],
                "strm_mappings": [{"target_dir": str(strm), "source_cid": "1"}],
                "upload_mappings": [
                    {
                        "source": str(source),
                        "target": "/115",
                        "strm_target": str(generated),
                    },
                    {"source": str(source), "target": "/backup"},
                ],
            }
            api, store = self.build_api(config)
            directories = [
                SimpleNamespace(
                    storage="local",
                    download_path=str(narrow_host_root),
                    library_storage="local",
                    library_path=str(narrow_host_root),
                )
            ]

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=directories):
                result = api.save_config({"checkin_enabled": True})

            self.assertTrue(result["success"])
            self.assertEqual(
                store.config["local_path_allowlist"],
                [str(strm.resolve()), str(source.resolve()), str(generated.resolve())],
            )
            self.assertNotIn(str((base / "media").resolve()), store.config["local_path_allowlist"])
            self.assertNotIn("/", store.config["local_path_allowlist"])

    def test_full_config_save_with_empty_allowlist_migrates_enabled_legacy_mappings(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            mapping = {
                "source": str(source),
                "target": "/115",
                "enabled": True,
            }
            config = {
                "enabled": True,
                "local_path_allowlist": [],
                "strm_mappings": [],
                "upload_mappings": [mapping],
            }
            api, store = self.build_api(config)

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                result = api.save_config(dict(config))

            self.assertTrue(result["success"])
            self.assertEqual(store.config["local_path_allowlist"], [str(source.resolve())])

    def test_migrated_paths_authorize_upload_execution(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "source"
            generated = base / "generated"
            source.mkdir()
            generated.mkdir()
            api, store = self.build_api(
                {
                    "local_path_allowlist": [],
                    "upload_generate_strm": True,
                    "upload_mappings": [
                        {
                            "source": str(source),
                            "target": "/115",
                            "strm_target": str(generated),
                            "enabled": True,
                        }
                    ],
                }
            )

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                saved = api.save_config({"checkin_enabled": True})
                self.assertTrue(saved["success"])
                self.assertEqual(api._authorized_local_path(source), source.resolve())
                self.assertEqual(api._authorized_local_path(generated), generated.resolve())
                with patch("app.plugins.p115liteassistant.api.DirectoryUploader") as uploader:
                    uploader.return_value.run.return_value = {"kind": "upload", "errors": 0}
                    result = api.run_upload()

            self.assertEqual(result["errors"], 0)
            uploader.assert_called_once()
            execution_mapping = uploader.call_args.args[2]["upload_mappings"][0]
            self.assertEqual(execution_mapping["source"], str(source.resolve()))
            self.assertEqual(execution_mapping["strm_target"], str(generated.resolve()))
            self.assertEqual(
                store.config["local_path_allowlist"],
                [str(source.resolve()), str(generated.resolve())],
            )

    def test_legacy_migration_does_not_authorize_ancestors_or_siblings(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "media" / "source"
            sibling = base / "media" / "sibling"
            source.mkdir(parents=True)
            sibling.mkdir()
            api, store = self.build_api(
                {"upload_mappings": [{"source": str(source), "target": "/115"}]}
            )

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                result = api.save_config({"checkin_enabled": True})
                parent = api._authorized_local_path(source.parent)
                unrelated = api._authorized_local_path(sibling)
                etc = api._authorized_local_path("/etc")

            self.assertTrue(result["success"])
            self.assertEqual(store.config["local_path_allowlist"], [str(source.resolve())])
            self.assertIsNone(parent)
            self.assertIsNone(unrelated)
            self.assertIsNone(etc)

    def test_legacy_migration_rejects_new_external_mapping_without_updating_store(self):
        with TemporaryDirectory() as temp:
            old_source = Path(temp) / "old"
            new_source = Path(temp) / "new"
            old_source.mkdir()
            new_source.mkdir()
            original = [{"source": str(old_source), "target": "/115"}]
            api, store = self.build_api({"upload_mappings": original})

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                result = api.save_config(
                    {
                        "checkin_enabled": True,
                        "upload_mappings": [
                            *original,
                            {"source": str(new_source), "target": "/new"},
                        ],
                    }
                )

            self.assertFalse(result["success"])
            self.assertIn("allowlist", result["message"])
            self.assertEqual(store.config, {"upload_mappings": original})

    def test_legacy_migration_rejects_invalid_candidates_without_updating_store(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            missing = base / "missing"
            file_path = base / "file.mkv"
            file_path.write_bytes(b"test")
            cases = (str(missing), str(file_path), "relative/path", "/")

            for value in cases:
                with self.subTest(value=value):
                    config = {
                        "upload_mappings": [{"source": value, "target": "/115"}]
                    }
                    api, store = self.build_api(config)
                    with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                        result = api.save_config({"checkin_enabled": True})

                    self.assertFalse(result["success"])
                    self.assertIn("无法迁移 allowlist", result["message"])
                    self.assertEqual(store.config, config)

    def test_legacy_migration_persists_symlink_target_and_retarget_does_not_expand(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            real = base / "real"
            redirected = base / "redirected"
            alias = base / "alias"
            real.mkdir()
            redirected.mkdir()
            alias.symlink_to(real, target_is_directory=True)
            api, store = self.build_api(
                {"upload_mappings": [{"source": str(alias), "target": "/115"}]}
            )

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                result = api.save_config({"checkin_enabled": True})
                self.assertTrue(result["success"])
                self.assertEqual(store.config["local_path_allowlist"], [str(real.resolve())])
                alias.unlink()
                alias.symlink_to(redirected, target_is_directory=True)
                self.assertIsNone(api._authorized_local_path(alias))
                self.assertEqual(api._authorized_local_path(real), real.resolve())

    def test_nonempty_allowlist_does_not_remigrate_new_mapping(self):
        with TemporaryDirectory() as temp:
            old_source = Path(temp) / "old"
            new_source = Path(temp) / "new"
            old_source.mkdir()
            new_source.mkdir()
            original = [{"source": str(old_source), "target": "/115"}]
            api, store = self.build_api(
                {
                    "local_path_allowlist": [str(old_source)],
                    "upload_mappings": original,
                }
            )

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                result = api.save_config(
                    {"upload_mappings": [{"source": str(new_source), "target": "/new"}]}
                )

            self.assertFalse(result["success"])
            self.assertEqual(store.config["local_path_allowlist"], [str(old_source)])
            self.assertEqual(store.config["upload_mappings"], original)

    def test_nonempty_allowlist_does_not_remigrate_on_unrelated_save(self):
        with TemporaryDirectory() as temp:
            old_source = Path(temp) / "old"
            new_source = Path(temp) / "new"
            old_source.mkdir()
            new_source.mkdir()
            config = {
                "local_path_allowlist": [str(old_source)],
                "upload_mappings": [{"source": str(new_source), "target": "/115"}],
            }
            api, store = self.build_api(config)

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                result = api.save_config({"checkin_enabled": True})

            self.assertTrue(result["success"])
            self.assertEqual(store.config["local_path_allowlist"], [str(old_source)])
            self.assertTrue(store.config["checkin_enabled"])

    def test_explicit_empty_allowlist_does_not_trigger_legacy_migration(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            config = {"upload_mappings": [{"source": str(source), "target": "/115"}]}
            api, store = self.build_api(config)

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                result = api.save_config({"local_path_allowlist": []})

            self.assertFalse(result["success"])
            self.assertIn("allowlist", result["message"])
            self.assertEqual(store.config, config)

    def test_clearing_nonempty_allowlist_in_full_config_does_not_remigrate(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            mapping = {
                "source": str(source),
                "target": "/115",
                "enabled": True,
            }
            config = {
                "enabled": True,
                "local_path_allowlist": [str(source)],
                "strm_mappings": [],
                "upload_mappings": [mapping],
            }
            api, store = self.build_api(config)
            payload = {**config, "local_path_allowlist": []}

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                result = api.save_config(payload)

            self.assertFalse(result["success"])
            self.assertIn("allowlist", result["message"])
            self.assertEqual(store.config, config)

    def test_legacy_migration_skips_disabled_missing_mapping(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "source"
            missing = base / "missing"
            source.mkdir()
            enabled_mapping = {
                "source": str(source),
                "target": "/115",
                "enabled": True,
            }
            disabled_mapping = {
                "source": str(missing),
                "target": "/disabled",
                "enabled": False,
            }
            config = {
                "enabled": True,
                "local_path_allowlist": [],
                "strm_mappings": [],
                "upload_mappings": [enabled_mapping, disabled_mapping],
            }
            api, store = self.build_api(config)

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                result = api.save_config(dict(config))

            self.assertTrue(result["success"])
            self.assertEqual(store.config["local_path_allowlist"], [str(source.resolve())])
            self.assertEqual(store.config["upload_mappings"], config["upload_mappings"])

    def test_disabled_only_legacy_mappings_do_not_trigger_migration_or_block_save(self):
        with TemporaryDirectory() as temp:
            missing = Path(temp) / "missing"
            mapping = {
                "source": str(missing),
                "target": "/115",
                "enabled": False,
            }
            config = {
                "local_path_allowlist": [],
                "upload_mappings": [mapping],
            }
            api, store = self.build_api(config)

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                result = api.save_config({"checkin_enabled": True})

            self.assertTrue(result["success"])
            self.assertEqual(store.config["local_path_allowlist"], [])
            self.assertEqual(store.config["upload_mappings"], [mapping])
            self.assertTrue(store.config["checkin_enabled"])

    def test_reenabling_missing_or_unauthorized_mapping_fails_closed(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            allowed = base / "allowed"
            missing = base / "missing"
            allowed.mkdir()
            disabled_mapping = {
                "source": str(missing),
                "target": "/115",
                "enabled": False,
            }
            config = {
                "local_path_allowlist": [str(allowed)],
                "upload_mappings": [disabled_mapping],
            }
            api, store = self.build_api(config)
            enabled_mapping = {**disabled_mapping, "enabled": True}

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                result = api.save_config({"upload_mappings": [enabled_mapping]})

            self.assertFalse(result["success"])
            self.assertIn("allowlist", result["message"])
            self.assertEqual(store.config, config)

    def test_legacy_migration_keeps_mount_path_views_independent(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            media_view = base / "media" / "Strm"
            mount_view = base / "strm"
            media_view.mkdir(parents=True)
            mount_view.mkdir()
            api, store = self.build_api(
                {"strm_mappings": [{"target_dir": str(media_view), "source_cid": "1"}]}
            )

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                migrated = api.save_config({"checkin_enabled": True})
                self.assertTrue(migrated["success"])
                self.assertEqual(api._authorized_local_path(media_view), media_view.resolve())
                self.assertIsNone(api._authorized_local_path(mount_view))
                explicit = api.save_config(
                    {"local_path_allowlist": [str(media_view), str(mount_view)]}
                )
                self.assertTrue(explicit["success"])
                self.assertEqual(api._authorized_local_path(mount_view), mount_view.resolve())

            self.assertEqual(
                store.config["local_path_allowlist"],
                [str(media_view.resolve()), str(mount_view.resolve())],
            )

    def test_saved_allowlist_root_replaced_by_symlink_rejects(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            allowed = base / "allowed"
            alias = base / "allowed-alias"
            redirected = base / "redirected"
            allowed.mkdir()
            redirected.mkdir()
            alias.symlink_to(allowed, target_is_directory=True)
            api, store = self.build_api({"upload_media_extensions": ".mkv"})

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                saved = api.save_config(
                    {
                        "local_path_allowlist": [str(alias)],
                        "strm_mappings": [
                            {"target_dir": str(allowed), "source_cid": "1"}
                        ],
                        "upload_mappings": [
                            {"source": str(allowed), "target": "/115"}
                        ],
                    }
                )

                self.assertTrue(saved["success"])
                self.assertEqual(store.config["local_path_allowlist"], [str(allowed.resolve())])

                alias.unlink()
                allowed.rmdir()
                allowed.symlink_to(redirected, target_is_directory=True)
                redirected_strm = redirected / "redirected.strm"
                redirected_media = redirected / "redirected.mkv"
                redirected_strm.write_text("https://example.invalid/file", encoding="utf-8")
                redirected_media.write_bytes(b"test")
                store.strm_records = {
                    "redirected": {"path": str(redirected_strm)}
                }

                self.assertEqual(api._local_roots(), [allowed])
                browse = api.browse_local()
                library = api.library_drop({"paths": [str(redirected_strm)]})
                source = api.source_drop({"paths": [str(redirected_media)]})

            self.assertEqual(browse, {"error": "目录超出 MoviePilot 根目录"})
            self.assertEqual(library["data"], {"removed": 0, "dropped": 0, "refused": 1})
            self.assertEqual(source["data"]["removed"], 0)
            self.assertEqual(source["data"]["refused"], 1)
            self.assertTrue(redirected_strm.exists())
            self.assertTrue(redirected_media.exists())

    def test_host_root_retarget_does_not_expand_authorization(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            host_root = base / "host"
            redirected = base / "redirected"
            host_root.mkdir()
            redirected.mkdir()
            api, _store = self.build_api()
            directories = [
                SimpleNamespace(
                    storage="local",
                    download_path=str(host_root),
                    library_storage="local",
                    library_path=str(host_root),
                )
            ]

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=directories):
                self.assertEqual(api._local_roots(), [host_root.resolve()])
                host_root.rmdir()
                host_root.symlink_to(redirected, target_is_directory=True)
                self.assertEqual(api._local_roots(), [])
                self.assertIsNone(api._authorized_local_path(redirected))

    def test_task_strm_once_rejects_target_outside_allowlist(self):
        with TemporaryDirectory() as temp:
            allowed = Path(temp) / "allowed"
            outside = Path(temp) / "outside"
            allowed.mkdir()
            outside.mkdir()
            api, _store = self.build_api({"local_path_allowlist": [str(allowed)]})

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]), patch.object(
                api, "_start"
            ) as start:
                result = api.task_strm_once(
                    {"source_cid": "1", "target_dir": str(outside)}
                )

            self.assertFalse(result["success"])
            self.assertIn("allowlist", result["message"])
            start.assert_not_called()

    def test_task_upload_once_rejects_source_outside_allowlist(self):
        with TemporaryDirectory() as temp:
            allowed = Path(temp) / "allowed"
            outside = Path(temp) / "outside"
            allowed.mkdir()
            outside.mkdir()
            api, _store = self.build_api({"local_path_allowlist": [str(allowed)]})

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]), patch.object(
                api, "_start"
            ) as start:
                result = api.task_upload_once({"source": str(outside), "target": "/115"})

            self.assertFalse(result["success"])
            self.assertIn("allowlist", result["message"])
            start.assert_not_called()

    def test_task_upload_once_rejects_unauthorized_strm_target(self):
        with TemporaryDirectory() as temp:
            allowed = Path(temp) / "allowed"
            source = allowed / "source"
            outside = Path(temp) / "outside"
            source.mkdir(parents=True)
            outside.mkdir()
            api, _store = self.build_api(
                {
                    "local_path_allowlist": [str(allowed)],
                    "upload_generate_strm": True,
                }
            )

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]), patch.object(
                api, "_start"
            ) as start:
                result = api.task_upload_once(
                    {
                        "source": str(source),
                        "target": "/115",
                        "strm_target": str(outside),
                    }
                )

            self.assertFalse(result["success"])
            self.assertIn("allowlist", result["message"])
            start.assert_not_called()

    def test_task_upload_once_requires_strm_target_when_generation_enabled(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            api, _store = self.build_api(
                {
                    "local_path_allowlist": [str(source)],
                    "upload_generate_strm": True,
                }
            )

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]), patch.object(
                api, "_start"
            ) as start:
                result = api.task_upload_once({"source": str(source), "target": "/115"})

            self.assertFalse(result["success"])
            self.assertIn("STRM 输出目录", result["message"])
            start.assert_not_called()

    def test_task_once_authorizes_valid_paths_before_starting(self):
        with TemporaryDirectory() as temp:
            allowed = Path(temp) / "allowed"
            source = allowed / "source"
            output = allowed / "output"
            source.mkdir(parents=True)
            output.mkdir()
            api, _store = self.build_api(
                {
                    "local_path_allowlist": [str(allowed)],
                    "moviepilot_address": "http://moviepilot:3000",
                }
            )

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]), patch.object(
                api, "_start", return_value={"success": True}
            ) as start:
                strm_result = api.task_strm_once(
                    {"source_cid": "1", "target_dir": str(output)}
                )
                upload_result = api.task_upload_once(
                    {"source": str(source), "target": "/115"}
                )

            self.assertTrue(strm_result["success"])
            self.assertTrue(upload_result["success"])
            self.assertEqual(start.call_count, 2)

    def test_browse_local_refuses_parent_traversal(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            allowed = base / "allowed"
            outside = base / "outside"
            allowed.mkdir()
            outside.mkdir()
            api, _store = self.build_api({"local_path_allowlist": [str(allowed)]})

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                result = api.browse_local("../outside")

            self.assertEqual(result, {"error": "目录超出 MoviePilot 根目录"})

    def test_browse_local_refuses_invalid_requested_root(self):
        with TemporaryDirectory() as temp:
            allowed = Path(temp) / "allowed"
            allowed.mkdir()
            api, _store = self.build_api({"local_path_allowlist": [str(allowed)]})

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]):
                result = api.browse_local(root="relative/path")

            self.assertEqual(result, {"error": "本地目录根路径无效"})

    def test_drop_endpoints_require_mapping_and_global_allowlist(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            allowed = base / "allowed"
            outside = base / "outside"
            allowed.mkdir()
            outside.mkdir()
            inside_strm = allowed / "inside.strm"
            outside_strm = outside / "outside.strm"
            inside_media = allowed / "inside.mkv"
            outside_media = outside / "outside.mkv"
            for path in (inside_strm, outside_strm, inside_media, outside_media):
                path.write_bytes(b"test")
            api, store = self.build_api(
                {
                    "local_path_allowlist": [str(base)],
                    "strm_mappings": [{"target_dir": str(base)}],
                    "upload_mappings": [{"source": str(base)}],
                    "upload_media_extensions": ".mkv",
                }
            )
            store.strm_records = {
                "inside": {"path": str(inside_strm), "owner_id": "default"},
                "outside": {"path": str(outside_strm), "owner_id": "default"},
            }

            with patch.object(api, "_local_roots", return_value=[allowed.resolve()]):
                library = api.library_drop({"paths": [str(inside_strm), str(outside_strm)]})
                source = api.source_drop({"paths": [str(inside_media), str(outside_media)]})

            self.assertEqual(library["data"], {"removed": 1, "dropped": 1, "refused": 1})
            self.assertEqual(source["data"]["removed"], 1)
            self.assertEqual(source["data"]["refused"], 1)
            self.assertFalse(inside_strm.exists())
            self.assertTrue(outside_strm.exists())
            self.assertFalse(inside_media.exists())
            self.assertTrue(outside_media.exists())

    def test_library_drop_reloads_claims_inside_cloud_lock_and_is_idempotent(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "Film.strm"
            target.write_text("https://example.invalid/file", encoding="utf-8")
            api, store = self.build_api({
                "local_path_allowlist": [str(root)],
                "strm_mappings": [{"id": "movies", "target_dir": str(root)}],
            })
            fresh = {"path": str(target), "owner_id": "movies", "version": 2}
            store.strm_records = {"movies:Film.mkv": dict(fresh)}
            original_get = store.get_strm_records
            observed = []

            def locked_get():
                observed.append(api._cloud_task_lock.locked())
                return original_get()

            store.get_strm_records = locked_get
            with patch.object(api, "_local_roots", return_value=[root.resolve()]):
                first = api.library_drop({"paths": [str(target)]})
                second = api.library_drop({"paths": [str(target)]})

            self.assertTrue(first["success"])
            self.assertEqual(first["data"], {"removed": 1, "dropped": 1, "refused": 0})
            self.assertTrue(second["success"])
            self.assertEqual(second["data"], {"removed": 0, "dropped": 0, "refused": 1})
            self.assertGreaterEqual(len(observed), 2)
            self.assertTrue(all(observed))
            self.assertEqual(store.strm_records, {})
            self.assertFalse(target.exists())
            self.assertFalse(api._cloud_task_lock.locked())

    def test_library_drop_busy_keeps_manual_response_shape_and_state(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "Film.strm"
            target.write_text("https://example.invalid/file", encoding="utf-8")
            api, store = self.build_api({
                "local_path_allowlist": [str(root)],
                "strm_mappings": [{"id": "movies", "target_dir": str(root)}],
            })
            store.strm_records = {
                "movies:Film.mkv": {"path": str(target), "owner_id": "movies"}
            }
            api._cloud_task_lock.acquire()
            try:
                with patch.object(api, "_local_roots", return_value=[root.resolve()]):
                    result = api.library_drop({"paths": [str(target)]})
            finally:
                api._cloud_task_lock.release()

            self.assertEqual(set(result), {"success", "message", "data"})
            self.assertFalse(result["success"])
            self.assertEqual(result["data"], {})
            self.assertTrue(target.exists())
            self.assertIn("movies:Film.mkv", store.strm_records)

    def test_run_strm_rejects_legacy_mapping_outside_allowlist_before_generator(self):
        with TemporaryDirectory() as temp:
            allowed = Path(temp) / "allowed"
            outside = Path(temp) / "outside"
            allowed.mkdir()
            outside.mkdir()
            api, store = self.build_api(
                {
                    "local_path_allowlist": [str(allowed)],
                    "strm_mappings": [
                        {"source_cid": "1", "target_dir": str(outside), "enabled": True}
                    ],
                }
            )

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]), patch(
                "app.plugins.p115liteassistant.api.StrmGenerator"
            ) as generator:
                entries = api.run_strm("http://moviepilot:3000")

            self.assertEqual(entries[0]["errors"], 1)
            self.assertIn("allowlist", entries[0]["message"])
            generator.assert_not_called()
            self.assertEqual(len(store.history), 1)

    def test_run_strm_rejects_mapping_retargeted_after_config_save(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            allowed = base / "allowed"
            output = allowed / "output"
            outside = base / "outside"
            output.mkdir(parents=True)
            outside.mkdir()
            mapping = {"source_cid": "1", "target_dir": str(output), "enabled": True}
            api, store = self.build_api(
                {"local_path_allowlist": [str(allowed)], "strm_mappings": [mapping]}
            )
            output.rmdir()
            output.symlink_to(outside, target_is_directory=True)

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]), patch(
                "app.plugins.p115liteassistant.api.StrmGenerator"
            ) as generator:
                entries = api.run_strm("http://moviepilot:3000")

            self.assertEqual(entries[0]["errors"], 1)
            generator.assert_not_called()
            self.assertEqual(store.config["strm_mappings"], [mapping])

    def test_run_upload_rejects_legacy_source_outside_allowlist_before_uploader(self):
        with TemporaryDirectory() as temp:
            allowed = Path(temp) / "allowed"
            outside = Path(temp) / "outside"
            allowed.mkdir()
            outside.mkdir()
            api, _store = self.build_api(
                {
                    "local_path_allowlist": [str(allowed)],
                    "upload_mappings": [
                        {"source": str(outside), "target": "/115", "enabled": True}
                    ],
                }
            )

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]), patch(
                "app.plugins.p115liteassistant.api.DirectoryUploader"
            ) as uploader:
                entry = api.run_upload()

            self.assertEqual(entry["errors"], 1)
            self.assertIn("allowlist", entry["message"])
            uploader.assert_not_called()

    def test_run_upload_rejects_source_retargeted_after_config_save(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            allowed = base / "allowed"
            source = allowed / "source"
            outside = base / "outside"
            source.mkdir(parents=True)
            outside.mkdir()
            mapping = {"source": str(source), "target": "/115", "enabled": True}
            api, store = self.build_api(
                {"local_path_allowlist": [str(allowed)], "upload_mappings": [mapping]}
            )
            source.rmdir()
            source.symlink_to(outside, target_is_directory=True)

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]), patch(
                "app.plugins.p115liteassistant.api.DirectoryUploader"
            ) as uploader:
                entry = api.run_upload()

            self.assertEqual(entry["errors"], 1)
            uploader.assert_not_called()
            self.assertEqual(store.config["upload_mappings"], [mapping])

    def test_run_upload_rejects_unauthorized_strm_target_before_uploader(self):
        with TemporaryDirectory() as temp:
            allowed = Path(temp) / "allowed"
            source = allowed / "source"
            outside = Path(temp) / "outside"
            source.mkdir(parents=True)
            outside.mkdir()
            api, _store = self.build_api(
                {
                    "local_path_allowlist": [str(allowed)],
                    "upload_generate_strm": True,
                    "upload_mappings": [
                        {
                            "source": str(source),
                            "target": "/115",
                            "strm_target": str(outside),
                            "enabled": True,
                        }
                    ],
                }
            )

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]), patch(
                "app.plugins.p115liteassistant.api.DirectoryUploader"
            ) as uploader:
                entry = api.run_upload()

            self.assertEqual(entry["errors"], 1)
            self.assertIn("STRM 输出目录", entry["message"])
            uploader.assert_not_called()

    def test_run_upload_requires_strm_target_when_generation_enabled(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            api, _store = self.build_api(
                {
                    "local_path_allowlist": [str(source)],
                    "upload_generate_strm": True,
                    "upload_mappings": [
                        {"source": str(source), "target": "/115", "enabled": True}
                    ],
                }
            )

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]), patch(
                "app.plugins.p115liteassistant.api.DirectoryUploader"
            ) as uploader:
                entry = api.run_upload()

            self.assertEqual(entry["errors"], 1)
            self.assertIn("STRM 输出目录", entry["message"])
            uploader.assert_not_called()

    def test_run_tasks_fail_closed_without_any_local_roots(self):
        api, _store = self.build_api(
            {
                "strm_mappings": [
                    {"source_cid": "1", "target_dir": "/strm", "enabled": True}
                ],
                "upload_mappings": [
                    {"source": "/source", "target": "/115", "enabled": True}
                ],
            }
        )

        with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]), patch(
            "app.plugins.p115liteassistant.api.StrmGenerator"
        ) as generator, patch(
            "app.plugins.p115liteassistant.api.DirectoryUploader"
        ) as uploader:
            strm_entries = api.run_strm("http://moviepilot:3000")
            upload_entry = api.run_upload()

        self.assertEqual(strm_entries[0]["errors"], 1)
        self.assertEqual(upload_entry["errors"], 1)
        generator.assert_not_called()
        uploader.assert_not_called()

    def test_execution_authorization_does_not_persist_normalized_mappings(self):
        with TemporaryDirectory() as temp:
            allowed = Path(temp) / "allowed"
            source = allowed / "source"
            output = allowed / "output"
            source.mkdir(parents=True)
            output.mkdir()
            source_value = str(allowed / "missing" / ".." / "source")
            output_value = str(allowed / "missing" / ".." / "output")
            strm_mapping = {
                "source_cid": "1",
                "target_dir": output_value,
                "enabled": True,
            }
            upload_mapping = {
                "source": source_value,
                "target": "/115",
                "enabled": True,
            }
            api, store = self.build_api(
                {
                    "local_path_allowlist": [str(allowed)],
                    "strm_mappings": [strm_mapping],
                    "upload_mappings": [upload_mapping],
                }
            )

            with patch("app.helper.directory.DirectoryHelper.get_dirs", return_value=[]), patch(
                "app.plugins.p115liteassistant.api.StrmGenerator"
            ) as generator, patch(
                "app.plugins.p115liteassistant.api.DirectoryUploader"
            ) as uploader:
                generator.return_value.run_mapping.return_value = {
                    "kind": "strm",
                    "mapping": "1",
                    "errors": 0,
                }
                uploader.return_value.run.return_value = {
                    "kind": "upload",
                    "errors": 0,
                }
                api.run_strm("http://moviepilot:3000")
                api.run_upload()

            self.assertEqual(store.config["strm_mappings"], [strm_mapping])
            self.assertEqual(store.config["upload_mappings"], [upload_mapping])
            self.assertEqual(
                generator.return_value.run_mapping.call_args.args[0]["target_dir"],
                str(output.resolve()),
            )
            execution_config = uploader.call_args.args[2]
            self.assertEqual(
                execution_config["upload_mappings"][0]["source"],
                str(source.resolve()),
            )


if __name__ == "__main__":
    unittest.main()
