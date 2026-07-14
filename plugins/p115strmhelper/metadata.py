from pathlib import Path, PurePosixPath

SIDECAR_EXTS = {".nfo", ".srt", ".ass", ".ssa", ".sup"}
SIDECAR_NAMES = {"poster.jpg", "fanart.jpg", "banner.jpg", "clearlogo.png", "landscape.jpg"}


def is_sidecar(name: str) -> bool:
    lower = name.lower()
    return PurePosixPath(lower).suffix in SIDECAR_EXTS or lower in SIDECAR_NAMES


class MetadataSync:
    """将 115 中的刮削文件（nfo/图片/字幕）按 rel_path 镜像到本地输出目录。"""

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

    def mirror(self, item: dict, target_dir: str) -> bool:
        """
        若 item 是 sidecar，则按其 rel_path 下载到 target_dir（与 .strm 同结构）。
        :return: 是否实际下载
        """
        name = item.get("name", "")
        if not is_sidecar(name):
            return False
        dest = Path(target_dir) / item.get("rel_path", name)
        if dest.exists():
            return False
        try:
            return self.download_file(item.get("pickcode", ""), dest)
        except Exception:  # noqa: BLE001
            return False

