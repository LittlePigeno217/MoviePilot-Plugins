from __future__ import annotations

import threading
from base64 import b64encode
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta
from io import BytesIO
from math import isfinite
from pathlib import Path
from time import monotonic, time
from typing import Any, Callable, Dict, Iterator
from urllib.parse import parse_qsl, quote, unquote, urlsplit
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.log import logger
from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

from .checkin_schedule import random_epoch_for_date, pick_next_run_epoch
from .client import U115AccessLimitError, U115ApiError, U115AuthError, U115Client
from .log_utils import safe_error_text
from .resilience import TtlCache, retry_call
from .store import DEFAULT_CONFIG, Store
from .strm import (
    StrmGenerator,
    normalize_moviepilot_url,
    normalize_pickcode,
    verify_redirect_signature,
)
from .uploader import DirectoryUploader


def _ok(data: Any = None, message: str = "") -> Dict[str, Any]:
    return {"success": True, "message": message, "data": {} if data is None else data}


def _error(message: str, **fields: Any) -> Dict[str, Any]:
    return {"success": False, "message": message, "data": {}, **fields}


class Api:
    _TASK_LABELS = {"strm": "STRM同步", "upload": "目录上传"}
    _CLOUD_TASK_KINDS = frozenset({"strm", "upload"})
    _DOWNLOAD_URL_CACHE_SAFETY_SECONDS = 300
    _PLAYBACK_COPY_CLEANUP_GRACE_SECONDS = 60
    _PLAYBACK_COPY_CLEANUP_FALLBACK_SECONDS = 300

    def __init__(self, client_provider: Callable[[], U115Client], store: Store):
        self._client_provider = client_provider
        self._store = store
        self._running: set[str] = set()
        self._lock = threading.Lock()
        self._cloud_task_lock = threading.Lock()
        self._checkin_lock = threading.Lock()
        self._browse_115_cache: TtlCache[str, list[Dict[str, Any]]] = TtlCache(30)
        self._redirect_cache: TtlCache[tuple[str, str, str], str] = TtlCache(60, maxsize=8096)
        self._redirect_flights_guard = threading.Lock()
        self._redirect_flights: Dict[str, tuple[Any, int]] = {}

    def get_config(self) -> Dict[str, Any]:
        config = deepcopy(self._store.get_config())
        config.pop("tokens", None)
        return _ok(config)

    def save_config(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        payload = payload or {}
        if not isinstance(payload, dict):
            return _error("配置格式无效")
        updates = dict(payload)
        if "link_redirect_mode" in updates:
            redirect_mode = str(updates.get("link_redirect_mode") or "").strip().lower()
            if redirect_mode not in {"cookie", "open"}:
                return _error(f"不支持的 302 取链模式: {redirect_mode}")
            updates["link_redirect_mode"] = redirect_mode
        if "moviepilot_address" in updates:
            moviepilot_address = str(updates.get("moviepilot_address") or "").strip()
            if moviepilot_address:
                try:
                    moviepilot_address = normalize_moviepilot_url(moviepilot_address)
                except ValueError as err:
                    return _error(str(err))
            updates["moviepilot_address"] = moviepilot_address
        allowed = set(DEFAULT_CONFIG) - {"tokens"}
        current = self._store.get_config()
        saved_updates = {key: updates[key] for key in allowed if key in updates}
        cookie_changed = (
            "cookie" in saved_updates
            and bool(str(saved_updates["cookie"] or "").strip())
            and saved_updates["cookie"] != current.get("cookie")
        )
        if cookie_changed:
            saved_updates["tokens"] = {}
        self._store.update_config(saved_updates)
        if any(
            key in saved_updates and saved_updates[key] != current.get(key)
            for key in ("cookie", "link_redirect_mode")
        ):
            self._browse_115_cache.clear()
            self._redirect_cache.clear()
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
                updates = {
                    "tokens": client.export_tokens(),
                    "login_client_type": client.client_type,
                }
                if client.cookie:
                    updates["cookie"] = client.cookie
                self._store.update_config(updates)
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
            for item in self._client_provider().get_dir_list(cache_key):
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

    def _strm_moviepilot_url(self) -> str:
        return str(self._store.get_config().get("moviepilot_address") or "").strip().rstrip("/")

    def _strm_start_error(self) -> str:
        config = self._store.get_config()
        try:
            normalize_moviepilot_url(str(config.get("moviepilot_address") or ""))
        except ValueError as err:
            return str(err)
        mappings = [
            mapping
            for mapping in config.get("strm_mappings") or []
            if isinstance(mapping, dict) and mapping.get("enabled", True)
        ]
        if not mappings:
            return "没有启用的 STRM 目录映射"
        for mapping in mappings:
            if not str(mapping.get("source_cid") or "").strip():
                return "115 源目录不能为空"
            if not str(mapping.get("target_dir") or "").strip():
                return "STRM 输出目录不能为空"
        return ""

    def trigger_strm(self) -> Dict[str, Any]:
        if error := self._strm_start_error():
            return _error(error)
        moviepilot_url = self._strm_moviepilot_url()
        return self._start("strm", lambda: self.run_strm(moviepilot_url), "STRM 同步已开始")

    def trigger_upload(
        self,
        payload: Dict[str, Any] | bool | None = None,
    ) -> Dict[str, Any]:
        if error := self._upload_start_error():
            return _error(error)
        incremental = payload if isinstance(payload, bool) else bool((payload or {}).get("incremental", True))
        moviepilot_url = self._strm_moviepilot_url()
        return self._start(
            "upload",
            lambda: self.run_upload(incremental, moviepilot_url),
            "目录上传已开始",
        )

    def _upload_start_error(self) -> str:
        config = self._store.get_config()
        if not config.get("upload_generate_strm"):
            return ""
        try:
            normalize_moviepilot_url(str(config.get("moviepilot_address") or ""))
        except ValueError as err:
            return str(err)
        mappings = [
            mapping
            for mapping in config.get("upload_mappings") or []
            if isinstance(mapping, dict) and mapping.get("enabled", True)
        ]
        for mapping in mappings:
            if not str(mapping.get("strm_target") or "").strip():
                return "上传完成生成 STRM 时，每个映射都必须配置 STRM 输出目录"
        return ""

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
            incremental,
            download_sidecars=bool(config.get("strm_download_sidecars", False)),
            sidecar_extensions=str(config.get("upload_sidecar_extensions") or ""),
        )
        entries = []
        totals = {
            "added": 0,
            "updated": 0,
            "removed": 0,
            "sidecars": 0,
            "skipped": 0,
            "conflicts": 0,
            "errors": 0,
            "duration_ms": 0,
        }
        for mapping in mappings:
            access_limited = False
            source = str(mapping.get("source_path") or mapping.get("source_cid") or "-")
            target = str(mapping.get("target_dir") or "-")
            logger.info(f"【STRM同步】开始处理映射：{source} -> {target}")
            mapping_started = monotonic()
            try:
                entry = retry_call(
                    lambda: generator.run_mapping(mapping),
                    attempts=3,
                    delay=3.0,
                    abort_on=(U115AccessLimitError, U115AuthError),
                )
            except U115AccessLimitError as err:
                access_limited = True
                logger.error(
                    f"【STRM同步】115 访问上限重试耗尽，停止后续映射："
                    f"{source} -> {target}，原因：{safe_error_text(err)}"
                )
                entry = {
                    "kind": "strm",
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "mapping": source,
                    "errors": 1,
                    "message": str(err),
                }
            except U115AuthError as err:
                access_limited = True
                logger.error(
                    f"【STRM同步】115 授权失效，停止后续映射："
                    f"{source} -> {target}，原因：{safe_error_text(err)}"
                )
                entry = {
                    "kind": "strm",
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "mapping": source,
                    "errors": 1,
                    "message": str(err),
                }
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
                f"清理 {int(entry.get('removed') or 0)}，"
                f"附属文件 {int(entry.get('sidecars') or 0)}，"
                f"跳过 {int(entry.get('skipped') or 0)}，失败 {int(entry.get('errors') or 0)}，"
                f"冲突候选 {int(entry.get('conflicts') or 0)}，"
                f"耗时 {int(entry.get('duration_ms') or 0)}ms"
            )
            log_result = logger.warning if int(entry.get("errors") or 0) else logger.info
            log_result(f"【STRM同步】映射完成：{source} -> {target}，{summary}")
            if access_limited:
                remaining = len(mappings) - len(entries)
                if remaining:
                    logger.warning(f"【STRM同步】延后剩余 {remaining} 个映射至下次任务")
                break
        total_summary = (
            f"新增 {totals['added']}，更新 {totals['updated']}，清理 {totals['removed']}，"
            f"附属文件 {totals['sidecars']}，"
            f"跳过 {totals['skipped']}，冲突候选 {totals['conflicts']}，"
            f"失败 {totals['errors']}，耗时 {totals['duration_ms']}ms"
        )
        log_total = logger.warning if totals["errors"] else logger.info
        log_total(f"【STRM同步】执行完成，{total_summary}")
        return entries

    def run_upload(self, incremental: bool = True, moviepilot_url: str = "") -> Dict[str, Any]:
        config = self._store.get_config()
        mappings = [mapping for mapping in config.get("upload_mappings") or [] if mapping.get("enabled", True)]
        logger.info(f"【目录上传】开始执行，模式：{'增量' if incremental else '全量'}，有效映射：{len(mappings)}")
        try:
            entry = DirectoryUploader(
                self._client_provider(),
                self._store,
                config,
                moviepilot_url or str(config.get("moviepilot_address") or ""),
            ).run(incremental)
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
            f"生成 STRM {int(entry.get('strm_generated') or 0)}，"
            f"跳过 {int(entry.get('skipped') or 0)}，删除 {int(entry.get('deleted') or 0)}，"
            f"延后 {int(entry.get('deferred') or 0)}，"
            f"失败 {int(entry.get('errors') or 0)}，耗时 {int(entry.get('duration_ms') or 0)}ms"
        )
        log_result = logger.warning if int(entry.get("errors") or 0) else logger.info
        log_result(f"【目录上传】执行完成，{summary}")
        return entry

    def run_checkin(self) -> Dict[str, Any]:
        if not self._checkin_lock.acquire(blocking=False):
            logger.warning("【115签到】签到任务正在运行，忽略重复触发")
            return _error("签到任务正在运行", busy=True)
        if not self._cloud_task_lock.acquire(blocking=False):
            self._checkin_lock.release()
            logger.warning("【115签到】115 数据任务正在运行，忽略本次签到")
            return _error("115 数据任务正在运行，请稍后签到", busy=True)
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
            self._cloud_task_lock.release()
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
        elif result.get("busy"):
            state["next_run_ts"] = now.timestamp() + 300
        else:
            state["next_run_ts"] = None
        self._store.save_checkin_schedule(state)
        return result

    def history(self) -> Dict[str, Any]:
        return _ok({"items": self._store.get_history()})

    @staticmethod
    def _download_url_lifetime(url: str) -> float | None:
        expires_value = next(
            (value for key, value in parse_qsl(urlsplit(url).query) if key == "t"),
            None,
        )
        if expires_value is None:
            return None
        try:
            remaining = int(expires_value) - time()
        except (TypeError, ValueError):
            return None
        if remaining <= 0:
            raise U115ApiError("115 下载地址已过期")
        return remaining

    @classmethod
    def _download_url_cache_ttl(cls, url: str) -> float | None:
        remaining = cls._download_url_lifetime(url)
        if remaining is None:
            return None
        ttl = remaining - cls._DOWNLOAD_URL_CACHE_SAFETY_SECONDS
        return ttl if ttl > 0 else None

    @staticmethod
    def _redirect_response(url: str, file_name: str = "") -> RedirectResponse:
        name = str(file_name or "").replace("\\", "/").rpartition("/")[-1].strip()
        if not name:
            name = unquote(urlsplit(url).path.rpartition("/")[-1])
        name = name.replace("\r", "").replace("\n", "")
        headers: Dict[str, str] = {}
        if name:
            try:
                name.encode("ascii")
                headers["Content-Disposition"] = f'inline; filename="{name.replace(chr(34), "_")}"'
            except UnicodeEncodeError:
                headers["Content-Disposition"] = f"inline; filename*=UTF-8''{quote(name, safe='')}"
        return RedirectResponse(url, status_code=302, headers=headers)

    @staticmethod
    def _schedule_playback_copy_cleanup(
        client: U115Client,
        file_id: str,
        auth_mode: str,
        delay_seconds: float,
    ) -> None:
        def cleanup() -> None:
            try:
                client.delete_file(file_id, mode=auth_mode)
                logger.debug(f"【302跳转服务】清理 {file_id} 文件")
            except Exception as err:  # noqa: BLE001
                logger.error(f"【302跳转服务】清理多端播放副本失败：{safe_error_text(err)}")

        timer = threading.Timer(max(0.0, delay_seconds), cleanup)
        timer.daemon = True
        timer.start()

    @contextmanager
    def _redirect_singleflight(self, pickcode: str) -> Iterator[None]:
        with self._redirect_flights_guard:
            current = self._redirect_flights.get(pickcode)
            if current is None:
                flight_lock = threading.Lock()
                self._redirect_flights[pickcode] = (flight_lock, 1)
            else:
                flight_lock, users = current
                self._redirect_flights[pickcode] = (flight_lock, users + 1)

        flight_lock.acquire()
        try:
            yield
        finally:
            flight_lock.release()
            with self._redirect_flights_guard:
                current = self._redirect_flights.get(pickcode)
                if current is not None and current[0] is flight_lock:
                    if current[1] == 1:
                        self._redirect_flights.pop(pickcode, None)
                    else:
                        self._redirect_flights[pickcode] = (flight_lock, current[1] - 1)

    def redirect(
        self,
        request: Request,
        pickcode: str = "",
        file_name: str = "",
        sign: str = "",
    ):
        try:
            pickcode = normalize_pickcode(pickcode)
        except ValueError as err:
            return JSONResponse({"success": False, "message": str(err)}, status_code=400)
        if not verify_redirect_signature(
            self._store.get_redirect_secret(),
            pickcode,
            sign,
        ):
            return JSONResponse(
                {"success": False, "message": "无效播放签名"},
                status_code=403,
            )
        user_agent = str(request.headers.get("user-agent") or "")
        auth_mode = str(
            self._store.get_config().get("link_redirect_mode") or "cookie"
        ).strip().lower()
        cache_ua = user_agent or "NoUA"
        cache_key = (pickcode, cache_ua, auth_mode)
        cached_url = self._redirect_cache.get(cache_key)
        if cached_url:
            return self._redirect_response(cached_url, file_name)
        with self._redirect_singleflight(pickcode):
            cached_url = self._redirect_cache.get(cache_key)
            if cached_url:
                return self._redirect_response(cached_url, file_name)

            client: U115Client | None = None
            playback_copy = None
            playback_copy_cleanup_delay = 0.0
            try:
                client = self._client_provider()
                post_pickcode = pickcode
                if (
                    self._store.get_config().get("same_playback")
                    and self._redirect_cache.count(lambda key: key[0] == pickcode) > 0
                ):
                    playback_copy = client.create_playback_copy(pickcode, mode=auth_mode)
                    post_pickcode = playback_copy.pickcode
                    logger.debug(
                        f"【302跳转服务】多端播放开启 {pickcode} -> {post_pickcode}"
                    )

                def fetch_url() -> str:
                    url = client.get_download_url(
                        post_pickcode,
                        user_agent=user_agent,
                        mode=auth_mode,
                    )
                    if not url:
                        raise U115ApiError("未获取到 115 下载地址")
                    return url

                url = retry_call(
                    fetch_url,
                    attempts=3,
                    delay=1.0,
                    abort_on=(U115AccessLimitError, U115AuthError),
                )
                lifetime = self._download_url_lifetime(url)
                ttl = (
                    lifetime - self._DOWNLOAD_URL_CACHE_SAFETY_SECONDS
                    if lifetime is not None
                    else None
                )
                if ttl is not None and ttl <= 0:
                    ttl = None
                if playback_copy is not None:
                    playback_copy_cleanup_delay = (
                        lifetime + self._PLAYBACK_COPY_CLEANUP_GRACE_SECONDS
                        if lifetime is not None
                        else self._PLAYBACK_COPY_CLEANUP_FALLBACK_SECONDS
                    )
                if ttl is not None:
                    self._redirect_cache.set(cache_key, url, ttl_seconds=ttl)
                return self._redirect_response(url, file_name)
            except Exception as err:  # noqa: BLE001
                logger.error(f"【302取链】获取下载地址失败：{safe_error_text(err)}")
                return JSONResponse({"success": False, "message": f"取链失败: {err}"}, status_code=502)
            finally:
                if client is not None and playback_copy is not None:
                    try:
                        self._schedule_playback_copy_cleanup(
                            client,
                            playback_copy.file_id,
                            playback_copy.auth_mode or auth_mode,
                            playback_copy_cleanup_delay,
                        )
                    except Exception as err:  # noqa: BLE001
                        logger.error(f"【302跳转服务】安排多端播放副本清理失败：{safe_error_text(err)}")

    def _start(self, kind: str, target: Callable[[], Any], message: str) -> Dict[str, Any]:
        label = self._TASK_LABELS.get(kind, kind)
        cloud_lock_acquired = False
        with self._lock:
            if kind in self._running:
                logger.warning(f"【{label}】任务正在运行，忽略重复触发")
                return _error(f"{kind} 任务正在运行")
            if kind in self._CLOUD_TASK_KINDS:
                cloud_lock_acquired = self._cloud_task_lock.acquire(blocking=False)
                if not cloud_lock_acquired:
                    running = "/".join(
                        self._TASK_LABELS.get(item, item)
                        for item in sorted(self._running & self._CLOUD_TASK_KINDS)
                    )
                    detail = f"（{running}）" if running else ""
                    logger.warning(
                        f"【{label}】115 数据任务正在运行{detail}，忽略本次触发"
                    )
                    return _error(f"115 数据任务正在运行{detail}，请稍后重试")
            self._running.add(kind)
        def run() -> None:
            try:
                target()
            except Exception as err:  # noqa: BLE001
                logger.error(f"【{label}】后台任务异常终止：{safe_error_text(err)}")
            finally:
                with self._lock:
                    self._running.discard(kind)
                if cloud_lock_acquired:
                    self._cloud_task_lock.release()

        thread = threading.Thread(target=run, name=f"p115liteassistant-{kind}", daemon=True)
        try:
            thread.start()
        except Exception as err:  # noqa: BLE001
            with self._lock:
                self._running.discard(kind)
            if cloud_lock_acquired:
                self._cloud_task_lock.release()
            logger.error(f"【{label}】任务启动失败：{safe_error_text(err)}")
            return _error(f"{kind} 任务启动失败")
        logger.info(f"【{label}】任务已提交")
        return _ok(message=message)
