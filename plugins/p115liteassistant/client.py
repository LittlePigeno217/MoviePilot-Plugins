from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterator, Optional

import httpx


class U115AuthError(RuntimeError):
    pass


class U115ApiError(RuntimeError):
    pass


@dataclass
class UploadResult:
    success: bool
    reused: bool = False
    file_item: Optional[Dict[str, Any]] = None
    message: str = ""


class U115Client:
    """独立的 115 客户端，只覆盖本插件需要的登录、浏览、上传、签到和取链能力。"""

    base_url = "https://proapi.115.com"
    passport_url = "https://passportapi.115.com"
    qrcode_status_url = "https://qrcodeapi.115.com/get/status/"
    qrcode_base_url = "https://qrcodeapi.115.com"
    points_sign_url = "https://webapi.115.com/user/points_sign"
    read_retry_attempts = 3
    read_retry_delay = 1.0
    qrcode_client_types = {
        "alipaymini",
        "wechatmini",
        "115android",
        "115ios",
        "web",
        "115ipad",
        "tv",
    }

    def __init__(
        self,
        cookie: str = "",
        tokens: Optional[Dict[str, Any]] = None,
        app_id: str = "",
        session: Any = None,
    ):
        self.cookie = cookie.strip()
        self.tokens = dict(tokens or {})
        self.app_id = app_id.strip()
        self._auth_state: Dict[str, Any] = {}
        self.session = session or self._create_session()
        self._init_headers()

    @staticmethod
    def _create_session() -> Any:
        import httpx

        return httpx.Client(follow_redirects=True, timeout=60.0)

    def _init_headers(self) -> None:
        self.session.headers.update(
            {
                "User-Agent": "P115LiteAssistant/1.0",
                "Accept-Encoding": "gzip, deflate",
                "Content-Type": "application/x-www-form-urlencoded",
            }
        )
        self.session.headers.pop("Cookie", None)
        self.session.headers.pop("Authorization", None)
        if self.cookie:
            self.session.headers["Cookie"] = self.cookie
        if self.tokens.get("access_token"):
            self.session.headers["Authorization"] = f"Bearer {self.tokens['access_token']}"

    def export_tokens(self) -> Dict[str, Any]:
        return dict(self.tokens)

    def is_authenticated(self) -> bool:
        return bool(self.cookie or self.tokens.get("access_token") or self.tokens.get("refresh_token"))

    def generate_qrcode(self, client_type: str = "alipaymini") -> Dict[str, Any]:
        client_type = client_type if client_type in self.qrcode_client_types else "alipaymini"
        payload = self._request_url(
            "GET",
            f"{self.qrcode_base_url}/api/1.0/web/1.0/token/",
            require_auth=False,
        )
        data = payload.get("data") or {}
        uid = str(data.get("uid") or "")
        timestamp = str(data.get("time") or "")
        sign = str(data.get("sign") or "")
        if not uid or not timestamp or not sign:
            return {"success": False, "message": "115 返回的二维码参数不完整"}
        self._auth_state = {
            "mode": "qrcode",
            "uid": uid,
            "time": timestamp,
            "sign": sign,
            "client_type": client_type,
        }
        return {
            "success": True,
            "data": {
                "code_content": data.get("qrcode") or f"https://115.com/scan/dg-{uid}",
                "client_type": client_type,
            },
        }

    def check_login(self) -> Dict[str, Any]:
        if not self._auth_state:
            return {"success": False, "message": "请先生成二维码"}
        if self._auth_state.get("mode") == "qrcode":
            return self._check_qrcode_login()
        payload = self._request_url(
            "GET",
            self.qrcode_status_url,
            require_auth=False,
            params={
                "uid": self._auth_state.get("uid"),
                "time": self._auth_state.get("time"),
                "sign": self._auth_state.get("sign"),
            },
        )
        if payload.get("code") != 0 or not payload.get("data"):
            return {"success": False, "message": payload.get("message") or "检查登录状态失败"}
        data = payload["data"]
        if data.get("status") == 2:
            token_payload = self._request(
                "POST",
                "/open/deviceCodeToToken",
                base_url=self.passport_url,
                require_auth=False,
                data={"uid": self._auth_state.get("uid"), "code_verifier": self._auth_state.get("code_verifier")},
            )
            if token_payload.get("code") != 0:
                return {"success": False, "message": token_payload.get("message") or "获取访问令牌失败"}
            self.tokens = {**(token_payload.get("data") or {}), "refresh_time": int(time.time())}
            self._auth_state = {}
            self._init_headers()
        return {"success": True, "data": {"status": data.get("status"), "tip": data.get("msg") or ""}}

    def _check_qrcode_login(self) -> Dict[str, Any]:
        payload = self._request_url(
            "GET",
            self.qrcode_status_url,
            require_auth=False,
            params={
                "uid": self._auth_state.get("uid"),
                "time": self._auth_state.get("time"),
                "sign": self._auth_state.get("sign"),
            },
        )
        data = payload.get("data") or {}
        status = data.get("status")
        if status != 2:
            return {"success": True, "data": {"status": status, "tip": data.get("msg") or ""}}

        client_type = str(self._auth_state.get("client_type") or "alipaymini")
        result = self._request_url(
            "POST",
            f"{self.qrcode_base_url}/app/1.0/{client_type}/1.0/login/qrcode/",
            require_auth=False,
            data={"account": self._auth_state.get("uid")},
        )
        cookie_data = (result.get("data") or {}).get("cookie")
        if not isinstance(cookie_data, dict):
            return {"success": False, "message": result.get("message") or "115 未返回登录 Cookie"}
        self.cookie = "; ".join(f"{key}={value}" for key, value in cookie_data.items() if key and value)
        if not self.cookie:
            return {"success": False, "message": "115 未返回有效登录 Cookie"}
        self.tokens = {}
        self._auth_state = {}
        self._init_headers()
        return {"success": True, "data": {"status": 2, "tip": "登录成功"}}

    def refresh_access_token(self) -> bool:
        refresh_token = self.tokens.get("refresh_token")
        if not refresh_token:
            return False
        payload = self._request(
            "POST",
            "/open/refreshToken",
            base_url=self.passport_url,
            require_auth=False,
            data={"refresh_token": refresh_token},
        )
        if payload.get("code") != 0:
            return False
        self.tokens = {**(payload.get("data") or {}), "refresh_time": int(time.time())}
        self._init_headers()
        return True

    def get_dir_list(self, cid: str = "0") -> list[Dict[str, Any]]:
        if self.cookie:
            payload = self._request_url(
                "GET",
                "https://webapi.115.com/files",
                params={
                    "aid": 1,
                    "cid": int(cid or 0),
                    "limit": 1000,
                    "offset": 0,
                    "show_dir": 1,
                },
            )
            data = self._response_data(payload)
            return list(data) if isinstance(data, list) else []

        payload = self._request(
            "GET",
            "/open/ufile/files",
            params={"cid": int(cid or 0), "limit": 1000, "offset": 0, "cur": True, "show_dir": 1},
        )
        data = self._response_data(payload)
        if isinstance(data, list):
            return data
        payload = self._request(
            "POST",
            "/open/folder/list",
            data={"cid": str(cid or "0")},
        )
        data = self._response_data(payload)
        if isinstance(data, dict):
            data = data.get("items", [])
        return list(data) if isinstance(data, list) else []

    def iter_files(self, cid: str) -> Iterator[Dict[str, Any]]:
        stack = [(str(cid), "")]
        while stack:
            current_cid, prefix = stack.pop()
            for raw in self.get_dir_list(current_cid):
                name = str(raw.get("fn") or raw.get("file_name") or raw.get("n") or "")
                if not name:
                    continue
                rel_path = f"{prefix}/{name}" if prefix else name
                if self._is_directory(raw):
                    child_cid = str(raw.get("cid") or raw.get("file_id") or raw.get("fid") or "")
                    if child_cid:
                        stack.append((child_cid, rel_path))
                    continue
                yield {
                    "name": name,
                    "pickcode": raw.get("pc") or raw.get("pick_code") or raw.get("pickcode") or "",
                    "size": raw.get("fs") or raw.get("size_byte") or raw.get("size") or 0,
                    "rel_path": rel_path,
                }

    def get_item(self, path: str) -> Optional[Dict[str, Any]]:
        normalized = self._normalize_cloud_path(path)
        payload = self._request(
            "POST", "/open/folder/get_info", no_error=True, data={"path": normalized}
        )
        data = self._response_data(payload)
        return self._item_from_info(data, normalized) if isinstance(data, dict) else None

    def ensure_remote_dir(self, path: str) -> Dict[str, Any]:
        current = {"fileid": "0", "path": "/", "name": "", "type": "dir"}
        cloud_path = self._normalize_cloud_path(path)
        for name in PurePosixPath(cloud_path).parts:
            if name == "/":
                continue
            found = next(
                (
                    item
                    for item in self.get_dir_list(current["fileid"])
                    if self._is_directory(item)
                    and str(item.get("fn") or item.get("file_name") or item.get("n") or "") == name
                ),
                None,
            )
            if found:
                current = {
                    "fileid": str(found.get("cid") or found.get("file_id") or found.get("fid") or ""),
                    "path": f"{current['path'].rstrip('/')}/{name}",
                    "name": name,
                    "type": "dir",
                }
                continue
            payload = self._request(
                "POST",
                "/open/folder/add",
                no_error=True,
                data={"pid": int(current["fileid"] or 0), "file_name": name},
            )
            data = self._response_data(payload)
            if not isinstance(data, dict):
                found = next(
                    (
                        item
                        for item in self.get_dir_list(current["fileid"])
                        if self._is_directory(item)
                        and str(item.get("fn") or item.get("file_name") or item.get("n") or "") == name
                    ),
                    None,
                )
                if not found:
                    raise U115ApiError(f"创建 115 目录失败: {name}")
                data = found
            current = {
                "fileid": str(data.get("file_id") or data.get("cid") or data.get("fid") or ""),
                "path": f"{current['path'].rstrip('/')}/{name}",
                "name": name,
                "type": "dir",
            }
        return current

    def upload_file(self, target_dir: Dict[str, Any], local_path: Path) -> UploadResult:
        self._ensure_auth()
        file_size = local_path.stat().st_size
        file_sha1 = self._calc_sha1(local_path)
        preid = self._calc_sha1(local_path, 128 * 1024 * 1024)
        target_cid = str(target_dir.get("fileid") or "0")
        init_data = {
            "file_name": local_path.name,
            "file_size": file_size,
            "target": f"U_1_{target_cid}",
            "fileid": file_sha1,
            "preid": preid,
        }
        payload = self._request("POST", "/open/upload/init", data=init_data)
        init_result = self._response_data(payload)
        if not isinstance(init_result, dict):
            return UploadResult(False, message="115 上传初始化失败")

        if int(init_result.get("code") or 0) in {700, 701} and init_result.get("sign_check"):
            init_data.update(self._build_sign_check_data(local_path, init_result))
            payload = self._request("POST", "/open/upload/init", data=init_data)
            init_result = self._response_data(payload)
            if not isinstance(init_result, dict):
                return UploadResult(False, message="115 上传二次认证失败")

        target_path = f"{str(target_dir.get('path') or '/').rstrip('/')}/{local_path.name}"
        if int(init_result.get("status") or 0) == 2:
            return UploadResult(True, reused=True, file_item=self.get_item(target_path))

        self._upload_to_oss(local_path, file_size, file_sha1, init_data["target"], init_result)
        return UploadResult(True, file_item=self.get_item(target_path))

    def get_download_url(self, pickcode: str) -> Optional[str]:
        if not pickcode:
            return None
        payload = self._request("POST", "/open/ufile/downurl", no_error=True, data={"pick_code": pickcode})
        data = self._response_data(payload)
        if isinstance(data, dict):
            for value in data.values():
                if isinstance(value, dict):
                    url = value.get("url")
                    if isinstance(url, dict) and url.get("url"):
                        return str(url["url"])
                    if isinstance(url, str):
                        return url
        return None

    def checkin(self, attempts: int = 3, retry_delay: float = 3.0) -> Dict[str, Any]:
        self._ensure_auth()
        current = self._request_url("GET", self.points_sign_url)
        data = self._response_data(current) or {}
        if isinstance(data, dict) and int(data.get("is_sign_today") or 0) == 1:
            return {"already": True, "message": "今日已签到"}
        total = max(1, int(attempts))
        last_error: Exception | None = None
        for attempt in range(1, total + 1):
            try:
                payload = self._request_url("POST", self.points_sign_url, no_error=True)
                data = self._response_data(payload) or {}
                if not self._is_response_success(payload):
                    raise U115ApiError(str(payload.get("message") or payload.get("error") or "115 签到失败"))
                return {
                    "already": False,
                    "continuous_day": data.get("continuous_day", 0) if isinstance(data, dict) else 0,
                    "points_num": data.get("points_num", 0) if isinstance(data, dict) else 0,
                    "message": "签到成功",
                }
            except (httpx.HTTPError, U115ApiError, ValueError) as err:
                last_error = err
                if attempt < total:
                    time.sleep(max(0.0, retry_delay))
        raise last_error or U115ApiError("115 签到失败")

    def _upload_to_oss(
        self,
        local_path: Path,
        file_size: int,
        file_sha1: str,
        target: str,
        init_result: Dict[str, Any],
    ) -> None:
        try:
            import oss2
            from oss2 import SizedFileAdapter, determine_part_size
            from oss2.models import PartInfo
        except ImportError as err:
            raise RuntimeError("缺少 oss2 依赖，无法上传未命中秒传的文件") from err

        token = self._response_data(self._request("GET", "/open/upload/get_token"))
        if not isinstance(token, dict):
            raise U115ApiError("获取 115 上传凭证失败")
        pick_code = init_result.get("pick_code")
        resume = self._response_data(
            self._request(
                "POST",
                "/open/upload/resume",
                no_error=True,
                data={"file_size": file_size, "target": target, "fileid": file_sha1, "pick_code": pick_code},
            )
        )
        callback = (resume or {}).get("callback") or init_result.get("callback") or {}
        auth = oss2.StsAuth(token.get("AccessKeyId"), token.get("AccessKeySecret"), token.get("SecurityToken"))
        bucket = oss2.Bucket(auth, token.get("endpoint"), init_result.get("bucket"))
        part_size = determine_part_size(file_size, preferred_size=10 * 1024 * 1024)
        upload_id = bucket.init_multipart_upload(
            init_result.get("object"), params={"encoding-type": "url", "sequential": ""}
        ).upload_id
        parts = []
        with local_path.open("rb") as fileobj:
            part_number, offset = 1, 0
            while offset < file_size:
                size = min(part_size, file_size - offset)
                result = bucket.upload_part(
                    init_result.get("object"), upload_id, part_number, SizedFileAdapter(fileobj, size)
                )
                parts.append(PartInfo(part_number, result.etag))
                part_number += 1
                offset += size
        headers = {"x-oss-forbid-overwrite": "false"}
        if callback.get("callback") and callback.get("callback_var"):
            headers.update(
                {
                    "X-oss-callback": oss2.utils.b64encode_as_string(callback["callback"]),
                    "x-oss-callback-var": oss2.utils.b64encode_as_string(callback["callback_var"]),
                }
            )
        bucket.complete_multipart_upload(init_result.get("object"), upload_id, parts, headers=headers)

    def _build_sign_check_data(self, local_path: Path, init_result: Dict[str, Any]) -> Dict[str, str]:
        start_text, end_text = str(init_result["sign_check"]).split("-", maxsplit=1)
        start, end = int(start_text), int(end_text)
        with local_path.open("rb") as handle:
            handle.seek(start)
            sign_value = hashlib.sha1(handle.read(end - start + 1)).hexdigest().upper()
        return {
            "pick_code": str(init_result.get("pick_code") or ""),
            "sign_key": str(init_result.get("sign_key") or ""),
            "sign_val": sign_value,
        }

    @staticmethod
    def _calc_sha1(path: Path, limit: int | None = None) -> str:
        digest = hashlib.sha1()
        remaining = limit
        with path.open("rb") as handle:
            while True:
                size = 1024 * 1024 if remaining is None else min(1024 * 1024, remaining)
                if size <= 0:
                    break
                chunk = handle.read(size)
                if not chunk:
                    break
                digest.update(chunk)
                if remaining is not None:
                    remaining -= len(chunk)
        return digest.hexdigest()

    def _request(
        self,
        method: str,
        endpoint: str,
        base_url: str | None = None,
        require_auth: bool = True,
        no_error: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return self._request_url(
            method,
            f"{base_url or self.base_url}{endpoint}",
            require_auth=require_auth,
            no_error=no_error,
            **kwargs,
        )

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
        attempts = self.read_retry_attempts if method.upper() in {"GET", "HEAD"} else 1
        for attempt in range(1, attempts + 1):
            try:
                response = self.session.request(method, url, **kwargs)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise U115ApiError("115 返回了无效响应")
                if not no_error and not self._is_response_success(payload):
                    raise U115ApiError(str(payload.get("message") or payload.get("error") or payload))
                return payload
            except (httpx.HTTPError, U115ApiError, ValueError):
                if attempt >= attempts:
                    raise
                time.sleep(self.read_retry_delay * attempt)
        raise U115ApiError("115 请求失败")

    def _ensure_auth(self) -> None:
        if not self.is_authenticated():
            raise U115AuthError("115 未登录，请配置 Cookie 或完成扫码登录")

    @staticmethod
    def _is_response_success(payload: Dict[str, Any]) -> bool:
        code = payload.get("code")
        return payload.get("state") is not False and code in (None, 0, 20004)

    @staticmethod
    def _response_data(payload: Dict[str, Any]) -> Any:
        return payload.get("data") if isinstance(payload, dict) and "data" in payload else payload

    @staticmethod
    def _is_directory(item: Dict[str, Any]) -> bool:
        return str(item.get("fc", item.get("file_category", "1"))) == "0" or (
            item.get("cid") is not None and item.get("fid") is None
        )

    @staticmethod
    def _normalize_cloud_path(path: str) -> str:
        normalized = PurePosixPath((path or "/").replace("\\", "/")).as_posix()
        if normalized == ".":
            normalized = "/"
        return normalized if normalized.startswith("/") else f"/{normalized}"

    @staticmethod
    def _item_from_info(info: Dict[str, Any], path: str) -> Dict[str, Any]:
        category = str(info.get("file_category", "1"))
        return {
            "fileid": str(info.get("file_id") or info.get("fid") or ""),
            "path": path,
            "type": "dir" if category == "0" else "file",
            "name": info.get("file_name") or PurePosixPath(path).name,
            "pickcode": info.get("pick_code") or info.get("pickcode") or "",
        }
