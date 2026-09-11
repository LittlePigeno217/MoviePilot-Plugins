from __future__ import annotations

import re
import threading
import uuid
from base64 import b64encode
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta
from io import BytesIO
from math import isfinite
from pathlib import Path
from time import monotonic, time
from typing import Any, Callable, Dict, Iterator, Optional
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
from .library_audit import find_untracked, media_records
from .cloud_check import CHECK_BUDGET, check_rows, cooldown_left, merge as merge_cloud_check, pick_rows
from .media_ledger import build_ledger
from .seeding import collect_seeding_paths, seeding_identities
from .log_utils import safe_error_text
from .notify import (
    CHANNELS as NOTIFY_CHANNELS,
    NOTIFY_TYPE_NAMES,
    NOTIFY_TYPE_SWITCHS_NAMES,
    Notifier,
    normalize_notify_type,
)
from .rate_limiter import RateLimiter
from .reverse_delete import RECENT_DELETE_TTL, ReverseDeleter, pending_batch_items
from .resilience import TtlCache, retry_call
from .store import DEFAULT_CONFIG, Store
from .strm import (
    CommitJournal,
    OwnedRemovalRequest,
    RecordClaims,
    StrmGenerator,
    StrmMaterializer,
    StrmRecoveryBlockedError,
    normalize_moviepilot_url,
    normalize_pickcode,
    verify_redirect_signature,
)
from .upload_watch import (
    UPLOAD_BATCH_SIZE,
    UPLOAD_BATCH_TIME_BUDGET,
    PendingUploadQueue,
    UploadCandidate,
    file_signature,
    mapping_revision,
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
    # uploader 自己已做请求级有限重试；这里仅负责失败批次释放 cloud lock 后的
    # 跨批次退避，不能在 worker 内 while/sleep 持锁重试。
    _UPLOAD_RETRY_DELAYS = (5.0, 30.0, 60.0)
    _PENDING_SWEEP_MAX = 4096

    def __init__(
        self,
        client_provider: Callable[[], U115Client],
        store: Store,
        on_config_saved: Callable[[], None] | None = None,
        life_monitor_status: Callable[[], bool] | None = None,
        notifier: Notifier | None = None,
        strm_watch_status: Callable[[], bool] | None = None,
        recover_strm_commits: Callable[[str], list[str]] | None = None,
        journal: CommitJournal | None = None,
        upload_queue: PendingUploadQueue | None = None,
    ):
        self._client_provider = client_provider
        self._store = store
        self._on_config_saved = on_config_saved
        self._life_monitor_status = life_monitor_status
        self._strm_watch_status = strm_watch_status
        self._notifier = notifier or Notifier(store.get_config)
        self._recover_strm_commits = recover_strm_commits or (lambda _stage: [])
        if journal is None:
            raise ValueError("Api 必须注入插件唯一 CommitJournal")
        self._strm_journal = journal
        self._running: set[str] = set()
        self._task_threads: set[threading.Thread] = set()
        #: 每个在跑的任务是什么时候起的（epoch 秒）。任务台要显示「已跑多久」，
        #: 而 _running 只是个集合，答不了这个问题。
        self._running_since: Dict[str, float] = {}
        self._task_leases: Dict[str, Dict[str, Any]] = {}
        self._task_context = threading.local()
        # 反向删除的待处理范围记在编排层：抢不到 115 数据任务锁的删除事件不会丢，
        # 锁释放时由 _drain_pending_sweep 接着跑完。None 语义的「全量」单独用布尔表示，
        # 因为空列表表示「没有待处理路径」，绝不能被当成「清理所有记录」。
        self._pending_sweep_paths: set[str] = set()
        self._pending_sweep_all = False
        # 反向删除刚清掉的 pickcode，正向同步据此跳过重建（115 列表接口有延迟）
        self._recent_deletes: TtlCache[str, bool] = TtlCache(RECENT_DELETE_TTL, maxsize=4096)
        # 自动上传只保存不同文件候选；手动上传不进入、也不消费这条队列。
        self._upload_queue = upload_queue if upload_queue is not None else PendingUploadQueue()
        # 旧 public queue_upload/trigger_upload(auto) 的整映射合并队列，与文件候选队列并存。
        self._pending_auto_upload = False
        self._pending_auto_upload_source = ""
        self._pending_auto_upload_queued_at = 0.0
        self._pending_auto_upload_count = 0
        self._upload_restabilize: Callable[[str, str], bool] | None = None
        self._upload_retry_timer: threading.Timer | None = None
        self._upload_retry_attempt = 0
        self._upload_retry_token = 0
        self._upload_retry_exhausted = False
        self._upload_scheduler_stopping = False
        # 通知去重：上传（开着“生成 STRM”）发出的入库卡片已经覆盖了同一批媒体的
        # STRM 变化，随后的 STRM 同步不该再发一张。这里记抑制窗的截止时刻（monotonic）。
        self._strm_notify_quiet_until = 0.0
        self._lock = threading.Lock()
        self._config_write_lock = threading.RLock()
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
        with self._config_write_lock:
            return self._save_config(payload)

    def _save_config(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
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
        if "local_path_allowlist" in updates:
            allowlist = updates.get("local_path_allowlist")
            if isinstance(allowlist, str):
                allowlist = [line.strip() for line in allowlist.splitlines() if line.strip()]
            if not isinstance(allowlist, list):
                return _error("本地目录 allowlist 格式无效")
            normalized_allowlist = self._allowlist_values({"local_path_allowlist": allowlist})
            if len(normalized_allowlist) != len(allowlist):
                return _error("本地目录 allowlist 格式无效")
            resolved_allowlist: list[str] = []
            for value in normalized_allowlist:
                root = self._resolved_local_root(value)
                if root is None:
                    return _error(f"本地目录 allowlist 路径无效或不可用：{value}")
                text = str(root)
                if text not in resolved_allowlist:
                    resolved_allowlist.append(text)
            updates["local_path_allowlist"] = resolved_allowlist
        allowed = set(DEFAULT_CONFIG) - {"tokens"}
        current = self._store.get_config()
        saved_updates = {key: updates[key] for key in allowed if key in updates}
        allowlist_in_payload = "local_path_allowlist" in saved_updates
        submitted_allowlist = self._allowlist_values(saved_updates)
        full_config_payload = all(
            key in payload
            for key in (
                "enabled",
                "strm_mappings",
                "upload_mappings",
                "local_path_allowlist",
            )
        )
        should_migrate = (
            not allowlist_in_payload
            or (not submitted_allowlist and full_config_payload)
        )
        if should_migrate:
            # MoviePilot 自身配置的下载/媒体库目录本来就是授权根。若本次候选
            # 映射已完全落在这些根内，就不应再因旧映射目录尚未创建而触发
            # legacy allowlist 迁移；否则仍按原规则把旧映射精确迁移进 allowlist。
            candidate_without_allowlist = {
                **current,
                **saved_updates,
                "local_path_allowlist": [],
            }
            host_roots = self._local_roots(candidate_without_allowlist)
            host_authorized = bool(host_roots) and not self._local_mapping_error(
                candidate_without_allowlist
            )
            if not host_authorized:
                migrated_allowlist, error = self._legacy_allowlist_migration(current)
                if error:
                    return _error(error)
                if migrated_allowlist is not None:
                    saved_updates["local_path_allowlist"] = migrated_allowlist
        if any(
            key in saved_updates
            for key in ("local_path_allowlist", "strm_mappings", "upload_mappings")
        ):
            candidate = {**current, **saved_updates}
            if error := self._local_mapping_error(candidate):
                return _error(error)
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
        headline = str(payload.get("title") or "通道自检")
        # 这条是排版的样板间：`**加粗**`、`•` 在微信 / Bark 这类渠道不会渲染，长横线在窄屏
        # 会折行，所以自检消息也照正式通知的规矩来写。
        lines = [
            "看到这条说明这条通道能正常送到你手上。",
            "",
            f"消息类型 {self._store.get_config().get(meta['type_key'])}",
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
                # 扫码授权恢复后无需等待原退避到期，也不依赖新文件事件。
                self.wake_pending_upload()
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
    def _allowlist_values(config: Dict[str, Any]) -> list[str]:
        values = config.get("local_path_allowlist") or []
        if isinstance(values, str):
            values = values.splitlines()
        if not isinstance(values, list):
            return []
        result: list[str] = []
        for value in values:
            if not isinstance(value, (str, Path)):
                continue
            text = str(value).strip()
            if text:
                result.append(text)
        return result

    @staticmethod
    def _mapping_local_values(
        config: Dict[str, Any],
        *,
        enabled_only: bool = False,
    ) -> list[str]:
        fields = (
            ("strm_mappings", "target_dir"),
            ("upload_mappings", "source"),
            ("upload_mappings", "strm_target"),
        )
        values: list[str] = []
        for collection, key in fields:
            for mapping in config.get(collection) or []:
                if not isinstance(mapping, dict):
                    continue
                if enabled_only and not mapping.get("enabled", True):
                    continue
                value = str(mapping.get(key) or "").strip()
                if value and value not in values:
                    values.append(value)
        return values

    def _legacy_mapping_allowlist(self, config: Dict[str, Any]) -> tuple[list[str], str]:
        migrated: list[str] = []
        for value in self._mapping_local_values(config, enabled_only=True):
            root = self._resolved_local_root(value)
            if root is None:
                return [], f"旧映射本地目录无效或不可用，无法迁移 allowlist：{value}"
            text = str(root)
            if text not in migrated:
                migrated.append(text)
        return migrated, ""

    def _legacy_allowlist_migration(
        self,
        config: Dict[str, Any],
    ) -> tuple[list[str] | None, str]:
        """统一生成旧映射迁移候选；无迁移需求时返回 ``(None, "")``。"""
        if self._allowlist_values(config):
            return None, ""
        if not self._mapping_local_values(config, enabled_only=True):
            return None, ""
        migrated, error = self._legacy_mapping_allowlist(config)
        if error:
            return None, error
        candidate = {**config, "local_path_allowlist": migrated}
        if error := self._local_mapping_error(candidate):
            return None, error
        return migrated, ""

    def migrate_legacy_allowlist(self) -> tuple[bool, str]:
        """启动时迁移旧映射授权，返回（是否写入，错误文本）。"""
        with self._config_write_lock:
            current = self._store.get_config()
            migrated, error = self._legacy_allowlist_migration(current)
            if error or migrated is None:
                return False, error
            self._store.update_config({"local_path_allowlist": migrated})
            persisted = self._allowlist_values(self._store.get_config())
            if persisted != migrated:
                return False, "allowlist 迁移结果未能持久化"
            return True, ""

    @staticmethod
    def _resolved_local_path(value: Any) -> Path | None:
        text = str(value or "").strip()
        if not text:
            return None
        candidate = Path(text).expanduser()
        if not candidate.is_absolute():
            return None
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError, ValueError):
            return None
        if resolved == Path("/"):
            return None
        return resolved

    @classmethod
    def _resolved_local_root(cls, value: Any) -> Path | None:
        resolved = cls._resolved_local_path(value)
        return resolved if resolved is not None and resolved.is_dir() else None

    @classmethod
    def _host_local_root(cls, value: Any) -> Path | None:
        """读取宿主目录根，但不允许根本身通过符号链接动态换靶。"""
        text = str(value or "").strip()
        if not text:
            return None
        try:
            candidate = Path(text).expanduser()
            if not candidate.is_absolute() or candidate == Path("/"):
                return None
            before = candidate.lstat()
            if candidate.is_symlink() or not candidate.is_dir():
                return None
            resolved = cls._resolved_local_path(candidate)
            after = candidate.lstat()
        except (OSError, RuntimeError, ValueError):
            return None
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            return None
        return resolved

    @staticmethod
    def _saved_local_root(value: Any) -> Path | None:
        """读取保存时已经固化的 allowlist 路径，不查询文件系统或重新 resolve。"""
        text = str(value or "").strip()
        if not text:
            return None
        try:
            root = Path(text)
            if not root.is_absolute() or root == Path("/") or ".." in root.parts:
                return None
        except (OSError, RuntimeError, ValueError):
            return None
        return root

    def _local_roots(self, config: Dict[str, Any] | None = None) -> list[Path]:
        """返回插件获准访问的本地根目录，绝不把整个容器根目录暴露出去。"""
        host_values: list[Any] = []
        try:
            try:
                # MoviePilot V2 兼容入口。
                from app.helper.directory import DirectoryHelper
            except ImportError:
                # MoviePilot V3 的目录应用服务入口。
                from app.application.directory import DirectoryHelper

            for directory in DirectoryHelper().get_dirs():
                if getattr(directory, "storage", None) in (None, "", "local"):
                    host_values.append(getattr(directory, "download_path", None))
                if getattr(directory, "library_storage", None) in (None, "", "local"):
                    host_values.append(getattr(directory, "library_path", None))
        except Exception as err:  # noqa: BLE001
            logger.warning(f"【本地目录】读取 MoviePilot 下载/媒体库目录失败：{safe_error_text(err)}")

        effective_config = config if config is not None else self._store.get_config()
        roots: list[Path] = []
        for value in host_values:
            root = self._host_local_root(value)
            if root is not None and root not in roots:
                roots.append(root)
        for value in self._allowlist_values(effective_config):
            root = self._saved_local_root(value)
            if root is not None and root not in roots:
                roots.append(root)
        return roots

    def _authorized_local_path(
        self,
        value: Any,
        config: Dict[str, Any] | None = None,
        roots: list[Path] | None = None,
    ) -> Path | None:
        """规范化本地路径，并确认它仍位于当前授权根内。"""
        target = self._resolved_local_path(value)
        if target is None:
            return None
        allowed_roots = roots if roots is not None else self._local_roots(config)
        if not allowed_roots:
            return None
        return target if any(self._path_within(target, root) for root in allowed_roots) else None

    def _local_mapping_error(self, config: Dict[str, Any]) -> str:
        """校验显式 allowlist 及配置中的所有本地映射路径。"""
        for value in self._allowlist_values(config):
            if self._saved_local_root(value) is None:
                return f"本地目录 allowlist 路径无效或不可用：{value}"

        roots = self._local_roots(config)
        fields = (
            ("strm_mappings", "target_dir", "STRM 输出目录"),
            ("upload_mappings", "source", "上传源目录"),
            ("upload_mappings", "strm_target", "上传 STRM 输出目录"),
        )
        for collection, key, label in fields:
            for index, mapping in enumerate(config.get(collection) or [], start=1):
                if not isinstance(mapping, dict):
                    continue
                if not mapping.get("enabled", True):
                    continue
                value = str(mapping.get(key) or "").strip()
                if not value:
                    continue
                target = self._resolved_local_path(value)
                if target is None:
                    return f"第 {index} 条{label}无效：{value}"
                if self._authorized_local_path(value, config=config, roots=roots) is None:
                    return f"第 {index} 条{label}不在本地目录 allowlist 内：{value}"
        return ""

    def browse_local(self, path: str = "", root: str = "") -> Dict[str, Any]:
        try:
            roots = self._local_roots()
            if not roots:
                return {"error": "没有可用的 MoviePilot 本地媒体或下载目录"}
            requested_root = self._authorized_local_path(root, roots=roots) if root else None
            base = next((item for item in roots if item == requested_root), roots[0])
            if root and base != requested_root:
                return {"error": "本地目录根路径无效"}
            target = self._authorized_local_path(
                base / path if path else base,
                roots=[base],
            )
            if target is None:
                return {"error": "目录超出 MoviePilot 根目录"}
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
            now = time()
            with self._lock:
                running = sorted(self._running)
                tasks = []
                for kind, lease in sorted(self._task_leases.items()):
                    started_at = float(lease.get("started_at") or now)
                    last_progress_at = float(lease.get("last_progress_at") or started_at)
                    tasks.append({
                        "kind": kind,
                        "label": self._TASK_LABELS.get(kind, kind),
                        "holder": str(lease.get("holder") or ""),
                        "started_at": started_at,
                        "age": max(0.0, now - started_at),
                        "elapsed_ms": max(0, int((now - started_at) * 1000)),
                        "heartbeat": last_progress_at,
                        "last_progress": max(0.0, now - last_progress_at),
                        "progress": lease.get("progress"),
                        "phase": str(lease.get("phase") or "starting"),
                        "current_item": str(lease.get("current_item") or ""),
                        "cancel_requested": bool(lease["cancel_event"].is_set()),
                        "holds_cloud_lock": kind in self._CLOUD_TASK_KINDS,
                    })
            upload_pending = self._upload_queue.snapshot()
            with self._lock:
                if self._pending_auto_upload:
                    upload_pending = dict(upload_pending)
                    upload_pending["pending"] = True
                    upload_pending["count"] = int(upload_pending.get("count") or 0) + self._pending_auto_upload_count
                    sources = set(filter(None, str(upload_pending.get("source") or "").split(",")))
                    sources.update(filter(None, self._pending_auto_upload_source.split(",")))
                    upload_pending["source"] = ",".join(sorted(sources))
                    stamps = [value for value in (float(upload_pending.get("queued_at") or 0),
                                                   self._pending_auto_upload_queued_at) if value]
                    upload_pending["queued_at"] = min(stamps) if stamps else 0.0
            try:
                pending_conflicts = sorted(
                    (
                        {
                            "path": str(item.get("path") or ""),
                            "target": str(item.get("target") or ""),
                            "reason": str(item.get("reason") or ""),
                            "first_seen": str(item.get("first_seen") or ""),
                        }
                        for item in self._store.get_upload_conflicts().values()
                        if isinstance(item, dict)
                    ),
                    key=lambda item: item["first_seen"],
                )
            except AttributeError:
                pending_conflicts = []
            try:
                pending_deletes = [
                    {
                        "id": str(batch.get("id") or ""),
                        "mapping": str(batch.get("mapping") or "-"),
                        "count": int(batch.get("count") or 0),
                        "total_size": int(batch.get("total_size") or 0),
                        "created_at": str(batch.get("created_at") or ""),
                        "updated_at": str(batch.get("updated_at") or ""),
                        "items_truncated": bool(batch.get("items_truncated")),
                    }
                    for batch in self._store.get_strm_delete_pending().values()
                    if isinstance(batch, dict)
                ]
            except AttributeError:
                pending_deletes = []
            try:
                recent_uploads = self._store.get_recent_uploaded_media(
                    parse_extensions(
                        config.get("upload_media_extensions", ""),
                        DEFAULT_MEDIA_EXTENSIONS,
                    )
                )
            except AttributeError:
                recent_uploads = []
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
                "pending_upload": upload_pending["pending"],
                "pending_upload_source": upload_pending["source"],
                "pending_upload_queued_at": upload_pending["queued_at"] or None,
                "pending_upload_count": upload_pending["count"],
                "pending_conflicts": pending_conflicts,
                "pending_deletes": pending_deletes,
                "running": running,
                # 任务台要的是「跑了多久」，running 只答得了「在不在跑」
                "tasks": tasks,
                "history": self._store.get_history(),
                "recent_uploads": recent_uploads,
            }
        except Exception as err:  # noqa: BLE001
            logger.error(f"【状态】获取运行状态失败：{safe_error_text(err)}")
            return {"error": safe_error_text(err)}

    def _strm_moviepilot_url(self) -> str:
        return str(self._store.get_config().get("moviepilot_address") or "").strip().rstrip("/")

    def _plugin_console_link(self) -> str:
        try:
            return settings.MP_DOMAIN("#/plugins?tab=installed&id=P115LiteAssistant")
        except Exception:  # noqa: BLE001
            return ""

    def _organize_history_link(self) -> str:
        try:
            return settings.MP_DOMAIN("#/history")
        except Exception:  # noqa: BLE001
            return self._plugin_console_link()

    def _strm_start_error(
        self,
        mappings: Optional[list[Dict[str, Any]]] = None,
    ) -> str:
        config = self._store.get_config()
        try:
            normalize_moviepilot_url(str(config.get("moviepilot_address") or ""))
        except ValueError as err:
            return str(err)
        if mappings is None:
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

    def trigger_strm(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """不带 ``mapping_id`` 跑全部通道；带了就只跑那一条**整条**。

        故意不支持「只跑这条通道里的某个子目录」：``run_mapping`` 会把本轮没见到的记录
        当成过期记录清掉（``strm.py`` 里 ``mapping_record_keys - seen_record_keys`` 那段），
        只喂一个子目录进去，这条通道里其它媒体的记录和 STRM 会被一起删掉。
        """
        if error := self._strm_start_error():
            return _error(error)
        mapping_id = str((payload or {}).get("mapping_id") or "").strip()
        mappings = None
        if mapping_id:
            mappings = [
                mapping
                for mapping in self._store.get_config().get("strm_mappings") or []
                if isinstance(mapping, dict)
                and mapping.get("enabled", True)
                and str(mapping.get("id") or mapping.get("source_cid") or "default") == mapping_id
            ]
            if not mappings:
                return _error("这条通道不存在或已停用")
        moviepilot_url = self._strm_moviepilot_url()
        return self._start(
            "strm",
            lambda: self.run_strm(moviepilot_url, mappings, manual=True),
            "已开始同步这条通道" if mapping_id else "STRM 同步已开始",
        )

    def task_gap_fill(
        self,
        payload: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """按最新清单定位缺集媒体，并整条重跑其当前启用的 STRM 映射。

        清单通过 ``channel_ids`` 保留同一媒体的全部映射归属；这里会跨行、同行去重，
        但必须跑完整映射，不能缩到媒体子目录，否则同步清理会误判其它记录已过期。
        """
        data = payload if isinstance(payload, dict) else {}
        raw_row_ids = data.get("row_ids")
        if isinstance(raw_row_ids, str):
            raw_row_ids = [raw_row_ids]
        if (
            not isinstance(raw_row_ids, list)
            or not raw_row_ids
            or any(not isinstance(row_id, str) for row_id in raw_row_ids)
        ):
            return _error("请选择要补缺集的媒体")

        row_ids: list[str] = []
        seen_row_ids: set[str] = set()
        for raw_row_id in raw_row_ids:
            row_id = raw_row_id.strip()
            if row_id and row_id not in seen_row_ids:
                seen_row_ids.add(row_id)
                row_ids.append(row_id)
        if not row_ids:
            return _error("请选择要补缺集的媒体")
        if len(row_ids) > 200:
            return _error("参数错误：一次最多选择 200 部媒体")

        rows, _meta = self._ledger_rows(with_seeding=False)
        rows_by_id = {
            str(row.get("id")): row
            for row in rows
            if isinstance(row, dict) and row.get("id")
        }
        config = self._store.get_config()
        configured_strm: Dict[str, Dict[str, Any]] = {}
        enabled_strm: Dict[str, Dict[str, Any]] = {}
        for mapping in config.get("strm_mappings") or []:
            if not isinstance(mapping, dict):
                continue
            mapping_id = str(
                mapping.get("id") or mapping.get("source_cid") or "default"
            )
            configured_strm[mapping_id] = mapping
            if mapping.get("enabled", True):
                enabled_strm[mapping_id] = mapping
        upload_mapping_ids = {
            str(mapping.get("id") or mapping.get("source") or "")
            for mapping in config.get("upload_mappings") or []
            if isinstance(mapping, dict)
            and str(mapping.get("id") or mapping.get("source") or "")
        }

        reasons: Dict[str, int] = {}

        def skip(reason: str) -> None:
            reasons[reason] = reasons.get(reason, 0) + 1

        selected_mapping_ids: set[str] = set()
        deduplicated = 0
        for row_id in row_ids:
            row = rows_by_id.get(row_id)
            if row is None:
                skip("not_found")
                continue
            if not row.get("missing"):
                skip("no_missing")
                continue
            raw_channel_ids = row.get("channel_ids")
            if isinstance(raw_channel_ids, list):
                channel_ids = [
                    str(channel_id).strip()
                    for channel_id in raw_channel_ids
                    if str(channel_id).strip()
                ]
            else:
                channel_id = str(row.get("channel_id") or "").strip()
                channel_ids = [channel_id] if channel_id else []
            # 兼容过渡期数据：channel_ids 为空时仍读取旧 channel_id。
            if not channel_ids:
                channel_id = str(row.get("channel_id") or "").strip()
                channel_ids = [channel_id] if channel_id else []
            if not channel_ids:
                skip("missing_channel")
                continue
            seen_row_channels: set[str] = set()
            for channel_id in channel_ids:
                if channel_id in seen_row_channels:
                    continue
                seen_row_channels.add(channel_id)
                if channel_id == "untracked":
                    skip("untracked")
                    continue
                if channel_id.startswith("once:"):
                    skip("once_mapping")
                    continue
                if channel_id in enabled_strm:
                    if channel_id in selected_mapping_ids:
                        deduplicated += 1
                    else:
                        selected_mapping_ids.add(channel_id)
                    continue
                if channel_id in upload_mapping_ids:
                    skip("upload_mapping")
                elif channel_id in configured_strm:
                    skip("disabled_mapping")
                else:
                    skip("missing_mapping")

        # 保持配置顺序；批量选择只提交一个 STRM 后台任务。
        mappings = [
            mapping
            for mapping_id, mapping in enabled_strm.items()
            if mapping_id in selected_mapping_ids
        ]
        mapping_ids = [
            str(mapping.get("id") or mapping.get("source_cid") or "default")
            for mapping in mappings
        ]
        summary = {
            "requested": len(row_ids),
            "triggered": len(mappings),
            "skipped": sum(reasons.values()),
            "deduplicated": deduplicated,
            "mapping_ids": mapping_ids,
            "reasons": reasons,
        }
        if not mappings:
            result = _error("选中的媒体没有可补跑的 STRM 映射")
            result["data"] = summary
            return result
        # 只预检本次选中的映射，配置错误必须在提交后台任务前同步返回。
        if error := self._strm_start_error(mappings):
            result = _error(error)
            result["data"] = summary
            return result

        result = self._start(
            "strm",
            # 补缺集只做增量；全量同步由独立入口负责。
            lambda: self.run_strm(
                self._strm_moviepilot_url(), mappings, manual=True, strm_incremental=True
            ),
            f"已开始补缺集：同步 {len(mappings)} 条 STRM 通道",
        )
        result["data"] = summary
        return result

    # ── 文件管理台：一次性任务 ──────────────────────────────────────────
    #
    # 「不建通道就跑一次」。记录照样写进 strm_records（mapping_id 用 once:<cid>），这样
    # 增量能跳过、体检能看见；但**反向删除不会管它们** —— decide() 只遍历配置里的通道，
    # once: 不在里面。要让本地删除联动网盘，得去设置里为这个目录建一条正式通道。

    def task_strm_once(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """给指定的 115 目录生成一批 STRM，不落通道配置。"""
        data = payload or {}
        source_cid = str(data.get("source_cid") or "").strip()
        target_dir = str(data.get("target_dir") or "").strip()
        if not source_cid:
            return _error("先选一个 115 源目录")
        if not target_dir:
            return _error("先选一个本地输出目录")
        config = self._store.get_config()
        authorized_target = self._authorized_local_path(target_dir, config=config)
        if authorized_target is None:
            return _error(f"STRM 输出目录不在本地目录 allowlist 内：{target_dir}")
        try:
            moviepilot_url = normalize_moviepilot_url(
                str(config.get("moviepilot_address") or "")
            )
        except ValueError as err:
            return _error(str(err))
        source_path = str(data.get("source_path") or "").strip()
        mapping = {
            "id": f"once:{source_cid}",
            "source_cid": source_cid,
            "source_path": source_path,
            "target_dir": str(authorized_target),
            "enabled": True,
        }
        return self._start(
            "strm",
            lambda: self.run_strm(moviepilot_url, [mapping], manual=True),
            f"已开始为 {source_path or source_cid} 生成 STRM",
        )

    def task_upload_once(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """把指定的本地目录传到指定的 115 目录，不落通道配置。"""
        data = payload or {}
        source = str(data.get("source") or "").strip()
        target = str(data.get("target") or "").strip().replace("\\", "/")
        if not source:
            return _error("先选一个本地源目录")
        if not target:
            return _error("先选一个 115 目标目录")
        config = self._store.get_config()
        source_dir = self._authorized_local_path(source, config=config)
        if source_dir is None:
            return _error(f"本地源目录不在本地目录 allowlist 内：{source}")
        if not source_dir.is_dir():
            return _error(f"本地源目录不存在：{source_dir}")
        strm_target = str(data.get("strm_target") or "").strip()
        authorized_strm_target: Path | None = None
        if config.get("upload_generate_strm"):
            if not strm_target:
                return _error("上传完成生成 STRM 时，必须配置 STRM 输出目录")
            authorized_strm_target = self._authorized_local_path(strm_target, config=config)
            if authorized_strm_target is None:
                return _error(f"上传 STRM 输出目录不在本地目录 allowlist 内：{strm_target}")
        moviepilot_url = ""
        if config.get("upload_generate_strm"):
            try:
                moviepilot_url = normalize_moviepilot_url(
                    str(config.get("moviepilot_address") or "")
                )
            except ValueError as err:
                return _error(str(err))
        incremental = bool(data.get("incremental", True))
        mapping = {
            "id": f"once:{source_dir.as_posix()}",
            "source": str(source_dir),
            "target": target,
            "strm_target": str(authorized_strm_target or ""),
            "enabled": True,
            "label": source_dir.name,
        }
        mode = "增量" if incremental else "全量"
        return self._start(
            "upload",
            lambda: self.run_upload(incremental, moviepilot_url, [mapping]),
            f"已开始{mode}上传 {source_dir.name} → {target}",
        )

    def trigger_upload(
        self,
        payload: Dict[str, Any] | bool | None = None,
    ) -> Dict[str, Any]:
        """兼容入口：None/False/{auto:true} 为自动合并；显式手动 payload 保持整映射语义。"""
        auto = payload in (False, None) or (isinstance(payload, dict) and bool(payload.get("auto")))
        if auto:
            source = str(payload.get("source") or "auto") if isinstance(payload, dict) else "auto"
            return self.queue_upload(source=source)
        if error := self._upload_start_error():
            return _error(error)
        incremental = payload if isinstance(payload, bool) else bool((payload or {}).get("incremental", True))
        return self._start(
            "upload",
            lambda: self.run_upload(incremental, self._strm_moviepilot_url()),
            "目录上传已开始",
        )

    def queue_upload(self, source: str = "watch") -> Dict[str, Any]:
        """旧自动整映射入口：忙时合并，cloud task 结束后最终补跑一次。"""
        if error := self._upload_start_error():
            return _error(error)
        result = self._start(
            "upload", lambda: self.run_upload(True, self._strm_moviepilot_url()),
            "目录上传已开始",
        )
        if result.get("success"):
            return result
        with self._lock:
            now = time()
            self._pending_auto_upload = True
            self._pending_auto_upload_queued_at = self._pending_auto_upload_queued_at or now
            sources = set(filter(None, self._pending_auto_upload_source.split(",")))
            sources.add(str(source or "auto"))
            self._pending_auto_upload_source = ",".join(sorted(sources))
            self._pending_auto_upload_count += 1
        logger.info("【目录上传】整映射自动任务忙，已合并排队等待补跑")
        return _ok(data={"queued": True}, message="已排队，等当前任务结束后自动补跑")

    def set_upload_restabilizer(self, callback: Callable[[str, str], bool] | None) -> None:
        self._upload_restabilize = callback

    def queue_upload_file(self, candidate: UploadCandidate) -> Dict[str, Any]:
        """稳定性线程的内部入口：按文件 key+signature 去重后请求一个短批次。"""
        if not isinstance(candidate, UploadCandidate):
            return _error("上传候选格式无效")
        outcome = self._upload_queue.offer(candidate)
        if outcome == "accepted":
            self._drain_pending_upload()
            return _ok(data={"accepted": True, "queued": True, "duplicate": False}, message="文件已加入上传队列")
        if outcome == "duplicate":
            return _ok(data={"accepted": True, "queued": bool(self._upload_queue), "duplicate": True}, message="文件已在上传队列中")
        # full 明确拒绝，StabilityTracker 据此保留/压成 full-marker 后走整映射重扫。
        return _error("待上传队列已满，已转为全量重扫回退", accepted=False, full=True)

    def clear_invalid_upload_candidates(
        self, valid_revisions: set[tuple[str, str, tuple]]
    ) -> int:
        return self._upload_queue.clear_invalid(valid_revisions)

    def _run_upload_batch(self) -> Dict[str, Any] | None:
        batch = self._upload_queue.take(UPLOAD_BATCH_SIZE)
        if not batch:
            return None
        started = monotonic()
        ready: list[UploadCandidate] = []
        for candidate in batch:
            current = file_signature(Path(candidate.file_path))
            if current is None:
                self._upload_queue.finish(candidate, processed=False)
                continue
            if current != candidate.signature:
                self._upload_queue.finish(candidate, processed=False)
                if self._upload_restabilize is not None:
                    self._upload_restabilize(candidate.file_path, candidate.source)
                continue
            ready.append(candidate)
        if not ready:
            return None
        for candidate in ready:
            if not self._upload_queue.mark_started(candidate):
                # 配置同步已清除此尚未开始的旧 revision。
                return None
        try:
            entry = self.run_upload_files(ready, self._strm_moviepilot_url())
        except Exception:
            self._upload_queue.restore(ready)
            self._schedule_upload_retry()
            raise
        errors_by_path = {
            str(item.get("path") or "")
            for item in entry.get("errors_detail") or []
            if isinstance(item, dict)
        }
        deferred = int(entry.get("deferred") or 0)
        unattributed_failure = int(entry.get("errors") or 0) > 0 and not errors_by_path
        restored = False
        for index, candidate in enumerate(ready):
            failed = unattributed_failure or candidate.file_path in errors_by_path
            was_deferred = deferred > 0 and index >= len(ready) - deferred
            if failed or was_deferred:
                if self._upload_candidate_is_current(candidate):
                    self._upload_queue.restore([candidate])
                    restored = True
                else:
                    self._upload_queue.finish(candidate, processed=False)
            else:
                # 已成功、已确认无需上传或已删源都属于完成态；预算只阻止下一批。
                self._upload_queue.finish(candidate, processed=True)
        if restored:
            self._schedule_upload_retry()
        else:
            self._reset_upload_retry()
        if monotonic() - started >= UPLOAD_BATCH_TIME_BUDGET:
            logger.info("【目录上传】文件批次达到时间预算，释放 115 数据锁后再调度下一批")
        return entry

    def _upload_candidate_is_current(self, candidate: UploadCandidate) -> bool:
        config = self._store.get_config()
        matches = 0
        for mapping in config.get("upload_mappings") or []:
            if not isinstance(mapping, dict) or not mapping.get("enabled", True):
                continue
            source_text = str(mapping.get("source") or "").strip()
            if not source_text:
                continue
            try:
                source_root = str(Path(source_text).expanduser().resolve())
                revision = mapping_revision(mapping, config, canonical_source=source_root)
            except (OSError, RuntimeError, ValueError):
                continue
            mapping_id = str(mapping.get("id") or source_root)
            if (
                mapping_id == candidate.mapping_id
                and source_root == candidate.source_root
                and revision == candidate.mapping_revision
            ):
                matches += 1
        return matches == 1

    def _drain_pending_upload(self) -> bool:
        """自动整映射队列优先，随后每次只启动一个文件短批次。"""
        if self._upload_start_error(validate_mappings=False):
            return False
        with self._lock:
            auto_pending = self._pending_auto_upload
            if auto_pending and "upload" not in self._running:
                self._pending_auto_upload = False
                self._pending_auto_upload_source = ""
                self._pending_auto_upload_queued_at = 0.0
                self._pending_auto_upload_count = 0
        if auto_pending:
            result = self._start(
                "upload", lambda: self.run_upload(True, self._strm_moviepilot_url()),
                "目录上传已开始（补跑）",
            )
            if result.get("success"):
                return True
            with self._lock:
                self._pending_auto_upload = True
            return False
        with self._lock:
            if (
                self._upload_scheduler_stopping
                or self._upload_retry_timer is not None
                or self._upload_retry_exhausted
            ):
                return False
        if not self._upload_queue or self._upload_start_error(validate_mappings=False):
            return False
        with self._lock:
            if "upload" in self._running:
                return False
        result = self._start("upload", self._run_upload_batch, "目录上传已开始（文件批次）")
        return bool(result.get("success"))

    def _schedule_upload_retry(self) -> bool:
        """为失败候选安排一次可取消的有界退避，不在当前 worker 原地循环。"""
        with self._lock:
            if self._upload_scheduler_stopping or self._upload_retry_timer is not None:
                return False
            if not self._upload_queue:
                self._upload_retry_attempt = 0
                return False
            if self._upload_retry_attempt >= len(self._UPLOAD_RETRY_DELAYS):
                self._upload_retry_exhausted = True
                logger.warning(
                    "【目录上传】自动退避重试次数已用完，候选继续保留；"
                    "保存配置或恢复授权后会立即唤醒"
                )
                return False
            delay = max(0.0, float(self._UPLOAD_RETRY_DELAYS[self._upload_retry_attempt]))
            self._upload_retry_attempt += 1
            self._upload_retry_token += 1
            token = self._upload_retry_token
            timer = threading.Timer(delay, self._upload_retry_wakeup, args=(token,))
            timer.name = "p115liteassistant-upload-retry"
            timer.daemon = True
            self._upload_retry_timer = timer
        try:
            timer.start()
        except Exception:
            with self._lock:
                if self._upload_retry_timer is timer:
                    self._upload_retry_timer = None
            raise
        logger.warning(
            f"【目录上传】失败候选已恢复，{delay:g}s 后进行第 "
            f"{self._upload_retry_attempt}/{len(self._UPLOAD_RETRY_DELAYS)} 次批次重试"
        )
        return True

    def _upload_retry_wakeup(self, token: int) -> None:
        with self._lock:
            if token != self._upload_retry_token or self._upload_scheduler_stopping:
                return
            self._upload_retry_timer = None
        started = self._drain_pending_upload()
        if started or not self._upload_queue:
            return
        # 正常 cloud task 结束时会自行 drain；仅在没有已登记任务却仍抢不到锁时
        # 继续下一档退避，避免异常外部持锁造成永久滞留。
        with self._lock:
            cloud_task_running = bool(self._running & self._CLOUD_TASK_KINDS)
        if not cloud_task_running:
            self._schedule_upload_retry()

    def _reset_upload_retry(self) -> None:
        timer: threading.Timer | None
        with self._lock:
            timer = self._upload_retry_timer
            # 正在执行回调的 Timer 已把引用清空；它不能取消自己，也无需 join。
            if timer is threading.current_thread():
                timer = None
            self._upload_retry_timer = None
            self._upload_retry_attempt = 0
            self._upload_retry_token += 1
            self._upload_retry_exhausted = False
        if timer is not None:
            timer.cancel()
            if timer.is_alive() and timer is not threading.current_thread():
                timer.join(timeout=0.5)

    def wake_pending_upload(self) -> None:
        """配置或凭证恢复入口：取消退避并立即尝试下一批。"""
        with self._lock:
            if self._upload_scheduler_stopping:
                return
        self._reset_upload_retry()
        self._drain_pending_upload()

    def stop_upload_retry_scheduler(self, timeout: float = 0.5) -> None:
        """停止自动补跑并有界回收 Timer 线程；pending 数据保持不变。"""
        with self._lock:
            self._upload_scheduler_stopping = True
            self._upload_retry_token += 1
            timer = self._upload_retry_timer
            self._upload_retry_timer = None
        if timer is not None:
            timer.cancel()
            if timer.is_alive() and timer is not threading.current_thread():
                timer.join(timeout=max(0.0, float(timeout)))

    def _upload_start_error(self, *, validate_mappings: bool = True) -> str:
        config = self._store.get_config()
        if not config.get("enabled"):
            return "插件未启用"
        if not config.get("upload_generate_strm"):
            return ""
        try:
            normalize_moviepilot_url(str(config.get("moviepilot_address") or ""))
        except ValueError as err:
            return str(err)
        if not validate_mappings:
            return ""
        mappings = [
            mapping
            for mapping in config.get("upload_mappings") or []
            if isinstance(mapping, dict) and mapping.get("enabled", True)
        ]
        for mapping in mappings:
            if not str(mapping.get("strm_target") or "").strip():
                return "上传完成生成 STRM 时，每个映射都必须配置 STRM 输出目录"
        return ""

    def run_strm(
        self,
        moviepilot_url: str,
        mappings: Optional[list[Dict[str, Any]]] = None,
        manual: bool = False,
        strm_incremental: Optional[bool] = None,
    ) -> list[Dict[str, Any]]:
        """``mappings`` 可限定通道；``strm_incremental=None`` 时沿用全局配置。"""
        config = self._store.get_config()
        incremental = (
            bool(config.get("strm_incremental", True))
            if strm_incremental is None
            else bool(strm_incremental)
        )
        if mappings is None:
            mappings = [mapping for mapping in config.get("strm_mappings") or [] if mapping.get("enabled", True)]
        logger.info(f"【STRM同步】开始执行，模式：{'增量' if incremental else '全量'}，有效映射：{len(mappings)}")
        if not mappings:
            logger.warning("【STRM同步】没有启用的目录映射，任务结束")
        allowed_roots = self._local_roots(config)
        generator: StrmGenerator | None = None
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
        for index, mapping in enumerate(mappings):
            source = str(mapping.get("source_path") or mapping.get("source_cid") or "-")
            self._task_checkpoint(phase="strm-mapping", current_item=source,
                                  progress={"current": index, "total": len(mappings)},
                                  raise_if_cancelled=True)
            access_limited = False
            target = str(mapping.get("target_dir") or "-")
            logger.info(f"【STRM同步】开始处理映射：{source} -> {target}")
            mapping_started = monotonic()
            authorized_target = self._authorized_local_path(target, roots=allowed_roots)
            if authorized_target is None:
                message = f"STRM 输出目录不在本地目录 allowlist 内：{target}"
                logger.error(f"【STRM同步】映射授权失败：{source} -> {target}，原因：{message}")
                entry = {
                    "kind": "strm",
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "mapping": source,
                    "errors": 1,
                    "message": message,
                }
            else:
                execution_mapping = deepcopy(mapping)
                execution_mapping["target_dir"] = str(authorized_target)
                if generator is None:
                    generator = StrmGenerator(
                        self._client_provider(),
                        self._store,
                        moviepilot_url,
                        incremental,
                        download_sidecars=bool(config.get("strm_download_sidecars", False)),
                        sidecar_extensions=str(config.get("upload_sidecar_extensions") or ""),
                        recent_deletes=self._recent_deletes,
                        journal=self._strm_journal,
                    )
                try:
                    entry = retry_call(
                        lambda: generator.run_mapping(execution_mapping),
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
        self._notify_strm(entries, totals, incremental, manual=manual)
        return entries

    # ---- 反向删除：本地 STRM 被删除后清理网盘上对应的文件 ----

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
        """定时巡检入口 —— 兜住实时监听漏掉的删除（容器重启、事件丢失、网络挂载等）。

        顺带在这里报一声库况：那条 cron 本来就在跑，不必为通知再加一个任务。
        """
        result = self.queue_strm_sweep()
        self.notify_ledger_digest()
        return result

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
                    if not value or self._pending_sweep_all:
                        continue
                    if value not in self._pending_sweep_paths and len(self._pending_sweep_paths) >= self._PENDING_SWEEP_MAX:
                        self._pending_sweep_paths.clear()
                        self._pending_sweep_all = True
                        logger.warning("【STRM反向删除】待巡检路径容量已满，已压为全量巡检标记")
                        break
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

    # ── 网盘管理 ──────────────────────────────────────────────────────
    #
    # 能力边界见 docs/research/115-api.md：浏览、新建、改名、删除都在开放接口里；
    # 移动、容量、回收站列表与还原只有 cookie 链路能做，且那几个端点还没实测过，
    # 所以这一版不给这些动作，界面上也不留一个按下去会报错的按钮。

    def disk_list(self, cid: str = "0") -> Dict[str, Any]:
        """列一个 115 目录，目录和文件都要。

        ``/browse-115`` 只回目录 —— 那个是给目录选择器用的；网盘管理器要看见文件、
        体积和时间，所以另开一个。面包屑由前端自己攒（一路点下去它知道来路），
        免得每翻一层多打一次 ``folder/get_info``。
        """
        try:
            target = str(cid or "0")
            items: list[Dict[str, Any]] = []
            for raw in self._client_provider().get_dir_list(target):
                if not isinstance(raw, dict):
                    continue
                name = U115Client._item_name(raw).strip()
                item_id = U115Client._item_id(raw)
                if not name or not item_id:
                    continue
                is_dir = U115Client._is_directory(raw)
                items.append(
                    {
                        "id": item_id,
                        "name": name,
                        "is_dir": is_dir,
                        "size": 0 if is_dir else int(U115Client._item_size(raw) or 0),
                        "mtime": int(U115Client._item_mtime(raw) or 0),
                        "pickcode": str(
                            raw.get("pc") or raw.get("pickcode") or raw.get("pick_code") or ""
                        ),
                    }
                )
            # 目录排前面，各自按名字排 —— 和 115 网页端同一个读法
            items.sort(key=lambda item: (not item["is_dir"], item["name"].lower()))
            return _ok({"cid": target, "items": items})
        except Exception as err:  # noqa: BLE001
            logger.error(f"【网盘】列目录失败：{safe_error_text(err)}")
            return _error(safe_error_text(err))

    def disk_mkdir(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        data = payload or {}
        name = str(data.get("name") or "").strip()
        if not name:
            return _error("目录名不能为空")
        try:
            self._client_provider().create_child_dir(str(data.get("cid") or "0"), name)
        except Exception as err:  # noqa: BLE001
            logger.error(f"【网盘】新建目录失败：{safe_error_text(err)}")
            return _error(safe_error_text(err))
        try:
            self._browse_115_cache.clear()
        except Exception as err:  # noqa: BLE001
            logger.warning(f"【目录上传】清理目录缓存失败：{safe_error_text(err)}")
        return _ok(message=f"已新建目录 {name}")

    def disk_rename(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        data = payload or {}
        file_id = str(data.get("file_id") or "").strip()
        name = str(data.get("name") or "").strip()
        if not file_id:
            return _error("缺少要改名的文件 ID")
        if not name:
            return _error("新名字不能为空")
        try:
            self._client_provider().rename_item(file_id, name)
        except Exception as err:  # noqa: BLE001
            logger.error(f"【网盘】改名失败：{safe_error_text(err)}")
            return _error(safe_error_text(err))
        self._browse_115_cache.clear()
        return _ok(message=f"已改名为 {name}")

    def _strm_claim_context(
        self, records: Dict[str, Any]
    ) -> tuple[RecordClaims, Dict[str, Path]]:
        config = self._store.get_config()
        mappings = [
            item for item in config.get("strm_mappings") or []
            if isinstance(item, dict)
        ]
        mapping_ids = {
            str(item.get("id") or item.get("source_cid") or "default")
            for item in mappings
        }
        mapping_ids.update(
            str(record.get("mapping_id") or "")
            for record in records.values()
            if isinstance(record, dict) and record.get("mapping_id")
        )
        upload_getter = getattr(self._store, "get_upload_records", None)
        upload_records = upload_getter() if callable(upload_getter) else {}
        claims = RecordClaims.from_records(
            records, upload_records, mapping_ids=mapping_ids,
            upload_mappings=config.get("upload_mappings") or [],
        )
        roots = {
            str(item.get("id") or item.get("source_cid") or "default"):
            Path(str(item.get("target_dir") or "")).expanduser().resolve()
            for item in mappings if str(item.get("target_dir") or "").strip()
        }
        return claims, roots

    @staticmethod
    def _claim_owner_id(claim) -> str:
        return str(claim.owner or "").removeprefix(f"{claim.container}:")

    def disk_delete(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """删除网盘条目；also_local 使用统一 owned-removal journal。"""
        data = payload or {}
        raw_ids = data.get("file_ids") or data.get("ids")
        if isinstance(raw_ids, (str, int)):
            raw_ids = [raw_ids]
        if not isinstance(raw_ids, list) or not raw_ids:
            return _error("没有要删的文件")
        ids = list(dict.fromkeys(
            str(value).strip() for value in raw_ids if str(value).strip()
        ))
        if not ids:
            return _error("没有要删的文件")
        try:
            self._client_provider().delete_file(ids)
        except Exception as err:  # noqa: BLE001
            logger.error(f"【网盘】删除失败：{safe_error_text(err)}")
            return _error(safe_error_text(err))
        self._browse_115_cache.clear()

        local_removed = records_dropped = local_refused = local_errors = 0
        if bool(data.get("also_local")):
            wanted = set(ids)
            records = self._store.get_strm_records()
            claims, roots = self._strm_claim_context(records)
            requests: list[OwnedRemovalRequest] = []
            for key, record in records.items():
                if not isinstance(record, dict):
                    continue
                file_id = str(record.get("file_id") or record.get("fileid") or "")
                if file_id not in wanted:
                    continue
                claim = claims.get(("strm", str(key)))
                owner_id = self._claim_owner_id(claim) if claim is not None else ""
                target_root = roots.get(owner_id)
                if claim is None or target_root is None:
                    local_refused += 1
                    continue
                requests.append(OwnedRemovalRequest(
                    ("strm", str(key)), record, target_root, owner_id
                ))
            results = StrmMaterializer(self._store).prepare_owned_removals(
                requests, claims
            )
            for result in results:
                if not result.may_drop_record or result.unit is None:
                    local_refused += 1
                    continue
                try:
                    self._strm_journal.execute(result.unit)
                except Exception as err:  # noqa: BLE001
                    local_errors += 1
                    logger.warning(f"【网盘】本地 STRM 删除事务失败：{safe_error_text(err)}")
                    continue
                records_dropped += len(result.unit.mutations)
                local_removed += sum(
                    1 for operation in result.unit.file_ops
                    if operation.action == "unlink"
                )
                for mutation in result.unit.mutations:
                    records.pop(mutation.key, None)

        message = f"网盘删了 {len(ids)} 个，进了 115 回收站，能在 115 上还原"
        if bool(data.get("also_local")):
            message += f"；本地跟着删了 {local_removed} 个 STRM"
            if local_refused or local_errors:
                message += f"，拒绝 {local_refused} 个，失败 {local_errors} 个"
        logger.info(f"【网盘】{message}")
        return _ok({
            "deleted": len(ids), "local_removed": local_removed,
            "records_dropped": records_dropped, "local_refused": local_refused,
            "local_errors": local_errors,
        }, message=message)

    # ── 媒体清单 ──────────────────────────────────────────────────────

    def _ledger_rows(
        self,
        with_seeding: bool = True,
    ) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
        """聚合清单的行。``with_seeding`` 给 False 就不去问下载器 —— 通知那条路每两小时
        跑一次，不该顺手拉一遍种子列表。"""
        config = self._store.get_config()
        records = self._store.get_strm_records()

        pending_paths: set[str] = set()
        for batch in self._store.get_strm_delete_pending().values():
            if not isinstance(batch, dict):
                continue
            for item in batch.get("items") or []:
                if isinstance(item, dict) and item.get("path"):
                    pending_paths.add(str(item["path"]))

        items = media_records(records)
        known: set[str] = set()
        for _key, record in items:
            raw = str(record.get("path") or "")
            if not raw:
                continue
            try:
                known.add(str(Path(raw).resolve()))
            except (OSError, RuntimeError, ValueError):
                known.add(raw)
        roots = [
            str(mapping.get("target_dir") or "").strip()
            for mapping in config.get("strm_mappings") or []
            if isinstance(mapping, dict) and str(mapping.get("target_dir") or "").strip()
        ]

        seeding_paths: set[str] = set()
        seed_ids: Dict[str, int] = {}
        seed_total = 0
        seed_error = "没有拉取做种信息"
        if with_seeding:
            seeding_paths, seed_hashes, seed_total, seed_error = collect_seeding_paths()
            seed_ids = seeding_identities(seed_hashes) if not seed_error else {}

        rows = build_ledger(
            records=records,
            strm_mappings=[
                mapping for mapping in config.get("strm_mappings") or [] if isinstance(mapping, dict)
            ],
            upload_mappings=[
                mapping
                for mapping in config.get("upload_mappings") or []
                if isinstance(mapping, dict) and mapping.get("enabled", True)
            ],
            upload_records=self._store.get_upload_records().to_dict(),
            upload_conflicts=self._store.get_upload_conflicts(),
            pending_paths=pending_paths,
            media_extensions=parse_extensions(
                config.get("upload_media_extensions", ""), DEFAULT_MEDIA_EXTENSIONS
            ),
            untracked=find_untracked(roots, known),
            seeding_paths=seeding_paths,
            seeding_identities=seed_ids,
        )
        meta = {
            "records": len(items),
            "roots": roots,
            "seed_total": seed_total,
            "seed_error": seed_error,
        }

        cache = self._store.get_cloud_check()
        cloud = cache.get("rows") or {}
        for row in rows:
            entry = cloud.get(row["id"]) if isinstance(cloud, dict) else None
            if isinstance(entry, dict) and entry.get("state") in ("yes", "no"):
                row["cloud_state"] = str(entry["state"])
                row["cloud_checked_at"] = int(entry.get("checked_at") or 0)
            else:
                row["cloud_state"] = "unchecked"
                row["cloud_checked_at"] = 0
        return rows, meta

    def media_ledger(self) -> Dict[str, Any]:
        """一部电影一行、一季剧一行的总账，加一份「有事可做」的小结。

        筛选与计数交给前端算 —— 计数要把「你已经选了的其它维度」考虑进去，放后端就得为
        每一次勾选往返一趟。行本身不多（真机 990 条记录聚合下来几百行），一次给完更快。
        """
        try:
            rows, meta = self._ledger_rows(with_seeding=True)
            cache = self._store.get_cloud_check()
            waiting = cooldown_left(cache)
            unchecked = sum(
                1 for row in rows if row["cloud_state"] == "unchecked" and row["cloud_folder"]
            )
            channels = sorted(
                {(row["channel_id"], row["channel"]) for row in rows if row["channel_id"]},
                key=lambda pair: pair[1],
            )
            return _ok(
                {
                    "rows": rows,
                    "channels": [{"id": item[0], "label": item[1]} for item in channels],
                    "records": meta["records"],
                    "roots": meta["roots"],
                    # 清单顶上那行总计要的三个「有事可做」的数
                    "summary": self._ledger_summary(rows),
                    # 做种这一维只在真拿到种子列表时才可用；拿不到就不画那组筛选，
                    # 也不解锁「删除源文件」
                    "has_seeding": not meta["seed_error"],
                    "seeding_note": meta["seed_error"],
                    "seeds": meta["seed_total"],
                    # 网盘核对是按预算的手动动作，不会在打开页面时偷偷打接口
                    "has_cloud_check": True,
                    "cloud_unchecked": unchecked,
                    "cloud_budget": CHECK_BUDGET,
                    "cloud_cooldown": waiting,
                    "cloud_note": (
                        f"115 报过访问上限，还要等 {waiting // 60 + 1} 分钟才能继续核对"
                        if waiting
                        else f"还有 {unchecked} 行没核对过网盘"
                        if unchecked
                        else "网盘核对都是最新的"
                    ),
                }
            )
        except Exception as err:  # noqa: BLE001
            logger.error(f"【媒体清单】聚合失败：{safe_error_text(err)}")
            return _error(safe_error_text(err))

    def ledger_verify(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """核对网盘：问 115「这些片的目录还在不在」。

        **这是清单里唯一会主动打 115 接口的动作**，所以它按限流的实际情况办事：一次有预算
        上限、冷却期内不打、撞上访问上限立刻停并如实说停在哪。给了 ``row_ids`` 就只核对那几行，
        没给就核对最久没核对过的那一批。
        """
        data = payload or {}
        cache = self._store.get_cloud_check()
        waiting = cooldown_left(cache)
        if waiting:
            return _error(
                f"115 报过访问上限，还要等 {waiting // 60 + 1} 分钟。"
                f"这段时间不打接口，免得把限流拖得更长"
            )
        if error := self._strm_start_error():
            return _error(error)

        report = self.media_ledger()
        if not report.get("success"):
            return report
        rows = (report.get("data") or {}).get("rows") or []
        wanted = data.get("row_ids")
        if isinstance(wanted, str):
            wanted = [wanted]
        try:
            budget = max(1, min(int(data.get("budget") or CHECK_BUDGET), CHECK_BUDGET))
        except (TypeError, ValueError):
            budget = CHECK_BUDGET

        if isinstance(wanted, list) and wanted:
            picked = [row for row in rows if row["id"] in set(wanted) and row["cloud_folder"]]
            if not picked:
                return _error("选中的这些行没记下它们在网盘上的位置，先跑一次同步")
            picked = picked[:budget]
        else:
            picked = pick_rows(rows, cache, budget)
        if not picked:
            return _error("没有需要核对的行")

        results, stopped = check_rows(self._client_provider, picked, budget)
        self._store.save_cloud_check(merge_cloud_check(cache, results, bool(stopped) and "访问上限" in stopped))

        gone = sum(1 for entry in results.values() if entry.get("state") == "no")
        message = f"核对了 {len(results)} 行，其中 {gone} 行网盘上已经没了"
        if stopped:
            message += f"；{stopped}"
        logger.info(f"【网盘核对】{message}")
        return _ok(
            {"checked": len(results), "gone": gone, "stopped": stopped, "asked": len(picked)},
            message=message,
        )

    def _ledger_summary(self, rows: list[Dict[str, Any]]) -> Dict[str, int]:
        """库况小结：三个「有事可做」的数，都不用问 115。

        ``source_left`` 是已经传上网盘、本地源文件还占着地方的字节数 —— 这是唯一能靠一次
        点击立刻腾出来的空间。``cloud_gone`` 只数**核对过**的行：没核对过的不算「没了」。
        """
        source_left = 0
        cloud_gone = 0
        untracked = 0
        for row in rows:
            if row.get("in_library") == "yes" and int(row.get("source_uploaded") or 0):
                source_left += int(row.get("source_size") or 0)
            if row.get("cloud_state") == "no":
                cloud_gone += 1
            if "untracked" in (row.get("flags") or ()):
                untracked += 1
        return {"source_left": source_left, "cloud_gone": cloud_gone, "untracked": untracked}

    def notify_ledger_digest(self) -> None:
        """库况有**新**问题时报一声，而不是每轮巡检都报一遍。

        触发点挂在定时巡检尾巴上：那条 cron 本来就在跑，不必再加一个任务。判定是「跟上次
        报过的比，某一类涨了」——没涨就闭嘴。这样通知的意思始终是「有新情况」，
        而不是「例行汇报」，后者两轮之后就没人看了。

        通道复用 STRM（巡检的通知也走它），不新增配置键：旧版本代码一次 init_plugin
        就会把它不认识的键按白名单从库里洗掉。
        """
        try:
            if not self._notifier.is_enabled("strm"):
                return
            # 不拉种子：这条路每两小时跑一次，不该顺手去问下载器
            rows, _meta = self._ledger_rows(with_seeding=False)
            current = self._ledger_summary(rows)
            previous = self._store.get_ledger_digest()
            lines: list[str] = []
            if current["cloud_gone"] > int(previous.get("cloud_gone") or 0):
                lines.append(f"网盘上没了 {current['cloud_gone']} 部，本地那几份 STRM 已经是死链")
            if current["source_left"] > int(previous.get("source_left") or 0):
                lines.append(
                    f"源文件还占着 {self._bytes_text(current['source_left'])}，这些片已经传上网盘了"
                )
            if current["untracked"] > int(previous.get("untracked") or 0):
                lines.append(f"记录里没有的 STRM {current['untracked']} 部，反向删除看不见它们")
            if not lines:
                return
            self._store.save_ledger_digest({**current, "at": int(time())})
            self._notifier.notify(
                "strm",
                "库里有新情况",
                lines + ["去侧栏的「115 轻量助手」看清单，筛一下就知道是哪几部。"],
            )
        except Exception as err:  # noqa: BLE001
            # 通知失败不该影响巡检本身
            logger.error(f"【库况】通知失败：{safe_error_text(err)}")

    @staticmethod
    def _bytes_text(value: int) -> str:
        """和界面同一套写法：数字与单位之间留一个空格。"""
        left = float(value or 0)
        for unit in ("B", "KB", "MB", "GB"):
            if left < 1024:
                return f"{left:.0f} {unit}" if unit == "B" else f"{left:.1f} {unit}"
            left /= 1024
        return f"{left:.1f} TB"

    # ── STRM 库体检 ────────────────────────────────────────────────────

    def library_drop(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """事务化清理本地 STRM 与所有明确命中的记录；不动网盘。"""
        data = payload or {}
        raw_paths = data.get("paths")
        if isinstance(raw_paths, str):
            raw_paths = [raw_paths]
        if not isinstance(raw_paths, list) or not raw_paths:
            return _error("没有要清理的文件")

        config = self._store.get_config()
        allowed_roots = self._local_roots(config)
        if not allowed_roots:
            return _error("没有可用的本地目录 allowlist，没有可清理的范围")
        mapping_roots: dict[str, Path] = {}
        roots: list[Path] = []
        has_mapping_root = False
        for mapping in config.get("strm_mappings") or []:
            if not isinstance(mapping, dict):
                continue
            value = str(mapping.get("target_dir") or "").strip()
            if not value:
                continue
            has_mapping_root = True
            mapping_root = self._resolved_local_path(value)
            if mapping_root is None:
                continue
            mapping_id = str(mapping.get("id") or mapping.get("source_cid") or "default")
            mapping_roots[mapping_id] = mapping_root
            root = self._authorized_local_path(value, roots=allowed_roots)
            if root is not None and root not in roots:
                roots.append(root)
            for allowed_root in allowed_roots:
                authorized = self._authorized_local_path(allowed_root, roots=[allowed_root])
                if (authorized is not None
                        and self._path_within(authorized, mapping_root)
                        and authorized not in roots):
                    roots.append(authorized)
        if not has_mapping_root:
            return _error("还没有配置 STRM 输出目录，没有可清理的范围")

        targets: list[Path] = []
        refused = 0
        for raw in raw_paths[:2000]:
            try:
                target = Path(str(raw)).expanduser().resolve()
            except (OSError, RuntimeError, ValueError):
                refused += 1
                continue
            if target in targets:
                continue
            if (target.suffix.lower() != ".strm"
                    or not any(self._path_within(target, root) for root in roots)
                    or self._authorized_local_path(target, roots=allowed_roots) is None):
                refused += 1
                continue
            targets.append(target)

        # 路径/allowlist 校验可以在锁外；claims 与 records 必须在 cloud lock 内重取，
        # 否则与同步、上传、反删任务各拿一份旧快照后提交，会对同一 record version 分叉。
        if not self._cloud_task_lock.acquire(blocking=False):
            return _error("115 数据任务正在运行，请稍后重试")
        try:
            records = self._store.get_strm_records()
            claims, _configured_roots = self._strm_claim_context(records)
            by_path: dict[Path, list[tuple[str, Dict[str, Any]]]] = {}
            for key, record in records.items():
                if not isinstance(record, dict):
                    continue
                value = str(record.get("output_path") or record.get("path") or "").strip()
                if not value:
                    continue
                try:
                    by_path.setdefault(Path(value).expanduser().resolve(), []).append(
                        (str(key), record)
                    )
                except (OSError, RuntimeError, ValueError):
                    continue

            removed = dropped = errors = 0
            materializer = StrmMaterializer(self._store)
            for target in targets:
                matches = by_path.get(target, [])
                if not matches:
                    refused += 1  # untracked 默认拒删
                    continue
                requests: list[OwnedRemovalRequest] = []
                invalid = False
                for key, record in matches:
                    claim = claims.get(("strm", key))
                    if claim is None or claim.owner_confidence == "ambiguous":
                        invalid = True
                        break
                    owner_id = self._claim_owner_id(claim)
                    target_root = mapping_roots.get(owner_id)
                    if target_root is None:
                        invalid = True
                        break
                    requests.append(OwnedRemovalRequest(
                        ("strm", key), record, target_root, owner_id
                    ))
                if invalid:
                    refused += 1
                    continue
                result = materializer.prepare_owned_removals(requests, claims)[0]
                if not result.may_drop_record or result.unit is None:
                    refused += 1
                    continue
                try:
                    self._strm_journal.execute(result.unit)
                except Exception as err:  # noqa: BLE001
                    errors += 1
                    logger.warning(f"【库体检】删除事务失败 {target}：{safe_error_text(err)}")
                    continue
                dropped += len(result.unit.mutations)
                removed += sum(
                    1 for operation in result.unit.file_ops if operation.action == "unlink"
                )
                for mutation in result.unit.mutations:
                    records.pop(mutation.key, None)
        finally:
            self._cloud_task_lock.release()

        logger.info(
            f"【库体检】清理完成：删掉 {removed} 个 STRM，清掉 {dropped} 条记录，"
            f"拒绝 {refused} 个，失败 {errors} 个，网盘上的文件一个都没动"
        )
        message = f"删掉 {removed} 个 STRM，清掉 {dropped} 条记录，网盘上的文件一个都没动"
        if refused:
            message += f"；拒绝 {refused} 个越界、未跟踪或归属含糊路径"
        if errors:
            message += f"；{errors} 个事务失败并保留记录"
        result = {"removed": removed, "dropped": dropped, "refused": refused}
        if errors:
            result["errors"] = errors
        return _ok(result, message=message)

    def source_drop(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """删掉本地**源文件**（上传通道源目录里的媒体文件）。网盘和 STRM 都不动。

        和 :meth:`library_drop` 的闸门是对称的：那个只放行 STRM 输出目录下的 ``.strm``，
        这个只放行上传通道源目录下、后缀在媒体扩展名里的文件。

        **上传记录保留不删。** 记录只表示「这个文件传过」，把它删掉的话文件哪天又被放回来
        就会被当成新文件重传一次 —— 那不是删源文件的人想要的。

        这是三个删除动作里**唯一不可撤回**的一个：本地文件系统没有回收站。
        """
        data = payload or {}
        raw_paths = data.get("paths")
        if isinstance(raw_paths, str):
            raw_paths = [raw_paths]
        if not isinstance(raw_paths, list) or not raw_paths:
            return _error("没有要删的源文件")

        config = self._store.get_config()
        allowed_roots = self._local_roots(config)
        if not allowed_roots:
            return _error("没有可用的本地目录 allowlist，没有可删的范围")
        roots: list[Path] = []
        has_mapping_root = False
        for mapping in config.get("upload_mappings") or []:
            if not isinstance(mapping, dict):
                continue
            value = str(mapping.get("source") or "").strip()
            if not value:
                continue
            has_mapping_root = True
            mapping_root = self._resolved_local_path(value)
            if mapping_root is None:
                continue
            root = self._authorized_local_path(value, roots=allowed_roots)
            if root is not None and root not in roots:
                roots.append(root)
            for allowed_root in allowed_roots:
                authorized = self._authorized_local_path(allowed_root, roots=[allowed_root])
                if (
                    authorized is not None
                    and self._path_within(authorized, mapping_root)
                    and authorized not in roots
                ):
                    roots.append(authorized)
        if not has_mapping_root:
            return _error("还没有配置上传通道源目录，没有可删的范围")
        suffixes = {
            str(value).lower()
            for value in parse_extensions(
                config.get("upload_media_extensions", ""), DEFAULT_MEDIA_EXTENSIONS
            )
            if str(value).strip()
        }

        removed = 0
        freed = 0
        refused = 0
        for raw in raw_paths[:2000]:
            try:
                target = Path(str(raw)).expanduser().resolve()
            except (OSError, RuntimeError, ValueError):
                refused += 1
                continue
            if (
                target.suffix.lower() not in suffixes
                or not any(self._path_within(target, root) for root in roots)
                or self._authorized_local_path(target, roots=allowed_roots) is None
            ):
                refused += 1
                continue
            try:
                if not target.is_file():
                    continue
                size = target.stat().st_size
                target.unlink()
            except OSError as err:
                logger.warning(f"【源文件】删不掉 {target}：{safe_error_text(err)}")
                continue
            removed += 1
            freed += int(size or 0)
        logger.info(
            f"【源文件】删掉 {removed} 个本地源文件，腾出 {freed} 字节，"
            f"拒绝 {refused} 个越界路径，网盘与 STRM 都没动"
        )
        message = f"删掉 {removed} 个本地源文件，网盘与 STRM 都没动"
        if refused:
            message += f"；{refused} 个路径不在上传通道源目录里，已拒绝"
        return _ok({"removed": removed, "freed": freed, "refused": refused}, message=message)

    @staticmethod
    def _path_within(target: Path, root: Path) -> bool:
        try:
            target.relative_to(root)
        except ValueError:
            return False
        return True

    #: 一次最多回多少字节日志。前端按秒轮询，回大了纯属浪费。
    _LOG_TAIL_MAX_BYTES = 64 * 1024

    def log_tail(self, offset: int = 0, limit: int = 0) -> Dict[str, Any]:
        """插件日志的尾部，供任务台实时看。

        ``offset`` 传上一次返回的 ``next_offset``，就只拿新增的那几行。三种边界：
        第一次进来（offset 给 0）从尾部往前截一段；日志被轮转截短过（offset 超过文件
        长度）从头重来并告知前端清屏；这一段里连一个换行都没有就什么都不回，等下一轮。
        """
        # 日志文件按插件目录名命名（见宿主 app/log.py），所以从目录名反查，改名不会失联
        path = Path(settings.LOG_PATH) / "plugins" / f"{Path(__file__).resolve().parent.name}.log"
        try:
            size = path.stat().st_size
        except OSError:
            return _ok({"lines": [], "next_offset": 0, "size": 0, "missing": True})

        cap = max(4096, min(int(limit or self._LOG_TAIL_MAX_BYTES), self._LOG_TAIL_MAX_BYTES))
        start = int(offset or 0)
        rotated = start > size
        seeked = False
        if start <= 0 or rotated:
            start = max(0, size - cap)
            seeked = start > 0
        want = min(cap, size - start)
        if want <= 0:
            return _ok({"lines": [], "next_offset": size, "size": size, "rotated": rotated})

        try:
            with path.open("rb") as handle:
                handle.seek(start)
                raw = handle.read(want)
        except OSError as err:
            return _error(f"读不到插件日志：{safe_error_text(err)}")

        # 只认到最后一个换行为止：末尾那行可能还没写完，留给下一轮
        cut = raw.rfind(b"\n")
        if cut < 0:
            return _ok({"lines": [], "next_offset": start, "size": size, "rotated": rotated})
        lines = raw[: cut + 1].decode("utf-8", errors="ignore").splitlines()
        # 自己跳到尾部时，第一行大概率是从中间切进去的半截
        if seeked and lines:
            lines = lines[1:]
        return _ok(
            {
                "lines": lines[-400:],
                "next_offset": start + cut + 1,
                "size": size,
                "rotated": rotated,
            }
        )

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
        try:
            return self.run_strm_sweep(scope)
        except Exception:
            self._queue_sweep_scope(scope)
            raise

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

    def _drain_pending_tasks(self, completed_kind: str) -> None:
        drains = (
            (self._drain_pending_upload, self._drain_pending_sweep)
            if completed_kind == "sweep"
            else (self._drain_pending_sweep, self._drain_pending_upload)
        )
        for drain in drains:
            try:
                drain()
            except Exception as err:  # noqa: BLE001
                logger.error(f"【任务编排】补跑排队任务失败：{safe_error_text(err)}")

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
        deleter = ReverseDeleter(
            self._client_provider, self._store, self._strm_journal, self._recent_deletes
        )
        scope_text = "全部记录" if paths is None else f"{len(paths)} 个路径"
        logger.info(
            f"【STRM反向删除】开始执行，范围：{scope_text}，有效通道：{len(mappings)}"
        )
        entries: list[Dict[str, Any]] = []
        totals: Dict[str, int] = {key: 0 for key in self._SWEEP_COUNT_KEYS}
        totals["duration_ms"] = 0
        for index, mapping in enumerate(mappings):
            label = ReverseDeleter.mapping_label(mapping)
            self._task_checkpoint(phase="sweep-mapping", current_item=label,
                                  progress={"current": index, "total": len(mappings)},
                                  raise_if_cancelled=True)
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
        # 日志用的词和运行台、通知里那套一致：对着一条通知回查日志时不用再翻译一遍
        summary = (
            f"网盘删了 {totals['cloud_deleted']}，刮削文件 {totals['scrapes_deleted']}，"
            f"空文件夹 {totals['cloud_dirs_deleted']}，新入队 {totals['pending']}，"
            f"队列中等待 {totals['queued']}，网盘上没了 {totals['already_gone']}，"
            f"对不上网盘文件 {totals['unidentified']}，没删掉 {totals['errors']}，"
            f"耗时 {self._duration_text(totals['duration_ms'])}"
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
        """反向删除通知复用 STRM 通道 —— 删除是破坏性动作，只要动过就报一声。

        全篇不加装饰：删掉的是网盘上的真文件，读的人只想知道「删了什么、能不能找回来、
        还有什么等着我」。排版照那套语法走：清单 → 小计 → 下一步。

        地名一律叫「网盘」，不叫「云端」，也不在正文里叫「115」——「115」留给服务本身
        （115 授权、115 回收站），「网盘」是文件待着的那个地方。以前这三个词混着用，
        一条通知里能出现两个地名指同一处。

        数只在标题里报一次：标题说「删了 3 个网盘文件」，清单行就只说是哪条映射、
        凭什么删，不再重复那个 3。
        """
        if not any(self._sweep_entry_is_noteworthy(entry) for entry in entries):
            return
        if not self._notifier.is_enabled("strm"):
            return
        deleted = int(totals.get("cloud_deleted", 0))
        pending = int(totals.get("pending", 0))
        failed = int(totals.get("errors", 0))
        if failed:
            headline = f"网盘清理完成：{failed} 个失败"
        elif pending:
            headline = f"网盘清理待确认：{pending} 个文件"
        elif deleted:
            headline = f"网盘清理完成：删除 {deleted} 个文件"
        else:
            headline = "网盘清理完成：没有要删除的文件"

        # 出事的、等人的排前面：映射多到要折叠时，被折掉的必须是已经办完的那几条。
        # 只有一条映射时（真机上的常态）行里不带数：那个数标题刚说过，行里要说的是
        # 「哪条映射」，那才是标题没给的信息
        ranked = sorted(
            (row for row in (self._sweep_row(entry) for entry in entries) if row[1]),
            key=lambda item: item[0],
        )
        if len(ranked) == 1:
            single = self._sweep_row(
                next(entry for entry in entries if self._sweep_row(entry)[1]), terse=True
            )
            ranked = [single]
        lines = [row for _rank, row in ranked[: self.NOTIFY_ROW_LIMIT]]
        if len(ranked) > self.NOTIFY_ROW_LIMIT:
            lines.append(f"另外 {len(ranked) - self.NOTIFY_ROW_LIMIT} 条映射见插件运行台")
        # 标题被失败数占了的时候，「已经删掉几个」没别的地方报，补进小计
        if aside := self._sweep_aside_line(totals, deleted if failed else 0):
            lines.append(aside)

        # 末尾按「最该动手的排前面」：等人确认 → 需要跑一次同步 → 兜底那句「能还原」。
        # 回收站那句是安慰，不是待办，所以垫在最后
        tail: list[str] = []
        if pending:
            tail.append("一次要删这么多，先让你过一眼。去插件运行台确认了才真删")
        if int(totals.get("unidentified", 0)):
            tail.append(
                f"另有 {int(totals['unidentified'])} 条记录对不上网盘文件（旧版本留下的），"
                f"跑一次全量 STRM 同步就能补上"
            )
        if deleted:
            # 破坏性动作必须把「能不能找回来」说在通知里 —— 收到「删了 20 个文件」时，
            # 第一个念头就是这个。运行台里本来有这句话，通知里一直没有
            tail.append("本地 STRM 没了才会删，删掉的进 115 回收站，能还原")
        if tail:
            lines.append("")
            lines.extend(tail)
        self._notifier.notify(
            "strm",
            headline,
            lines or ["这次没有需要处理的"],
            link=self._plugin_console_link(),
            title_prefix="",
        )

    @classmethod
    def _sweep_row(cls, entry: Dict[str, Any], terse: bool = False) -> tuple[int, str]:
        """一条映射这一轮的结果：(排序权重, 行文本)；什么都没发生返回 (0, "")。

        一条映射可能既删了几个、又搁下一批等确认，这里只报最要紧的那一种 —— 一行里
        塞两个状态位，读的人得先分辨这行到底算成还是没成。

        行里报的是「这条映射怎么了」，不是「一共几个」：总数在标题里已经说过一次，
        映射只有一条时（真机上的常态）行里再写一遍就是复述标题。所以：
          ❌ 只说原因（数在标题里）
          ⏳ 说搁下了几个（多映射时各不相同，标题给的是总数）
          ✅ 说删了几个（同上）
        「凭什么删」是全局的同一句话，放在末尾那段，不在每行里各抄一遍。
        """
        failed = int(entry.get("errors") or 0)
        pending = int(entry.get("pending") or 0)
        deleted = int(entry.get("cloud_deleted") or 0)
        reason = cls._short_note(entry.get("reason"))
        if failed:
            # 只留原因：失败数已经在标题里，护栏原话截短后往往也只剩那个数
            return 1, cls._row("❌", entry.get("mapping"), reason or "没说原因")
        if pending or (reason and not deleted):
            note = "" if terse and pending else (f"{pending} 个先搁着没删" if pending else reason)
            return 2, cls._row("⏳", entry.get("mapping"), note)
        if deleted:
            return 3, cls._row("✅", entry.get("mapping"), "" if terse else f"删了 {deleted} 个")
        return 0, ""

    @staticmethod
    def _sweep_aside_line(totals: Dict[str, int], deleted: int = 0) -> str:
        """小计：跟着一起清掉的东西，必要时补上已经删掉的数目。

        刮削文件和空文件夹不是谁点名要删的，但它们确实在网盘上被删了 —— 破坏性动作必须
        把连带影响说出来，哪怕只占半行。
        ``deleted`` 由调用方在「标题被失败数占掉」时传进来：那种场合成功删掉的几个没有
        别的地方可报。
        """
        swept = [
            f"{int(totals.get('scrapes_deleted', 0))} 个刮削文件"
            if int(totals.get("scrapes_deleted", 0)) else "",
            f"{int(totals.get('cloud_dirs_deleted', 0))} 个空文件夹"
            if int(totals.get("cloud_dirs_deleted", 0)) else "",
        ]
        swept = [cell for cell in swept if cell]
        cells = [f"另外 {deleted} 个已经删了"] if deleted else []
        if swept:
            cells.append(f"连带清掉网盘上 {'、'.join(swept)}")
        return " · ".join(cells)

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
            items = pending_batch_items(batch)
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
                    "total_size": int(batch.get("total_size") or 0),
                    "items_truncated": bool(batch.get("items_truncated")),
                    "offset": page_offset,
                    "limit": page_limit,
                    "total": len(items),
                    "items": [
                        {
                            "path": str(item.get("path") or ""),
                            "cloud_path": str(item.get("cloud_path") or ""),
                            "name": str(item.get("name") or ""),
                            "size": int(item.get("size") or 0),
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
                "total_size": int(batch.get("total_size") or 0),
                "created_at": str(batch.get("created_at") or ""),
                "updated_at": str(batch.get("updated_at") or ""),
                "reason": str(batch.get("reason") or ""),
                "items_truncated": bool(batch.get("items_truncated")),
                "samples": [
                    str(item.get("path") or "")
                    for item in pending_batch_items(batch)[:20]
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
        """原子 claim 待删批次；token 是唯一所有权证明，checkpoint 只允许单调推进。"""
        batch_ids = self._requested_batch_ids(payload)
        if not batch_ids:
            return _error("缺少批次 ID")
        if error := self._sweep_start_error():
            return _error(error)
        claim_token = uuid.uuid4().hex
        with self._config_write_lock:
            batches = self._store.get_strm_delete_pending()
            claimed: list[Dict[str, Any]] = []
            now = datetime.now().isoformat(timespec="seconds")
            for batch_id in batch_ids:
                batch = batches.get(batch_id)
                if not isinstance(batch, dict):
                    continue
                # 新 claim 有 token，严格拒绝二次认领；旧版/崩溃遗留的无 token claimed
                # 允许从持久化 checkpoint 迁移接续。
                if batch.get("status") == "claimed" and batch.get("claim_token"):
                    continue
                items = pending_batch_items(batch)
                try:
                    declared_count = int(batch.get("count") or len(items))
                except (TypeError, ValueError):
                    continue
                if not items or declared_count != len(items):
                    continue
                checkpoint = batch.get("checkpoint")
                if not isinstance(checkpoint, dict):
                    checkpoint = {"page": 0, "offset": 0, "processed": 0}
                try:
                    completed = max(0, min(len(items), int(checkpoint.get("offset") or 0)))
                except (TypeError, ValueError):
                    continue
                batch["status"] = "claimed"
                batch["claim_token"] = claim_token
                batch["claim_owner"] = f"{threading.current_thread().name}:{threading.get_ident()}"
                batch["claimed_at"] = now
                batch["checkpoint"] = {
                    "page": completed // self._PENDING_PAGE_LIMIT,
                    "offset": completed,
                    "processed": completed,
                }
                batches[batch_id] = batch
                claimed.append(deepcopy(batch))
            if claimed:
                self._store.save_strm_delete_pending(batches)
        if not claimed:
            return _error("批次不存在、正在执行或确认明细不完整")
        jobs = []
        for batch in claimed:
            items = pending_batch_items(batch)
            offset = int((batch.get("checkpoint") or {}).get("offset") or 0)
            paths = [str(item.get("path") or "") for item in items[offset:] if item.get("path")]
            if paths:
                jobs.append((str(batch.get("id") or ""), str(batch.get("mapping_id") or ""), offset, paths, claim_token))
        if not jobs:
            self._restore_batches(claimed, claim_token=claim_token)
            return _error("批次没有可执行的明细，请等下一轮巡检重新统计")
        total = sum(len(job[3]) for job in jobs)
        result = self._start(
            "sweep", lambda: self._run_confirmed_delete_pages(jobs),
            f"已确认 {len(jobs)} 个批次，开始清理 {total} 个媒体对应的 115 文件",
        )
        if not result.get("success"):
            self._restore_batches(claimed, claim_token=claim_token)
        return result

    def _run_confirmed_delete_pages(
        self, jobs: list[tuple[str, str, int, list[str], str]],
    ) -> list[Dict[str, Any]]:
        entries: list[Dict[str, Any]] = []
        for batch_id, mapping_id, start_offset, paths, claim_token in jobs:
            try:
                for offset in range(0, len(paths), self._PENDING_PAGE_LIMIT):
                    self._task_checkpoint(phase="confirmed-delete", current_item=batch_id,
                                          progress=start_offset + offset, raise_if_cancelled=True)
                    page = paths[offset : offset + self._PENDING_PAGE_LIMIT]
                    page_entries = self.run_strm_sweep(page, bypass_confirm=True, mapping_id=mapping_id)
                    entries.extend(page_entries)
                    if any(int(entry.get("errors") or 0) > 0 or int(entry.get("unidentified") or 0) > 0
                           for entry in page_entries if isinstance(entry, dict)):
                        raise RuntimeError("确认删除页存在未完成条目，保留 checkpoint 等待重试")
                    self._checkpoint_strm_delete_batch(
                        batch_id, claim_token=claim_token,
                        page=((start_offset + offset) // self._PENDING_PAGE_LIMIT) + 1,
                        offset=start_offset + offset + len(page),
                    )
                self._complete_strm_delete_batch(batch_id, claim_token=claim_token)
            except Exception:
                self._release_strm_delete_batch(batch_id, claim_token=claim_token)
                raise
        return entries

    def _checkpoint_strm_delete_batch(self, batch_id: str, *, claim_token: str, page: int, offset: int) -> None:
        with self._config_write_lock:
            batches = self._store.get_strm_delete_pending()
            batch = batches.get(str(batch_id))
            if not isinstance(batch, dict) or batch.get("claim_token") != claim_token:
                return
            current = batch.get("checkpoint") if isinstance(batch.get("checkpoint"), dict) else {}
            current_offset = max(0, int(current.get("offset") or 0))
            if int(offset) < current_offset:
                return
            batch["checkpoint"] = {"page": int(page), "offset": int(offset), "processed": int(offset)}
            batch["updated_at"] = datetime.now().isoformat(timespec="seconds")
            batches[str(batch_id)] = batch
            self._store.save_strm_delete_pending(batches)

    def _complete_strm_delete_batch(self, batch_id: str, *, claim_token: str) -> None:
        with self._config_write_lock:
            batches = self._store.get_strm_delete_pending()
            batch = batches.get(str(batch_id))
            if isinstance(batch, dict) and batch.get("claim_token") == claim_token:
                batches.pop(str(batch_id), None)
                self._store.save_strm_delete_pending(batches)

    def _release_strm_delete_batch(self, batch_id: str, *, claim_token: str) -> None:
        with self._config_write_lock:
            batches = self._store.get_strm_delete_pending()
            batch = batches.get(str(batch_id))
            if not isinstance(batch, dict) or batch.get("claim_token") != claim_token:
                return
            batch["status"] = "pending"
            for key in ("claim_token", "claim_owner", "claimed_at"):
                batch.pop(key, None)
            batches[str(batch_id)] = batch
            self._store.save_strm_delete_pending(batches)

    def _restore_batches(self, taken: list[Dict[str, Any]], *, claim_token: str = "") -> None:
        with self._config_write_lock:
            batches = self._store.get_strm_delete_pending()
            for original in taken:
                batch_id = str(original.get("id") or "")
                current = batches.get(batch_id)
                if not isinstance(current, dict):
                    continue
                token = claim_token or str(original.get("claim_token") or "")
                if token and current.get("claim_token") != token:
                    continue
                current["status"] = "pending"
                for key in ("claim_token", "claim_owner", "claimed_at"):
                    current.pop(key, None)
                batches[batch_id] = current
            self._store.save_strm_delete_pending(batches)

    def dismiss_strm_delete(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """仅驳回尚未执行的批次；claimed/running 保持可见且拒绝误导文案。"""
        batch_ids = self._requested_batch_ids(payload)
        if not batch_ids:
            return _error("缺少批次 ID")
        dropped = 0
        blocked = 0
        with self._config_write_lock:
            batches = self._store.get_strm_delete_pending()
            for batch_id in batch_ids:
                batch = batches.get(batch_id)
                if not isinstance(batch, dict):
                    continue
                if batch.get("status") == "claimed" or batch.get("claim_token"):
                    blocked += 1
                    continue
                batches.pop(batch_id, None)
                dropped += 1
                logger.info(f"【STRM反向删除】用户驳回待确认批次 {batch_id}（尚未开始云端删除）")
            if dropped:
                self._store.save_strm_delete_pending(batches)
        if not dropped:
            if blocked:
                return _error("批次正在执行，不能驳回；云端删除可能已经开始")
            return _error("批次不存在或已处理")
        message = f"已忽略 {dropped} 个批次（均尚未执行）"
        if blocked:
            message += f"；另有 {blocked} 个正在执行，未移除"
        return _ok(message=message)

    # ── 上传身份冲突：记录说 A、远端躺着 B，让用户拍板 ─────────────────────
    #
    # 配置里的 ``upload_conflict_policy`` 管自动处理（adopt/reupload）；``ask``
    # 策略下冲突挂到这里，两个动作各自动一块：采用远端只改记录不碰网盘，
    # 重传覆盖先删远端（进回收站）再清记录。「先不管」只摘条目，下一轮增量
    # 还会发现，这不是 bug 是诚实的兜底。

    _CONFLICT_ACTION_LABELS = {"adopt": "采用远端", "reupload": "重传覆盖", "dismiss": "先不管"}

    def upload_conflicts(self) -> Dict[str, Any]:
        """待处理的上传身份冲突清单。"""
        conflicts = self._store.get_upload_conflicts()
        items = sorted(
            (item for item in conflicts.values() if isinstance(item, dict)),
            key=lambda item: str(item.get("first_seen") or ""),
        )
        return _ok(
            {
                "policy": str(self._store.get_config().get("upload_conflict_policy") or "ask"),
                "count": len(items),
                "items": [
                    {
                        "path": str(item.get("path") or ""),
                        "target": str(item.get("target") or ""),
                        "reason": str(item.get("reason") or ""),
                        "recorded_pickcode": str(item.get("recorded_pickcode") or ""),
                        "remote_pickcode": str(item.get("remote_pickcode") or ""),
                        "recorded_size": item.get("recorded_size"),
                        "first_seen": str(item.get("first_seen") or ""),
                        "last_seen": str(item.get("last_seen") or ""),
                    }
                    for item in items
                ],
            }
        )

    def resolve_upload_conflicts(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """处理清单里挂着的身份冲突。``action``: adopt | reupload | dismiss。"""
        payload = payload or {}
        action = str(payload.get("action") or "").strip()
        if action not in self._CONFLICT_ACTION_LABELS:
            return _error("未知的处理方式")
        paths = [
            str(value or "").strip()
            for value in (payload.get("paths") or [])
            if str(value or "").strip()
        ]
        if not paths:
            return _error("没有选择要处理的冲突")
        conflicts = self._store.get_upload_conflicts()
        records = self._store.get_upload_records()
        resolved: list[str] = []
        failed: list[Dict[str, str]] = []
        for path in paths:
            conflict = conflicts.get(path)
            if not isinstance(conflict, dict):
                failed.append({"path": path, "message": "冲突不存在或已处理"})
                continue
            target = str(conflict.get("target") or "")
            try:
                if action == "adopt":
                    if not records.get(Path(path)):
                        raise ValueError("上传记录不存在，无法采用远端")
                    remote_pickcode = str(conflict.get("remote_pickcode") or "")
                    if not remote_pickcode:
                        raise ValueError("冲突里没有远端 Pickcode，请用重传覆盖或等下一轮上传")
                    records.update_metadata(Path(path), {"pickcode": remote_pickcode})
                elif action == "reupload":
                    file_item = self._client_provider().get_item(target) or {}
                    file_id = str(file_item.get("fileid") or "")
                    if file_id:
                        self._client_provider().delete_file(file_id)
                    records.remove(Path(path))
                # dismiss 不需要任何动作：只把条目摘掉
            except Exception as err:  # noqa: BLE001
                failed.append({"path": path, "message": safe_error_text(err)})
                continue
            conflicts.pop(path, None)
            resolved.append(path)
        self._store.save_upload_records(records)
        self._store.save_upload_conflicts(conflicts)
        label = self._CONFLICT_ACTION_LABELS[action]
        if failed:
            return _ok(
                data={"resolved": resolved, "failed": failed},
                message=f"{label}完成 {len(resolved)} 个，{len(failed)} 个没成",
            )
        return _ok(
            data={"resolved": resolved, "failed": []},
            message=f"已按「{label}」处理 {len(resolved)} 个冲突",
        )

    # ── 已废弃的飞书卡片排版零件 ────────────────────────────────────────────
    #
    # 保留这些私有方法，避免旧测试或外部补丁导入断裂；正式通知统一走宿主 post_message。

    @staticmethod
    def _card_text(content: str, *, margin: str = "4px 16px 0px 16px", align: str = "") -> dict:
        element: dict = {"tag": "markdown", "content": content, "margin": margin}
        if align:
            element["text_align"] = align
        return element

    @staticmethod
    def _card_rule(margin: str = "8px 16px 4px 16px") -> dict:
        return {"tag": "hr", "margin": margin}

    @classmethod
    def _card_stats(cls, cells: list[tuple], *, margin: str = "8px 16px 0px 16px") -> dict:
        """一行读数：每格上面一个大数，下面一个灰色小标签。

        格数按传进来的算，不补空列 —— 三格里只放两个数，会让人以为第三格丢了。
        """
        return {
            "tag": "column_set",
            "flex_mode": "none",
            "margin": margin,
            "columns": [
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "elements": [
                        cls._card_text(f"**{value}**", margin="0px", align="center"),
                        cls._card_text(
                            f"<font color='grey'>{label}</font>", margin="0px", align="center"
                        ),
                    ],
                }
                for value, label in cells
            ],
        }

    @staticmethod
    def _card_close(elements: list[dict]) -> list[dict]:
        """给卡片最后一行补底部留白，收尾不至于贴着边。"""
        if elements:
            elements[-1] = {**elements[-1], "margin": "4px 16px 12px 16px"}
        return elements

    def _notify_strm(
        self,
        entries: list[Dict[str, Any]],
        totals: Dict[str, int],
        incremental: bool,
        manual: bool = False,
    ) -> None:
        """STRM 完成通知统一交给宿主；自动空跑保持静默。"""
        if not self._notifier.is_enabled("strm"):
            return
        quiet_remaining = self._strm_notify_quiet_until - monotonic()
        if quiet_remaining > 0:
            # 上传（开着“生成 STRM”）刚发过同一批入库的卡片，这里不再叠一张；
            # 独立于上传的 STRM 变化在窗口过后照常通知。
            logger.info(
                f"【STRM同步】入库已由上传通道通知，STRM 通知抑制 "
                f"{int(quiet_remaining / 60) + 1} 分钟内生效"
            )
            return
        changed = sum(
            int(totals.get(key) or 0) for key in ("added", "updated", "removed", "errors")
        )
        if not changed and not manual:
            return
        headline, lines = self._strm_text_notice(entries, totals, incremental)
        self._notifier.notify(
            "strm",
            headline,
            lines,
            link=self._plugin_console_link(),
            title_prefix="",
        )

    # 通知里最多逐行列几条映射，再多就折叠 —— 锁屏上看不完那么长
    NOTIFY_ROW_LIMIT = 8
    # 上传卡片发出后，STRM 同步的重复入库通知抑制多久。要盖过生活监控的事件
    # 防抖加一轮同步的时差，太短压不住，太长会吞掉真正独立的 STRM 动态。
    STRM_NOTIFY_QUIET_SECONDS = 30 * 60

    def _arm_strm_notify_suppression(self) -> None:
        """上传通道发出入库通知后，给 STRM 通道上一段静默窗。

        只在上传任务自己生成 STRM（``upload_generate_strm``）时才需要 —— 那种
        配置下两张卡说的是同一批入库。没开生成就各通知各的，STRM 卡是唯一一张。
        """
        if not self._store.get_config().get("upload_generate_strm"):
            return
        self._strm_notify_quiet_until = monotonic() + self.STRM_NOTIFY_QUIET_SECONDS

    # 附在行尾的原因截断到这么长
    NOTIFY_NOTE_LIMIT = 24
    # 短于这个长度的分句不算「说完了一句话」，截断时会接着往下取
    NOTE_MIN_CLAUSE = 4

    @classmethod
    def _short_note(cls, message: Any) -> str:
        """把一句原因压成能读完的话。

        底层抛上来的原话多是「结论，加一串通用建议」。通知里要的是结论，所以在第一个
        说得完整的分句处收住；分句短到不成话（「失败」这种）就接着往下取。
        """
        note = re.sub(r"\s+", " ", str(message or "").strip())
        if not note:
            return ""
        head = note[: cls.NOTIFY_NOTE_LIMIT]
        cut = next(
            (
                index
                for index, char in enumerate(head)
                if char in "，。；！？,;." and index >= cls.NOTE_MIN_CLAUSE
            ),
            -1,
        )
        if cut < 0:
            return note if len(note) <= cls.NOTIFY_NOTE_LIMIT else f"{head}…"
        return note[:cut] if cut == len(note) - 1 else f"{note[:cut]}…"

    @staticmethod
    def _strm_change_text(entry: Dict[str, Any]) -> str:
        """一条映射这次动了什么。用「新增 / 更新 / 清理」而不是 +~✕ —— 符号省地方，
        但通知是给人看一眼的，不该让人先猜图例。三个词和卡片上那排读数用的是同一套，
        同一件事在飞书和微信里不能有两个名字。"""
        failed = int(entry.get("errors") or 0)
        if failed:
            return f"{failed} 个没生成"
        parts = [
            f"{label} {int(entry.get(key) or 0)} 个"
            for key, label in (("added", "新增"), ("updated", "更新"), ("removed", "清理"))
            if int(entry.get(key) or 0)
        ]
        return "，".join(parts) if parts else "已经是最新的"

    @staticmethod
    def _row(mark: str, name: Any, note: str = "") -> str:
        """清单行的统一写法：状态位 + 名称 + 两个空格 + 发生了什么。

        行首那个状态位自己对齐成一列 —— 不拿空格填充，各家通知渠道字体宽度不同，空格
        对齐到手机上就散了。这套写法和签到插件那边逐字一致：两个插件的消息落在同一个
        通知列表里，读的人只该学一遍。
        """
        head = f"{mark} {name or '-'}"
        return f"{head}  {note}" if note else head

    @classmethod
    def _strm_row_line(cls, entry: Dict[str, Any]) -> str:
        """一条映射一行：✅/❌ 名称  这次动了什么 · 没成的原因。

        失败必须带原因：只报一个数字，人还得自己去翻日志。
        """
        failed = int(entry.get("errors") or 0)
        note = cls._strm_change_text(entry)
        if failed and (reason := cls._short_note(entry.get("message"))):
            note = f"{note} · {reason}"
        return cls._row("❌" if failed else "✅", entry.get("mapping"), note)

    def _strm_text_notice(
        self, entries: list[Dict[str, Any]], totals: Dict[str, int], incremental: bool,
    ) -> tuple:
        """STRM 同步的纯文本通知：标题报最该知道的那个数，正文一条映射一行。

        标题先说新增而不是新增 + 更新的和：新片子进来了几个才是消息，更新是维护。两个
        数放一起加成一个「生成 12 个」，反而谁都说不清。
        正文分两段：清单（一条映射一行）紧接小计（跳过和刮削文件），小计不带行首状态位，
        视觉上退出清单那一列。这一条不加落款 —— 同步是家务活，没什么值得庆祝的。
        """
        added = int(totals.get("added", 0))
        updated = int(totals.get("updated", 0))
        failed = int(totals.get("errors", 0))
        if failed:
            headline = f"STRM 同步完成：{failed} 个失败"
        elif added:
            headline = f"STRM 同步完成：新增 {added} 个"
        elif updated:
            headline = f"STRM 同步完成：更新 {updated} 个"
        else:
            headline = "STRM 已是最新"
        # 出错的映射排在前面：映射多到要折叠时，被折掉的必须是「都好」的那几条
        ordered = sorted(entries, key=lambda entry: not int(entry.get("errors") or 0))
        lines = [self._strm_row_line(entry) for entry in ordered[: self.NOTIFY_ROW_LIMIT]]
        if len(ordered) > self.NOTIFY_ROW_LIMIT:
            lines.append(f"另外 {len(ordered) - self.NOTIFY_ROW_LIMIT} 条映射见插件运行台")
        summary = (
            f"新增 {added} 个，更新 {updated} 个，清理 {int(totals.get('removed') or 0)} 个"
        )
        meta = (
            f"{'增量' if incremental else '全量'}同步，{len(entries)} 条映射，"
            f"耗时 {self._duration_text(totals.get('duration_ms'))}"
        )
        lines = [summary, meta, *([""] if ordered else []), *lines]
        if aside := self._strm_aside_line(totals, incremental):
            lines.append(aside)
        return headline, lines

    @staticmethod
    def _strm_aside_line(totals: Dict[str, int], incremental: bool) -> str:
        """小计：这一轮里不需要人操心的那些数。

        跳过和刮削文件平时没人看，出事的时候才会被翻出来核对，所以挤成一行读数，
        不和上面那几个主数字抢注意力。
        """
        cells: list[str] = []
        if skipped := int(totals.get("skipped", 0)):
            cells.append(f"跳过 {skipped} 个没变化的" if incremental else f"{skipped} 个已经是最新的")
        if sidecars := int(totals.get("sidecars", 0)):
            cells.append(f"顺带 {sidecars} 个刮削文件")
        return " · ".join(cells)

    # ── 库存带 ────────────────────────────────────────────────────────
    #
    # 一季有几集在 115 上，一眼看得出。和签到插件那条打卡带用的是同一套记号
    # （■ 有、□ 没有），换的只是单位：一个数天，一个数集。两个插件的消息落在同一个
    # 通知列表里，同一套图形让它们看起来出自同一只手。
    #
    # 固定十格，不按集数伸缩：一季 24 集就画 24 格，手机上直接折行。格数固定，长度才
    # 可预期；精确到第几集由后面那句读数负责 —— 图形报量级，文字报数目。
    SEASON_BAR_CELLS = 10

    @classmethod
    def _season_bar(cls, have: int, total: int) -> str:
        """库存带。总集数为 0（TMDB 没答上来）时返回空串，不画一条骗人的带子。

        只差一集也绝不画满：59/60 集按比例算正好是十格，图形说齐了、读数说没齐，眼睛
        第一时间信的是图形。
        """
        if total <= 0:
            return ""
        cells = cls.SEASON_BAR_CELLS
        filled = cells if have >= total else min(cells - 1, max(0, have) * cells // total)
        return "■" * filled + "□" * (cells - filled)

    @staticmethod
    def _season_episodes_map(se_text: Any) -> dict[int, set[int]]:
        """把 `第2季 第1-3、7集` 拆成 {2: {1, 2, 3, 7}}。"""
        result: dict[int, set[int]] = {}
        for part in str(se_text or "").split("，"):
            match = re.match(r"第(\d+)季\s*第([\d、\-]+)集", part.strip())
            if not match:
                continue
            episodes: set[int] = set()
            for segment in re.findall(r"\d+(?:-\d+)?", match.group(2)):
                if "-" in segment:
                    start, end = segment.split("-")
                    episodes.update(range(int(start), int(end) + 1))
                else:
                    episodes.add(int(segment))
            result[int(match.group(1))] = episodes
        return result

    @staticmethod
    def _season_ranges(se_text: Any) -> dict[int, str]:
        """把 `第2季 第1-10集` 拆成 {2: "第 1-10 集"}。

        数字两边留一个空格是这一仓的中文排版惯例（「近 7 天」「10 集齐了」都这么写）。
        只在显示时插空格，`_aggregate_seasons()` 的原格式不动 —— 那串文本还要被正则
        拆回季号和集号。
        """
        return {
            int(match.group(1)): f"第 {match.group(2)} 集"
            for match in (
                re.match(r"第(\d+)季\s*第([\d、\-]+)集", part.strip())
                for part in str(se_text or "").split("，")
            )
            if match
        }

    @classmethod
    def _season_lines(
        cls, se_text: Any, progress: dict[int, tuple[int, int]] | None = None,
    ) -> list[str]:
        """每季一行：第 N 季  库存带  读数。

        ``progress`` 是 {季号: (115 上已有集数, 该季总集数)}。TMDB 答不上来时退回集号
        范围那一行 —— 画不出满不满，就老实报有哪几集，不含糊过去。
        """
        ranges = cls._season_ranges(se_text)
        progress = progress or {}
        lines: list[str] = []
        for season in sorted(set(ranges) | set(progress)):
            have, total = progress.get(season, (0, 0))
            if bar := cls._season_bar(have, total):
                reading = f"{total} 集齐了" if have >= total else f"{total} 集里有 {have} 集"
                lines.append(f"第 {season} 季  {bar}  {reading}")
            elif text := ranges.get(season, ""):
                lines.append(f"第 {season} 季  {text}")
        return lines

    @staticmethod
    def _upload_haul_line(facts: Dict[str, Any]) -> str:
        """这次进了多少那一行。并列的读数用「·」隔开，读起来是一排读数而不是一句话。

        上面那几行库存带讲的是「现在 115 上有多少」，这一行讲的是「这一趟搬了多少」——
        两个数不是一回事，收到通知的人先想知道后者，因为那才是这条消息的由来。
        剧集论集、电影论文件：说「这次进了 4 集」比「4 个文件」贴近人怎么想这件事。
        秒传才值得单独说 —— 上传是默认动作，写「上传 6 个」和前面的「6 个」是同一个
        数字说两遍；秒传是「没真传、几秒就完事」，那是消息。
        """
        count = int(facts.get("count") or 0)
        instant = int(facts.get("instant") or 0)
        unit = "集" if facts.get("season_lines") else "个文件"
        cells = [f"这次进了 {count} {unit}", str(facts.get("size") or "-")]
        if instant and instant >= count:
            cells.append("全部秒传")
        elif instant:
            cells.append(f"其中 {instant} {unit}秒传")
        return " · ".join(cells)

    @classmethod
    def _upload_text_lines(cls, facts: Dict[str, Any]) -> list[str]:
        """上传通道的纯文本正文。

        顺序照「最想知道什么」排：这一季现在齐没齐 → 这次进了多少 → 放在哪。以前是一行
        挤七个「字段：值」，在手机上要横着读完才知道入库的是第几集。
        库存带自己占一段，和下面两行之间空一行 —— 它是这条通知里唯一的装饰，紧贴读数
        就成了表头。
        """
        lines: list[str] = [str(line) for line in (facts.get("season_lines") or [])]
        if lines:
            lines.append("")
        lines.append(cls._upload_haul_line(facts))
        placed = [f"存进「{facts.get('library') or '媒体库'}」"]
        if int(facts.get("strm") or 0):
            placed.append(f"生成 {int(facts['strm'])} 个 STRM")
        if int(facts.get("sidecars") or 0):
            placed.append(f"带上 {int(facts['sidecars'])} 个刮削文件")
        lines.append("，".join(placed))
        return lines

    @staticmethod
    def _duration_text(duration_ms: Any) -> str:
        """耗时读数。写「8.6 秒」而不是「8600ms」—— 通知是给人看的，毫秒是给日志看的。"""
        try:
            value = int(duration_ms or 0)
        except (TypeError, ValueError):
            return "-"
        if value <= 0:
            return "-"
        if value < 1000:
            return "不到 1 秒"
        seconds = value / 1000
        if seconds < 60:
            return f"{seconds:.1f} 秒"
        minutes, rest = divmod(int(seconds), 60)
        return f"{minutes} 分 {rest} 秒" if rest else f"{minutes} 分"

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

    def _season_progress(
        self,
        title: str,
        year: str,
        cloud_seasons: dict[int, set[int]],
    ) -> dict[int, tuple[int, int]]:
        """每季在网盘上有多少集、这一季一共该有多少集：{季号: (已有, 总数)}。

        走的还是以前那批 TMDB 请求，只是把「齐了没有」这个布尔换成两个数 —— 库存带要
        画出「差多少」，一个布尔画不出来。TMDB 查不到（没配 key、搜不到剧、季不存在）
        时总数记 0，调用方据此退回集号范围那一行。
        """
        if not cloud_seasons:
            return {}
        tv_id = self._tmdb_tv_id(title, year)
        if not tv_id:
            return {}
        progress: dict[int, tuple[int, int]] = {}
        for season, cloud_eps in cloud_seasons.items():
            total = self._tmdb_season_episodes(tv_id, season)
            # 交集而不是 len(cloud_eps)：网盘上偶尔躺着 TMDB 没登记的特别篇，
            # 拿它去凑数会让一季看起来比实际更齐
            have = len(cloud_eps & total) if total else len(cloud_eps)
            progress[season] = (have, len(total))
        return progress

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

    def run_upload(
        self,
        incremental: bool = True,
        moviepilot_url: str = "",
        mappings: Optional[list[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        return self._run_upload_impl(incremental, moviepilot_url, mappings, None)

    def run_upload_files(
        self,
        candidates: list[UploadCandidate],
        moviepilot_url: str = "",
    ) -> Dict[str, Any]:
        """只授权并执行候选精确归属的 mapping；任何 revision 歧义均 fail-closed。"""
        config = self._store.get_config()
        selected: list[Dict[str, Any]] = []
        selected_keys: set[tuple[str, str]] = set()
        configured = [item for item in config.get("upload_mappings") or [] if isinstance(item, dict)]
        for candidate in candidates:
            matches: list[Dict[str, Any]] = []
            for mapping in configured:
                if not mapping.get("enabled", True):
                    continue
                source_text = str(mapping.get("source") or "").strip()
                if not source_text:
                    continue
                try:
                    source_root = str(Path(source_text).expanduser().resolve())
                    revision = mapping_revision(mapping, config, canonical_source=source_root)
                except (OSError, RuntimeError, ValueError):
                    continue
                mapping_id = str(mapping.get("id") or source_root)
                if (
                    mapping_id == candidate.mapping_id
                    and source_root == candidate.source_root
                    and revision == candidate.mapping_revision
                ):
                    matches.append(mapping)
            if len(matches) != 1:
                message = f"上传候选映射缺失、已变更或不唯一：{candidate.file_path}"
                logger.error(f"【目录上传】{message}")
                return self._record_upload_candidate_failure(candidate, message)
            key = (candidate.mapping_id, candidate.source_root)
            if key not in selected_keys:
                selected_keys.add(key)
                selected.append(matches[0])
        return self._run_upload_impl(True, moviepilot_url, selected, candidates)

    def _record_upload_candidate_failure(
        self, candidate: UploadCandidate, message: str
    ) -> Dict[str, Any]:
        entry = {
            "kind": "upload",
            "time": datetime.now().isoformat(timespec="seconds"),
            "incremental": True,
            "errors": 1,
            "errors_detail": [{
                "path": candidate.file_path,
                "target": "",
                "message": message,
            }],
            "message": message,
        }
        self._store.append_history(entry)
        logger.warning(f"【目录上传】执行完成，失败 1：{message}")
        self._notify_upload(entry, True)
        return entry

    def _run_upload_impl(
        self,
        incremental: bool,
        moviepilot_url: str,
        mappings: Optional[list[Dict[str, Any]]],
        candidates: list[UploadCandidate] | None,
    ) -> Dict[str, Any]:
        """``mappings`` 给了就只传这些。DirectoryUploader 自己从 config 里读通道，
        所以收窄要落在传给它的那份 config 上。"""
        config = self._store.get_config()
        if mappings is not None:
            config = {**config, "upload_mappings": mappings}
        mappings = [mapping for mapping in config.get("upload_mappings") or [] if mapping.get("enabled", True)]
        logger.info(f"【目录上传】开始执行，模式：{'增量' if incremental else '全量'}，有效映射：{len(mappings)}")
        allowed_roots = self._local_roots(config)
        execution_mappings: list[Dict[str, Any]] = []
        authorization_errors: list[Dict[str, str]] = []
        for mapping in mappings:
            source = str(mapping.get("source") or "").strip()
            authorized_source = self._authorized_local_path(source, roots=allowed_roots)
            if authorized_source is None:
                authorization_errors.append(
                    {
                        "path": source,
                        "target": str(mapping.get("target") or ""),
                        "message": f"上传源目录不在本地目录 allowlist 内：{source or '-'}",
                    }
                )
                continue
            if not authorized_source.is_dir():
                authorization_errors.append(
                    {
                        "path": source,
                        "target": str(mapping.get("target") or ""),
                        "message": f"上传源目录不存在：{authorized_source}",
                    }
                )
                continue
            execution_mapping = deepcopy(mapping)
            execution_mapping["source"] = str(authorized_source)
            if config.get("upload_generate_strm"):
                strm_target = str(mapping.get("strm_target") or "").strip()
                if not strm_target:
                    authorization_errors.append(
                        {
                            "path": source,
                            "target": str(mapping.get("target") or ""),
                            "message": "上传完成生成 STRM 时，必须配置 STRM 输出目录",
                        }
                    )
                    continue
                authorized_strm_target = self._authorized_local_path(
                    strm_target,
                    roots=allowed_roots,
                )
                if authorized_strm_target is None:
                    authorization_errors.append(
                        {
                            "path": source,
                            "target": str(mapping.get("target") or ""),
                            "message": f"上传 STRM 输出目录不在本地目录 allowlist 内：{strm_target}",
                        }
                    )
                    continue
                execution_mapping["strm_target"] = str(authorized_strm_target)
            execution_mappings.append(execution_mapping)

        if authorization_errors:
            for error in authorization_errors:
                logger.error(f"【目录上传】映射授权失败：{error['message']}")
            entry = {
                "kind": "upload",
                "time": datetime.now().isoformat(timespec="seconds"),
                "incremental": incremental,
                "errors": len(authorization_errors),
                "errors_detail": authorization_errors[:20],
                "message": authorization_errors[0]["message"],
            }
        else:
            execution_config = {**config, "upload_mappings": execution_mappings}
            try:
                uploader = DirectoryUploader(
                    self._client_provider(),
                    self._store,
                    execution_config,
                    moviepilot_url or str(config.get("moviepilot_address") or ""),
                    poster_search=self._search_poster,
                    journal=self._strm_journal,
                    task_checkpoint=self._task_checkpoint,
                )
                entry = (
                    uploader.run_files(candidates, incremental=True)
                    if candidates is not None
                    else uploader.run(incremental)
                )
            except Exception as err:  # noqa: BLE001
                logger.error(f"【目录上传】执行失败：{safe_error_text(err)}")
                entry = {
                    "kind": "upload",
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "incremental": incremental,
                    "errors": 1,
                    "message": str(err),
                }
        self._browse_115_cache.clear()
        self._store.append_history(entry)
        summary = (
            f"上传 {int(entry.get('uploaded') or 0)}，秒传 {int(entry.get('instant') or 0)}，"
            f"生成 STRM {int(entry.get('strm_generated') or 0)}，"
            f"跳过 {int(entry.get('skipped') or 0)}，删除 {int(entry.get('deleted') or 0)}，"
            f"延后 {int(entry.get('deferred') or 0)}，"
            f"冲突 {int(entry.get('conflicts') or 0)}，"
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
        # 卡片确定要发了：开着“生成 STRM”的上传已经把同一批入库说完了，
        # 给 STRM 通道上一段静默窗，免得生活监控触发的同步再叠一张卡。
        self._arm_strm_notify_suppression()

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

            # 库存带：这一季在 115 上齐没齐。TMDB 不可用时 progress 为空，_season_lines()
            # 会退回集号范围那一行
            progress: dict[int, tuple[int, int]] = {}
            if has_meta and _se_text:
                first_meta = next((m for m in meta_list if m.get("title")), {})
                title_meta = str(first_meta.get("title") or "")
                if title_meta:
                    try:
                        cloud_records = self._store.get_upload_records().to_dict()
                    except Exception:  # noqa: BLE001
                        cloud_records = None
                    meta_for_cloud = [m for m in meta_list if m.get("title")]
                    progress = self._season_progress(
                        title_meta,
                        str(first_meta.get("year") or ""),
                        self._season_episodes_map(
                            self._aggregate_seasons(meta_for_cloud, cloud_records)
                        ),
                    )
            _season_lines = self._season_lines(_se_text, progress)

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

            episode_title = self._upload_episode_title(_se_text)
            headline = f"{title_key}{f' {episode_title}' if episode_title else ''} 已入库"
            facts = {
                "season_lines": _season_lines,
                "count": _count,
                "size": _size,
                "instant": int(_methods.get("instant") or 0),
                "library": _label_str,
                "strm": _strm,
                "sidecars": _sidecars,
            }
            self._notifier.notify(
                "upload",
                headline,
                self._upload_text_lines(facts),
                image=poster,
                link=self._organize_history_link(),
                title_prefix="",
            )
        # 汇总通知（有错误时补充）。标题已经报了失败数，正文只说标题装不下的：这一批
        # 里还有多少是好的，以及去哪儿看失败原因
        if errors:
            lines = ["失败的文件名和原因在插件运行台的记录里"]
            if per_file:
                lines.insert(0, f"同一批里另外 {len(per_file)} 个已经进库了")
            self._notifier.notify(
                "upload",
                f"{errors} 个文件没传上去",
                lines,
                link=self._plugin_console_link(),
                title_prefix="",
            )

    @staticmethod
    def _upload_episode_title(se_text: Any) -> str:
        """把聚合结果压成原生入库标题使用的 Sxx Exx-Eyy 形式。"""
        parts: list[str] = []
        for season_text in str(se_text or "").split("，"):
            match = re.match(r"第(\d+)季\s*第([\d、\-]+)集", season_text.strip())
            if not match:
                continue
            episode_text = match.group(2)
            ranges = re.findall(r"\d+(?:-\d+)?", episode_text)
            if not ranges:
                continue
            formatted_ranges: list[str] = []
            for segment in ranges:
                if "-" in segment:
                    start, end = segment.split("-", 1)
                    formatted_ranges.append(f"E{int(start):02d}-E{int(end):02d}")
                else:
                    formatted_ranges.append(f"E{int(segment):02d}")
            formatted = "、".join(formatted_ranges)
            parts.append(f"S{int(match.group(1)):02d} {formatted}")
        return " ".join(parts)

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
        """每日签到通知。

        标题把结论说完，正文只补标题装不下的那点东西 —— 通知自带到达时间，再写一行
        「时间：」是白占锁屏上的位置。
        """
        if not self._notifier.is_enabled("checkin"):
            return
        message = str(entry.get("message") or "").strip()
        if not success:
            self._notifier.notify(
                "checkin",
                "115 签到失败",
                [message or "115 没说原因，去插件运行台看这次的记录"],
                title_prefix="",
            )
            return
        points = int(entry.get("points_num") or 0)
        continuous = int(entry.get("continuous_day") or 0)
        if entry.get("already"):
            headline = "115 今日已签到"
        else:
            headline = "115 签到成功"
        # 连续 1 天也照写：真机上刚断签重来的那天正文只剩一句「签到已记录」，
        # 而标题已经说了「已签到，+1 积分」—— 那一行等于把同一句话说第二遍。
        # 「连续签到 1 天」反倒是新消息：连签断了，从今天重新数
        if points and not entry.get("already"):
            lines = [
                f"连续签到 {continuous} 天，获得 {points} 积分"
                if continuous >= 1
                else f"获得 {points} 积分"
            ]
        else:
            lines = [f"当前连续签到 {continuous} 天"] if continuous >= 1 else []
        # 115 的回执偶尔带活动提示之类的内容，和上面两句不重复时才附上
        if message and message not in {"签到成功", "今日已签到"} and message not in headline:
            lines.append(message)
        self._notifier.notify(
            "checkin",
            headline,
            lines or ["签到已记录"],
            title_prefix="",
        )

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

    def join_task_threads(self, timeout: float = 0.5) -> None:
        """插件停止时仅作有界 join，不等待 pacer 的完整休眠周期。"""
        deadline = monotonic() + max(0.0, float(timeout))
        with self._lock:
            threads = list(self._task_threads)
        for thread in threads:
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            if thread is not threading.current_thread():
                thread.join(timeout=remaining)

    def _task_checkpoint(
        self, *, phase: str | None = None, current_item: str | None = None,
        progress: Any = None, raise_if_cancelled: bool = False,
    ) -> bool:
        """更新当前 worker lease；取消只在调用方选择的安全检查点生效。"""
        kind = getattr(self._task_context, "kind", "")
        with self._lock:
            lease = self._task_leases.get(kind)
            if lease is None:
                return False
            lease["last_progress_at"] = time()
            if phase is not None:
                lease["phase"] = phase
            if current_item is not None:
                lease["current_item"] = current_item
            if progress is not None:
                lease["progress"] = progress
            cancelled = lease["cancel_event"].is_set()
        if cancelled and raise_if_cancelled:
            raise RuntimeError("任务已在安全检查点协作取消")
        return cancelled

    def cancel_task(self, payload: Dict[str, Any] | str | None = None) -> Dict[str, Any]:
        """请求协作取消；不强杀线程，也不跨线程释放锁。"""
        kind = str(payload.get("kind") or "") if isinstance(payload, dict) else str(payload or "")
        with self._lock:
            lease = self._task_leases.get(kind)
            if lease is None:
                return _error("任务不存在或已经结束")
            lease["cancel_event"].set()
            lease["last_progress_at"] = time()
        return _ok(message="已请求任务在下一个安全检查点停止")

    def _start(self, kind: str, target: Callable[[], Any], message: str) -> Dict[str, Any]:
        label = self._TASK_LABELS.get(kind, kind)
        cloud_lock_acquired = False
        started_at = time()
        cancel_event = threading.Event()
        holder = f"p115liteassistant-{kind}:{uuid.uuid4().hex[:8]}"
        with self._lock:
            if kind in self._running:
                logger.warning(f"【{label}】任务正在运行，忽略重复触发")
                return _error(f"{kind} 任务正在运行")
            if kind in self._CLOUD_TASK_KINDS:
                cloud_lock_acquired = self._cloud_task_lock.acquire(blocking=False)
                if not cloud_lock_acquired:
                    running = "/".join(self._TASK_LABELS.get(item, item)
                                       for item in sorted(self._running & self._CLOUD_TASK_KINDS))
                    detail = f"（{running}）" if running else ""
                    logger.warning(f"【{label}】115 数据任务正在运行{detail}，忽略本次触发")
                    return _error(f"115 数据任务正在运行{detail}，请稍后重试")
            self._running.add(kind)
            self._running_since[kind] = started_at
            self._task_leases[kind] = {
                "holder": holder, "started_at": started_at,
                "last_progress_at": started_at, "progress": None,
                "phase": "starting", "current_item": "", "cancel_event": cancel_event,
            }

        def run() -> None:
            recovery_failed = False
            self._task_context.kind = kind
            try:
                self._task_checkpoint(phase="recovery" if kind in self._CLOUD_TASK_KINDS else "running")
                if kind in self._CLOUD_TASK_KINDS:
                    self._recover_strm_commits(f"{label}任务启动")
                self._task_checkpoint(phase="running", raise_if_cancelled=True)
                target()
                self._task_checkpoint(phase="completed")
            except StrmRecoveryBlockedError as err:
                recovery_failed = True
                logger.error(f"【{label}】STRM journal 恢复失败，任务已阻断：{safe_error_text(err)}")
            except Exception as err:  # noqa: BLE001
                logger.error(f"【{label}】后台任务异常终止：{safe_error_text(err)}")
            finally:
                with self._lock:
                    self._running.discard(kind)
                    self._running_since.pop(kind, None)
                    self._task_leases.pop(kind, None)
                    self._task_threads.discard(threading.current_thread())
                self._task_context.kind = ""
                if cloud_lock_acquired:
                    self._cloud_task_lock.release()
                if not recovery_failed:
                    self._drain_pending_tasks(kind)

        thread = threading.Thread(target=run, name=holder, daemon=True)
        try:
            with self._lock:
                self._task_threads.add(thread)
            thread.start()
        except Exception as err:  # noqa: BLE001
            with self._lock:
                self._running.discard(kind)
                self._running_since.pop(kind, None)
                self._task_leases.pop(kind, None)
                self._task_threads.discard(thread)
            if cloud_lock_acquired:
                self._cloud_task_lock.release()
            logger.error(f"【{label}】任务启动失败：{safe_error_text(err)}")
            return _error(f"{kind} 任务启动失败")
        logger.info(f"【{label}】任务已提交")
        return _ok(message=message)
