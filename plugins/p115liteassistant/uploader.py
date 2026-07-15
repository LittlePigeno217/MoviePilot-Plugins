from __future__ import annotations

from datetime import datetime
from pathlib import Path, PurePosixPath
from time import monotonic
from typing import Any, Dict, Iterable, Iterator, Tuple

from app.log import logger

from .log_utils import safe_error_text
from .resilience import retry_call


def parse_extensions(value: str, defaults: Iterable[str]) -> set[str]:
    parts = {part.strip().lower() for part in str(value or "").split(",") if part.strip()}
    return {part if part.startswith(".") else f".{part}" for part in (parts or set(defaults))}


class DirectoryUploader:
    def __init__(self, client, store, config: Dict[str, Any]):
        self._client = client
        self._store = store
        self._config = config
        self._media_extensions = parse_extensions(
            config.get("upload_media_extensions", ""),
            (".mkv", ".mp4", ".ts", ".m2ts", ".avi", ".mov", ".wmv", ".iso", ".rmvb", ".flv"),
        )
        self._sidecar_extensions = parse_extensions(
            config.get("upload_sidecar_extensions", ""),
            (".nfo", ".jpg", ".jpeg", ".png", ".webp", ".srt", ".ass", ".ssa", ".sup"),
        )

    def _iter_files(self) -> Iterator[Tuple[Path, str, str, Path]]:
        include_sidecars = bool(self._config.get("upload_include_sidecars", True))
        for mapping in self._config.get("upload_mappings", []):
            if not mapping.get("enabled", True):
                continue
            source = Path(str(mapping.get("source") or "")).expanduser().resolve()
            target = PurePosixPath(str(mapping.get("target") or "/"))
            if not source.is_dir():
                raise FileNotFoundError(f"上传源目录不存在: {source}")
            for local_path in sorted(path for path in source.rglob("*") if path.is_file()):
                extension = local_path.suffix.lower()
                kind = "media" if extension in self._media_extensions else "sidecar"
                if kind == "sidecar" and (not include_sidecars or extension not in self._sidecar_extensions):
                    continue
                if kind != "media" and extension not in self._sidecar_extensions:
                    continue
                rel_path = local_path.relative_to(source).as_posix()
                yield local_path, (target / PurePosixPath(rel_path)).as_posix(), kind, source

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
        files: list[Tuple[Path, str, str, Path]],
        uploaded_paths: set[Path],
        counts: Dict[str, int],
        errors: list[Dict[str, str]],
    ) -> None:
        targets = {local_path: target_path for local_path, target_path, _kind, _source_root in files}
        source_roots = {local_path: source_root for local_path, _target_path, _kind, source_root in files}
        media_paths = [local_path for local_path, _target_path, kind, _source_root in files if kind == "media"]
        sidecar_paths = [local_path for local_path, _target_path, kind, _source_root in files if kind == "sidecar"]
        bundles = {local_path: [local_path] for local_path in media_paths}

        for sidecar_path in sidecar_paths:
            candidates = [
                media_path
                for media_path in media_paths
                if media_path.parent == sidecar_path.parent and sidecar_path.name.startswith(f"{media_path.stem}.")
            ]
            if candidates:
                bundles[max(candidates, key=lambda path: len(path.stem))].append(sidecar_path)

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

    def run(self, incremental: bool = True) -> Dict[str, Any]:
        started = monotonic()
        records = self._store.get_upload_records()
        delete_source = bool(self._config.get("upload_delete_source", False))
        counts = {"uploaded": 0, "instant": 0, "skipped": 0, "deleted": 0, "errors": 0}
        errors = []
        files = list(self._iter_files())
        logger.info(f"【目录上传】目录扫描完成，待处理文件：{len(files)}")
        uploaded_paths: set[Path] = set()
        for local_path, target_path, _kind, _source_root in files:
            if incremental and not records.has_changed(local_path, target_path):
                counts["skipped"] += 1
                logger.debug(f"【目录上传】文件未变化，跳过：{local_path} -> {target_path}")
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
                records.mark_uploaded(local_path, target_path)
                uploaded_paths.add(local_path)
                counts["instant" if result.reused else "uploaded"] += 1
                logger.info(
                    f"【目录上传】{'秒传成功' if result.reused else '上传成功'}："
                    f"{local_path} -> {target_path}"
                )
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
