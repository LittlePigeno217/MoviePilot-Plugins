from typing import Optional

from app.log import logger


class RedirectResolver:
    """将 pickcode 解析为 115 短时效下载直链。"""

    def __init__(self, client):
        self._client = client

    def resolve(self, pickcode: str) -> Optional[str]:
        if not pickcode:
            return None
        try:
            return self._client.get_download_url(pickcode)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[U115Strm] 取直链失败 pickcode={pickcode}: {e}")
            return None
