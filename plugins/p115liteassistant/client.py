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

from app.log import logger


class U115AuthError(RuntimeError):
    pass


class U115ApiError(RuntimeError):
    pass


class U115AccessLimitError(U115ApiError):
    pass


class _U115OpenAuthError(U115ApiError):
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
    web_copy_url = "https://webapi.115.com/files/copy"
    web_delete_url = "https://webapi.115.com/rb/delete"
    life_calendar_url = "https://life.115.com/api/1.0/web/1.0/calendar/setoption"
    life_behavior_ios_url = "https://proapi.115.com/ios/behavior/detail"
    life_behavior_web_url = "https://webapi.115.com/behavior/detail"
    cookie_download_url = "https://proapi.115.com/android/2.0/ufile/download"
    ios_user_agent = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/20D502 UDown/38.0.2"
    )
    read_retry_attempts = 3
    read_retry_delay = 1.0
    transient_http_statuses = frozenset({408, 425, 429, 500, 502, 503, 504})
    rate_limit_default_delay = 60.0
    rate_limit_delay_padding = 5.0
    http_rate_limit_attempts = 3
    open_access_limit_attempts = 6
    open_access_limit_delay = 70.0
    upload_request_timeout = 120.0
    upload_part_attempts = 3
    upload_part_retry_delay = 1.0
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
        self._request_limit_context = threading.local()
        self._remote_dir_cache_lock = threading.RLock()
        self._remote_dir_cache: Dict[str, Dict[str, Any]] = {
            "/": {"fileid": "0", "path": "/", "name": "", "type": "dir"}
        }
        self._playback_dir_lock = threading.Lock()
        self._playback_copy_lock = threading.Lock()
        self._playback_dir_id = ""
        self._token_saver = token_saver
        self.session = session or self._create_session()
        self._init_headers()

    @staticmethod
    def _create_session() -> Any:
        import httpx

        return httpx.Client(follow_redirects=True, timeout=20.0)

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
            except U115AccessLimitError:
                raise
            except (httpx.HTTPError, U115ApiError, ValueError):
                return False
            message = str(payload.get("message") or payload.get("error") or payload)
            if self._is_access_limit_message(message):
                raise U115AccessLimitError(message)
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
                except U115AccessLimitError:
                    raise
                except (httpx.HTTPError, U115ApiError, ValueError) as err:
                    raise U115AuthError(f"无法使用 115 Cookie 获取 Open 授权: {err}") from err
            raise U115AuthError("缺少有效的 115 Open 授权，请重新扫码登录")

    @staticmethod
    def _is_open_auth_error(err: Exception) -> bool:
        status_code = getattr(getattr(err, "response", None), "status_code", None)
        return status_code in {401, 403}

    @staticmethod
    def _is_open_auth_payload(payload: Dict[str, Any]) -> bool:
        code = str(payload.get("code") or payload.get("errno") or "")
        return code in {"401", "403", "40140125"}

    def _recover_open_auth(self, failed_access_token: str, err: Exception) -> None:
        with self._open_auth_lock:
            current_access_token = str(self.tokens.get("access_token") or "")
            if current_access_token and current_access_token != failed_access_token:
                return
            if self.refresh_access_token():
                return
            if not self.cookie:
                raise U115AuthError("115 Open 授权已失效，请重新扫码登录") from err
            try:
                self._authorize_open_from_cookie()
            except U115AccessLimitError:
                raise
            except (httpx.HTTPError, U115ApiError, U115AuthError, ValueError) as auth_err:
                raise U115AuthError(
                    f"无法使用 115 Cookie 获取 Open 授权: {auth_err}"
                ) from auth_err

    def ensure_upload_ready(self) -> None:
        self._request("GET", "/open/user/info")

    def get_dir_list(self, cid: str = "0") -> list[Dict[str, Any]]:
        return self._get_open_dir_list(cid)

    def _get_open_dir_list(self, cid: str) -> list[Dict[str, Any]]:
        items: list[Dict[str, Any]] = []
        offset = 0
        page_size = 1150
        while True:
            self._acquire_directory_request_slot()
            payload = self._request(
                "GET",
                "/open/ufile/files",
                params={
                    "cid": int(cid or 0),
                    "limit": page_size,
                    "offset": offset,
                    "show_dir": 1,
                    "o": "user_utime",
                    "asc": 0,
                },
            )
            data = self._response_data(payload)
            if not isinstance(data, list):
                raise U115ApiError("115 Open 目录分页返回了无效响应")
            batch = list(data)
            items.extend(batch)
            next_offset = offset + len(batch)
            try:
                total = int(payload.get("count"))
            except (TypeError, ValueError):
                total = -1
            if not batch or (total >= 0 and next_offset >= total):
                return items
            if total < 0 and len(batch) < page_size:
                return items
            offset = next_offset

    def _acquire_directory_request_slot(self) -> None:
        self._raise_if_shared_access_limited()
        interval = max(0.0, float(self.directory_request_interval))
        if not interval:
            return
        with self._directory_rate_lock:
            now = time.monotonic()
            delay = max(0.0, self._next_directory_request_at - now)
            self._next_directory_request_at = max(now, self._next_directory_request_at) + interval
        if delay:
            self._wait_for_request_retry(delay)
        self._raise_if_shared_access_limited()

    @staticmethod
    def new_access_limit_state() -> Dict[str, Any]:
        return {
            "event": threading.Event(),
            "lock": threading.Lock(),
            "message": "",
        }

    def run_with_access_limit_state(
        self,
        state: Dict[str, Any],
        operation: Callable[[], Any],
    ) -> Any:
        previous = getattr(self._request_limit_context, "limit_state", None)
        self._request_limit_context.limit_state = state
        try:
            self._raise_if_shared_access_limited()
            return operation()
        except U115AccessLimitError as err:
            self._mark_shared_access_limited(err)
            raise
        finally:
            self._request_limit_context.limit_state = previous

    def _raise_if_shared_access_limited(self) -> None:
        state = getattr(self._request_limit_context, "limit_state", None)
        if state is None:
            return
        with state["lock"]:
            if not state["event"].is_set():
                return
            message = str(state.get("message") or "").strip()
        raise U115AccessLimitError(message or "115 并发任务因访问上限中止")

    def _mark_shared_access_limited(self, error: Optional[BaseException] = None) -> bool:
        state = getattr(self._request_limit_context, "limit_state", None)
        if state is None:
            return False
        with state["lock"]:
            if error is not None and not state.get("message"):
                state["message"] = str(error)
            first = not state["event"].is_set()
            state["event"].set()
        return first

    def _wait_for_request_retry(self, delay: float) -> None:
        state = getattr(self._request_limit_context, "limit_state", None)
        if state is None:
            time.sleep(max(0.0, float(delay)))
            return
        if state["event"].wait(max(0.0, float(delay))):
            self._raise_if_shared_access_limited()
            raise U115AccessLimitError("115 并发任务因访问上限中止")

    def _acquire_download_request_slot(self) -> None:
        self._raise_if_shared_access_limited()
        interval = max(0.0, float(self.download_request_interval))
        if not interval:
            return
        with self._download_rate_lock:
            now = time.monotonic()
            delay = max(0.0, self._next_download_request_at - now)
            self._next_download_request_at = max(now, self._next_download_request_at) + interval
        if delay:
            self._wait_for_request_retry(delay)
        self._raise_if_shared_access_limited()

    def iter_files(
        self,
        cid: str,
        access_limit_state: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Dict[str, Any]]:
        root_cid = str(cid or "0")
        pending = deque([(root_cid, "")])
        seen_directories = {root_cid}
        in_flight = {}
        workers = max(1, int(self.directory_scan_workers))
        prefetch = max(workers, int(self.directory_scan_prefetch))
        scan_abort = threading.Event()
        scan_limit = (
            access_limit_state
            if access_limit_state is not None
            else self.new_access_limit_state()
        )

        def fetch_directory(current_cid: str) -> list[Dict[str, Any]]:
            if scan_abort.is_set():
                return []
            try:
                return self.run_with_access_limit_state(
                    scan_limit,
                    lambda: self.get_dir_list(current_cid),
                )
            except BaseException as err:
                scan_abort.set()
                if isinstance(err, U115AccessLimitError):
                    with scan_limit["lock"]:
                        scan_limit["event"].set()
                raise

        executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="p115-strm-scan")
        try:
            while pending or in_flight:
                while pending and len(in_flight) < prefetch:
                    current_cid, prefix = pending.popleft()
                    future = executor.submit(fetch_directory, current_cid)
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
                            "fileid": self._item_id(raw),
                            "parent_id": str(_current_cid),
                            "name": name,
                            "pickcode": raw.get("pc") or raw.get("pick_code") or raw.get("pickcode") or "",
                            "size": raw.get("fs") or raw.get("s") or raw.get("size_byte") or raw.get("size") or 0,
                            "mtime": self._item_mtime(raw),
                            "rel_path": rel_path,
                        }
        except BaseException:
            scan_abort.set()
            for future in in_flight:
                future.cancel()
            executor.shutdown(wait=True, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True)

    def get_item(self, path: str) -> Optional[Dict[str, Any]]:
        normalized = self._normalize_cloud_path(path)
        payload = self._request(
            "POST", "/open/folder/get_info", no_error=True, data={"path": normalized}
        )
        return self._parse_open_item(payload, requested_path=normalized)

    def get_item_by_id(self, file_id: str | int) -> Optional[Dict[str, Any]]:
        normalized_id = str(file_id or "").strip()
        if not normalized_id:
            raise ValueError("115 文件 ID 不能为空")
        if normalized_id == "0":
            return {
                "fileid": "0",
                "parent_id": "0",
                "path": "/",
                "type": "dir",
                "name": "",
                "pickcode": "",
                "size": None,
                "mtime": 0,
            }
        payload = self._request(
            "POST",
            "/open/folder/get_info",
            no_error=True,
            data={"file_id": normalized_id},
        )
        return self._parse_open_item(payload, strict=False)

    def _parse_open_item(
        self,
        payload: Dict[str, Any],
        requested_path: str = "",
        strict: bool = True,
    ) -> Optional[Dict[str, Any]]:
        if not self._is_response_success(payload):
            code = str(payload.get("code") or payload.get("errno") or "")
            message = str(payload.get("message") or payload.get("error") or payload)
            if code in {"10014", "20018", "404"} or any(
                marker in message for marker in ("不存在", "未找到", "找不到")
            ):
                return None
            raise U115ApiError(message)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise U115ApiError("115 文件信息响应无效")
        file_id = self._item_id(data)
        category = data.get("file_category", data.get("fc"))
        if category in (None, ""):
            category = "0" if not (
                data.get("pick_code") or data.get("pickcode") or data.get("pc")
            ) else "1"
        name = self._item_name(data)
        path = requested_path or self._path_from_open_info(data)
        if not file_id or (not name and path != "/"):
            raise U115ApiError("115 文件信息字段不完整")
        category = str(category)
        if category not in {"0", "1"}:
            raise U115ApiError(f"115 文件信息类型无效: {category}")
        if strict and self._item_mtime(data) <= 0:
            raise U115ApiError("115 文件信息缺少有效修改时间")
        if category == "1":
            if not str(
                data.get("pick_code") or data.get("pickcode") or data.get("pc") or ""
            ).strip() and strict:
                raise U115ApiError("115 文件信息缺少 pick_code")
            size = self._item_size(data)
            if (size is None or size < 0) and strict:
                raise U115ApiError("115 文件信息缺少有效文件大小")
        item = self._item_from_info(data, path)
        paths = data.get("paths")
        if isinstance(paths, list) and paths:
            parent = paths[-1]
            if isinstance(parent, dict):
                item["parent_id"] = str(
                    parent.get("file_id")
                    or parent.get("cid")
                    or parent.get("id")
                    or "0"
                )
        if "parent_id" not in item:
            item["parent_id"] = str(data.get("parent_id") or data.get("pid") or "0")
        return item

    @classmethod
    def _path_from_open_info(cls, info: Dict[str, Any]) -> str:
        direct = info.get("path") or info.get("file_path")
        if isinstance(direct, str) and direct.strip():
            normalized = cls._normalize_cloud_path(direct)
            name = cls._item_name(info)
            if name and PurePosixPath(normalized).name != name:
                normalized = cls._normalize_cloud_path(f"{normalized.rstrip('/')}/{name}")
            return normalized

        path_value = info.get("paths")
        if isinstance(path_value, str) and path_value.strip():
            normalized = cls._normalize_cloud_path(path_value)
            name = cls._item_name(info)
            if name and PurePosixPath(normalized).name != name:
                normalized = cls._normalize_cloud_path(f"{normalized.rstrip('/')}/{name}")
            return normalized

        parts: list[str] = []
        if isinstance(path_value, list):
            for entry in path_value:
                if isinstance(entry, dict):
                    entry_id = str(
                        entry.get("file_id")
                        or entry.get("cid")
                        or entry.get("id")
                        or ""
                    )
                    name = str(
                        entry.get("file_name")
                        or entry.get("name")
                        or entry.get("n")
                        or ""
                    ).strip("/\\")
                    if entry_id == "0" or name in {"根目录", "全部文件", "文件"}:
                        continue
                    if name:
                        parts.append(name)
                elif isinstance(entry, str):
                    parts.extend(
                        part for part in entry.replace("\\", "/").split("/") if part
                    )
        name = cls._item_name(info)
        if name and (not parts or parts[-1] != name):
            parts.append(name)
        if not parts:
            raise U115ApiError("115 文件信息缺少完整路径")
        return cls._normalize_cloud_path("/" + "/".join(parts))

    def enable_life_events(self) -> None:
        payload = self._request_url(
            "POST",
            self.life_calendar_url,
            data={"locus": 1, "open_life": 1},
            headers={"User-Agent": self.ios_user_agent},
        )
        if not self._is_response_success(payload):
            message = str(payload.get("message") or payload.get("error") or payload)
            raise U115ApiError(f"开启 115 生活事件失败: {message}")

    def get_life_events_page(
        self,
        *,
        app: str = "ios",
        offset: int = 0,
        limit: int = 1000,
        event_type: str = "",
        date: str = "",
    ) -> Dict[str, Any]:
        normalized_app = str(app or "ios").strip().lower()
        if normalized_app not in {"ios", "web"}:
            raise ValueError(f"不支持的 115 生活事件接口: {normalized_app}")
        url = (
            self.life_behavior_web_url
            if normalized_app == "web"
            else self.life_behavior_ios_url
        )
        params = {
            "type": str(event_type or ""),
            "date": str(date or ""),
            "limit": min(1000, max(1, int(limit))),
            "offset": max(0, int(offset)),
        }
        payload = self._request_url(
            "GET",
            url,
            params=params,
            headers={"User-Agent": self.ios_user_agent},
        )
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("list"), list):
            raise U115ApiError("115 生活事件响应无效")
        return {
            "events": [item for item in data["list"] if isinstance(item, dict)],
            "count": int(data.get("count") or 0),
        }

    def pull_life_events(
        self,
        *,
        app: str = "ios",
        offset: int = 0,
        limit: int = 1000,
    ) -> list[Dict[str, Any]]:
        """兼容上游命名的单页生活事件读取方法。"""

        return list(
            self.get_life_events_page(
                app=app,
                offset=offset,
                limit=limit,
            ).get("events")
            or []
        )

    def ensure_remote_dir(self, path: str) -> Dict[str, Any]:
        cloud_path = self._normalize_cloud_path(path)
        current = self._cached_remote_dir("/")
        if cloud_path == "/":
            return current
        for name in PurePosixPath(cloud_path).parts:
            if name == "/":
                continue
            child_path = f"{current['path'].rstrip('/')}/{name}"
            cached = self._cached_remote_dir(child_path)
            if cached:
                current = cached
                continue
            found = self._find_open_directory(current["fileid"], name)
            if found:
                current = {
                    "fileid": self._item_id(found),
                    "path": child_path,
                    "name": name,
                    "type": "dir",
                }
                self._remember_remote_dir(current)
                continue
            payload = self._request(
                "POST",
                "/open/folder/add",
                no_error=True,
                data={"pid": int(current["fileid"] or 0), "file_name": name},
            )
            data = self._response_data(payload)
            if self._is_existing_directory_response(payload):
                found = self._find_open_directory(current["fileid"], name)
                if not found:
                    raise U115ApiError(f"创建 115 目录失败: {name}（目录已存在但无法读取）")
                data = found
            elif not isinstance(data, dict) or not self._item_id(data):
                message = str(payload.get("message") or payload.get("error") or payload)
                raise U115ApiError(f"创建 115 目录失败: {name}，原因：{message}")
            current = {
                "fileid": self._item_id(data),
                "path": child_path,
                "name": name,
                "type": "dir",
            }
            self._remember_remote_dir(current)
        return current

    def _cached_remote_dir(self, path: str) -> Optional[Dict[str, Any]]:
        with self._remote_dir_cache_lock:
            item = self._remote_dir_cache.get(path)
            return dict(item) if item else None

    def _remember_remote_dir(self, item: Dict[str, Any]) -> None:
        path = self._normalize_cloud_path(str(item.get("path") or "/"))
        with self._remote_dir_cache_lock:
            self._remote_dir_cache[path] = dict(item)

    def clear_remote_dir_cache(self) -> None:
        with self._remote_dir_cache_lock:
            self._remote_dir_cache = {
                "/": {"fileid": "0", "path": "/", "name": "", "type": "dir"}
            }

    def _find_open_directory(self, parent_id: str, name: str) -> Optional[Dict[str, Any]]:
        return next(
            (
                item
                for item in self._get_open_dir_list(parent_id)
                if self._is_directory(item) and self._item_name(item) == name
            ),
            None,
        )

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
        payload = self._request(
            "POST",
            "/open/upload/init",
            data=init_data,
            timeout=self.upload_request_timeout,
        )
        init_result = self._response_data(payload)
        if not isinstance(init_result, dict):
            return UploadResult(False, message="115 上传初始化失败")

        if int(init_result.get("code") or 0) in {700, 701} and init_result.get("sign_check"):
            first_init_result = dict(init_result)
            init_data.update(self._build_sign_check_data(local_path, init_result))
            payload = self._request(
                "POST",
                "/open/upload/init",
                data=init_data,
                timeout=self.upload_request_timeout,
            )
            second_init_result = self._response_data(payload)
            if not isinstance(second_init_result, dict):
                return UploadResult(False, message="115 上传二次认证失败")
            init_result = self._merge_upload_init_results(
                first_init_result,
                second_init_result,
            )

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

    @staticmethod
    def _merge_upload_init_results(
        first: Dict[str, Any],
        second: Dict[str, Any],
    ) -> Dict[str, Any]:
        merged = {**first, **second}
        for key in ("bucket", "object", "callback", "pick_code"):
            if first.get(key):
                merged[key] = first[key]
        return merged

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
                        self._raise_if_shared_access_limited()
                        handle.write(chunk)
            temp_output.replace(output)
        except httpx.HTTPStatusError as err:
            if err.response.status_code == 429:
                raise U115AccessLimitError(
                    "115 文件下载返回 HTTP 429，已停止本次任务"
                ) from err
            raise
        finally:
            temp_output.unlink(missing_ok=True)

    @staticmethod
    def _pickcode_to_file_id(pickcode: str) -> int:
        try:
            from p115pickcode import to_id
        except ImportError as err:
            raise U115ApiError("缺少 p115pickcode 依赖，无法启用多端播放") from err
        return int(to_id(pickcode))

    def _playback_directory_id(self) -> str:
        if self._playback_dir_id:
            return self._playback_dir_id
        with self._playback_dir_lock:
            if not self._playback_dir_id:
                directory = self.ensure_remote_dir(self.playback_copy_directory)
                self._playback_dir_id = str(directory.get("fileid") or "")
                if not self._playback_dir_id:
                    raise U115ApiError("创建 115 多端播放目录失败")
        return self._playback_dir_id

    def create_playback_copy(self, pickcode: str, mode: str = "") -> PlaybackCopy:
        mode = self._playback_auth_mode(mode)
        target_cid = self._playback_directory_id()
        source_file_id = self._pickcode_to_file_id(pickcode)
        with self._playback_copy_lock:
            baseline_item = self._latest_playback_copy_item(target_cid)
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
                item = self._latest_playback_copy_item(target_cid)
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
        try:
            current = self._request_url(
                "GET",
                self.points_sign_url,
                headers=self.points_sign_headers,
            )
            data = current.get("data")
            if not isinstance(data, dict):
                raise U115ApiError("115 签到状态返回数据无效")
            is_signed_today = int(data.get("is_sign_today") or 0) == 1
        except U115AuthError:
            raise
        except U115AccessLimitError:
            raise
        except (httpx.HTTPError, U115ApiError, ValueError) as err:
            raise U115ApiError(f"查询 115 签到状态失败: {err}") from err
        if is_signed_today:
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
                data = payload.get("data")
                if not isinstance(data, dict):
                    raise U115ApiError("115 签到返回数据无效")
                return {
                    "already": False,
                    "continuous_day": data.get("continuous_day", 0),
                    "points_num": data.get("points_num", 0),
                    "message": "签到成功",
                }
            except U115AccessLimitError:
                raise
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

        def get_upload_token() -> Dict[str, Any]:
            token = self._response_data(
                self._request(
                    "GET",
                    "/open/upload/get_token",
                    timeout=self.upload_request_timeout,
                )
            )
            required = ("AccessKeyId", "AccessKeySecret", "SecurityToken", "endpoint")
            if not isinstance(token, dict) or any(not token.get(key) for key in required):
                raise U115ApiError("获取 115 上传凭证失败")
            return token

        bucket_name = str(init_result.get("bucket") or "")
        object_name = str(init_result.get("object") or "")
        if not bucket_name or not object_name:
            raise U115ApiError("115 上传初始化响应缺少对象存储信息")

        def build_bucket(token: Dict[str, Any]):
            auth = oss2.StsAuth(
                token["AccessKeyId"],
                token["AccessKeySecret"],
                token["SecurityToken"],
            )
            return oss2.Bucket(
                auth,
                token["endpoint"],
                bucket_name,
                connect_timeout=self.upload_request_timeout,
            )

        bucket = build_bucket(get_upload_token())
        pick_code = init_result.get("pick_code")
        resume = self._response_data(
            self._request(
                "POST",
                "/open/upload/resume",
                no_error=True,
                timeout=self.upload_request_timeout,
                data={"file_size": file_size, "target": target, "fileid": file_sha1, "pick_code": pick_code},
            )
        )
        resume_callback = resume.get("callback") if isinstance(resume, dict) else None
        callback = resume_callback or init_result.get("callback") or {}
        if not isinstance(callback, dict) or not all(
            str(callback.get(key) or "").strip()
            for key in ("callback", "callback_var")
        ):
            raise U115ApiError("115 上传初始化响应缺少有效回调参数")
        part_size = determine_part_size(file_size, preferred_size=10 * 1024 * 1024)
        attempts = max(1, int(self.upload_part_attempts))
        upload_id = ""
        upload_completed = False

        def retry_delay(attempt: int) -> None:
            time.sleep(
                max(0.0, float(self.upload_part_retry_delay))
                * (2 ** max(0, attempt - 1))
            )

        def refresh_bucket():
            return build_bucket(get_upload_token())

        def is_credential_error(err: BaseException) -> bool:
            return str(getattr(err, "code", "")) in {
                "SecurityTokenExpired",
                "InvalidAccessKeyId",
            }

        try:
            last_error: BaseException | None = None
            for attempt in range(1, attempts + 1):
                try:
                    upload_id = str(
                        bucket.init_multipart_upload(
                            object_name,
                            params={"encoding-type": "url", "sequential": ""},
                        ).upload_id
                    )
                    if not upload_id:
                        raise U115ApiError("115 未返回分片上传 ID")
                    break
                except Exception as err:  # noqa: BLE001
                    last_error = err
                    if is_credential_error(err):
                        bucket = refresh_bucket()
                    if attempt < attempts:
                        retry_delay(attempt)
            if not upload_id:
                raise U115ApiError(f"初始化 115 分片上传失败: {last_error}") from last_error

            parts = []
            with local_path.open("rb") as fileobj:
                part_number, offset = 1, 0
                while offset < file_size:
                    size = min(part_size, file_size - offset)
                    last_error = None
                    for attempt in range(1, attempts + 1):
                        try:
                            fileobj.seek(offset)
                            result = bucket.upload_part(
                                object_name,
                                upload_id,
                                part_number,
                                SizedFileAdapter(fileobj, size),
                            )
                            etag = str(getattr(result, "etag", "") or "")
                            if not etag:
                                raise U115ApiError(
                                    f"115 分片 {part_number} 上传未返回 ETag"
                                )
                            parts.append(PartInfo(part_number, etag))
                            break
                        except Exception as err:  # noqa: BLE001
                            last_error = err
                            if is_credential_error(err):
                                bucket = refresh_bucket()
                            if attempt < attempts:
                                retry_delay(attempt)
                    else:
                        raise U115ApiError(
                            f"115 分片 {part_number} 上传失败: {last_error}"
                        ) from last_error
                    part_number += 1
                    offset += size

            headers = {
                "X-oss-callback": oss2.utils.b64encode_as_string(callback["callback"]),
                "x-oss-callback-var": oss2.utils.b64encode_as_string(callback["callback_var"]),
                "x-oss-forbid-overwrite": "false",
            }

            complete_result = None
            last_error = None
            for attempt in range(1, attempts + 1):
                try:
                    complete_result = bucket.complete_multipart_upload(
                        object_name,
                        upload_id,
                        parts,
                        headers=headers,
                    )
                    status = getattr(complete_result, "status", 200)
                    if status != 200:
                        raise U115ApiError(f"完成 115 分片上传失败，HTTP 状态 {status}")
                    upload_completed = True
                    break
                except Exception as err:  # noqa: BLE001
                    last_error = err
                    if is_credential_error(err):
                        bucket = refresh_bucket()
                    if attempt < attempts:
                        retry_delay(attempt)
            else:
                raise U115ApiError(f"完成 115 分片上传失败: {last_error}") from last_error

            try:
                callback_payload = complete_result.resp.response.json()
            except Exception as err:  # noqa: BLE001
                raise U115ApiError("115 上传回调未返回有效结果") from err
            if not isinstance(callback_payload, dict) or not self._is_upload_callback_success(
                callback_payload
            ):
                message = (
                    callback_payload.get("message")
                    or callback_payload.get("error")
                    or callback_payload
                    if isinstance(callback_payload, dict)
                    else callback_payload
                )
                raise U115ApiError(f"115 上传回调失败: {message}")
        except Exception:
            if upload_id and not upload_completed:
                abort = getattr(bucket, "abort_multipart_upload", None)
                if callable(abort):
                    try:
                        abort(object_name, upload_id)
                    except Exception as cleanup_err:  # noqa: BLE001
                        logger.warning(
                            f"【115 上传】清理失败的分片任务异常: {cleanup_err}"
                        )
            raise

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
        if endpoint == self.download_endpoint:
            self._acquire_download_request_slot()
        url = f"{base_url or self.base_url}{endpoint}"
        if not require_auth:
            return self._request_url(
                method,
                url,
                require_auth=False,
                no_error=no_error,
                **kwargs,
            )

        self._ensure_open_auth()
        failed_access_token = str(self.tokens.get("access_token") or "")
        if not failed_access_token:
            raise U115AuthError("缺少有效的 115 Open 授权，请重新扫码登录")
        try:
            return self._request_open_with_token(
                method,
                url,
                failed_access_token,
                no_error=no_error,
                **kwargs,
            )
        except (_U115OpenAuthError, httpx.HTTPStatusError) as err:
            if isinstance(err, httpx.HTTPStatusError) and not self._is_open_auth_error(err):
                raise
            self._recover_open_auth(failed_access_token, err)

        access_token = str(self.tokens.get("access_token") or "")
        if not access_token:
            raise U115AuthError("缺少有效的 115 Open 授权，请重新扫码登录")
        try:
            return self._request_open_with_token(
                method,
                url,
                access_token,
                no_error=no_error,
                **kwargs,
            )
        except _U115OpenAuthError as err:
            raise U115AuthError("115 Open 授权恢复后仍然无效，请重新扫码登录") from err
        except httpx.HTTPStatusError as err:
            if not self._is_open_auth_error(err):
                raise
            raise U115AuthError("115 Open 授权恢复后仍然无效，请重新扫码登录") from err

    def _request_open_with_token(
        self,
        method: str,
        url: str,
        access_token: str,
        no_error: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        kwargs["headers"] = self._scoped_auth_headers(
            kwargs.get("headers"),
            bearer=access_token,
        )
        total_attempts = max(1, int(self.open_access_limit_attempts))
        for attempt in range(1, total_attempts + 1):
            self._raise_if_shared_access_limited()
            payload = self._request_url(
                method,
                url,
                require_auth=False,
                no_error=True,
                **kwargs,
            )
            if self._is_response_success(payload):
                return payload
            if self._is_open_auth_payload(payload):
                code = payload.get("code") or payload.get("errno") or ""
                message = str(payload.get("message") or payload.get("error") or payload)
                raise _U115OpenAuthError(f"{code}: {message}" if code else message)

            message = str(payload.get("message") or payload.get("error") or payload)
            if self._is_access_limit_message(message):
                limit_error = U115AccessLimitError(
                    f"{message}（并发任务已停止本次任务）"
                )
                if self._mark_shared_access_limited(limit_error):
                    raise limit_error
                self._raise_if_shared_access_limited()
                if attempt >= total_attempts:
                    raise U115AccessLimitError(
                        f"{message}（已按上游策略尝试 {total_attempts} 次）"
                    )
                delay = max(0.0, float(self.open_access_limit_delay))
                logger.info(
                    "【115 Open API】达到当前访问上限，"
                    f"等待 {delay:g} 秒后重试（{attempt}/{total_attempts - 1}）"
                )
                self._wait_for_request_retry(delay)
                continue
            if not no_error:
                raise U115ApiError(message)
            return payload
        raise U115AccessLimitError("115 Open API 访问上限重试未返回结果")

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
        method = method.upper()
        transient_attempts = (
            max(1, int(self.read_retry_attempts)) if method in {"GET", "HEAD"} else 1
        )
        rate_limit_attempts = max(1, int(self.http_rate_limit_attempts))
        total_attempts = max(transient_attempts, rate_limit_attempts)
        for attempt in range(1, total_attempts + 1):
            try:
                self._raise_if_shared_access_limited()
                response = self.session.request(method, url, **kwargs)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise U115ApiError("115 返回了无效响应")
                if not self._is_response_success(payload):
                    message = str(payload.get("message") or payload.get("error") or payload)
                    if (cookie_request or not no_error) and self._is_access_limit_message(message):
                        limit_error = U115AccessLimitError(
                            f"{message}（并发任务已停止本次任务）"
                        )
                        if self._mark_shared_access_limited(limit_error):
                            raise limit_error
                        self._raise_if_shared_access_limited()
                        raise U115AccessLimitError(message)
                    if not no_error and self._is_cookie_auth_error(payload, message):
                        raise U115AuthError("115 Cookie 已失效，请重新扫码登录")
                    if not no_error:
                        raise U115ApiError(message)
                return payload
            except httpx.HTTPStatusError as err:
                status_code = err.response.status_code
                if status_code == 429:
                    limit_error = U115AccessLimitError(
                        "115 并发任务返回 HTTP 429，已停止本次任务"
                    )
                    if self._mark_shared_access_limited(limit_error):
                        raise limit_error from err
                    self._raise_if_shared_access_limited()
                if status_code == 429 and attempt >= rate_limit_attempts:
                    raise U115AccessLimitError(
                        "115 返回 HTTP 429，访问上限重试已耗尽"
                    ) from err
                if status_code == 429:
                    delay = self._http_status_retry_delay(err, attempt)
                    logger.info(
                        f"【115 HTTP】请求返回临时状态 {status_code}，"
                        f"等待 {delay:g} 秒后重试（{attempt}/{rate_limit_attempts - 1}）"
                    )
                    self._wait_for_request_retry(delay)
                    continue
                if (
                    status_code not in self.transient_http_statuses
                    or attempt >= transient_attempts
                ):
                    raise
                delay = self._http_status_retry_delay(err, attempt)
                logger.info(
                    f"【115 HTTP】请求返回临时状态 {status_code}，"
                    f"等待 {delay:g} 秒后重试（{attempt}/{transient_attempts - 1}）"
                )
                self._wait_for_request_retry(delay)
            except (httpx.HTTPError, ValueError):
                if attempt >= transient_attempts:
                    raise
                self._wait_for_request_retry(
                    max(0.0, float(self.read_retry_delay)) * attempt
                )
        raise U115ApiError("115 请求失败")

    def _http_status_retry_delay(
        self,
        err: httpx.HTTPStatusError,
        attempt: int,
    ) -> float:
        if err.response.status_code == 429:
            value = err.response.headers.get("X-RateLimit-Reset")
            try:
                reset_delay = float(value) if value not in (None, "") else self.rate_limit_default_delay
            except (TypeError, ValueError):
                reset_delay = self.rate_limit_default_delay
            return max(0.0, reset_delay) + max(0.0, float(self.rate_limit_delay_padding))
        return max(0.0, float(self.read_retry_delay)) * (2 ** max(0, attempt - 1))

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
    def _is_access_limit_message(message: str) -> bool:
        return "已达到当前访问上限" in str(message or "")

    @staticmethod
    def _is_response_success(payload: Dict[str, Any]) -> bool:
        code = payload.get("code")
        if code in (None, "") and "errno" in payload:
            code = payload.get("errno")
        if code not in (None, "", 0, "0"):
            return False
        state = payload.get("state")
        if state in (False, 0, "0"):
            return False
        if state in (True, 1, "1"):
            return True
        return code in (None, "", 0, "0")

    @staticmethod
    def _is_upload_callback_success(payload: Dict[str, Any]) -> bool:
        code = payload.get("code")
        if code in (None, "") and "errno" in payload:
            code = payload.get("errno")
        state = payload.get("state")
        if code not in (None, "", 0, "0"):
            return False
        if state not in (None, "", True, 1, "1"):
            return False
        return code in (0, "0") or state in (True, 1, "1")

    @staticmethod
    def _is_existing_directory_response(payload: Dict[str, Any]) -> bool:
        code = payload.get("code") or payload.get("errno")
        return str(code) == "20004"

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
    def _item_mtime(item: Dict[str, Any]) -> int:
        for key in ("user_utime", "utime", "mtime", "tu", "t"):
            value = item.get(key)
            if value in (None, ""):
                continue
            try:
                return int(float(value))
            except (TypeError, ValueError):
                continue
        return 0

    @staticmethod
    def _item_size(item: Dict[str, Any]) -> Optional[int]:
        raw_size = next(
            (
                item.get(key)
                for key in ("size_byte", "file_size", "size", "fs")
                if item.get(key) is not None
            ),
            None,
        )
        try:
            return int(raw_size) if raw_size is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_cloud_path(path: str) -> str:
        normalized = PurePosixPath((path or "/").replace("\\", "/")).as_posix()
        if normalized == ".":
            normalized = "/"
        return normalized if normalized.startswith("/") else f"/{normalized}"

    @staticmethod
    def _item_from_info(info: Dict[str, Any], path: str) -> Dict[str, Any]:
        category = str(info.get("file_category", info.get("fc", "1")))
        return {
            "fileid": U115Client._item_id(info),
            "path": path,
            "type": "dir" if category == "0" else "file",
            "name": U115Client._item_name(info) or PurePosixPath(path).name,
            "pickcode": info.get("pick_code") or info.get("pickcode") or info.get("pc") or "",
            "size": U115Client._item_size(info),
            "mtime": U115Client._item_mtime(info),
        }
