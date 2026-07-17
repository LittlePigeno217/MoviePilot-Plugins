from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, Iterator, Optional

import httpx
from p115cipher import rsa_decrypt, rsa_encrypt


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


@dataclass(frozen=True)
class PlaybackCopy:
    file_id: str
    pickcode: str
    auth_mode: str = ""


class U115Client:
    """独立的 115 客户端，只覆盖本插件需要的登录、浏览、上传、签到和取链能力。"""

    base_url = "https://proapi.115.com"
    passport_url = "https://passportapi.115.com"
    qrcode_status_url = "https://qrcodeapi.115.com/get/status/"
    qrcode_base_url = "https://qrcodeapi.115.com"
    points_sign_url = "https://proapi.115.com/android/2.0/user/points_sign"
    points_sign_headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://proapi.115.com",
    }
    web_files_url = "https://webapi.115.com/files"
    web_add_directory_url = "https://webapi.115.com/files/add"
    web_copy_url = "https://webapi.115.com/files/copy"
    web_delete_url = "https://webapi.115.com/rb/delete"
    cookie_download_url = "https://proapi.115.com/android/2.0/ufile/download"
    ios_user_agent = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/20D502 UDown/38.0.2"
    )
    read_retry_attempts = 3
    read_retry_delay = 1.0
    download_endpoint = "/open/ufile/downurl"
    download_request_interval = 1.0
    directory_request_interval = 1 / 3
    directory_scan_workers = 6
    directory_scan_prefetch = 12
    playback_copy_discovery_delays = (0.0, 0.5, 1.0, 2.0)
    playback_copy_directory = "多端播放"
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
        client_type: str = "",
        session: Any = None,
        token_saver: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.cookie = cookie.strip()
        self.tokens = dict(tokens or {})
        self.client_type = client_type.strip() if client_type in self.qrcode_client_types else ""
        self._auth_state: Dict[str, Any] = {}
        self._open_auth_lock = threading.RLock()
        self._download_rate_lock = threading.Lock()
        self._next_download_request_at = 0.0
        self._directory_rate_lock = threading.Lock()
        self._next_directory_request_at = 0.0
        self._playback_dir_lock = threading.Lock()
        self._playback_copy_lock = threading.Lock()
        self._playback_dir_id = ""
        self._token_saver = token_saver
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
            }
        )
        self.session.headers.pop("Content-Type", None)
        self.session.headers.pop("Cookie", None)
        self.session.headers.pop("Authorization", None)

    def export_tokens(self) -> Dict[str, Any]:
        return dict(self.tokens)

    def _persist_tokens(self, tokens: Dict[str, Any]) -> None:
        tokens = dict(tokens)
        if self._token_saver:
            self._token_saver(dict(tokens))
        self.tokens = tokens
        self._init_headers()

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
        self.client_type = client_type
        self._auth_state = {}
        self._init_headers()
        return {"success": True, "data": {"status": 2, "tip": "登录成功"}}

    def refresh_access_token(self) -> bool:
        with self._open_auth_lock:
            refresh_token = self.tokens.get("refresh_token")
            if not refresh_token:
                return False
            try:
                payload = self._request(
                    "POST",
                    "/open/refreshToken",
                    base_url=self.passport_url,
                    require_auth=False,
                    no_error=True,
                    data={"refresh_token": refresh_token},
                )
            except (httpx.HTTPError, U115ApiError, ValueError):
                return False
            data = payload.get("data") or {}
            if payload.get("code") != 0 or not isinstance(data, dict) or not data.get("access_token"):
                return False
            self._persist_tokens({**data, "refresh_time": int(time.time())})
            return True

    @staticmethod
    def _open_client_id() -> str:
        try:
            from app.core.config import settings

            return str(settings.U115_APP_ID or "").strip() or "100197847"
        except Exception:  # noqa: BLE001
            return "100197847"

    def _authorize_open_from_cookie(self) -> None:
        self._ensure_cookie_auth()
        with self._open_auth_lock:
            code_verifier = secrets.token_urlsafe(96)[:128]
            code_challenge = base64.b64encode(
                hashlib.sha256(code_verifier.encode("utf-8")).digest()
            ).decode("ascii")
            device_payload = self._request_url(
                "POST",
                f"{self.passport_url}/open/authDeviceCode",
                require_auth=False,
                data={
                    "client_id": self._open_client_id(),
                    "code_challenge": code_challenge,
                    "code_challenge_method": "sha256",
                },
            )
            device_data = device_payload.get("data") or {}
            uid = str(device_data.get("uid") or "") if isinstance(device_data, dict) else ""
            if not uid:
                raise U115AuthError("115 未返回 Open 授权设备码")

            self._request_url(
                "GET",
                f"{self.qrcode_base_url}/api/2.0/prompt.php",
                params={"uid": uid},
            )
            self._request_url(
                "GET",
                f"{self.qrcode_base_url}/api/2.0/slogin.php",
                params={"key": uid, "uid": uid, "client": 0},
            )
            token_payload = self._request_url(
                "POST",
                f"{self.passport_url}/open/deviceCodeToToken",
                require_auth=False,
                data={"uid": uid, "code_verifier": code_verifier},
            )
            token_data = token_payload.get("data") or {}
            if not isinstance(token_data, dict) or not token_data.get("access_token"):
                raise U115AuthError("115 未返回有效 Open 访问令牌")
            self._persist_tokens({**token_data, "refresh_time": int(time.time())})

    def _open_token_expired(self) -> bool:
        if not self.tokens.get("access_token"):
            return True
        try:
            expires_in = int(self.tokens.get("expires_in") or 0)
            refresh_time = int(self.tokens.get("refresh_time") or 0)
        except (TypeError, ValueError):
            return True
        if not expires_in or not refresh_time:
            return False
        return int(time.time()) >= refresh_time + max(0, expires_in - 60)

    def _ensure_open_auth(self) -> None:
        with self._open_auth_lock:
            if not self._open_token_expired():
                return
            if self.tokens.get("refresh_token") and self.refresh_access_token():
                return
            if self.cookie:
                try:
                    self._authorize_open_from_cookie()
                    return
                except (httpx.HTTPError, U115ApiError, ValueError) as err:
                    raise U115AuthError(f"无法使用 115 Cookie 获取 Open 授权: {err}") from err
            raise U115AuthError("缺少有效的 115 Open 授权，请重新扫码登录")

    def ensure_upload_ready(self) -> None:
        self._ensure_open_auth()
        try:
            self._request("GET", "/open/user/info")
        except (U115ApiError, httpx.HTTPStatusError) as err:
            error_text = str(err).lower()
            status_code = getattr(getattr(err, "response", None), "status_code", None)
            if status_code not in {401, 403} and not any(
                value in error_text for value in ("access_token", "token", "40140125", "授权")
            ):
                raise
            with self._open_auth_lock:
                if not self.refresh_access_token():
                    if not self.cookie:
                        raise U115AuthError("115 Open 授权已失效，请重新扫码登录") from err
                    self._authorize_open_from_cookie()
            self._request("GET", "/open/user/info")

    def get_dir_list(self, cid: str = "0") -> list[Dict[str, Any]]:
        if self.cookie:
            return self._get_cookie_dir_list(cid)

        return self._get_open_dir_list(cid)

    def _get_open_dir_list(self, cid: str) -> list[Dict[str, Any]]:
        items: list[Dict[str, Any]] = []
        offset = 0
        page_size = 1000
        while True:
            self._acquire_directory_request_slot()
            payload = self._request(
                "GET",
                "/open/ufile/files",
                params={
                    "cid": int(cid or 0),
                    "limit": page_size,
                    "offset": offset,
                    "cur": True,
                    "show_dir": 1,
                },
            )
            data = self._response_data(payload)
            if not isinstance(data, list):
                if offset:
                    raise U115ApiError("115 Open 目录分页返回了无效响应")
                self._acquire_directory_request_slot()
                payload = self._request(
                    "POST",
                    "/open/folder/list",
                    data={"cid": str(cid or "0")},
                )
                data = self._response_data(payload)
                if isinstance(data, dict):
                    data = data.get("items", [])
                return list(data) if isinstance(data, list) else []
            batch = list(data)
            items.extend(batch)
            if not batch or len(batch) < page_size:
                return items
            offset += len(batch)

    def _acquire_directory_request_slot(self) -> None:
        interval = max(0.0, float(self.directory_request_interval))
        if not interval:
            return
        with self._directory_rate_lock:
            now = time.monotonic()
            delay = max(0.0, self._next_directory_request_at - now)
            self._next_directory_request_at = max(now, self._next_directory_request_at) + interval
        if delay:
            time.sleep(delay)

    def _acquire_download_request_slot(self) -> None:
        interval = max(0.0, float(self.download_request_interval))
        if not interval:
            return
        with self._download_rate_lock:
            now = time.monotonic()
            delay = max(0.0, self._next_download_request_at - now)
            self._next_download_request_at = max(now, self._next_download_request_at) + interval
        if delay:
            time.sleep(delay)

    @staticmethod
    def _directory_page_complete(
        payload: Dict[str, Any], item_count: int, batch_size: int, page_size: int
    ) -> bool:
        try:
            total = int(payload.get("count"))
        except (TypeError, ValueError):
            total = -1
        if total >= 0:
            return item_count >= total
        return batch_size < page_size

    def _get_cookie_dir_list(self, cid: str) -> list[Dict[str, Any]]:
        items: list[Dict[str, Any]] = []
        offset = 0
        page_size = 1150
        while True:
            self._acquire_directory_request_slot()
            payload = self._request_url(
                "GET",
                self.web_files_url,
                headers={"User-Agent": self.ios_user_agent},
                params={
                    "aid": 1,
                    "cid": int(cid or 0),
                    "count_folders": 1,
                    "limit": page_size,
                    "offset": offset,
                    "record_open_time": 1,
                    "show_dir": 1,
                    "cur": 1,
                    "fc_mix": 1,
                    "asc": 1,
                    "o": "user_ptime",
                    "custom_order": 1,
                },
            )
            data = self._response_data(payload)
            batch = list(data) if isinstance(data, list) else []
            items.extend(batch)
            if self._directory_page_complete(payload, len(items), len(batch), page_size):
                return items
            offset += len(batch)

    def iter_files(self, cid: str) -> Iterator[Dict[str, Any]]:
        root_cid = str(cid or "0")
        pending = deque([(root_cid, "")])
        seen_directories = {root_cid}
        in_flight = {}
        workers = max(1, int(self.directory_scan_workers))
        prefetch = max(workers, int(self.directory_scan_prefetch))

        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="p115-strm-scan") as executor:
            while pending or in_flight:
                while pending and len(in_flight) < prefetch:
                    current_cid, prefix = pending.popleft()
                    future = executor.submit(self.get_dir_list, current_cid)
                    in_flight[future] = (current_cid, prefix)
                done, _ = wait(tuple(in_flight), return_when=FIRST_COMPLETED)
                for future in done:
                    _current_cid, prefix = in_flight.pop(future)
                    for raw in future.result():
                        name = self._item_name(raw)
                        if not name:
                            continue
                        rel_path = f"{prefix}/{name}" if prefix else name
                        if self._is_directory(raw):
                            child_cid = self._item_id(raw)
                            if child_cid and child_cid not in seen_directories:
                                seen_directories.add(child_cid)
                                pending.append((child_cid, rel_path))
                            continue
                        yield {
                            "name": name,
                            "pickcode": raw.get("pc") or raw.get("pick_code") or raw.get("pickcode") or "",
                            "size": raw.get("fs") or raw.get("s") or raw.get("size_byte") or raw.get("size") or 0,
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
                    for item in self._get_open_dir_list(current["fileid"])
                    if self._is_directory(item)
                    and self._item_name(item) == name
                ),
                None,
            )
            if found:
                current = {
                    "fileid": self._item_id(found),
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
                        for item in self._get_open_dir_list(current["fileid"])
                        if self._is_directory(item)
                        and self._item_name(item) == name
                    ),
                    None,
                )
                if not found:
                    raise U115ApiError(f"创建 115 目录失败: {name}")
                data = found
            current = {
                "fileid": self._item_id(data),
                "path": f"{current['path'].rstrip('/')}/{name}",
                "name": name,
                "type": "dir",
            }
        return current

    def upload_file(self, target_dir: Dict[str, Any], local_path: Path) -> UploadResult:
        self._ensure_open_auth()
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

        file_item = self._upload_file_item(init_result, local_path.name)
        if int(init_result.get("status") or 0) == 2:
            return UploadResult(True, reused=True, file_item=file_item)

        self._upload_to_oss(local_path, file_size, file_sha1, init_data["target"], init_result)
        return UploadResult(True, file_item=file_item)

    @staticmethod
    def _upload_file_item(data: Dict[str, Any], file_name: str) -> Optional[Dict[str, Any]]:
        file_id = data.get("file_id") or data.get("fileid") or data.get("fid")
        pickcode = data.get("pick_code") or data.get("pickcode") or data.get("pc")
        if not file_id and not pickcode:
            return None
        item: Dict[str, Any] = {"name": file_name}
        if file_id:
            item["fileid"] = str(file_id)
        if pickcode:
            item["pickcode"] = str(pickcode)
        return item

    def _playback_auth_mode(self, mode: str = "") -> str:
        mode = str(mode or "").strip().lower()
        if not mode:
            mode = "cookie" if self.cookie else "open"
        if mode not in {"cookie", "open"}:
            raise ValueError(f"不支持的 302 取链模式: {mode}")
        if mode == "cookie":
            self._ensure_cookie_auth()
        return mode

    def get_download_url(
        self,
        pickcode: str,
        user_agent: str = "",
        mode: str = "",
    ) -> Optional[str]:
        if not pickcode:
            return None
        mode = self._playback_auth_mode(mode)
        if mode == "cookie":
            self._acquire_download_request_slot()
            return self._get_cookie_download_url(pickcode, user_agent)
        return self._get_open_download_url(pickcode, user_agent)

    def _get_cookie_download_url(self, pickcode: str, user_agent: str) -> Optional[str]:
        encrypted = rsa_encrypt(
            json.dumps(
                {"pick_code": pickcode},
                separators=(",", ":"),
            ).encode("utf-8")
        ).decode("utf-8")
        payload = self._request_url(
            "POST",
            self.cookie_download_url,
            data={"data": encrypted},
            headers={"User-Agent": user_agent},
        )
        encrypted_data = payload.get("data")
        if not encrypted_data:
            raise U115ApiError("115 Cookie 取链未返回加密数据")
        try:
            data = json.loads(rsa_decrypt(encrypted_data))
        except (TypeError, ValueError, json.JSONDecodeError) as err:
            raise U115ApiError("115 Cookie 下载地址解析失败") from err
        if not isinstance(data, dict):
            raise U115ApiError("115 Cookie 下载地址响应无效")
        return self._extract_download_url(data)

    @staticmethod
    def _extract_download_url(data: Any) -> Optional[str]:
        if not isinstance(data, dict):
            return None
        candidates = [data]
        candidates.extend(value for value in data.values() if isinstance(value, dict))
        for candidate in candidates:
            url = candidate.get("url")
            if isinstance(url, dict):
                url = url.get("url")
            if isinstance(url, str) and url:
                return url
        return None

    def _get_open_download_url(self, pickcode: str, user_agent: str) -> Optional[str]:
        payload = self._request(
            "POST",
            "/open/ufile/downurl",
            no_error=True,
            data={"pick_code": pickcode},
            headers={"User-Agent": user_agent},
        )
        data = self._response_data(payload)
        return self._extract_download_url(data)

    def download_file(self, pickcode: str, output: Path, create_parent: bool = True) -> None:
        user_agent = self.ios_user_agent
        url = self.get_download_url(pickcode, user_agent=user_agent)
        if not url:
            raise U115ApiError("未获取到 115 下载地址")
        if create_parent:
            output.parent.mkdir(parents=True, exist_ok=True)
        temp_output = output.with_name(f".{output.name}.{threading.get_ident()}.tmp")
        try:
            with httpx.stream(
                "GET",
                url,
                headers={"User-Agent": user_agent},
                follow_redirects=True,
                timeout=60.0,
            ) as response:
                response.raise_for_status()
                with temp_output.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        handle.write(chunk)
            temp_output.replace(output)
        finally:
            temp_output.unlink(missing_ok=True)

    @staticmethod
    def _pickcode_to_file_id(pickcode: str) -> int:
        try:
            from p115pickcode import to_id
        except ImportError as err:
            raise U115ApiError("缺少 p115pickcode 依赖，无法启用多端播放") from err
        return int(to_id(pickcode))

    def _playback_directory_id(self, mode: str) -> str:
        if self._playback_dir_id:
            return self._playback_dir_id
        with self._playback_dir_lock:
            if not self._playback_dir_id:
                if mode == "cookie":
                    items = self._get_cookie_dir_list("0")
                    directory = next(
                        (
                            item
                            for item in items
                            if self._is_directory(item)
                            and self._item_name(item) == self.playback_copy_directory
                        ),
                        None,
                    )
                    if directory is None:
                        payload = self._request_url(
                            "POST",
                            self.web_add_directory_url,
                            data={"cname": self.playback_copy_directory, "pid": 0},
                            headers={"User-Agent": self.ios_user_agent},
                        )
                        data = self._response_data(payload)
                        directory = data if isinstance(data, dict) else payload
                    self._playback_dir_id = self._item_id(directory)
                else:
                    directory = self.ensure_remote_dir(self.playback_copy_directory)
                    self._playback_dir_id = str(directory.get("fileid") or "")
                if not self._playback_dir_id:
                    raise U115ApiError("创建 115 多端播放目录失败")
        return self._playback_dir_id

    def create_playback_copy(self, pickcode: str, mode: str = "") -> PlaybackCopy:
        mode = self._playback_auth_mode(mode)
        target_cid = self._playback_directory_id(mode)
        source_file_id = self._pickcode_to_file_id(pickcode)
        with self._playback_copy_lock:
            baseline_item = self._latest_playback_copy_item(target_cid, mode)
            baseline_file_id = self._playback_copy_file_id(baseline_item or {})
            if mode == "cookie":
                self._request_url(
                    "POST",
                    self.web_copy_url,
                    data={"fid": source_file_id, "pid": int(target_cid)},
                    headers={"User-Agent": self.ios_user_agent},
                )
            else:
                self._request(
                    "POST",
                    "/open/ufile/copy",
                    data={"file_id": source_file_id, "pid": int(target_cid)},
                    headers={"User-Agent": self.ios_user_agent},
                )
            confirmed_file_id = ""
            last_error: Exception | None = None
            for delay in self.playback_copy_discovery_delays:
                if delay:
                    time.sleep(delay)
                item = self._latest_playback_copy_item(target_cid, mode)
                if not item:
                    continue
                candidate_file_id = self._playback_copy_file_id(item)
                if not candidate_file_id or candidate_file_id == baseline_file_id:
                    continue
                try:
                    copy = self._playback_copy_from_item(item)
                    return PlaybackCopy(copy.file_id, copy.pickcode, mode)
                except Exception as err:  # noqa: BLE001
                    confirmed_file_id = candidate_file_id
                    last_error = err
            if confirmed_file_id:
                try:
                    self.delete_file(confirmed_file_id, mode)
                except Exception as cleanup_err:  # noqa: BLE001
                    raise U115ApiError(
                        f"读取多端播放副本失败，且无法清理临时副本: {cleanup_err}"
                    ) from last_error
            if last_error is not None:
                raise last_error
            raise U115ApiError("复制多端播放文件后未发现新副本")

    def _latest_playback_copy_item(
        self,
        target_cid: str,
        mode: str,
    ) -> Optional[Dict[str, Any]]:
        params = {
            "cid": int(target_cid),
            "limit": 1,
            "offset": 0,
            "cur": 1,
            "show_dir": 1,
            "o": "user_ptime",
            "asc": 0,
            "custom_order": 2,
        }
        if mode == "cookie":
            payload = self._request_url(
                "GET",
                self.web_files_url,
                params=params,
                headers={"User-Agent": self.ios_user_agent},
            )
        else:
            payload = self._request(
                "GET",
                "/open/ufile/files",
                params=params,
                headers={"User-Agent": self.ios_user_agent},
            )
        data = self._response_data(payload)
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            return None
        return data[0]

    @staticmethod
    def _playback_copy_file_id(item: Dict[str, Any]) -> str:
        return str(item.get("fid") or item.get("file_id") or "")

    @staticmethod
    def _playback_copy_from_item(item: Dict[str, Any]) -> PlaybackCopy:
        copied_pickcode = str(
            item.get("pc") or item.get("pick_code") or item.get("pickcode") or ""
        )
        copied_file_id = U115Client._playback_copy_file_id(item)
        if not copied_pickcode or not copied_file_id:
            raise U115ApiError("115 多端播放副本信息不完整")
        return PlaybackCopy(file_id=copied_file_id, pickcode=copied_pickcode)

    def delete_file(self, file_id: str, mode: str = "") -> None:
        mode = self._playback_auth_mode(mode)
        if mode == "cookie":
            self._request_url(
                "POST",
                self.web_delete_url,
                data={"fid": int(file_id)},
                headers={"User-Agent": self.ios_user_agent},
            )
        else:
            self._request(
                "POST",
                "/open/ufile/delete",
                data={"file_ids": int(file_id)},
                headers={"User-Agent": self.ios_user_agent},
            )

    def checkin(self, attempts: int = 3, retry_delay: float = 3.0) -> Dict[str, Any]:
        self._ensure_cookie_auth()
        user_id = self._cookie_user_id()
        current = self._request_url(
            "GET",
            self.points_sign_url,
            headers=self.points_sign_headers,
        )
        data = self._response_data(current) or {}
        if isinstance(data, dict) and int(data.get("is_sign_today") or 0) == 1:
            return {"already": True, "message": "今日已签到"}
        total = max(1, int(attempts))
        last_error: Exception | None = None
        for attempt in range(1, total + 1):
            try:
                token_time = int(time.time())
                token = hashlib.sha1(
                    f"{user_id}-Points_Sign@#115-{token_time}".encode("utf-8")
                ).hexdigest()
                payload = self._request_url(
                    "POST",
                    self.points_sign_url,
                    headers=self.points_sign_headers,
                    data={"token": token, "token_time": token_time},
                )
                data = self._response_data(payload) or {}
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

    def _cookie_user_id(self) -> int:
        for part in self.cookie.split(";"):
            key, separator, value = part.strip().partition("=")
            if key.upper() != "UID" or not separator:
                continue
            user_id = value.partition("_")[0]
            if user_id.isdigit():
                return int(user_id)
            break
        raise U115AuthError("115 Cookie 缺少有效 UID，请重新扫码登录")

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
        if require_auth:
            self._ensure_open_auth()
            access_token = str(self.tokens.get("access_token") or "")
            if not access_token:
                raise U115AuthError("缺少有效的 115 Open 授权，请重新扫码登录")
            kwargs["headers"] = self._scoped_auth_headers(
                kwargs.get("headers"),
                bearer=access_token,
            )
            require_auth = False
        if endpoint == self.download_endpoint:
            self._acquire_download_request_slot()
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
        cookie_request = require_auth
        if require_auth:
            self._ensure_cookie_auth()
            kwargs["headers"] = self._scoped_auth_headers(
                kwargs.get("headers"),
                cookie=self.cookie,
            )
        attempts = self.read_retry_attempts if method.upper() in {"GET", "HEAD"} else 1
        for attempt in range(1, attempts + 1):
            try:
                response = self.session.request(method, url, **kwargs)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise U115ApiError("115 返回了无效响应")
                if not no_error and not self._is_response_success(payload):
                    message = str(payload.get("message") or payload.get("error") or payload)
                    if cookie_request and self._is_cookie_auth_error(payload, message):
                        raise U115AuthError("115 Cookie 已失效，请重新扫码登录")
                    raise U115ApiError(message)
                return payload
            except httpx.HTTPStatusError as err:
                status_code = err.response.status_code
                if 400 <= status_code < 500 or attempt >= attempts:
                    raise
                time.sleep(self.read_retry_delay * attempt)
            except (httpx.HTTPError, U115ApiError, ValueError):
                if attempt >= attempts:
                    raise
                time.sleep(self.read_retry_delay * attempt)
        raise U115ApiError("115 请求失败")

    def _ensure_cookie_auth(self) -> None:
        if not self.cookie:
            raise U115AuthError("缺少有效的 115 Cookie，请重新扫码登录")

    @staticmethod
    def _scoped_auth_headers(
        headers: Optional[Dict[str, Any]],
        *,
        cookie: str = "",
        bearer: str = "",
    ) -> Dict[str, Any]:
        scoped = dict(headers or {})
        for key in tuple(scoped):
            if str(key).lower() in {"authorization", "cookie"}:
                scoped.pop(key, None)
        if cookie:
            scoped["Cookie"] = cookie
        if bearer:
            scoped["Authorization"] = f"Bearer {bearer}"
        return scoped

    @staticmethod
    def _is_cookie_auth_error(payload: Dict[str, Any], message: str) -> bool:
        errno = payload.get("errno") or payload.get("code")
        normalized = message.lower()
        return errno in (990001, "990001") or any(
            marker in normalized
            for marker in ("登录超时", "请重新登录", "重新扫码", "cookie")
        )

    @staticmethod
    def _is_response_success(payload: Dict[str, Any]) -> bool:
        state = payload.get("state")
        if state in (True, 1, "1"):
            return True
        code = payload.get("code")
        if state in (False, 0, "0"):
            return code in (0, "0", 20004, "20004")
        return code in (None, "", 0, "0", 20004, "20004")

    @staticmethod
    def _response_data(payload: Dict[str, Any]) -> Any:
        return payload.get("data") if isinstance(payload, dict) and "data" in payload else payload

    @staticmethod
    def _is_directory(item: Dict[str, Any]) -> bool:
        return str(item.get("fc", item.get("file_category", "1"))) == "0" or (
            item.get("cid") is not None and item.get("fid") is None
        )

    @staticmethod
    def _item_name(item: Dict[str, Any]) -> str:
        return str(
            item.get("fn")
            or item.get("file_name")
            or item.get("n")
            or item.get("category_name")
            or ""
        )

    @staticmethod
    def _item_id(item: Dict[str, Any]) -> str:
        return str(
            item.get("cid")
            or item.get("file_id")
            or item.get("fid")
            or item.get("category_id")
            or ""
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
        raw_size = next(
            (
                info.get(key)
                for key in ("size_byte", "file_size", "size", "fs")
                if info.get(key) is not None
            ),
            None,
        )
        try:
            size = int(raw_size) if raw_size is not None else None
        except (TypeError, ValueError):
            size = None
        return {
            "fileid": U115Client._item_id(info),
            "path": path,
            "type": "dir" if category == "0" else "file",
            "name": U115Client._item_name(info) or PurePosixPath(path).name,
            "pickcode": info.get("pick_code") or info.get("pickcode") or "",
            "size": size,
        }
