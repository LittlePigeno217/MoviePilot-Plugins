from pathlib import Path, PurePosixPath
from typing import List

SIDECAR_EXTS = {".nfo", ".srt", ".ass", ".ssa", ".sup"}
SIDECAR_NAMES = {"poster.jpg", "fanart.jpg", "banner.jpg", "clearlogo.png", "landscape.jpg"}


def _is_sidecar(name: str) -> bool:
    lower = name.lower()
    return PurePosixPath(lower).suffix in SIDECAR_EXTS or lower in SIDECAR_NAMES


class MetadataSync:
    """下载与媒体同目录的刮削文件（nfo/图片/字幕）到 .strm 同目录。"""

    def __init__(self, client):
        self._client = client

    def download_file(self, pickcode: str, dest: Path) -> bool:
        url = self._client.get_download_url(pickcode)
        if not url:
            return False
        resp = self._client.session.get(url)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        return True

    def sync_for(self, media_item: dict, strm_path: Path, siblings: List[dict]) -> int:
        """
        下载 siblings 中的 sidecar 文件到 strm_path 同目录。
        :return: 实际下载数量
        """
        count = 0
        for sib in siblings:
            name = sib.get("name", "")
            if not _is_sidecar(name):
                continue
            dest = strm_path.parent / name
            if dest.exists():
                continue
            try:
                if self.download_file(sib.get("pickcode", ""), dest):
                    count += 1
            except Exception:  # noqa: BLE001
                continue
        return count
