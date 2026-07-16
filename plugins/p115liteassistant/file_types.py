from __future__ import annotations

from typing import Iterable


DEFAULT_MEDIA_EXTENSIONS = (
    ".mkv",
    ".mp4",
    ".ts",
    ".m2ts",
    ".avi",
    ".mov",
    ".wmv",
    ".iso",
    ".rmvb",
    ".flv",
)
DEFAULT_SIDECAR_EXTENSIONS = (
    ".nfo",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".srt",
    ".ass",
    ".ssa",
    ".sup",
)


def parse_extensions(value: str, defaults: Iterable[str]) -> set[str]:
    parts = {part.strip().lower() for part in str(value or "").split(",") if part.strip()}
    return {part if part.startswith(".") else f".{part}" for part in (parts or set(defaults))}
