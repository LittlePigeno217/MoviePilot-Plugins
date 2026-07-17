from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from time import monotonic, sleep
from typing import Any, Dict, Iterator, Tuple

from app.log import logger

from .client import U115AuthError
from .file_types import DEFAULT_MEDIA_EXTENSIONS, DEFAULT_SIDECAR_EXTENSIONS, parse_extensions
from .log_utils import safe_error_text
from .resilience import retry_call
from .strm import (
    STRM_URL_FORMAT_VERSION,
    build_strm_content,
    normalize_pickcode,
    strm_file_matches,
    uploaded_strm_path,
    write_uploaded_strm,
)


class DirectoryUploader:
    def __init__(
        self,
        client,
        store,
        config: Dict[str, Any],
        moviepilot_url: str = "",
    ):
        self._client = client
        self._store = store
        self._config = config
        self._moviepilot_url = moviepilot_url.rstrip("/")
        self._generate_strm = bool(config.get("upload_generate_strm", False))
        self._redirect_secret = store.get_redirect_secret() if self._generate_strm else ""
        self._media_extensions = parse_extensions(
            config.get("upload_media_extensions", ""),
            DEFAULT_MEDIA_EXTENSIONS,
        )
        self._sidecar_extensions = parse_extensions(
            config.get("upload_sidecar_extensions", ""),
            DEFAULT_SIDECAR_EXTENSIONS,
        )

    def _iter_files(self) -> Iterator[Tuple[Path, str, str, Path, str]]:
        include_sidecars = bool(self._config.get("upload_include_sidecars", True))
        mappings: list[tuple[Path, PurePosixPath, str]] = []
        for mapping in self._config.get("upload_mappings", []):
            if not mapping.get("enabled", True):
                continue
            source_value = str(mapping.get("source") or "").strip()
            target_value = str(mapping.get("target") or "").strip().replace("\\", "/")
            if not source_value or not target_value:
                raise ValueError("启用的上传映射必须同时配置本地源目录和 115 目标目录")
            source = Path(source_value).expanduser().resolve()
            target = PurePosixPath(target_value)
            if not target.is_absolute() or ".." in target.parts:
                raise ValueError(f"115 目标目录无效: {target_value}")
            strm_target = str(mapping.get("strm_target") or "").strip()
            if not source.is_dir():
                raise FileNotFoundError(f"上传源目录不存在: {source}")
            if self._generate_strm and not strm_target:
                raise ValueError(f"目录上传已启用生成 STRM，但映射未配置输出目录: {source}")
            mappings.append((source, target, strm_target))

        for index, (source, _target, _strm_target) in enumerate(mappings):
            for other_source, _other_target, _other_strm_target in mappings[index + 1 :]:
                if (
                    source == other_source
                    or source in other_source.parents
                    or other_source in source.parents
                ):
                    raise ValueError(
                        "启用的上传源目录不能相同或互为父子目录: "
                        f"{source} <-> {other_source}"
                    )

        for source, target, strm_target in mappings:
            entries = sorted(source.rglob("*"))
            symlink = next((path for path in entries if path.is_symlink()), None)
            if symlink is not None:
                raise ValueError(f"上传源目录不允许包含符号链接: {symlink}")
            for local_path in (path for path in entries if path.is_file()):
                self._validate_source_file(local_path, source)
                extension = local_path.suffix.lower()
                kind = "media" if extension in self._media_extensions else "sidecar"
                if kind == "sidecar" and (not include_sidecars or extension not in self._sidecar_extensions):
                    continue
                if kind != "media" and extension not in self._sidecar_extensions:
                    continue
                rel_path = local_path.relative_to(source).as_posix()
                yield local_path, (target / PurePosixPath(rel_path)).as_posix(), kind, source, strm_target

    @staticmethod
    def _validate_strm_output_paths(
        files: list[Tuple[Path, str, str, Path, str]],
    ) -> None:
        claimed: Dict[Path, Path] = {}
        for local_path, _target_path, kind, source_root, strm_target in files:
            if kind != "media" or not strm_target:
                continue
            output = uploaded_strm_path(local_path, source_root, Path(strm_target))
            previous = claimed.get(output)
            if previous is not None and previous != local_path:
                raise ValueError(
                    f"STRM 输出路径冲突: {previous} 与 {local_path} 均映射到 {output}"
                )
            claimed[output] = local_path

    @staticmethod
    def _validate_source_file(local_path: Path, source_root: Path) -> None:
        if local_path.is_symlink():
            raise ValueError(f"上传源文件不能是符号链接: {local_path}")
        resolved = local_path.resolve(strict=True)
        try:
            resolved.relative_to(source_root)
        except ValueError as err:
            raise ValueError(f"上传源文件超出映射目录: {local_path}") from err
        if not resolved.is_file():
            raise ValueError(f"上传源文件不可用: {local_path}")

    @staticmethod
    def _remove_empty_parents(directory: Path, source_root: Path) -> None:
        while directory != source_root:
            try:
                directory.rmdir()
            except OSError:
                return
            logger.info(f"【目录上传】删除空目录：{directory}")
            directory = directory.parent

    @staticmethod
    def _delete_uploaded_sources(
        files: list[Tuple[Path, str, str, Path, str]],
        uploaded_paths: set[Path],
        counts: Dict[str, int],
        errors: list[Dict[str, str]],
    ) -> None:
        targets = {
            local_path: target_path
            for local_path, target_path, _kind, _source_root, _strm_target in files
        }
        source_roots = {
            local_path: source_root
            for local_path, _target_path, _kind, source_root, _strm_target in files
        }
        media_paths = [
            local_path
            for local_path, _target_path, kind, _source_root, _strm_target in files
            if kind == "media"
        ]
        sidecar_paths = [
            local_path
            for local_path, _target_path, kind, _source_root, _strm_target in files
            if kind == "sidecar"
        ]
        bundles = {local_path: [local_path] for local_path in media_paths}

        for sidecar_path in sidecar_paths:
            candidates = [
                media_path
                for media_path in media_paths
                if media_path.parent == sidecar_path.parent and sidecar_path.name.startswith(f"{media_path.stem}.")
            ]
            if candidates:
                bundles[max(candidates, key=lambda path: len(path.stem))].append(sidecar_path)
            else:
                bundles[sidecar_path] = [sidecar_path]

        for bundle in bundles.values():
            if not all(path in uploaded_paths for path in bundle):
                continue
            for local_path in bundle:
                try:
                    local_path.unlink()
                    counts["deleted"] += 1
                    logger.info(f"【目录上传】删除源文件：{local_path}")
                    DirectoryUploader._remove_empty_parents(local_path.parent, source_roots[local_path])
                except OSError as err:
                    counts["errors"] += 1
                    logger.error(f"【目录上传】删除源文件失败：{local_path}，原因：{safe_error_text(err)}")
                    errors.append(
                        {
                            "path": str(local_path),
                            "target": targets[local_path],
                            "message": f"删除源文件失败: {err}",
                        }
                    )

    def _generate_strm_after_upload(
        self,
        file_item: Dict[str, Any] | None,
        local_path: Path,
        source_root: Path,
        strm_target: str,
    ) -> Path:
        if not self._moviepilot_url:
            raise ValueError("请先配置媒体服务器可访问的 MoviePilot 地址")
        pickcode = str((file_item or {}).get("pickcode") or "")
        output = write_uploaded_strm(
            local_path=local_path,
            source_root=source_root,
            target_root=Path(strm_target),
            pickcode=pickcode,
            moviepilot_url=self._moviepilot_url,
            redirect_secret=self._redirect_secret,
        )
        logger.info(f"【目录上传】生成 STRM 成功：{output}")
        return output

    def _strm_record_metadata(self, strm_target: str) -> Dict[str, str]:
        signature = sha256(
            f"v{STRM_URL_FORMAT_VERSION}\0{self._moviepilot_url}".encode("utf-8")
        ).hexdigest()
        return {
            "strm_target": str(Path(strm_target).expanduser().resolve()),
            "strm_signature": signature,
        }

    def _uploaded_strm_matches(
        self,
        local_path: Path,
        source_root: Path,
        strm_target: str,
        pickcode: str,
    ) -> bool:
        try:
            expected = build_strm_content(
                self._moviepilot_url,
                normalize_pickcode(pickcode),
                self._redirect_secret,
                local_path.name,
            )
        except ValueError:
            return False
        output = uploaded_strm_path(local_path, source_root, Path(strm_target))
        return strm_file_matches(output, expected)

    def _resolve_uploaded_file_item(
        self,
        file_item: Dict[str, Any] | None,
        target_path: str,
        wait_for_upload: bool,
        retry_missing: bool = True,
    ) -> Dict[str, Any] | None:
        if (file_item or {}).get("pickcode"):
            return file_item
        if wait_for_upload:
            delays = (5, 10, 20)
        elif retry_missing:
            delays = (0, 5, 10, 20)
        else:
            delays = (0,)
        last_error: Exception | None = None
        for delay in delays:
            if delay:
                sleep(delay)
            try:
                file_item = self._client.get_item(target_path)
            except U115AuthError:
                raise
            except Exception as err:  # noqa: BLE001
                last_error = err
                continue
            if (file_item or {}).get("pickcode"):
                return file_item
        if last_error is not None:
            raise last_error
        return file_item

    def _complete_strm(
        self,
        records,
        file_item: Dict[str, Any] | None,
        local_path: Path,
        source_root: Path,
        strm_target: str,
        record_metadata: Dict[str, str],
        counts: Dict[str, int],
        errors: list[Dict[str, str]],
    ) -> bool:
        try:
            self._generate_strm_after_upload(
                file_item,
                local_path,
                source_root,
                strm_target,
            )
            records.update_metadata(local_path, record_metadata)
            counts["strm_generated"] += 1
            return True
        except Exception as err:  # noqa: BLE001
            counts["strm_errors"] += 1
            counts["errors"] += 1
            logger.error(
                f"【目录上传】生成 STRM 失败：{local_path}，原因：{safe_error_text(err)}"
            )
            errors.append(
                {
                    "path": str(local_path),
                    "target": strm_target,
                    "message": f"生成 STRM 失败: {err}",
                }
            )
            return False

    @staticmethod
    def _normalize_identity_path(path: Any) -> str:
        normalized = PurePosixPath(str(path or "").strip().replace("\\", "/")).as_posix()
        if normalized in ("", "."):
            return ""
        return normalized if normalized.startswith("/") else f"/{normalized}"

    @classmethod
    def _validate_pending_strm_identity(
        cls,
        records,
        local_path: Path,
        target_path: str,
        file_item: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        record = records.get(local_path)
        recorded_pickcode = str(record.get("pickcode") or "")
        remote_pickcode = str((file_item or {}).get("pickcode") or "")
        if recorded_pickcode:
            if recorded_pickcode != remote_pickcode:
                raise ValueError("上传记录 Pickcode 与当前远端文件不一致")
            return {}

        if not remote_pickcode:
            raise ValueError("远端文件缺少 Pickcode，无法迁移旧上传记录身份")

        expected_target = cls._normalize_identity_path(target_path)
        recorded_target = cls._normalize_identity_path(record.get("target"))
        if not expected_target or recorded_target != expected_target:
            raise ValueError("旧上传记录目标路径与当前上传映射不一致")

        stat = local_path.stat()
        if record.get("size") != stat.st_size or record.get("mtime_ns") != stat.st_mtime_ns:
            raise ValueError("旧上传记录本地文件指纹与当前文件不一致")

        remote_path = cls._normalize_identity_path((file_item or {}).get("path"))
        if not remote_path:
            raise ValueError("远端文件响应缺少路径，无法确认旧上传记录身份")
        if remote_path != expected_target:
            raise ValueError("远端文件路径与旧上传记录目标路径不一致")

        expected_name = PurePosixPath(expected_target).name
        remote_name = str((file_item or {}).get("name") or "")
        if remote_name != expected_name:
            raise ValueError("远端文件名与旧上传记录目标文件名不一致")
        if str((file_item or {}).get("type") or "") != "file":
            raise ValueError("旧上传记录目标路径当前不是文件")

        remote_size = next(
            (
                (file_item or {}).get(key)
                for key in ("size", "file_size", "size_byte", "fs")
                if (file_item or {}).get(key) is not None
            ),
            None,
        )
        if remote_size is None:
            raise ValueError("远端文件响应缺少大小，无法确认旧上传记录身份")
        try:
            normalized_remote_size = int(remote_size)
            normalized_recorded_size = int(record.get("size"))
        except (TypeError, ValueError) as err:
            raise ValueError("文件大小格式无效，无法确认旧上传记录身份") from err
        if not (
            normalized_remote_size == normalized_recorded_size == stat.st_size
        ):
            raise ValueError("远端文件大小与旧上传记录或当前本地文件大小不一致")

        migrated_at = datetime.now().isoformat(timespec="seconds")
        migration = {
            "pickcode": remote_pickcode,
            "pickcode_identity_source": "verified_target_path",
            "pickcode_identity_target": expected_target,
            "pickcode_identity_migrated_at": migrated_at,
        }
        remote_fileid = str((file_item or {}).get("fileid") or "")
        if remote_fileid:
            migration["pickcode_identity_fileid"] = remote_fileid
        return migration

    def _resolve_and_validate_uploaded_identity(
        self,
        records,
        local_path: Path,
        target_path: str,
        wait_for_upload: bool,
        retry_missing: bool,
    ) -> Dict[str, Any] | None:
        file_item = self._resolve_uploaded_file_item(
            None,
            target_path,
            wait_for_upload=wait_for_upload,
            retry_missing=retry_missing,
        )
        identity_migration = self._validate_pending_strm_identity(
            records,
            local_path,
            target_path,
            file_item,
        )
        if identity_migration:
            records.update_metadata(local_path, identity_migration)
            logger.info(
                f"【目录上传】旧上传记录身份迁移成功：{local_path} -> {target_path}"
            )
        return file_item

    def run(self, incremental: bool = True) -> Dict[str, Any]:
        started = monotonic()
        logger.info("【目录上传】开始校验 115 上传授权")
        self._client.ensure_upload_ready()
        logger.info("【目录上传】115 上传授权校验通过")
        records = self._store.get_upload_records()
        delete_source = bool(self._config.get("upload_delete_source", False))
        counts = {
            "uploaded": 0,
            "instant": 0,
            "strm_generated": 0,
            "strm_errors": 0,
            "skipped": 0,
            "deleted": 0,
            "errors": 0,
        }
        errors = []
        files = list(self._iter_files())
        if self._generate_strm:
            self._validate_strm_output_paths(files)
        logger.info(f"【目录上传】目录扫描完成，待处理文件：{len(files)}")
        uploaded_paths: set[Path] = set()
        for local_path, target_path, kind, source_root, strm_target in files:
            self._validate_source_file(local_path, source_root)
            record_metadata = (
                self._strm_record_metadata(strm_target)
                if self._generate_strm and kind == "media"
                else {}
            )
            upload_changed = records.has_changed(local_path, target_path)
            record = records.get(local_path)
            strm_pending = bool(record_metadata) and (
                records.has_changed(local_path, target_path, record_metadata)
                or not self._uploaded_strm_matches(
                    local_path,
                    source_root,
                    strm_target,
                    str(record.get("pickcode") or ""),
                )
            )
            if incremental and not upload_changed:
                counts["skipped"] += 1
                if not record_metadata:
                    logger.debug(f"【目录上传】文件未变化，跳过：{local_path} -> {target_path}")
                    continue
                try:
                    file_item = self._resolve_and_validate_uploaded_identity(
                        records,
                        local_path,
                        target_path,
                        wait_for_upload=False,
                        retry_missing=strm_pending,
                    )
                    if not strm_pending:
                        logger.debug(
                            f"【目录上传】远端文件身份未变化，跳过：{local_path} -> {target_path}"
                        )
                        continue
                    logger.info(f"【目录上传】上传记录未变化，继续生成 STRM：{local_path}")
                    if self._complete_strm(
                        records,
                        file_item,
                        local_path,
                        source_root,
                        strm_target,
                        record_metadata,
                        counts,
                        errors,
                    ):
                        uploaded_paths.add(local_path)
                except Exception as err:  # noqa: BLE001
                    counts["strm_errors"] += 1
                    counts["errors"] += 1
                    logger.error(
                        f"【目录上传】校验已上传文件失败：{target_path}，原因：{safe_error_text(err)}"
                    )
                    errors.append(
                        {
                            "path": str(local_path),
                            "target": target_path,
                            "message": f"校验已上传文件失败: {err}",
                        }
                    )
                continue
            try:
                logger.debug(f"【目录上传】开始处理文件：{local_path} -> {target_path}")

                def upload_once():
                    target_dir = self._client.ensure_remote_dir(str(PurePosixPath(target_path).parent))
                    result = self._client.upload_file(target_dir, local_path)
                    if not result.success:
                        raise RuntimeError(result.message or "115 上传失败")
                    return result

                result = retry_call(upload_once, attempts=3, delay=1.0)
                counts["instant" if result.reused else "uploaded"] += 1
                logger.info(
                    f"【目录上传】{'秒传成功' if result.reused else '上传成功'}："
                    f"{local_path} -> {target_path}"
                )
                upload_metadata = {}
                if (result.file_item or {}).get("pickcode"):
                    upload_metadata["pickcode"] = str(result.file_item["pickcode"])
                records.mark_uploaded(
                    local_path,
                    target_path,
                    metadata=upload_metadata,
                )
                completed = True
                if self._generate_strm and kind == "media":
                    try:
                        result.file_item = self._resolve_uploaded_file_item(
                            result.file_item,
                            target_path,
                            wait_for_upload=True,
                        )
                        if (result.file_item or {}).get("pickcode"):
                            records.update_metadata(
                                local_path,
                                {"pickcode": str(result.file_item["pickcode"])},
                            )
                    except Exception as err:  # noqa: BLE001
                        counts["strm_errors"] += 1
                        counts["errors"] += 1
                        logger.error(
                            f"【目录上传】读取已上传文件失败：{target_path}，"
                            f"原因：{safe_error_text(err)}"
                        )
                        errors.append(
                            {
                                "path": str(local_path),
                                "target": target_path,
                                "message": f"读取已上传文件失败: {err}",
                            }
                        )
                        continue
                    completed = self._complete_strm(
                        records,
                        result.file_item,
                        local_path,
                        source_root,
                        strm_target,
                        record_metadata,
                        counts,
                        errors,
                    )
                if completed:
                    uploaded_paths.add(local_path)
            except Exception as err:  # noqa: BLE001
                counts["errors"] += 1
                logger.error(
                    f"【目录上传】上传失败：{local_path} -> {target_path}，原因：{safe_error_text(err)}"
                )
                errors.append({"path": str(local_path), "target": target_path, "message": str(err)})
        if delete_source:
            self._delete_uploaded_sources(files, uploaded_paths, counts, errors)
        self._store.save_upload_records(records)
        return {
            "kind": "upload",
            "time": datetime.now().isoformat(timespec="seconds"),
            "incremental": incremental,
            **counts,
            "errors_detail": errors[:20],
            "duration_ms": int((monotonic() - started) * 1000),
        }
