from __future__ import annotations

import base64
import hashlib
import secrets
import time
from pathlib import PurePosixPath
from typing import Any, Dict, Iterator, Optional


class U115AuthError(RuntimeError):
    pass


class U115Client:
    """115 开放平台客户端（STRM 场景：授权、目录遍历、取下载直链）。"""

    base_url = "https://proapi.115.com"
    qrcode_status_url = "https://qrcodeapi.115.com/get/status/"

    def __init__(
        self,
        cookie: str = "",
        tokens: Optional[Dict[str, Any]] = None,
        session: Any = None,
        app_id: str = "",
        auth_server: str = "",
        logger: Any = None,
    ):
        self.cookie = cookie or ""
        self.tokens = dict(tokens or {})
        self.app_id = app_id or ""
        self.auth_server = auth_server or ""
        self.logger = logger
        self._auth_state: Dict[str, Any] = {}
        self.session = session or self._create_session()
        self._init_headers()

    @staticmethod
    def _create_session() -> Any:
        import httpx

        return httpx.Client(follow_redirects=True, timeout=30.0)

    def _init_headers(self) -> None:
        self.session.headers.update(
            {
                "User-Agent": "U115Strm/1.0",
                "Accept-Encoding": "gzip, deflate",
                "Content-Type": "application/x-www-form-urlencoded",
            }
        )
        if self.cookie:
            self.session.headers.update({"Cookie": self.cookie})
        access_token = self.tokens.get("access_token")
        if access_token:
            self.session.headers.update({"Authorization": f"Bearer {access_token}"})

    def export_tokens(self) -> Dict[str, Any]:
        return dict(self.tokens)

    def is_authenticated(self) -> bool:
        return bool(self.cookie or self.tokens.get("access_token") or self.tokens.get("refresh_token"))

    # ---------------------------------------------------------------- 授权
    def generate_qrcode(self) -> Dict[str, Any]:
        if not self.app_id:
            return {"success": False, "message": "缺少 115 APP ID"}

        code_verifier = secrets.token_urlsafe(96)[:128]
        code_challenge = base64.b64encode(
            hashlib.sha256(code_verifier.encode("utf-8")).digest()
        ).decode("utf-8")
        result = self._request(
            "POST",
            "/open/authDeviceCode",
            base_url="https://passportapi.115.com",
            data={
                "client_id": self.app_id,
                "code_challenge": code_challenge,
                "code_challenge_method": "sha256",
            },
            require_auth=False,
        )
        if result.get("code") != 0:
            return {"success": False, "message": result.get("message") or "生成二维码失败"}

        data = result.get("data") or {}
        self._auth_state = {
            "code_verifier": code_verifier,
            "uid": data.get("uid"),
            "time": data.get("time"),
            "sign": data.get("sign"),
        }
        return {"success": True, "data": {"codeContent": data.get("qrcode")}}

    def check_login(self) -> Dict[str, Any]:
        if not self._auth_state:
            return {"success": False, "message": "请先生成二维码"}

        result = self._request_url(
            "GET",
            self.qrcode_status_url,
            params={
                "uid": self._auth_state.get("uid"),
                "time": self._auth_state.get("time"),
                "sign": self._auth_state.get("sign"),
            },
            require_auth=False,
        )
        if result.get("code") != 0 or not result.get("data"):
            return {"success": False, "message": result.get("message") or "检查登录状态失败"}

        data = result["data"]
        if data.get("status") == 2:
            token_result = self._request(
                "POST",
                "/open/deviceCodeToToken",
                base_url="https://passportapi.115.com",
                data={
                    "uid": self._auth_state.get("uid"),
                    "code_verifier": self._auth_state.get("code_verifier"),
                },
                require_auth=False,
            )
            if token_result.get("code") != 0:
                return {
                    "success": False,
                    "message": token_result.get("message") or "获取 access_token 失败",
                }
            self.tokens = {
                **(token_result.get("data") or {}),
                "refresh_time": int(time.time()),
            }
            self._auth_state = {}
            self._init_headers()
        return {"success": True, "data": {"status": data.get("status"), "tip": data.get("msg")}}

    def refresh_access_token(self) -> bool:
        refresh_token = self.tokens.get("refresh_token")
        if not refresh_token:
            return False
        result = self._request(
            "POST",
            "/open/refreshToken",
            base_url="https://passportapi.115.com",
            data={"refresh_token": refresh_token},
            require_auth=False,
        )
        if result.get("code") != 0:
            return False
        self.tokens = {
            **(result.get("data") or {}),
            "refresh_time": int(time.time()),
        }
        self._init_headers()
        return True

    # ------------------------------------------------------------ 目录 / 文件
    def get_item(self, path: str) -> Optional[Dict[str, Any]]:
        result = self._request(
            "POST",
            "/open/folder/get_info",
            data={"path": self._normalize_cloud_path(path)},
            no_error=True,
        )
        data = self._response_data(result)
        if not data:
            return None
        return self._file_item_from_info(data, self._normalize_cloud_path(path))

    def get_dir_list(self, cid: str = "0") -> list:
        """获取 115 目录列表"""
        result = self._request(
            "POST",
            "/open/folder/list",
            data={"cid": cid},
            no_error=True,
        )
        data = self._response_data(result)
        if not data:
            return []
        items = data.get("items", []) if isinstance(data, dict) else data
        return list(items) if isinstance(items, list) else []

    def get_download_url(self, pickcode: str) -> Optional[str]:
        """
        取指定文件的 115 短时效下载直链（供 302 重定向）
        :param pickcode: 115 文件 pickcode
        """
        if not pickcode:
            return None
        result = self._request(
            "POST",
            "/open/ufile/downurl",
            data={"pick_code": pickcode},
            no_error=True,
        )
        data = self._response_data(result)
        if not isinstance(data, dict):
            return None
        # 115 downurl 返回以 file_id 为键的字典，每项含 url 或 url.url
        for item in data.values():
            if isinstance(item, dict):
                url = item.get("url")
                if isinstance(url, dict):
                    return url.get("url")
                if isinstance(url, str):
                    return url
        return None

    def iter_files(self, cid: str, recursive: bool = True) -> Iterator[Dict[str, Any]]:
        """
        递归遍历目录，产出文件项（不含子目录本身）。
        产出字段：{name, pickcode, size, fileid, cid, rel_path}
        """
        stack = [(str(cid), "")]
        while stack:
            current_cid, rel_prefix = stack.pop()
            for raw in self.get_dir_list(current_cid):
                name = raw.get("fn") or raw.get("file_name") or raw.get("n") or ""
                is_dir = str(raw.get("fc", raw.get("file_category", "1"))) == "0" or (
                    raw.get("cid") is not None and raw.get("fid") is None
                )
                child_rel = f"{rel_prefix}/{name}" if rel_prefix else name
                if is_dir:
                    sub_cid = str(raw.get("cid") or raw.get("file_id") or raw.get("fid") or "")
                    if recursive and sub_cid:
                        stack.append((sub_cid, child_rel))
                    continue
                yield {
                    "name": name,
                    "pickcode": raw.get("pc") or raw.get("pick_code") or raw.get("pickcode") or "",
                    "size": raw.get("s") or raw.get("size_byte") or raw.get("size") or 0,
                    "fileid": str(raw.get("fid") or raw.get("file_id") or ""),
                    "cid": current_cid,
                    "rel_path": child_rel,
                }

    # ---------------------------------------------------------------- 内部
    def _request(
        self,
        method: str,
        endpoint: str,
        base_url: Optional[str] = None,
        require_auth: bool = True,
        no_error: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        url = f"{base_url or self.base_url}{endpoint}"
        return self._request_url(method, url, require_auth=require_auth, no_error=no_error, **kwargs)

    def _request_url(
        self,
        method: str,
        url: str,
        require_auth: bool = True,
        no_error: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if require_auth:
            self._ensure_auth()
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") not in (None, 0, 20004) and not no_error:
            self._log_warning(f"115 请求失败: {payload.get('message') or payload}")
        return payload

    def _ensure_auth(self) -> None:
        if not self.is_authenticated():
            raise U115AuthError("115 未授权")

    @staticmethod
    def _response_data(payload: Dict[str, Any]) -> Any:
        if not payload:
            return None
        return payload.get("data") if "data" in payload else payload

    @staticmethod
    def _normalize_cloud_path(path: str) -> str:
        cloud_path = PurePosixPath((path or "/").replace("\\", "/")).as_posix()
        if cloud_path == ".":
            cloud_path = "/"
        if not cloud_path.startswith("/"):
            cloud_path = f"/{cloud_path}"
        return cloud_path

    @staticmethod
    def _file_item_from_info(info: Dict[str, Any], path: str) -> Dict[str, Any]:
        category = str(info.get("file_category", "1"))
        return {
            "storage": "u115",
            "fileid": str(info.get("file_id") or info.get("fid") or ""),
            "path": path,
            "type": "file" if category == "1" else "dir",
            "name": info.get("file_name") or PurePosixPath(path).name,
            "pickcode": info.get("pick_code") or info.get("pickcode"),
            "size": info.get("size_byte") or info.get("size"),
            "modify_time": info.get("utime") or info.get("modify_time"),
        }

    def _log_warning(self, message: str) -> None:
        if self.logger and hasattr(self.logger, "warning"):
            self.logger.warning(message)
