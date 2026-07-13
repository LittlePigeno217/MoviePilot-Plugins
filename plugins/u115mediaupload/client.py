from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Optional


class U115AuthError(RuntimeError):
    pass


class U115UploadError(RuntimeError):
    pass


@dataclass(frozen=True)
class U115UploadResult:
    success: bool
    reused: bool
    file_item: Optional[Dict[str, Any]] = None
    message: str = ""


class U115Client:
    base_url = "https://proapi.115.com"
    qrcode_status_url = "https://qrcodeapi.115.com/get/status/"
    chunk_size = 10 * 1024 * 1024

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
                "User-Agent": "W115MediaUpload/1.0",
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

    def get_folder(self, path: str) -> Optional[Dict[str, Any]]:
        path = self._normalize_cloud_path(path)
        existing = self.get_item(path)
        if existing:
            return existing

        current = {"fileid": "0", "path": "/"}
        cloud = PurePosixPath(path)
        for part in [item for item in cloud.parts if item != "/"]:
            child_path = self._normalize_cloud_path(
                (PurePosixPath(current["path"]) / part).as_posix()
            )
            existing = self.get_item(child_path)
            if existing:
                current = existing
                continue
            created = self.create_folder(current, part)
            if not created:
                return None
            current = created
        return current

    def create_folder(self, parent: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
        parent_path = self._normalize_cloud_path(parent.get("path") or "/")
        target_path = self._normalize_cloud_path((PurePosixPath(parent_path) / name).as_posix())
        result = self._request(
            "POST",
            "/open/folder/add",
            data={
                "pid": int(parent.get("fileid") or 0),
                "file_name": name,
            },
        )
        if result.get("code") == 20004:
            return self.get_item(target_path)
        if not result.get("state"):
            return None
        data = self._response_data(result) or {}
        return {
            "storage": "u115",
            "fileid": str(data.get("file_id") or data.get("cid") or ""),
            "path": target_path,
            "name": name,
            "type": "dir",
        }

    def upload_file(
        self,
        target_dir: Dict[str, Any],
        local_path: Path,
        new_name: Optional[str] = None,
    ) -> U115UploadResult:
        self._ensure_auth()
        local_path = Path(local_path)
        if not local_path.exists():
            raise FileNotFoundError(str(local_path))

        target_name = new_name or local_path.name
        target_root = self._normalize_cloud_path(target_dir.get("path") or "/")
        target_path = self._normalize_cloud_path((PurePosixPath(target_root) / target_name).as_posix())
        target_cid = str(target_dir.get("fileid") or "0")
        file_size = local_path.stat().st_size
        file_sha1 = self.calc_sha1(local_path)
        file_preid = self.calc_sha1(local_path, 128 * 1024 * 1024)

        init_data = {
            "file_name": target_name,
            "file_size": file_size,
            "target": f"U_1_{target_cid}",
            "fileid": file_sha1,
            "preid": file_preid,
        }
        init_result = self._init_upload(init_data, local_path)

        if init_result.get("status") == 2 or init_result.get("reuse"):
            return U115UploadResult(
                success=True,
                reused=True,
                file_item=self._resolve_uploaded_item(init_result, target_path),
                message="秒传成功",
            )

        token = self._response_data(self._request("GET", "/open/upload/get_token"))
        if not token:
            return U115UploadResult(success=False, reused=False, message="获取上传凭证失败")

        callback = init_result.get("callback")
        resume = self._response_data(
            self._request(
                "POST",
                "/open/upload/resume",
                data={
                    "file_size": file_size,
                    "target": f"U_1_{target_cid}",
                    "fileid": file_sha1,
                    "pick_code": init_result.get("pick_code"),
                },
                no_error=True,
            )
        )
        if resume and resume.get("callback"):
            callback = resume["callback"]

        uploaded = self._oss_upload(
            token=token,
            bucket_name=init_result.get("bucket"),
            object_name=init_result.get("object"),
            callback=callback,
            local_path=local_path,
        )
        if not uploaded:
            return U115UploadResult(success=False, reused=False, message="OSS 上传失败")

        return U115UploadResult(
            success=True,
            reused=False,
            file_item=self.get_item(target_path),
            message="上传成功",
        )

    def _init_upload(self, init_data: Dict[str, Any], local_path: Path) -> Dict[str, Any]:
        result = self._request("POST", "/open/upload/init", data=init_data)
        if not result or not result.get("state"):
            raise U115UploadError(result.get("error") or result.get("message") or "初始化上传失败")
        init_result = self._response_data(result) or {}

        if init_result.get("code") in (700, 701) and init_result.get("sign_check"):
            start, end = [int(item) for item in str(init_result["sign_check"]).split("-", 1)]
            init_data.update(
                {
                    "pick_code": init_result.get("pick_code"),
                    "sign_key": init_result.get("sign_key"),
                    "sign_val": self.calc_range_sha1(local_path, start, end).upper(),
                }
            )
            result = self._request("POST", "/open/upload/init", data=init_data)
            if not result or not result.get("state"):
                raise U115UploadError(result.get("error") or result.get("message") or "上传二次认证失败")
            init_result = {**init_result, **(self._response_data(result) or {})}

        return init_result

    def _resolve_uploaded_item(self, init_result: Dict[str, Any], target_path: str) -> Optional[Dict[str, Any]]:
        file_id = init_result.get("file_id")
        if file_id:
            time.sleep(0.1)
            info = self._response_data(
                self._request(
                    "GET",
                    "/open/folder/get_info",
                    params={"file_id": int(file_id)},
                    no_error=True,
                )
            )
            if info:
                return self._file_item_from_info(info, target_path)
        return self.get_item(target_path)

    def _oss_upload(
        self,
        token: Dict[str, Any],
        bucket_name: str,
        object_name: str,
        callback: Dict[str, Any],
        local_path: Path,
    ) -> bool:
        if not bucket_name or not object_name or not callback:
            return False

        import oss2
        from oss2 import SizedFileAdapter, determine_part_size
        from oss2.models import PartInfo

        auth = oss2.StsAuth(
            access_key_id=token.get("AccessKeyId"),
            access_key_secret=token.get("AccessKeySecret"),
            security_token=token.get("SecurityToken"),
        )
        bucket = oss2.Bucket(auth, token.get("endpoint"), bucket_name)
        upload_id = bucket.init_multipart_upload(
            object_name, params={"encoding-type": "url", "sequential": ""}
        ).upload_id
        parts = []
        part_size = determine_part_size(local_path.stat().st_size, preferred_size=self.chunk_size)

        with open(local_path, "rb") as fileobj:
            part_number = 1
            offset = 0
            file_size = local_path.stat().st_size
            while offset < file_size:
                num_to_upload = min(part_size, file_size - offset)
                result = bucket.upload_part(
                    object_name,
                    upload_id,
                    part_number,
                    data=SizedFileAdapter(fileobj, num_to_upload),
                )
                parts.append(PartInfo(part_number, result.etag))
                offset += num_to_upload
                part_number += 1

        headers = {
            "X-oss-callback": oss2.utils.b64encode_as_string(callback["callback"]),
            "x-oss-callback-var": oss2.utils.b64encode_as_string(callback["callback_var"]),
            "x-oss-forbid-overwrite": "false",
        }
        result = bucket.complete_multipart_upload(object_name, upload_id, parts, headers=headers)
        return int(getattr(result, "status", 0)) == 200

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
    def calc_sha1(filepath: Path, size: Optional[int] = None) -> str:
        sha1 = hashlib.sha1()
        with open(filepath, "rb") as fileobj:
            if size:
                sha1.update(fileobj.read(size))
            else:
                while True:
                    chunk = fileobj.read(1024 * 1024)
                    if not chunk:
                        break
                    sha1.update(chunk)
        return sha1.hexdigest()

    @staticmethod
    def calc_range_sha1(filepath: Path, start: int, end: int) -> str:
        sha1 = hashlib.sha1()
        with open(filepath, "rb") as fileobj:
            fileobj.seek(start)
            sha1.update(fileobj.read(end - start + 1))
        return sha1.hexdigest()

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

    def _log_warning(self, message: str) -> None:
        if self.logger and hasattr(self.logger, "warning"):
            self.logger.warning(message)
