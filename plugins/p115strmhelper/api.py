from pathlib import Path
from typing import Any, Callable, Dict, List

from fastapi.responses import RedirectResponse, JSONResponse
from app.log import logger
from app.core.config import settings

try:  # 运行时相对导入；单测直接导入模块时回退绝对导入
    from .store import Store
    from .models import Mapping, HistoryEntry
    from .strm import StrmGenerator
    from .metadata import MetadataSync
    from .redirect import RedirectResolver
except ImportError:  # pragma: no cover
    from store import Store
    from models import Mapping, HistoryEntry
    from strm import StrmGenerator
    from metadata import MetadataSync
    from redirect import RedirectResolver

try:
    from qrcode import make as qr_make
    from io import BytesIO
    from base64 import b64encode
    _HAS_QR = True
except Exception:  # noqa: BLE001  # pragma: no cover
    _HAS_QR = False


def _ok(data=None, message=""):
    return {"success": True, "message": message, "data": data or {}}


def _err(message):
    return {"success": False, "message": message, "data": {}}


def _is_dir_item(it: Dict[str, Any]) -> bool:
    return str(it.get("fc", it.get("file_category", "1"))) == "0" or (
        it.get("cid") is not None and it.get("fid") is None
    )


class Api:
    """前端 API 与 302 重定向端点。"""

    def __init__(self, client_provider: Callable, store: Store, api_token_provider: Callable):
        self._client_provider = client_provider     # 返回当前 U115Client
        self._store = store
        self._api_token_provider = api_token_provider

    # ---------------------------------------------------------------- 授权
    def qrcode(self) -> Dict:
        client = self._client_provider()
        try:
            res = client.generate_qrcode()
            content = (res.get("data") or {}).get("codeContent", "") if res.get("success") else ""
            if not content:
                return _err(res.get("message") or "获取二维码内容失败")
            if not _HAS_QR:
                return _ok({"codeContent": content}, "qrcode 库未安装，仅返回内容")
            img = qr_make(content)
            buf = BytesIO()
            img.save(buf, format="PNG")
            b64 = b64encode(buf.getvalue()).decode()
            return _ok({"qrcode": f"data:image/png;base64,{b64}", "codeContent": content})
        except Exception as e:  # noqa: BLE001
            logger.error(f"[P115StrmHelper] 二维码失败: {e}")
            return _err(f"二维码失败: {e}")

    def check_login(self) -> Dict:
        try:
            client = self._client_provider()
            res = client.check_login()
            if res.get("success"):
                cfg = self._store.get_config()
                cfg["tokens"] = client.export_tokens()
                if client.cookie:
                    cfg["cookie"] = client.cookie
                self._store.save_config(cfg)
            return _ok(res.get("data") or {}, res.get("message", ""))
        except Exception as e:  # noqa: BLE001
            return _err(f"检查登录失败: {e}")

    # ------------------------------------------------------------ 目录浏览
    def browse_115(self, cid: str = "0") -> Dict:
        try:
            items = self._client_provider().get_dir_list(cid)
            dirs = [
                {
                    "name": it.get("fn") or it.get("file_name") or it.get("n") or "",
                    "cid": str(it.get("cid") or it.get("file_id") or it.get("fid") or ""),
                    "is_dir": True,
                }
                for it in items if _is_dir_item(it)
            ]
            return _ok({"cid": cid, "items": dirs})
        except Exception as e:  # noqa: BLE001
            return _err(f"浏览 115 目录失败: {e}")

    def browse_local(self, path: str = "") -> Dict:
        try:
            base = Path(settings.LIBRARY_PATH or "/media")
            target = base / path if path else base
            target.relative_to(base)  # 越界防护
            if not target.is_dir():
                return _err(f"目录不存在: {target}")
            items = [
                {"name": p.name, "path": str(p.relative_to(base)), "is_dir": True}
                for p in sorted(target.iterdir(), key=lambda x: x.name)
                if p.is_dir() and not p.name.startswith(".")
            ]
            cur = str(target.relative_to(base)) if target != base else ""
            return _ok({"base": str(base), "current": cur, "items": items})
        except ValueError:
            return _err("路径超出允许范围")
        except Exception as e:  # noqa: BLE001
            return _err(f"浏览本地目录失败: {e}")

    # ---------------------------------------------------------------- 配置
    def get_config(self) -> Dict:
        cfg = self._store.get_config()
        cfg.pop("tokens", None)  # 不外泄 token
        return _ok(cfg)

    def save_config(self, payload: Dict = None) -> Dict:
        payload = payload or {}
        cfg = self._store.get_config()
        for key in ("cookie", "mappings", "schedule_cron", "incremental",
                    "sync_metadata", "moviepilot_url"):
            if key in payload:
                cfg[key] = payload[key]
        self._store.save_config(cfg)
        return _ok(message="已保存")

    # ---------------------------------------------------------------- 同步
    def _build_generator(self) -> StrmGenerator:
        cfg = self._store.get_config()
        client = self._client_provider()
        meta = MetadataSync(client) if cfg.get("sync_metadata") else None
        return StrmGenerator(
            client, self._store, cfg.get("moviepilot_url", ""),
            self._api_token_provider(), incremental=cfg.get("incremental", True),
            metadata_sync=meta,
        )

    def run_sync(self) -> List[HistoryEntry]:
        cfg = self._store.get_config()
        gen = self._build_generator()
        entries = []
        for raw in cfg.get("mappings", []):
            m = Mapping(**raw)
            if not m.enabled:
                continue
            entry = gen.run_mapping(m)
            self._store.append_history(entry)
            entries.append(entry)
        return entries

    def trigger_sync(self) -> Dict:
        import threading
        threading.Thread(target=self.run_sync, daemon=True).start()
        return _ok(message="同步已在后台开始")

    def history(self) -> Dict:
        return _ok({"items": self._store.get_history()})

    # ---------------------------------------------------------------- 重定向
    def redirect(self, pickcode: str, apikey: str):
        if apikey != self._api_token_provider():
            return JSONResponse({"success": False, "message": "无效 apikey"}, status_code=403)
        url = RedirectResolver(self._client_provider()).resolve(pickcode)
        if not url:
            return JSONResponse({"success": False, "message": "取直链失败"}, status_code=404)
        return RedirectResponse(url, status_code=302)
