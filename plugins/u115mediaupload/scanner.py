from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .records import IncrementalRecordStore


@dataclass(frozen=True)
class UploadPlanItem:
    path: Path
    target_path: str
    kind: str
    size: int
    mtime_ns: int
    source_root: str
    target_root: str


def normalize_extensions(values: Optional[Iterable[str]]) -> List[str]:
    result = []
    for value in values or []:
        ext = str(value or "").strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = f".{ext}"
        if ext not in result:
            result.append(ext)
    return result


class MediaScanner:
    def __init__(
        self,
        media_extensions: Optional[Iterable[str]] = None,
        sidecar_extensions: Optional[Iterable[str]] = None,
    ):
        self.media_extensions = normalize_extensions(
            media_extensions
            or [
                ".mkv",
                ".mp4",
                ".avi",
                ".mov",
                ".ts",
                ".iso",
                ".m2ts",
                ".rmvb",
                ".wmv",
            ]
        )
        self.sidecar_extensions = normalize_extensions(
            sidecar_extensions
            or [".nfo", ".jpg", ".jpeg", ".png", ".webp", ".srt", ".ass", ".ssa", ".sup"]
        )

    def scan_mappings(
        self,
        mappings: Iterable[Dict[str, Any]],
        include_sidecars: bool,
        records: Optional[IncrementalRecordStore] = None,
        incremental: bool = False,
    ) -> Tuple[List[UploadPlanItem], List[Dict[str, str]]]:
        items: List[UploadPlanItem] = []
        failures: List[Dict[str, str]] = []

        for mapping in mappings or []:
            if not mapping or not mapping.get("enabled", True):
                continue
            source = Path(str(mapping.get("source") or "")).expanduser()
            target = self._normalize_target_root(str(mapping.get("target") or "/"))
            if not source.exists() or not source.is_dir():
                failures.append(
                    {
                        "source": str(source),
                        "target": target,
                        "reason": "源目录不存在",
                    }
                )
                continue

            for path in sorted(source.rglob("*")):
                if not path.is_file():
                    continue
                kind = self._classify(path, include_sidecars)
                if not kind:
                    continue
                if incremental and records and not records.has_changed(path):
                    continue
                items.append(self._build_item(path, source, target, kind))

        return items, failures

    def plan_for_paths(
        self,
        paths: Iterable[Path],
        source_root: Path,
        target_root: str,
        kind: str = "sidecar",
        records: Optional[IncrementalRecordStore] = None,
        incremental: bool = False,
    ) -> List[UploadPlanItem]:
        items: List[UploadPlanItem] = []
        target = self._normalize_target_root(target_root)
        for path in sorted({Path(item) for item in paths}):
            if not path.exists() or not path.is_file():
                continue
            if incremental and records and not records.has_changed(path):
                continue
            items.append(self._build_item(path, Path(source_root), target, kind))
        return items

    def _classify(self, path: Path, include_sidecars: bool) -> Optional[str]:
        ext = path.suffix.lower()
        if ext in self.media_extensions:
            return "media"
        if include_sidecars and ext in self.sidecar_extensions:
            return "sidecar"
        return None

    def _build_item(
        self, path: Path, source_root: Path, target_root: str, kind: str
    ) -> UploadPlanItem:
        stat = path.stat()
        rel = path.relative_to(source_root)
        target_path = (PurePosixPath(target_root) / PurePosixPath(rel.as_posix())).as_posix()
        if not target_path.startswith("/"):
            target_path = f"/{target_path}"
        return UploadPlanItem(
            path=path,
            target_path=target_path,
            kind=kind,
            size=int(stat.st_size),
            mtime_ns=int(stat.st_mtime_ns),
            source_root=str(source_root),
            target_root=target_root,
        )

    @staticmethod
    def _normalize_target_root(value: str) -> str:
        target = PurePosixPath((value or "/").replace("\\", "/")).as_posix()
        if target == ".":
            target = "/"
        if not target.startswith("/"):
            target = f"/{target}"
        return target.rstrip("/") or "/"
