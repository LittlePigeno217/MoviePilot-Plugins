from __future__ import annotations

import re
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

import requests

from apscheduler.triggers.cron import CronTrigger
from app.core.config import settings
from app.log import logger
from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

from .checkin_schedule import random_epoch_for_date, pick_next_run_epoch
from .client import U115AccessLimitError, U115ApiError, U115AuthError, U115Client
from .file_types import DEFAULT_MEDIA_EXTENSIONS, parse_extensions
from .log_utils import safe_error_text
from .notify import (
    CHANNELS as NOTIFY_CHANNELS,
    NOTIFY_TYPE_NAMES,
    NOTIFY_TYPE_SWITCHS_NAMES,
    Notifier,
    normalize_notify_type,
)
from .rate_limiter import RateLimiter
from .reverse_delete import RECENT_DELETE_TTL, ReverseDeleter
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


def _cron_error(text: str) -> str:
    """校验五位 cron 表达式，合法返回空串，非法返回给用户看的原因。"""
    try:
        CronTrigger.from_crontab(str(text or "").strip())
    except Exception as err:  # noqa: BLE001
        return str(err) or "表达式无法解析"
    return ""


class Api:
    _TASK_LABELS = {"strm": "STRM同步", "upload": "目录上传", "sweep": "STRM反向删除"}
    _CLOUD_TASK_KINDS = frozenset({"strm", "upload", "sweep"})
    _DOWNLOAD_URL_CACHE_SAFETY_SECONDS = 300
    _PLAYBACK_COPY_CLEANUP_GRACE_SECONDS = 60
    _PLAYBACK_COPY_CLEANUP_FALLBACK_SECONDS = 300
    # /redirect 是匿名接口（播放器带不了 MoviePilot 的 JWT），签名之外再按来源 IP 限流，
    # 免得签名泄漏后被人当免费下载中转。上限按单个播放器的正常请求量留足余量。
    _REDIRECT_RATE_LIMIT = 60
    _REDIRECT_RATE_WINDOW = 60.0

    def __init__(
        self,
        client_provider: Callable[[], U115Client],
        store: Store,
        on_config_saved: Callable[[], None] | None = None,
        life_monitor_status: Callable[[], bool] | None = None,
        notifier: Notifier | None = None,
        strm_watch_status: Callable[[], bool] | None = None,
    ):
        self._client_provider = client_provider
        self._store = store
        self._on_config_saved = on_config_saved
        self._life_monitor_status = life_monitor_status
        self._strm_watch_status = strm_watch_status
        self._notifier = notifier or Notifier(store.get_config)
        self._running: set[str] = set()
        # 反向删除的待处理范围记在编排层：抢不到 115 数据任务锁的删除事件不会丢，
        # 锁释放时由 _drain_pending_sweep 接着跑完。None 语义的「全量」单独用布尔表示，
        # 因为空列表表示「没有待处理路径」，绝不能被当成「清理所有记录」。
        self._pending_sweep_paths: set[str] = set()
        self._pending_sweep_all = False
        # 反向删除刚清掉的 pickcode，正向同步据此跳过重建（115 列表接口有延迟）
        self._recent_deletes: TtlCache[str, bool] = TtlCache(RECENT_DELETE_TTL, maxsize=4096)
        self._lock = threading.Lock()
        self._cloud_task_lock = threading.Lock()
        self._checkin_lock = threading.Lock()
        self._browse_115_cache: TtlCache[str, list[Dict[str, Any]]] = TtlCache(30)
        self._redirect_cache: TtlCache[tuple[str, str, str], str] = TtlCache(60, maxsize=8096)
        self._redirect_flights_guard = threading.Lock()
        self._redirect_flights: Dict[str, tuple[Any, int]] = {}
        self._redirect_rate_limiter = RateLimiter(
            self._REDIRECT_RATE_LIMIT,
            self._REDIRECT_RATE_WINDOW,
        )

    def get_config(self) -> Dict[str, Any]:
        config = deepcopy(self._store.get_config())
        config.pop("tokens", None)
        # 附加动态通知类型列表（从 MoviePilot MessageType 源派生），供前端渲染「消息类型」下拉，
        # 与 MoviePilot 通知渠道 switchs 分流的中文 value 保持同步。
        try:
            config["notify_types"] = [
                {"value": name, "title": NOTIFY_TYPE_SWITCHS_NAMES[name]}
                for name in NOTIFY_TYPE_NAMES
                if name in NOTIFY_TYPE_SWITCHS_NAMES
            ]
        except Exception:  # noqa: BLE001
            config.pop("notify_types", None)
        return config

    def save_config(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        payload = payload or {}
        if not isinstance(payload, dict):
            return _error("配置格式无效")
        updates = dict(payload)
        if "monitor_life_enabled" in updates and "life_monitor_enabled" not in updates:
            updates["life_monitor_enabled"] = updates["monitor_life_enabled"]
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
        if "strm_delete_sweep_cron" in updates:
            cron_text = str(updates.get("strm_delete_sweep_cron") or "").strip()
            if cron_text and (error := _cron_error(cron_text)):
                return _error(f"反向删除巡检周期无效：{error}")
            updates["strm_delete_sweep_cron"] = cron_text
        # 消息类型只接受白名单里的枚举名，界面传了别的就退回 Plugin
        for meta in NOTIFY_CHANNELS.values():
            type_key = meta["type_key"]
            if type_key in updates:
                updates[type_key] = normalize_notify_type(updates[type_key])
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
        if self._on_config_saved:
            try:
                self._on_config_saved()
            except Exception as err:  # noqa: BLE001
                logger.error(f"【配置】保存后刷新运行服务失败：{safe_error_text(err)}")
                return _error(f"配置已保存，但刷新运行服务失败：{err}")
        return _ok(message="配置已保存")

    def test_notify(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """发送一条模拟通知，走 MoviePilot 完整通知管道（post_message → 模板渲染 → 渠道分流 → 各模块发送）。

        可选参数：
        - channel: strm | upload | checkin（默认 upload）
        - title: 自定义标题（默认按通道生成）
        """
        payload = payload or {}
        channel = str(payload.get("channel") or "upload").strip()
        meta = NOTIFY_CHANNELS.get(channel)
        if not meta:
            return _error(f"未知通知通道: {channel}，可选: {', '.join(NOTIFY_CHANNELS)}")
        if not self._notifier.is_enabled(channel):
            return _error(
                f"通道未开启：{meta['label']}（{meta['enabled_key']}=True 才发送），"
                f"当前类型 {meta['type_key']}="
                f"{self._store.get_config().get(meta['type_key'])}"
            )
        headline = str(payload.get("title") or "模拟测试通知")
        lines = [
            "━━━━━━━━━━━━━",
            "**📨 MoviePilot 通知管道测试**",
            "• 通道：115 轻量助手",
            f"• 消息类型：{self._store.get_config().get(meta['type_key'])}",
            "• 说明：本条由插件 API /test-notify 触发，走宿主 post_message 完整链路",
            f"• 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        self._notifier.notify(channel, headline, lines)
        return _ok(message=f"已通过 MoviePilot 通知管道发送（{meta['label']}）")

    @property
    def cloud_task_lock(self) -> threading.Lock:
        return self._cloud_task_lock

    @property
    def recent_deletes(self) -> TtlCache:
        """反向删除刚清掉的条目，正向同步与生活监控共用这一份。"""
        return self._recent_deletes

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
                return {"status": -3, "tip": result.get("message") or "检查登录状态失败"}
            data = result.get("data") or {}
            if data.get("status") == 2:
                updates = {
                    "tokens": client.export_tokens(),
                    "login_client_type": client.client_type,
                }
                if client.cookie:
                    updates["cookie"] = client.cookie
                self._store.update_config(updates)
                self._browse_115_cache.clear()
                self._redirect_cache.clear()
            return data
        except Exception as err:  # noqa: BLE001
            logger.error(f"【登录】检查登录状态失败：{safe_error_text(err)}")
            return {"status": -3, "tip": "检查登录状态失败"}

    def browse_115(self, cid: str = "0") -> Dict[str, Any]:
        try:
            cache_key = str(cid or "0")
            cached = self._browse_115_cache.get(cache_key)
            if cached is not None:
                return {"cid": cache_key, "items": deepcopy(cached)}
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
            return {"cid": cache_key, "items": items}
        except Exception as err:  # noqa: BLE001
            logger.error(f"【浏览】浏览 115 目录失败：{safe_error_text(err)}")
            return {"error": safe_error_text(err)}

    @staticmethod
    def _local_roots() -> list[Path]:
        root = Path("/").resolve()
        return [root] if root.is_dir() else []

    def browse_local(self, path: str = "", root: str = "") -> Dict[str, Any]:
        try:
            roots = self._local_roots()
            if not roots:
                return {"error": "MoviePilot 根目录不可用"}
            requested_root = Path(root).expanduser().resolve() if root else None
            base = next((item for item in roots if item == requested_root), roots[0])
            if requested_root and base != requested_root:
                return {"error": "本地目录根路径无效"}
            target = (base / path).resolve() if path else base
            target.relative_to(base)
            if not target.is_dir():
                return {"error": f"目录不存在: {target}"}
            return {
                "base": str(base),
                "roots": [{"name": str(item), "path": str(item)} for item in roots],
                "current": "" if target == base else target.relative_to(base).as_posix(),
                "items": [
                    {"name": entry.name, "path": entry.relative_to(base).as_posix()}
                    for entry in sorted(target.iterdir(), key=lambda item: item.name.lower())
                    if entry.is_dir() and not entry.name.startswith(".")
                ],
            }
        except ValueError:
            return {"error": "目录超出 MoviePilot 根目录"}
        except Exception as err:  # noqa: BLE001
            logger.error(f"【浏览】浏览本地目录失败：{safe_error_text(err)}")
            return {"error": safe_error_text(err)}

    def status(self) -> Dict[str, Any]:
        try:
            config = self._store.get_config()
            with self._lock:
                running = sorted(self._running)
            return {
                "enabled": bool(config.get("enabled")),
                "authenticated": self._client_provider().is_authenticated(),
                "strm_mappings": len(config.get("strm_mappings") or []),
                "upload_mappings": len(config.get("upload_mappings") or []),
                "life_monitor_enabled": bool(config.get("life_monitor_enabled")),
                "life_monitor_running": bool(
                    self._life_monitor_status and self._life_monitor_status()
                ),
                "strm_delete_enabled": bool(config.get("strm_delete_cloud_on_missing")),
                "strm_delete_watch_running": bool(
                    self._strm_watch_status and self._strm_watch_status()
                ),
                "pending_sweep": self._pending_sweep_text(),
                "pending_deletes": [
                    {
                        "id": str(batch.get("id") or ""),
                        "mapping": str(batch.get("mapping") or "-"),
                        "count": int(batch.get("count") or 0),
                        "updated_at": str(batch.get("updated_at") or ""),
                        "items_truncated": bool(batch.get("items_truncated")),
                    }
                    for batch in self._store.get_strm_delete_pending().values()
                    if isinstance(batch, dict)
                ],
                "running": running,
                "history": self._store.get_history(),
                "recent_uploads": self._store.get_recent_uploaded_media(
                    parse_extensions(
                        config.get("upload_media_extensions", ""),
                        DEFAULT_MEDIA_EXTENSIONS,
                    )
                ),
            }
        except Exception as err:  # noqa: BLE001
            logger.error(f"【状态】获取运行状态失败：{safe_error_text(err)}")
            return {"error": safe_error_text(err)}

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
            recent_deletes=self._recent_deletes,
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
        self._notify_strm(entries, totals, incremental)
        return entries

    # ---- 反向删除：本地 STRM 被删除后清理 115 云端 ----

    def _sweep_start_error(self) -> str:
        config = self._store.get_config()
        if not config.get("enabled"):
            return "插件未启用"
        if not config.get("strm_delete_cloud_on_missing"):
            return "未开启「本地 STRM 被删除时同步删除 115 对应文件」"
        mappings = [
            mapping
            for mapping in config.get("strm_mappings") or []
            if isinstance(mapping, dict) and mapping.get("enabled", True)
        ]
        if not mappings:
            return "没有启用的 STRM 通道"
        for mapping in mappings:
            if not str(mapping.get("target_dir") or "").strip():
                return "STRM 输出目录不能为空"
        return ""

    def trigger_strm_sweep(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """手动触发反向删除：抢不到 115 数据任务锁时直接拒绝并说明原因。"""
        paths = (payload or {}).get("paths") if isinstance(payload, dict) else None
        return self._enqueue_strm_sweep(paths, auto=False)

    def queue_strm_sweep(self, paths: Any = None) -> Dict[str, Any]:
        """自动触发（定时巡检、本地删除监听）：抢不到锁不算失败，排队等补跑。"""
        return self._enqueue_strm_sweep(paths, auto=True)

    def run_scheduled_strm_sweep(self) -> Dict[str, Any]:
        """定时巡检入口 —— 兜住实时监听漏掉的删除（容器重启、事件丢失、网络挂载等）。"""
        return self.queue_strm_sweep()

    def _enqueue_strm_sweep(self, paths: Any = None, auto: bool = False) -> Dict[str, Any]:
        """反向删除的唯一入口：先把范围记进编排层，再尝试起任务。"""
        if error := self._sweep_start_error():
            return _error(error)
        queued = self._queue_sweep_scope(paths)
        result = self._start("sweep", self._sweep_worker, "STRM 反向删除已开始")
        if result.get("success") or not auto:
            return result
        logger.info(
            f"【STRM反向删除】{queued}已排队，等当前 115 任务结束后自动补跑"
        )
        return _ok(data={"queued": queued}, message="已排队，等当前任务结束后自动补跑")

    def _queue_sweep_scope(self, paths: Any = None) -> str:
        """登记待巡检范围。``paths`` 为 None 表示全量巡检。返回排队情况的文字描述。"""
        with self._lock:
            if paths is None:
                self._pending_sweep_all = True
            else:
                for item in paths:
                    value = str(item or "").strip()
                    if value:
                        self._pending_sweep_paths.add(value)
            if self._pending_sweep_all:
                return "全部记录"
            return f"{len(self._pending_sweep_paths)} 个路径"

    def _take_sweep_scope(self) -> tuple[list[str] | None, bool]:
        """取走待巡检范围，返回 ``(范围, 是否有内容)``；范围为 None 表示全量。

        空列表不等于全量 —— 那会把「没有待处理路径」误判成「清理所有记录」。
        """
        with self._lock:
            full = self._pending_sweep_all
            paths = sorted(self._pending_sweep_paths)
            self._pending_sweep_all = False
            self._pending_sweep_paths = set()
        if full:
            return None, True
        return paths, bool(paths)

    def _pending_sweep_text(self) -> str:
        """运行台用：有没有一批删除在等当前任务结束。没有就返回空串。"""
        with self._lock:
            if self._pending_sweep_all:
                return "全部记录"
            count = len(self._pending_sweep_paths)
        return f"{count} 个路径" if count else ""

    def _sweep_worker(self) -> list[Dict[str, Any]]:
        scope, has_scope = self._take_sweep_scope()
        if not has_scope:
            logger.debug("【STRM反向删除】没有待处理的目标，本次跳过")
            return []
        return self.run_strm_sweep(scope)

    def _drain_pending_sweep(self) -> None:
        """115 数据任务释放锁之后补跑排队中的反向删除；没有排队就什么都不做。"""
        with self._lock:
            if not (self._pending_sweep_paths or self._pending_sweep_all):
                return
            if "sweep" in self._running:
                return
        if self._sweep_start_error():
            return
        logger.debug("【STRM反向删除】上一个 115 任务已结束，补跑排队中的反向删除")
        self._start("sweep", self._sweep_worker, "STRM 反向删除已开始")

    _SWEEP_COUNT_KEYS = (
        "cloud_deleted",
        "scrapes_deleted",
        "cloud_dirs_deleted",
        "already_gone",
        "unidentified",
        "records_dropped",
        "errors",
        "pending",
        "queued",
    )

    @classmethod
    def _sweep_entry_is_noteworthy(cls, entry: Dict[str, Any]) -> bool:
        """这条巡检结果值不值得占一格执行记录。

        巡检每两小时跑一次，绝大多数轮次什么都没发生；照常写记录会把只有 50 条的
        历史刷空。只有真动过东西、或者护栏拦下了一次（那正是用户最需要看到的）才留。
        """
        if any(int(entry.get(key) or 0) for key in cls._SWEEP_COUNT_KEYS):
            return True
        return bool(str(entry.get("reason") or "").strip())

    def run_strm_sweep(
        self,
        paths: list[str] | None = None,
        *,
        bypass_confirm: bool = False,
        mapping_id: str = "",
    ) -> list[Dict[str, Any]]:
        config = self._store.get_config()
        mappings = [
            mapping
            for mapping in config.get("strm_mappings") or []
            if isinstance(mapping, dict) and mapping.get("enabled", True)
        ]
        if mapping_id:
            mappings = [
                mapping
                for mapping in mappings
                if ReverseDeleter.mapping_prefixes(mapping)[0] == mapping_id
            ]
        if not mappings:
            logger.warning("【STRM反向删除】没有匹配的 STRM 通道，任务结束")
            return []
        deleter = ReverseDeleter(self._client_provider, self._store, self._recent_deletes)
        scope_text = "全部记录" if paths is None else f"{len(paths)} 个路径"
        logger.info(
            f"【STRM反向删除】开始执行，范围：{scope_text}，有效通道：{len(mappings)}"
        )
        entries: list[Dict[str, Any]] = []
        totals: Dict[str, int] = {key: 0 for key in self._SWEEP_COUNT_KEYS}
        totals["duration_ms"] = 0
        for mapping in mappings:
            label = ReverseDeleter.mapping_label(mapping)
            started = monotonic()
            stop = False
            try:
                entry = deleter.sweep(mapping, paths, bypass_confirm=bypass_confirm)
            except (U115AccessLimitError, U115AuthError) as err:
                stop = True
                logger.error(
                    f"【STRM反向删除】115 访问受限或授权失效，停止后续通道：{label}，"
                    f"原因：{safe_error_text(err)}"
                )
                entry = {
                    "kind": "strm_sweep",
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "mapping": label,
                    "errors": 1,
                    "message": str(err),
                }
            except Exception as err:  # noqa: BLE001
                logger.error(
                    f"【STRM反向删除】通道处理失败：{label}，原因：{safe_error_text(err)}"
                )
                entry = {
                    "kind": "strm_sweep",
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "mapping": label,
                    "errors": 1,
                    "message": str(err),
                }
            entry["duration_ms"] = int(entry.get("duration_ms") or (monotonic() - started) * 1000)
            if self._sweep_entry_is_noteworthy(entry):
                self._store.append_history(entry)
            entries.append(entry)
            for key in totals:
                totals[key] += int(entry.get(key) or 0)
            if stop:
                break
        summary = (
            f"云端删除 {totals['cloud_deleted']}，刮削 {totals['scrapes_deleted']}，"
            f"空目录 {totals['cloud_dirs_deleted']}，新入队 {totals['pending']}，"
            f"队列中等待 {totals['queued']}，云端已无 {totals['already_gone']}，"
            f"溯源缺失 {totals['unidentified']}，失败 {totals['errors']}，"
            f"耗时 {totals['duration_ms']}ms"
        )
        log_total = logger.warning if totals["errors"] else logger.info
        log_total(f"【STRM反向删除】执行完成，{summary}")
        self._notify_strm_sweep(entries, totals)
        return entries

    def _notify_strm_sweep(
        self,
        entries: list[Dict[str, Any]],
        totals: Dict[str, int],
    ) -> None:
        """反向删除通知复用 STRM 通道 —— 删除是破坏性动作，只要动过就报一声。"""
        if not any(self._sweep_entry_is_noteworthy(entry) for entry in entries):
            return
        if not self._notifier.is_enabled("strm"):
            return
        if totals.get("errors"):
            headline = "❌ 有失败"
        elif totals.get("pending"):
            headline = "⏸ 待确认"
        else:
            headline = "✅ 已清理"
        lines = [
            f"  {headline}  │  {len(entries)} 通道  │  {self._duration_text(totals.get('duration_ms'))}",
            "",
            f"  云端删除 {totals.get('cloud_deleted', 0)}  ·  刮削 {totals.get('scrapes_deleted', 0)}"
            f"  ·  空目录 {totals.get('cloud_dirs_deleted', 0)}",
        ]
        if totals.get("pending"):
            lines.append(f"  待人工确认 {totals['pending']} 个，请到插件运行台处理")
        if totals.get("unidentified"):
            lines.append(
                f"  {totals['unidentified']} 条记录缺少 115 溯源信息，跑一次全量 STRM 同步即可补齐"
            )
        for entry in entries:
            reason = str(entry.get("reason") or "").strip()
            if reason:
                lines.append(f"  📁 {entry.get('mapping') or '-'}  ·  {reason}")
        self._notifier.notify("strm", headline, lines)

    _PENDING_PAGE_LIMIT = 200

    def strm_delete_pending(
        self,
        batch_id: str = "",
        offset: int = 0,
        limit: int = 0,
    ) -> Dict[str, Any]:
        """待确认删除批次。

        不带 ``batch_id`` 时返回各批次摘要 + 少量样本路径，够运行台画卡片；带 ``batch_id``
        时返回**那一批的完整清单**（分页），删除前该看的就是这个。
        """
        batches = self._store.get_strm_delete_pending()
        if batch_id:
            batch = batches.get(str(batch_id))
            if not isinstance(batch, dict):
                return _error("批次不存在或已处理")
            items = [item for item in (batch.get("items") or []) if isinstance(item, dict)]
            page_limit = max(1, int(limit or self._PENDING_PAGE_LIMIT))
            page_offset = max(0, int(offset or 0))
            window = items[page_offset : page_offset + page_limit]
            return _ok(
                {
                    "id": str(batch.get("id") or ""),
                    "mapping": str(batch.get("mapping") or "-"),
                    "count": int(batch.get("count") or 0),
                    "created_at": str(batch.get("created_at") or ""),
                    "updated_at": str(batch.get("updated_at") or ""),
                    "reason": str(batch.get("reason") or ""),
                    "items_truncated": bool(batch.get("items_truncated")),
                    "offset": page_offset,
                    "limit": page_limit,
                    "total": len(items),
                    "items": [
                        {
                            "path": str(item.get("path") or ""),
                            "cloud_path": str(item.get("cloud_path") or ""),
                            "name": str(item.get("name") or ""),
                        }
                        for item in window
                    ],
                }
            )
        ordered = sorted(
            (batch for batch in batches.values() if isinstance(batch, dict)),
            key=lambda batch: str(batch.get("created_at") or ""),
            reverse=True,
        )
        summary = [
            {
                "id": str(batch.get("id") or ""),
                "mapping": str(batch.get("mapping") or "-"),
                "count": int(batch.get("count") or 0),
                "created_at": str(batch.get("created_at") or ""),
                "updated_at": str(batch.get("updated_at") or ""),
                "reason": str(batch.get("reason") or ""),
                "items_truncated": bool(batch.get("items_truncated")),
                "samples": [
                    str(item.get("path") or "")
                    for item in (batch.get("items") or [])[:20]
                    if isinstance(item, dict)
                ],
            }
            for batch in ordered
        ]
        return _ok({"batches": summary})

    @staticmethod
    def _requested_batch_ids(payload: Dict[str, Any] | None) -> list[str]:
        """取要处理的批次 ID：单个 ``batch_id`` 或一组 ``batch_ids``（运行台的全部确认/驳回）。"""
        payload = payload or {}
        raw = payload.get("batch_ids")
        if raw is None:
            raw = [payload.get("batch_id")]
        elif isinstance(raw, str):
            raw = [raw]
        result: list[str] = []
        for value in raw or []:
            text = str(value or "").strip()
            if text and text not in result:
                result.append(text)
        return result

    def confirm_strm_delete(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """确认执行待删批次。护栏照跑、本地存在性重新核对，只跳过规模闸门。"""
        batch_ids = self._requested_batch_ids(payload)
        if not batch_ids:
            return _error("缺少批次 ID")
        if error := self._sweep_start_error():
            return _error(error)
        taken: list[Dict[str, Any]] = []
        for batch_id in batch_ids:
            batch = self._store.pop_strm_delete_batch(batch_id)
            if isinstance(batch, dict):
                taken.append(batch)
        if not taken:
            return _error("批次不存在或已处理")
        jobs: list[tuple[str, list[str]]] = []
        for batch in taken:
            paths = [
                str(item.get("path") or "")
                for item in (batch.get("items") or [])
                if isinstance(item, dict) and item.get("path")
            ]
            if paths:
                jobs.append((str(batch.get("mapping_id") or ""), paths))
        if not jobs:
            self._restore_batches(taken)
            return _error("批次没有可执行的明细，请等下一轮巡检重新统计")
        total = sum(len(paths) for _mapping_id, paths in jobs)
        result = self._start(
            "sweep",
            lambda: [entry for job in jobs for entry in self.run_strm_sweep(
                job[1], bypass_confirm=True, mapping_id=job[0]
            )],
            f"已确认 {len(jobs)} 个批次，开始清理 {total} 个媒体对应的 115 文件",
        )
        if not result.get("success"):
            # 起不来就把批次放回去 —— 用户点了一次不能就这么丢了
            self._restore_batches(taken)
        return result

    def _restore_batches(self, taken: list[Dict[str, Any]]) -> None:
        batches = self._store.get_strm_delete_pending()
        for batch in taken:
            batches[str(batch.get("id") or "")] = batch
        self._store.save_strm_delete_pending(batches)

    def dismiss_strm_delete(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """驳回待删批次：只丢批次，115 云端一个文件都不动。"""
        batch_ids = self._requested_batch_ids(payload)
        if not batch_ids:
            return _error("缺少批次 ID")
        dropped = 0
        for batch_id in batch_ids:
            batch = self._store.pop_strm_delete_batch(batch_id)
            if not isinstance(batch, dict):
                continue
            dropped += 1
            logger.info(
                f"【STRM反向删除】用户驳回待确认批次 {batch_id}"
                f"（{int(batch.get('count') or 0)} 个），115 云端文件保持不动"
            )
        if not dropped:
            return _error("批次不存在或已处理")
        return _ok(message=f"已忽略 {dropped} 个批次，115 云端文件保持不动")

    def _notify_strm(
        self,
        entries: list[Dict[str, Any]],
        totals: Dict[str, int],
        incremental: bool,
    ) -> None:
        """STRM 通道执行完成后的通知，美化卡片 + 按消息类型分流。"""
        if not self._notifier.is_enabled("strm"):
            return
        has_errors = bool(totals.get("errors"))
        status_icon = "❌" if has_errors else "✅"
        status_text = "有失败" if has_errors else "完成"
        duration = self._duration_text(totals.get("duration_ms"))
        title = "115 轻量助手・STRM 同步"

        # 构造卡片元素
        elements: list[dict] = []
        # 状态行
        elements.append({
            "tag": "markdown",
            "content": f"**{status_icon} {status_text}**　<font color='grey'>{'增量' if incremental else '全量'} · {len(entries)} 映射 · {duration}</font>",
            "margin": "0px 16px 0px 16px",
        })
        elements.append({"tag": "hr", "margin": "8px 16px 4px 16px"})

        # 统计三列（新增/更新/清理）
        stat_cols = []
        for value, label in [
            (totals.get("added", 0), "新增"),
            (totals.get("updated", 0), "更新"),
            (totals.get("removed", 0), "清理"),
        ]:
            stat_cols.append({
                "tag": "column", "width": "weighted", "weight": 1,
                "elements": [
                    {"tag": "markdown", "content": f"**{value}**", "margin": "0px", "text_align": "center"},
                    {"tag": "markdown", "content": label, "margin": "0px", "text_align": "center"},
                ],
            })
        elements.append({"tag": "column_set", "flex_mode": "none", "columns": stat_cols,
                         "margin": "8px 16px 0px 16px"})

        # 附属/跳过/失败
        sub_cols = []
        for value, label in [
            (totals.get("sidecars", 0), "附属"),
            (totals.get("skipped", 0), "跳过"),
            (totals.get("errors", 0), "失败"),
        ]:
            sub_cols.append({
                "tag": "column", "width": "weighted", "weight": 1,
                "elements": [
                    {"tag": "markdown", "content": f"**{value}**", "margin": "0px", "text_align": "center"},
                    {"tag": "markdown", "content": label, "margin": "0px", "text_align": "center"},
                ],
            })
        elements.append({"tag": "column_set", "flex_mode": "none", "columns": sub_cols,
                         "margin": "8px 16px 0px 16px"})

        # 映射详情
        has_mapping = False
        for entry in entries:
            mapping = str(entry.get("mapping") or "-")
            if int(entry.get("errors") or 0):
                detail = f"❌ 失败 {int(entry.get('errors') or 0)}"
            else:
                parts = []
                for k, sym in [("added", "+"), ("updated", "~"), ("removed", "✕")]:
                    v = int(entry.get(k) or 0)
                    if v:
                        parts.append(f"{sym}{v}")
                detail = "  ".join(parts) if parts else "无变化"
            message = str(entry.get("message") or "").strip()

            if not has_mapping:
                elements.append({"tag": "hr", "margin": "8px 16px 8px 16px"})
                elements.append({"tag": "markdown", "content": "**映射**", "margin": "0px 16px 0px 16px"})
                has_mapping = True
            line = f"📁 {mapping}  {detail}"
            if message:
                line += f"  ·  {message}"
            elements.append({
                "tag": "markdown", "content": line,
                "margin": "4px 16px 0px 16px",
            })

        # 优先飞书卡片，失败回退文本
        strm_mtype = normalize_notify_type(
            self._store.get_config().get("strm_notify_type")
        )
        if not self._notifier.send_upload_feishu_card(title, elements, mtype=strm_mtype):
            # 文本回退（保持原有纯文本格式）
            headline = "❌ 有失败" if has_errors else "✅ 完成"
            lines = [
                f"  {headline}  │  {'增量' if incremental else '全量'}  │  {len(entries)} 映射  │  {duration}",
            ]
            self._notifier.notify("strm", headline, lines)

    @staticmethod
    def _duration_text(duration_ms: Any) -> str:
        try:
            value = int(duration_ms or 0)
        except (TypeError, ValueError):
            return "-"
        if value <= 0:
            return "-"
        return f"{value}ms" if value < 1000 else f"{value / 1000:.1f}s"

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """将字节转换为人类可读的文件大小。"""
        if not size_bytes:
            return "-"
        units = ["B", "KB", "MB", "GB", "TB"]
        value = float(size_bytes)
        unit_idx = 0
        while value >= 1024 and unit_idx < len(units) - 1:
            value /= 1024
            unit_idx += 1
        if unit_idx == 0:
            return f"{int(value)} {units[unit_idx]}"
        return f"{value:.1f} {units[unit_idx]}"

    @staticmethod
    def _extract_media_title(filename: str) -> str:
        """从文件名中提取媒体标题，用于分组。"""
        stem = str(Path(filename).stem)
        title = re.sub(
            r"(?:19\d{2}|20\d{2})|"
            r"\b(?:2160p|1080p|720p|4K|BluRay|WEB-DL|WEBRip|HDRip|"
            r"HEVC|x264|x265|H\.264|H\.265|AAC|DTS|AC3|TrueHD|"
            r"CHS|CHT|ENG|SUB|SUBBED|)"
            r"|[-.\s]+$",
            "",
            stem,
            flags=re.IGNORECASE,
        ).strip().replace(".", " ").replace("_", " ").replace("-", " ")
        title = re.sub(r"\s+", " ", title).strip()
        # 去掉 S01E01 / EP01 / 第 N 集 等剧集编号使其归到同一组
        title = re.sub(
            r"\s*[SE]\d{2,}(?:E\d{2,})*\s*|\s*第\s*\d+\s*集\s*",
            " ",
            title,
            flags=re.IGNORECASE,
        ).strip()
        # 如果标题太短（可能是纯剧集编号），保留原始文件名
        if len(title) < 2:
            title = stem
        return title

    @staticmethod
    def _extract_season_episode(filename: str) -> tuple[int, int] | None:
        """从文件名提取 (季, 集)。匹配 S01E01 / S01E01-E09 / 第1季第1集 等格式。"""
        name = str(filename)
        m = re.search(r"[Ss](\d{1,2})\s*[Ee](\d{1,3})", name)
        if m:
            return int(m.group(1)), int(m.group(2))
        m = re.search(r"第\s*(\d+)\s*季.*?第\s*(\d+)\s*集", name)
        if m:
            return int(m.group(1)), int(m.group(2))
        return None

    @staticmethod
    def _format_season_episodes(files: list[dict]) -> str:
        """按季聚合同组文件的集数范围，如：第1季 第1-8集，第2季 第1-9集。

        跨季时按季分段显示；电影或无法识别的文件返回空串。
        """
        seasons: dict[int, set[int]] = {}
        for f in files:
            se = Api._extract_season_episode(f.get("name", ""))
            if se:
                seasons.setdefault(se[0], set()).add(se[1])
        if not seasons:
            return ""
        parts: list[str] = []
        for season in sorted(seasons):
            eps = sorted(seasons[season])
            # 合并连续集数：1,2,3,5 -> 1-3,5
            ranges: list[tuple[int, int]] = []
            start = prev = eps[0]
            for ep in eps[1:]:
                if ep == prev + 1:
                    prev = ep
                else:
                    ranges.append((start, prev))
                    start = prev = ep
            ranges.append((start, prev))
            ep_text = "、".join(
                f"{a}" if a == b else f"{a}-{b}" for a, b in ranges
            )
            parts.append(f"第{season}季 第{ep_text}集")
        return "，".join(parts)

    _TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/multi"
    _TMDB_MOVIE_SEARCH_URL = "https://api.themoviedb.org/3/search/movie"
    _TMDB_TV_SEARCH_URL = "https://api.themoviedb.org/3/search/tv"
    _TMDB_TV_DETAIL_URL = "https://api.themoviedb.org/3/tv/{tv_id}/season/{season}"
    _TMDB_BACKDROP_URL = "https://image.tmdb.org/t/p/w500"
    _TMDB_POSTER_URL = "https://image.tmdb.org/t/p/w342"

    def _tmdb_tv_id(self, title: str, year: str) -> int:
        """用标题+年份搜索 TMDB 获取 tv id；失败返回 0。"""
        api_key = self._tmdb_api_key()
        if not api_key or not title:
            return 0
        try:
            resp = requests.get(
                self._TMDB_TV_SEARCH_URL,
                params={"api_key": api_key, "query": title, "language": "zh-CN"},
                timeout=5,
            )
            resp.raise_for_status()
            results = (resp.json()).get("results") or []
            if not results:
                resp = requests.get(
                    self._TMDB_TV_SEARCH_URL,
                    params={"api_key": api_key, "query": title, "language": "en-US"},
                    timeout=5,
                )
                resp.raise_for_status()
                results = (resp.json()).get("results") or []
            if not results:
                return 0
            first = results[0]
            # 若传了年份，优先匹配同年条目
            if year:
                for item in results:
                    item_year = str(item.get("first_air_date") or "")[:4]
                    if item_year == str(year):
                        first = item
                        break
            return int(first.get("id") or 0)
        except Exception:
            return 0

    def _tmdb_season_episodes(self, tv_id: int, season: int) -> set[int]:
        """查 TMDB 某剧某季的集号集合；失败返回空集。"""
        api_key = self._tmdb_api_key()
        if not api_key or not tv_id:
            return set()
        try:
            resp = requests.get(
                self._TMDB_TV_DETAIL_URL.format(tv_id=tv_id, season=season),
                params={"api_key": api_key, "language": "zh-CN"},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                int(e.get("episode_number") or 0)
                for e in (data.get("episodes") or [])
                if e.get("episode_number")
            }
        except Exception:
            return set()

    def _complete_seasons(
        self,
        title: str,
        year: str,
        cloud_seasons: dict[int, set[int]],
    ) -> list[int]:
        """判断哪些季在网盘中已整季完整。

        网盘已有集数 == TMDB 该季总集数 → 该季完整。
        返回完整季号列表，如 [1, 2]。失败（无 TMDB 数据）返回空。
        """
        if not cloud_seasons:
            return []
        tv_id = self._tmdb_tv_id(title, year)
        if not tv_id:
            return []
        complete: list[int] = []
        for season, cloud_eps in cloud_seasons.items():
            total = self._tmdb_season_episodes(tv_id, season)
            if total and cloud_eps == total:
                complete.append(season)
        return complete

    def _tmdb_api_key(self) -> str:
        """优先使用 MoviePilot 内置的 TMDB API Key，插件配置作为可选回退。"""
        try:
            from app.core.config import settings
            key = str(getattr(settings, "TMDB_API_KEY", "") or "").strip()
            if key:
                return key
        except Exception:
            pass
        try:
            return str((self._store.get_config() or {}).get("tmdb_api_key") or "").strip()
        except Exception:
            return ""

    def _search_poster(self, filename: str, exact_title: str = "", exact_year: str = "") -> str:
        """从文件名中提取标题，搜索 TMDB 获取海报 URL。

        根据文件名是否包含季集信息，自动选择 TV 或 Movie 搜索，
        避免 `search/multi` 混合搜索返回同名但类型错误的结果（如"安娜"）。
        同时提取年份（`(2022)` / `.2022.`）作为搜索过滤参数，
        避免同名不同年份的作品互相误匹配（如"安娜"电影/剧/安娜的爱人）。

        可传 exact_title/exact_year（来自 MoviePilot 整理历史，100% 准确），
        优先使用；否则从文件名猜测。
        """
        api_key = self._tmdb_api_key()
        if not api_key:
            return ""
        if exact_title:
            title = exact_title
        else:
            title = self._extract_media_title(filename)
        if not title or len(title) < 2:
            return ""

        # 年份：优先精确年份，否则从文件名提取
        year = exact_year
        if not year:
            year_match = re.search(r"(?:\(|\[|\s|\.)(19\d{2}|20\d{2})(?:\)|\]|\s|\.)", str(filename))
            if year_match:
                year = year_match.group(1)

        # 判断媒体类型：有季集信息 → TV，否则 → Movie
        has_season = self._extract_season_episode(filename) is not None
        search_url = (
            self._TMDB_TV_SEARCH_URL
            if has_season
            else self._TMDB_MOVIE_SEARCH_URL
        )
        # 年份过滤参数：TV 用 first_air_date_year，Movie 用 year
        year_param = "first_air_date_year" if has_season else "year"

        def _try_search(url: str, lang: str, extra_year: str = "") -> list[dict]:
            try:
                params = {"api_key": api_key, "query": title, "language": lang}
                if extra_year:
                    params[year_param] = extra_year
                resp = requests.get(url, params=params, timeout=5)
                resp.raise_for_status()
                return (resp.json()).get("results") or []
            except Exception:
                return []

        results = _try_search(search_url, "zh-CN", year)
        if not results:
            results = _try_search(search_url, "en-US", year)
        # 回退：带年份无结果时去掉年份再试
        if not results:
            results = _try_search(search_url, "zh-CN")
            if not results:
                results = _try_search(search_url, "en-US")
        # 回退：search_type 未找到时试试另一种类型
        if not results:
            fallback_url = (
                self._TMDB_MOVIE_SEARCH_URL
                if has_season
                else self._TMDB_TV_SEARCH_URL
            )
            results = _try_search(fallback_url, "zh-CN")
            if not results:
                results = _try_search(fallback_url, "en-US")
        # 最后回退 search/multi
        if not results:
            results = _try_search(self._TMDB_SEARCH_URL, "zh-CN")
            if not results:
                results = _try_search(self._TMDB_SEARCH_URL, "en-US")

        for item in results:
            # 与 MoviePilot get_message_image 一致：优先横版背景图（16:9），
            # 飞书 fit_horizontal 模式下高度自然，不会撑得过高；无背景图再退回海报。
            backdrop = item.get("backdrop_path") or ""
            if backdrop:
                return f"{self._TMDB_BACKDROP_URL}{backdrop}"
            poster = item.get("poster_path") or ""
            if poster:
                return f"{self._TMDB_POSTER_URL}{poster}"
        return ""

    def _transfer_meta(self, local_path: str) -> dict:
        """按上传路径查询 MoviePilot 整理历史，返回已识别的媒体信息。

        100% 准确数据源：MoviePilot 整理时已完成媒体识别，transferhistory
        表存有 title/year/seasons/episodes/image。插件上传的文件路径正是
        transferhistory.dest，直接按路径查询即可，不依赖文件名猜测。

        返回 {title, year, seasons, episodes, image}，未命中返回空 dict。
        """
        try:
            from app.db.oper.transferhistory import TransferHistoryOper
            hit = TransferHistoryOper().get_by_dest(local_path)
            if hit:
                return self._transfer_meta_from_hit(hit)
        except Exception as err:  # noqa: BLE001
            logger.debug(f"【整理历史】TransferHistoryOper 不可用，改直连查询: {safe_error_text(err)}")
        # 回退：直连 PostgreSQL（独立脚本/Oper 未装配时可用）
        try:
            return self._transfer_meta_direct(local_path)
        except Exception as err:  # noqa: BLE001
            logger.debug(f"【整理历史】直连查询失败: {safe_error_text(err)}")
            return {}

    @staticmethod
    def _transfer_meta_from_hit(hit: Any) -> dict:
        """从 TransferHistory 模型对象提取字段。"""
        return {
            "title": str(hit.title or "").strip(),
            "year": str(hit.year or "").strip(),
            "seasons": str(hit.seasons or "").strip(),
            "episodes": str(hit.episodes or "").strip(),
            "image": str(hit.image or "").strip(),
        }

    def _transfer_meta_direct(self, local_path: str) -> dict:
        """直连 PostgreSQL 查询 transferhistory（不依赖应用组合根）。"""
        from sqlalchemy import create_engine, text
        db_user = str(settings.DB_POSTGRESQL_USERNAME or "moviepilot")
        db_pass = str(settings.DB_POSTGRESQL_PASSWORD or "")
        db_host = str(settings.DB_POSTGRESQL_HOST or "localhost")
        db_port = int(settings.DB_POSTGRESQL_PORT or 5433)
        db_name = str(settings.DB_POSTGRESQL_DATABASE or "moviepilot")
        url = f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
        engine = create_engine(url, pool_pre_ping=True, pool_size=1, max_overflow=1)
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text(
                        "SELECT title, year, seasons, episodes, image "
                        "FROM transferhistory WHERE dest = :dest LIMIT 1"
                    ),
                    {"dest": local_path},
                ).mappings().first()
            if not row:
                return {}
            return {
                "title": str(row.get("title") or "").strip(),
                "year": str(row.get("year") or "").strip(),
                "seasons": str(row.get("seasons") or "").strip(),
                "episodes": str(row.get("episodes") or "").strip(),
                "image": str(row.get("image") or "").strip(),
            }
        finally:
            engine.dispose()

    def _aggregate_seasons(
        self,
        details: list[dict],
        cloud_records: dict | None = None,
    ) -> str:
        """聚合季集范围：本次上传 + 115 网盘已存在的并集。

        输入为 transferhistory 查询结果（每条含 seasons/episodes），
        cloud_records 为 upload_records.to_dict()（键=本地路径，值含 target）。
        当本组文件同目录下网盘已有更多集（漏集补传场景）时，合并显示完整范围。

        输出格式：第1季 第1-6集，第2季 第1-8集（按季分组、集数去重合并）。
        """
        per_season: dict[int, set[int]] = {}
        for d in details:
            seasons = str(d.get("seasons") or "").strip()
            episodes = str(d.get("episodes") or "").strip()
            # seasons 如 "S01"，episodes 如 "E01-E06" 或 "E01"
            for s_part in re.findall(r"[Ss](\d{1,2})", seasons):
                s_num = int(s_part)
                eps = per_season.setdefault(s_num, set())
                for e_part in re.findall(r"[Ee](\d{1,3})", episodes):
                    eps.add(int(e_part))

        # 合并 115 网盘已有集数：按 target 目录前缀匹配同剧集
        if cloud_records:
            # 收集本组文件的 target 目录前缀（如 /媒体库/.../安娜 (2022)/Season 1/）
            dir_prefixes: set[str] = set()
            for d in details:
                local_path = str(d.get("local_path") or d.get("dest") or "")
                record = cloud_records.get(local_path)
                target = str((record or {}).get("target") or "")
                if not target:
                    continue
                # 取到 Season N/ 目录为止的前缀；无 Season 则取到文件名父目录
                season_m = re.search(r"^(.*?/Season \d+/)(?:[^/]+)$", target)
                if season_m:
                    dir_prefixes.add(season_m.group(1))
                else:
                    dir_prefixes.add(str(Path(target).parent.as_posix()) + "/")
            for _local, record in cloud_records.items():
                target = str((record or {}).get("target") or "")
                if not target:
                    continue
                for prefix in dir_prefixes:
                    if target.startswith(prefix) and re.search(r"[Ee]\d{1,3}", target):
                        m_season = re.search(r"/Season (\d+)/", target)
                        m_ep = re.search(r"[Ee](\d{1,3})", target)
                        if m_season and m_ep:
                            per_season.setdefault(int(m_season.group(1)), set()).add(
                                int(m_ep.group(1))
                            )

        if not per_season:
            return ""
        parts = []
        for season in sorted(per_season):
            ep_list = sorted(per_season[season])
            # 连续区间合并
            ranges: list[tuple[int, int]] = []
            for ep in ep_list:
                if ranges and ep == ranges[-1][1] + 1:
                    ranges[-1] = (ranges[-1][0], ep)
                else:
                    ranges.append((ep, ep))
            range_text = "、".join(
                f"{a}-{b}" if a != b else f"{a}" for a, b in ranges
            )
            parts.append(f"第{season}季 第{range_text}集")
        return "，".join(parts)

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
                poster_search=self._search_poster,
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
        self._notify_upload(entry, incremental)
        return entry

    def _notify_upload(self, entry: Dict[str, Any], incremental: bool) -> None:
        """上传通道执行完成后的通知，按媒体条目分组发送。

        优先使用 MoviePilot 整理历史（transferhistory）的识别结果：
        - 分组键：识别出的 title+year（100% 准确，含年份避免同名混淆）
        - 季集范围：transferhistory.seasons/episodes 聚合（100% 准确）
        - 海报：transferhistory.image（MoviePilot 识别时存的准确海报）
        未命中整理历史时回退文件名猜测逻辑。
        """
        if not self._notifier.is_enabled("upload"):
            return
        errors = int(entry.get("errors") or 0)
        per_file = entry.get("per_file_details") or []
        per_file = [d for d in per_file if d.get("method") in ("upload", "instant")]
        if not per_file and not errors:
            return

        # 逐文件查询整理历史，附带识别结果
        transfer_meta_by_path: dict[str, dict] = {}
        for d in per_file:
            local_path = str(d.get("local_path") or "")
            if local_path and local_path not in transfer_meta_by_path:
                meta = self._transfer_meta(local_path)
                if meta:
                    transfer_meta_by_path[local_path] = meta

        # 分组键：优先识别标题（含年份），回退文件名提取
        groups: dict[str, list[dict]] = {}
        for d in per_file:
            meta = transfer_meta_by_path.get(str(d.get("local_path") or ""), {})
            if meta.get("title"):
                title_key = f"{meta['title']} ({meta['year']})" if meta.get("year") else meta["title"]
            else:
                title_key = self._extract_media_title(d.get("name", ""))
            groups.setdefault(title_key, []).append(d)

        # 每组发一条通知
        for title_key, files in sorted(groups.items()):
            _count = len(files)
            _size = self._format_size(sum(int(f.get("size", 0)) for f in files))
            _methods: dict[str, int] = {}
            for f in files:
                m = f.get("method", "upload")
                _methods[m] = _methods.get(m, 0) + 1
            _method_parts = []
            if _methods.get("upload"):
                _method_parts.append(f"上传 {_methods['upload']}")
            if _methods.get("instant"):
                _method_parts.append(f"秒传 {_methods['instant']}")
            _method_str = "，".join(_method_parts) if _method_parts else "上传"
            _strm = sum(1 for f in files if f.get("strm_generated"))
            _sidecars = sum(len(f.get("sidecars") or []) for f in files)
            _labels = sorted(set(f.get("mapping_label", "") for f in files if f.get("mapping_label")))
            _label_str = "、".join(_labels) if _labels else "媒体库"

            # 季集范围：优先整理历史聚合（含网盘已有集数），回退文件名提取
            meta_list = [
                transfer_meta_by_path.get(str(f.get("local_path") or ""), {})
                for f in files
            ]
            has_meta = any(m.get("title") for m in meta_list)
            if has_meta:
                try:
                    cloud_records = self._store.get_upload_records().to_dict()
                except Exception:  # noqa: BLE001
                    cloud_records = None
                _se_text = self._aggregate_seasons(meta_list, cloud_records)
            else:
                _se_text = self._format_season_episodes(files)

            # 整季完整提示：网盘已有集数 == TMDB 该季总集数
            complete_hint = ""
            if has_meta and _se_text:
                first_meta = next((m for m in meta_list if m.get("title")), {})
                title_meta = first_meta.get("title", "")
                year_meta = first_meta.get("year", "")
                try:
                    cloud_records = self._store.get_upload_records().to_dict()
                except Exception:  # noqa: BLE001
                    cloud_records = None
                if title_meta:
                    cloud_seasons: dict[int, set[int]] = {}
                    meta_for_cloud = [m for m in meta_list if m.get("title")]
                    se_text_with_cloud = self._aggregate_seasons(meta_for_cloud, cloud_records)
                    # 从聚合文本解析出网盘集数分布（含 cloud 合并后）
                    for part in [p.strip() for p in se_text_with_cloud.split("，")]:
                        m = re.match(r"第(\d+)季 第([\d、\-]+)集", part)
                        if m:
                            s = int(m.group(1))
                            eps: set[int] = set()
                            for seg in re.findall(r"\d+(?:-\d+)?", m.group(2)):
                                if "-" in seg:
                                    a, b = seg.split("-")
                                    eps.update(range(int(a), int(b) + 1))
                                else:
                                    eps.add(int(seg))
                            cloud_seasons[s] = eps
                    complete = self._complete_seasons(title_meta, year_meta, cloud_seasons)
                    if complete:
                        complete_hint = "✅ " + "、".join(
                            f"第{s}季已整季完整" for s in complete
                        )
            _complete_hint = complete_hint

            # 海报：优先用识别出的 title+year 精确搜 TMDB backdrop（横版），
            # 其次 transferhistory.image（豆瓣，可能竖版），最后回退文件名搜索
            poster = ""
            if has_meta:
                # 取第一个有 title 的 meta 作为搜索依据
                first_meta = next((m for m in meta_list if m.get("title")), {})
                if first_meta.get("title"):
                    # ⚠️ 必须传真实文件名（含 S01E01/第N集），否则 _search_poster 里
                    # has_season 恒为 False → 剧集被当成电影搜 → 海报识别错误。
                    # 取本组第一个带 meta 的文件名（local_path 含目录，name 是文件名）。
                    _poster_src = next(
                        (f.get("name", "") for f in files
                         if transfer_meta_by_path.get(str(f.get("local_path") or ""), {}).get("title")),
                        "",
                    )
                    poster = self._search_poster(
                        _poster_src,
                        exact_title=first_meta.get("title", ""),
                        exact_year=first_meta.get("year", ""),
                    )
                if not poster:
                    poster = next(
                        (m.get("image", "") for m in meta_list if m.get("image")),
                        "",
                    )
            if not poster:
                poster = next(
                    (f.get("poster_url", "") for f in files if f.get("poster_url")),
                    "",
                )

            # 构造 column_set 卡片（季集在上，统计在下）
            elements: list[dict] = []
            if _se_text:
                elements.append(
                    {"tag": "markdown", "content": "**季集**", "text_size": "normal", "margin": "0px 16px 0px 16px"}
                )
                entries: list[tuple[str, str]] = []
                for season_part in [s.strip() for s in _se_text.split("，")]:
                    m = re.match(r"第(\d+)季 第([\d、\-]+)集", season_part)
                    if m:
                        entries.append((f"第{m.group(1)}季", f"第{m.group(2)}集"))
                for i in range(0, len(entries), 3):
                    cols = []
                    for season, eps in entries[i:i+3]:
                        cols.append({
                            "tag": "column", "width": "weighted", "weight": 1,
                            "elements": [{"tag": "markdown", "content": f"**{season}**\n{eps}", "margin": "0px", "text_align": "center"}],
                        })
                    while len(cols) < 3:
                        cols.append({
                            "tag": "column", "width": "weighted", "weight": 1,
                            "elements": [{"tag": "markdown", "content": " ", "margin": "0px"}],
                        })
                    elements.append({
                        "tag": "column_set", "flex_mode": "none",
                        "columns": cols, "margin": "2px 16px 0px 16px",
                    })
            # 整季完整提示（季集区下方）
            if _complete_hint:
                elements.append({
                    "tag": "markdown",
                    "content": f"<font color='green'>{_complete_hint}</font>",
                    "margin": "4px 16px 0px 16px",
                })
            # 统计区
            elements.append({"tag": "hr", "margin": "8px 16px 4px 16px"})
            elements.append({
                "tag": "column_set", "flex_mode": "none",
                "columns": [
                    {"tag": "column", "width": "weighted", "weight": 1,
                     "elements": [{"tag": "markdown", "content": f"**{_count}**\n文件", "margin": "0px", "text_align": "center"}]},
                    {"tag": "column", "width": "weighted", "weight": 1,
                     "elements": [{"tag": "markdown", "content": f"**{_size}**\n大小", "margin": "0px", "text_align": "center"}]},
                    {"tag": "column", "width": "weighted", "weight": 1,
                     "elements": [{"tag": "markdown", "content": f"**{_method_str}**\n方式", "margin": "0px", "text_align": "center"}]},
                ],
                "margin": "4px 16px 0px 16px",
            })
            elements.append({
                "tag": "column_set", "flex_mode": "none",
                "columns": [
                    {"tag": "column", "width": "weighted", "weight": 1,
                     "elements": [{"tag": "markdown", "content": _label_str, "margin": "0px", "text_align": "center"}]},
                    {"tag": "column", "width": "weighted", "weight": 1,
                     "elements": [{"tag": "markdown", "content": f"STRM {_strm}", "margin": "0px", "text_align": "center"}]},
                    {"tag": "column", "width": "weighted", "weight": 1,
                     "elements": [{"tag": "markdown", "content": f"附属 {_sidecars}", "margin": "0px", "text_align": "center"}]},
                ],
                "margin": "0px 16px 12px 16px",
            })
            # 优先飞书美化卡片，失败回退文本（mtype 用配置的消息类型分流渠道）
            card_title = f"115 网盘・{title_key} 已入库"
            upload_mtype = normalize_notify_type(
                self._store.get_config().get("upload_notify_type")
            )
            if not self._notifier.send_upload_feishu_card(card_title, elements, poster, upload_mtype):
                lines = [
                    f"类型：媒体，映射：{_label_str}，共 {_count} 个文件，大小：{_size}"
                    f"，方式：{_method_str}，STRM {_strm} 个，附属 {_sidecars} 个",
                ]
                if _se_text:
                    lines.append(_se_text)
                self._notifier.notify(
                    "upload", f"{title_key} 已入库", lines, image=poster,
                )
        # 汇总通知（有错误时补充）
        if errors:
            self._notifier.notify(
                "upload",
                "❌ 有失败",
                [f"本次上传共 {len(per_file)} 个文件，以下文件处理失败：{errors} 个"],
            )

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
            self._notify_checkin(entry, True)
            return _ok(entry, result.get("message") or "签到完成")
        except Exception as err:  # noqa: BLE001
            entry = {"kind": "checkin", "time": datetime.now().isoformat(timespec="seconds"), "message": str(err)}
            self._store.append_history(entry)
            logger.error(f"【115签到】执行失败：{safe_error_text(err)}")
            self._notify_checkin(entry, False)
            return _error(str(err))
        finally:
            self._cloud_task_lock.release()
            self._checkin_lock.release()

    def _notify_checkin(self, entry: Dict[str, Any], success: bool) -> None:
        """每日签到通知，成功和失败都发，失败时带上原因。"""
        if not self._notifier.is_enabled("checkin"):
            return
        message = str(entry.get("message") or "").strip()
        if not success:
            self._notifier.notify(
                "checkin",
                "❌ 失败",
                [
                    "━━ 115 轻量助手 · 每日签到 ━━",
                    "",
                    "  ❌ 签到失败",
                    "────────────────────────────",
                    f"  时间：{entry.get('time') or '-'}",
                    f"  原因：{message or '未知错误'}",
                ],
            )
            return
        headline = "✅ 今日已签到" if entry.get("already") else "✅ 签到成功"
        lines = [
            "━━ 115 轻量助手 · 每日签到 ━━",
            "",
            f"  {headline}",
            "────────────────────────────",
            f"  时间：{entry.get('time') or '-'}",
        ]
        if continuous := int(entry.get("continuous_day") or 0):
            lines.append(f"  连续签到：{continuous} 天")
        if points := int(entry.get("points_num") or 0):
            lines.append(f"  本次积分：+{points}")
        if message:
            lines.append("")
            lines.append(f"  📝 回执：{message}")
        self._notifier.notify("checkin", headline, lines)

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
        return {"items": self._store.get_history()}

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

    @staticmethod
    def _client_ip(request: Request) -> str:
        """取限流用的来源标识。

        反代后面 request.client 是反代自己的地址，优先看 X-Forwarded-For 的第一跳。
        取不到就退回固定串，让所有匿名请求共用一个桶——宁可粗糙也不要漏掉限流。
        """
        forwarded = str(request.headers.get("x-forwarded-for") or "")
        if forwarded:
            first = forwarded.split(",")[0].strip()
            if first:
                return first
        real_ip = str(request.headers.get("x-real-ip") or "").strip()
        if real_ip:
            return real_ip
        client = getattr(request, "client", None)
        host = getattr(client, "host", "") if client else ""
        return str(host or "unknown")

    def redirect(
        self,
        request: Request,
        pickcode: str = "",
        file_name: str = "",
        sign: str = "",
    ):
        source = self._client_ip(request)
        if not self._redirect_rate_limiter.check(source):
            retry_after = self._redirect_rate_limiter.retry_after(source) or 1
            logger.warning(f"【302跳转服务】{source} 请求过于频繁，已限流 {retry_after}s")
            return JSONResponse(
                {"success": False, "message": "请求过于频繁，请稍后再试"},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
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
                # 锁已释放，这时候才轮得到排队中的反向删除。放在 finally 里是因为
                # 任务异常终止同样要让排队的删除跑起来，不然事件就永远压在队列里。
                try:
                    self._drain_pending_sweep()
                except Exception as err:  # noqa: BLE001
                    logger.error(f"【STRM反向删除】补跑排队任务失败：{safe_error_text(err)}")

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
