from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

from .scanner import normalize_extensions


class MetadataScraper:
    def __init__(self, sidecar_extensions: Iterable[str], logger: Any = None):
        self.sidecar_extensions = normalize_extensions(sidecar_extensions)
        self.logger = logger

    def scrape_and_collect(self, media_path: Path, overwrite: bool = False) -> Dict[str, Any]:
        media_path = Path(media_path)
        before = self._snapshot(media_path)
        try:
            self._scrape(media_path, overwrite=overwrite)
        except Exception as err:
            self._warn(f"{media_path} 刮削失败: {err}")
            return {"success": False, "paths": [], "message": str(err)}

        after = self._snapshot(media_path)
        changed = [
            path
            for path, fingerprint in after.items()
            if path not in before or before[path] != fingerprint
        ]
        return {"success": True, "paths": changed, "message": ""}

    def _scrape(self, media_path: Path, overwrite: bool) -> None:
        from app.chain.media import MediaChain
        from app.schemas import FileItem

        fileitem = FileItem(
            storage="local",
            path=media_path.as_posix(),
            name=media_path.name,
            basename=media_path.stem,
            extension=media_path.suffix[1:] if media_path.suffix else None,
            type="file" if media_path.is_file() else "dir",
        )
        parent = None
        if media_path.is_file():
            parent_path = media_path.parent
            parent = FileItem(
                storage="local",
                path=parent_path.as_posix(),
                name=parent_path.name,
                basename=parent_path.name,
                type="dir",
            )
        MediaChain().scrape_metadata(
            fileitem=fileitem,
            init_folder=media_path.is_dir(),
            parent=parent,
            overwrite=overwrite,
            recursive=True,
        )

    def _snapshot(self, media_path: Path) -> Dict[Path, tuple[int, int]]:
        roots = self._candidate_roots(media_path)
        result: Dict[Path, tuple[int, int]] = {}
        for root in roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_file() and path.suffix.lower() in self.sidecar_extensions:
                    stat = path.stat()
                    result[path] = (int(stat.st_size), int(stat.st_mtime_ns))
        return result

    @staticmethod
    def _candidate_roots(media_path: Path) -> Set[Path]:
        if media_path.is_dir():
            return {media_path}
        return {media_path.parent}

    def _warn(self, message: str) -> None:
        if self.logger and hasattr(self.logger, "warning"):
            self.logger.warning(message)
