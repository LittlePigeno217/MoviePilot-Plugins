from __future__ import annotations

import threading
from base64 import b64encode
from copy import deepcopy
from datetime import datetime, timedelta
from io import BytesIO
from math import isfinite
from pathlib import Path
from time import monotonic
from typing import Any, Callable, Dict
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.log import logger
from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

from .checkin_schedule import random_epoch_for_date, pick_next_run_epoch
from .client import U115ApiError, U115Client
from .log_utils import safe_error_text
from .resilience import TtlCache, retry_call
from .store import DEFAULT_CONFIG, Store
from .strm import StrmGenerator
from .uploader import DirectoryUploader


def _ok(data: Any = None, message: str = "") -> Dict[str, Any]:
    return {"success": True, "message": message, "data": {} if data is None else data}


def _error(message: str) -> Dict[str, Any]:
    return {"success": False, "message": message, "data": {}}


class Api:
    _TASK_LABELS = {"strm": "STRM同步", "upload": "目录上传"}

    def __init__(self, client_provider: Callable[[], U115Client], store: Store, token_provider: Callable[[], str]):
        self._client_provider = client_provider
        self._store = store
        self._token_provider = token_provider
        self._running: set[str] = set()
        self._lock = threading.Lock()
        self._checkin_lock = threading.Lock()
        self._browse_115_cache: TtlCache[str, list[Dict[str, Any]]] = TtlCache(30)
        self._redirect_cache: TtlCache[str, str] = TtlCache(60)

    def get_config(self) -> Dict[str, Any]:
        config = deepcopy(self._store.get_config())
        config.pop("tokens", None)
        return _ok(config)

    def save_config(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        payload = payload or {}
        if not isinstance(payload, dict):
            return _error("配置格式无效")
        config = self._store.get_config()
        allowed = set(DEFAULT_CONFIG) - {"tokens"}
        for key in allowed:
            if key in payload:
                config[key] = payload[key]
        self._store.save_config(config)
        return _ok(message="配置已保存")

    def qrcode(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        try:
            client_type = str((payload or {}).get("client_type") or "alipaymini")
            result = self._client_provider().generate_qrcode(client_type)
            if not result.get("success"):
                return _error(result.get("message") or "获取二维码失败")
            content = str((result.get("data") or {}).get("code_content") or "")
            if not content:
                return _error("115 未返回二维码内容")
            try:
                from qrcode import make as make_qrcode
            except ImportError:
                return _error("缺少 qrcode 依赖，请重新安装插件依赖")
            image = make_qrcode(content)
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            return _ok(
                {
                    "qrcode": f"data:image/png;base64,{b64encode(buffer.getvalue()).decode()}",
                    "content": content,
                    "client_type": (result.get("data") or {}).get("client_type") or client_type,
                }
            )
        except Exception as err:  # noqa: BLE001
            return _error(f"获取二维码失败: {err}")

    def check_login(self) -> Dict[str, Any]:
        try:
            client = self._client_provider()
            result = client.check_login()
            if not result.get("success"):
                return _error(result.get("message") or "检查登录状态失败")
            if (result.get("data") or {}).get("status") == 2:
                config = self._store.get_config()
                config["tokens"] = client.export_tokens()
                config["login_client_type"] = client.client_type
                if client.cookie:
                    config["cookie"] = client.cookie
                self._store.save_config(config)
                self._browse_115_cache.clear()
                self._redirect_cache.clear()
            return _ok(result.get("data") or {}, result.get("message") or "")
        except Exception as err:  # noqa: BLE001
            return _error(f"检查登录状态失败: {err}")

    def browse_115(self, cid: str = "0") -> Dict[str, Any]:
        try:
            cache_key = str(cid or "0")
            cached = self._browse_115_cache.get(cache_key)
            if cached is not None:
                return _ok({"cid": cache_key, "items": deepcopy(cached)})
            items = []
            for item in retry_call(lambda: self._client_provider().get_dir_list(cache_key), attempts=3, delay=1.0):
                if not U115Client._is_directory(item):
                    continue
                name = U115Client._item_name(item).strip()
                item_cid = U115Client._item_id(item)
                if not name or not item_cid:
                    continue
                items.append(
                    {
                        "name": name,
                        "cid": item_cid,
                    }
                )
            items.sort(key=lambda item: item["name"].lower())
            self._browse_115_cache.set(cache_key, items)
            return _ok({"cid": cache_key, "items": items})
        except Exception as err:  # noqa: BLE001
            return _error(f"浏览 115 目录失败: {err}")

    @staticmethod
    def _local_roots() -> list[Path]:
        root = Path("/").resolve()
        return [root] if root.is_dir() else []

    def browse_local(self, path: str = "", root: str = "") -> Dict[str, Any]:
        try:
            roots = self._local_roots()
            if not roots:
                return _error("MoviePilot 根目录不可用")
            requested_root = Path(root).expanduser().resolve() if root else None
            base = next((item for item in roots if item == requested_root), roots[0])
            if requested_root and base != requested_root:
                return _error("本地目录根路径无效")
            target = (base / path).resolve() if path else base
            target.relative_to(base)
            if not target.is_dir():
                return _error(f"目录不存在: {target}")
            return _ok(
                {
                    "base": str(base),
                    "roots": [{"name": str(item), "path": str(item)} for item in roots],
                    "current": "" if target == base else target.relative_to(base).as_posix(),
                    "items": [
                        {"name": entry.name, "path": entry.relative_to(base).as_posix()}
                        for entry in sorted(target.iterdir(), key=lambda item: item.name.lower())
                        if entry.is_dir() and not entry.name.startswith(".")
                    ],
                }
            )
        except ValueError:
            return _error("目录超出 MoviePilot 根目录")
        except Exception as err:  # noqa: BLE001
            return _error(f"浏览本地目录失败: {err}")

    def status(self) -> Dict[str, Any]:
        config = self._store.get_config()
        with self._lock:
            running = sorted(self._running)
        return _ok(
            {
                "enabled": bool(config.get("enabled")),
                "authenticated": self._client_provider().is_authenticated(),
                "strm_mappings": len(config.get("strm_mappings") or []),
                "upload_mappings": len(config.get("upload_mappings") or []),
                "running": running,
                "history": self._store.get_history(),
            }
        )

    @staticmethod
    def _moviepilot_url(request: Request) -> str:
        scheme = str(request.headers.get("x-forwarded-proto") or request.url.scheme).split(",", 1)[0].strip()
        host = str(request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc).split(",", 1)[0].strip()
        return f"{scheme}://{host}".rstrip("/")

    def _strm_moviepilot_url(self, request: Request) -> str:
        configured = str(self._store.get_config().get("moviepilot_address") or "").strip()
        return configured.rstrip("/") or self._moviepilot_url(request)

    def trigger_strm(self, request: Request) -> Dict[str, Any]:
        moviepilot_url = self._strm_moviepilot_url(request)
        return self._start("strm", lambda: self.run_strm(moviepilot_url), "STRM 同步已开始")

    def trigger_upload(self, payload: Dict[str, Any] | bool | None = None) -> Dict[str, Any]:
        incremental = payload if isinstance(payload, bool) else bool((payload or {}).get("incremental", True))
        return self._start("upload", lambda: self.run_upload(incremental), "目录上传已开始")

    def run_strm(self, moviepilot_url: str) -> list[Dict[str, Any]]:
        config = self._store.get_config()
        incremental = bool(config.get("strm_incremental", True))
        mappings = [mapping for mapping in config.get("strm_mappings") or [] if mapping.get("enabled", True)]
        logger.info(f"【STRM同步】开始执行，模式：{'增量' if incremental else '全量'}，有效映射：{len(mappings)}")
        if not mappings:
            logger.warning("【STRM同步】没有启用的目录映射，任务结束")
        generator = StrmGenerator(
            self._client_provider(),
            self._store,
            moviepilot_url,
            self._token_provider(),
            incremental,
        )
        entries = []
        totals = {"added": 0, "updated": 0, "skipped": 0, "errors": 0, "duration_ms": 0}
        for mapping in mappings:
            source = str(mapping.get("source_path") or mapping.get("source_cid") or "-")
            target = str(mapping.get("target_dir") or "-")
            logger.info(f"【STRM同步】开始处理映射：{source} -> {target}")
            mapping_started = monotonic()
            try:
                entry = retry_call(lambda: generator.run_mapping(mapping), attempts=3, delay=3.0)
            except Exception as err:  # noqa: BLE001
                logger.error(
                    f"【STRM同步】映射处理失败：{source} -> {target}，原因：{safe_error_text(err)}"
                )
                entry = {
                    "kind": "strm",
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "mapping": source,
                    "errors": 1,
                    "message": str(err),
                }
            entry["duration_ms"] = int((monotonic() - mapping_started) * 1000)
            self._store.append_history(entry)
            entries.append(entry)
            for key in totals:
                totals[key] += int(entry.get(key) or 0)
            summary = (
                f"新增 {int(entry.get('added') or 0)}，更新 {int(entry.get('updated') or 0)}，"
                f"跳过 {int(entry.get('skipped') or 0)}，失败 {int(entry.get('errors') or 0)}，"
                f"耗时 {int(entry.get('duration_ms') or 0)}ms"
            )
            log_result = logger.warning if int(entry.get("errors") or 0) else logger.info
            log_result(f"【STRM同步】映射完成：{source} -> {target}，{summary}")
        total_summary = (
            f"新增 {totals['added']}，更新 {totals['updated']}，跳过 {totals['skipped']}，"
            f"失败 {totals['errors']}，耗时 {totals['duration_ms']}ms"
        )
        log_total = logger.warning if totals["errors"] else logger.info
        log_total(f"【STRM同步】执行完成，{total_summary}")
        return entries

    def run_upload(self, incremental: bool = True) -> Dict[str, Any]:
        config = self._store.get_config()
        mappings = [mapping for mapping in config.get("upload_mappings") or [] if mapping.get("enabled", True)]
        logger.info(f"【目录上传】开始执行，模式：{'增量' if incremental else '全量'}，有效映射：{len(mappings)}")
        try:
            entry = DirectoryUploader(self._client_provider(), self._store, config).run(incremental)
        except Exception as err:  # noqa: BLE001
            logger.error(f"【目录上传】执行失败：{safe_error_text(err)}")
            entry = {
                "kind": "upload",
                "time": datetime.now().isoformat(timespec="seconds"),
                "incremental": incremental,
                "errors": 1,
                "message": str(err),
            }
        finally:
            self._browse_115_cache.clear()
        self._store.append_history(entry)
        summary = (
            f"上传 {int(entry.get('uploaded') or 0)}，秒传 {int(entry.get('instant') or 0)}，"
            f"跳过 {int(entry.get('skipped') or 0)}，删除 {int(entry.get('deleted') or 0)}，"
            f"失败 {int(entry.get('errors') or 0)}，耗时 {int(entry.get('duration_ms') or 0)}ms"
        )
        log_result = logger.warning if int(entry.get("errors") or 0) else logger.info
        log_result(f"【目录上传】执行完成，{summary}")
        return entry

    def run_checkin(self) -> Dict[str, Any]:
        if not self._checkin_lock.acquire(blocking=False):
            logger.warning("【115签到】签到任务正在运行，忽略重复触发")
            return _error("签到任务正在运行")
        logger.info("【115签到】开始执行")
        try:
            result = self._client_provider().checkin()
            entry = {"kind": "checkin", "time": datetime.now().isoformat(timespec="seconds"), **result}
            self._store.append_history(entry)
            if result.get("already"):
                logger.info("【115签到】执行完成：今日已签到")
            else:
                logger.info(
                    f"【115签到】执行完成：{result.get('message') or '签到成功'}，"
                    f"连续 {int(result.get('continuous_day') or 0)} 天，本次积分 {int(result.get('points_num') or 0)}"
                )
            return _ok(entry, result.get("message") or "签到完成")
        except Exception as err:  # noqa: BLE001
            entry = {"kind": "checkin", "time": datetime.now().isoformat(timespec="seconds"), "message": str(err)}
            self._store.append_history(entry)
            logger.error(f"【115签到】执行失败：{safe_error_text(err)}")
            return _error(str(err))
        finally:
            self._checkin_lock.release()

    @staticmethod
    def _checkin_timezone():
        try:
            return ZoneInfo(str(getattr(settings, "TZ", "Asia/Shanghai")))
        except Exception:  # noqa: BLE001
            return ZoneInfo("Asia/Shanghai")

    def run_scheduled_checkin(self) -> Dict[str, Any]:
        """每五分钟维护一次上游同款的随机签到时间窗。"""

        config = self._store.get_config()
        if not config.get("enabled") or not config.get("checkin_enabled"):
            return _error("115 每日签到未启用")

        timezone = self._checkin_timezone()
        now = datetime.now(timezone)
        today = now.strftime("%Y-%m-%d")
        state = self._store.get_checkin_schedule()
        last_done = str(state.get("last_done_date") or "").strip()
        try:
            next_run_ts = float(state["next_run_ts"]) if state.get("next_run_ts") is not None else None
        except (TypeError, ValueError):
            next_run_ts = None
        if next_run_ts is not None and not isfinite(next_run_ts):
            next_run_ts = None

        time_range = str(config.get("checkin_time_range") or "06:00-09:00")
        if last_done == today:
            try:
                next_is_tomorrow = next_run_ts is not None and datetime.fromtimestamp(next_run_ts, timezone).date() > now.date()
            except (OSError, OverflowError, ValueError):
                next_is_tomorrow = False
            if not next_is_tomorrow:
                tomorrow = now.date() + timedelta(days=1)
                state["next_run_ts"] = random_epoch_for_date(tomorrow, timezone, time_range)
                self._store.save_checkin_schedule(state)
            return _ok(message="今日签到已完成")

        if next_run_ts is None:
            next_run_ts = pick_next_run_epoch(now, timezone, time_range)
            state["next_run_ts"] = next_run_ts
            self._store.save_checkin_schedule(state)
            logger.debug("115 轻量助手：已安排下次签到时间 %s", next_run_ts)

        if now.timestamp() < next_run_ts:
            return _ok(message="等待签到时间窗")

        result = self.run_checkin()
        if result.get("success"):
            state["last_done_date"] = today
            tomorrow = now.date() + timedelta(days=1)
            state["next_run_ts"] = random_epoch_for_date(tomorrow, timezone, time_range)
        else:
            state["next_run_ts"] = None
        self._store.save_checkin_schedule(state)
        return result

    def history(self) -> Dict[str, Any]:
        return _ok({"items": self._store.get_history()})

    def redirect(self, pickcode: str, apikey: str):
        if not apikey or apikey != self._token_provider():
            return JSONResponse({"success": False, "message": "无效 apikey"}, status_code=403)
        cached_url = self._redirect_cache.get(pickcode)
        if cached_url:
            return RedirectResponse(cached_url, status_code=302)
        try:
            def fetch_url() -> str:
                url = self._client_provider().get_download_url(pickcode)
                if not url:
                    raise U115ApiError("未获取到 115 下载地址")
                return url

            url = retry_call(fetch_url, attempts=3, delay=1.0)
        except Exception as err:  # noqa: BLE001
            logger.error(f"【302取链】获取下载地址失败：{safe_error_text(err)}")
            return JSONResponse({"success": False, "message": f"取链失败: {err}"}, status_code=502)
        self._redirect_cache.set(pickcode, url)
        return RedirectResponse(url, status_code=302)

    def _start(self, kind: str, target: Callable[[], Any], message: str) -> Dict[str, Any]:
        label = self._TASK_LABELS.get(kind, kind)
        with self._lock:
            if kind in self._running:
                logger.warning(f"【{label}】任务正在运行，忽略重复触发")
                return _error(f"{kind} 任务正在运行")
            self._running.add(kind)
        def run() -> None:
            try:
                target()
            except Exception as err:  # noqa: BLE001
                logger.error(f"【{label}】后台任务异常终止：{safe_error_text(err)}")
            finally:
                with self._lock:
                    self._running.discard(kind)

        thread = threading.Thread(target=run, name=f"p115liteassistant-{kind}", daemon=True)
        try:
            thread.start()
        except Exception as err:  # noqa: BLE001
            with self._lock:
                self._running.discard(kind)
            logger.error(f"【{label}】任务启动失败：{safe_error_text(err)}")
            return _error(f"{kind} 任务启动失败")
        logger.info(f"【{label}】任务已提交")
        return _ok(message=message)
