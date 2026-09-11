from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from apscheduler.triggers.cron import CronTrigger
from app.core.event import Event, eventmanager
from app.log import logger
from app.plugins import _PluginBase
from app.scheduler import Scheduler
from app.schemas.types import EventType, NotificationType

from .api import Api
from .client import U115Client
from .life_monitor import LifeMonitor
from .log_utils import safe_error_text
from .notify import Notifier
from .store import Store
from .strm import CommitJournal, StrmRecoveryBlockedError
from .strm_watch import StrmDeleteWatcher
from .upload_watch import PendingUploadQueue, StabilityTracker, UploadWatcher, mapping_revision


class P115LiteAssistant(_PluginBase):
    plugin_name = "115 轻量助手"
    plugin_desc = "独立提供 115 登录、生活事件监控、STRM/302、目录上传秒传和签到；侧栏有一份媒体清单，一部电影一行、一季剧一行地管入库、做种与删除。"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/cloud.png"
    plugin_version = "1.3.2"
    plugin_author = "LittlePigeno"
    author_url = "https://github.com/LittlePigeno217"
    plugin_config_prefix = "p115liteassistant_"
    plugin_order = 52
    auth_level = 1

    def __init__(self):
        super().__init__()
        self._store = Store(self)
        self._client: Optional[U115Client] = None
        self._client_signature: Optional[Tuple[str, ...]] = None
        self._strm_journal = CommitJournal(
            self._store, self.get_data_path() / "strm-journal"
        )
        self._strm_recovery_blocked = False
        self._strm_recovery_alerted = False
        # 通知走宿主的 post_message，通道开关和消息类型都存在插件配置里
        self._notifier = Notifier(
            self._store.get_config,
            poster=self.post_message,
            title_prefix=self.plugin_name,
        )
        self._upload_queue = PendingUploadQueue()
        self._api = Api(
            self._get_client,
            self._store,
            on_config_saved=self._on_config_saved,
            life_monitor_status=self._is_life_monitor_running,
            notifier=self._notifier,
            strm_watch_status=self._is_strm_watch_running,
            recover_strm_commits=self._recover_strm_commits,
            journal=self._strm_journal,
            upload_queue=self._upload_queue,
        )
        self._life_monitor = LifeMonitor(
            self._get_client,
            self._store,
            self._api.cloud_task_lock,
            self._moviepilot_url,
            recent_deletes=self._api.recent_deletes,
            recover_strm_commits=self._recover_strm_commits,
            journal=self._strm_journal,
        )
        # 本地 STRM 删除的实时监听：只上报路径，删不删由反向删除巡检判定
        self._strm_watch = StrmDeleteWatcher(
            self._store.get_config,
            self._trigger_strm_sweep,
        )
        # 稳定性确认仅做本地 stat；稳定候选交给 API 的有界文件队列。
        self._upload_stability = StabilityTracker(
            self._store.get_config,
            self._api.queue_upload_file,
            full_rescan_callback=self._api.queue_upload,
        )
        self._api.set_upload_restabilizer(self._upload_stability.submit_path)
        self._upload_watch = UploadWatcher(
            self._store.get_config,
            self._upload_stability,
        )
        self._upload_watch_signature = self._upload_watch_config_signature(
            self._store.get_config()
        )

    def init_plugin(self, config: dict | None = None) -> None:
        if config:
            self._store.update_config(config)
        self._client = None
        self._client_signature = None
        with self._api.cloud_task_lock:
            try:
                self._recover_strm_commits("插件启动")
            except StrmRecoveryBlockedError:
                self._strm_recovery_blocked = True
                self._life_monitor.stop()
                self._strm_watch.stop()
                self._upload_watch.stop()
                tracker = getattr(self, "_upload_stability", None)
                if tracker is not None:
                    tracker.stop()
                return
            self._strm_recovery_blocked = False
        self._migrate_legacy_allowlist_on_startup()
        self._sync_life_monitor()
        self._sync_strm_watch()
        self._sync_upload_watch()
        self._upload_watch_signature = self._upload_watch_config_signature(
            self._store.get_config()
        )

    def _recover_strm_commits(self, stage: str) -> list[str]:
        """在云任务锁内恢复 journal；失败时告警并阻断输出任务。"""

        try:
            recovered = self._strm_journal.recover_all()
        except Exception as err:  # noqa: BLE001
            detail = safe_error_text(err)
            self._strm_recovery_blocked = True
            # 运行期恢复失败与启动期语义一致：立即停止所有会触碰输出的后台组件。
            # 之后只能由保存配置时的锁内恢复成功来清除阻断并重新启动。
            for component_name in ("_life_monitor", "_strm_watch", "_upload_watch", "_upload_stability"):
                component = getattr(self, component_name, None)
                if component is not None:
                    try:
                        component.stop()
                    except Exception as stop_err:  # noqa: BLE001
                        logger.error(
                            f"【STRM恢复】停止 {component_name} 失败："
                            f"{safe_error_text(stop_err)}"
                        )
            logger.error(f"【STRM恢复】{stage}失败，输出任务已阻断：{detail}")
            if not self._strm_recovery_alerted:
                delivered = False
                try:
                    self.post_message(
                        mtype=NotificationType.Plugin,
                        title=f"{self.plugin_name} · STRM 恢复失败",
                        text=(
                            f"阶段：{stage}\n原因：{detail}\n"
                            "STRM/上传/反向删除已停止"
                        ),
                    )
                    delivered = True
                except Exception as notify_err:  # noqa: BLE001
                    logger.error(
                        "【STRM恢复】发送系统告警失败："
                        f"{safe_error_text(notify_err)}"
                    )
                # 仅在宿主管道成功受理后去重；投递失败保留重试机会。
                if delivered:
                    self._strm_recovery_alerted = True
            raise StrmRecoveryBlockedError(detail) from err
        self._strm_recovery_alerted = False
        if recovered:
            logger.info(
                f"【STRM恢复】{stage}完成：{', '.join(recovered)}"
            )
        return recovered

    def _migrate_legacy_allowlist_on_startup(self) -> None:
        try:
            migrated, error = self._api.migrate_legacy_allowlist()
            if error:
                logger.error(f"【本地目录】启动迁移 allowlist 失败：{error}")
            elif migrated:
                logger.info("【本地目录】已从启用的旧映射自动迁移 allowlist")
        except Exception as err:  # noqa: BLE001
            logger.error(
                "【本地目录】启动迁移 allowlist 异常，将在下次启动重试："
                f"{safe_error_text(err)}"
            )

    def _moviepilot_url(self) -> str:
        return str(self._store.get_config().get("moviepilot_address") or "").strip().rstrip("/")

    def _is_life_monitor_running(self) -> bool:
        monitor = getattr(self, "_life_monitor", None)
        return bool(monitor and monitor.is_running)

    def _is_strm_watch_running(self) -> bool:
        watcher = getattr(self, "_strm_watch", None)
        return bool(watcher and watcher.is_running)

    def _trigger_strm_sweep(self, paths: Optional[List[str]] = None) -> Dict[str, Any]:
        """监听器的上报入口：走自动排队语义，抢不到 115 数据任务锁不算失败。"""
        return self._api.queue_strm_sweep(paths)

    def _on_config_saved(self) -> None:
        self._client = None
        self._client_signature = None
        recovered_from_block = getattr(self, "_strm_recovery_blocked", False)
        if recovered_from_block:
            with self._api.cloud_task_lock:
                try:
                    self._recover_strm_commits("保存配置")
                except StrmRecoveryBlockedError:
                    self._strm_recovery_blocked = True
                    self._life_monitor.stop()
                    self._strm_watch.stop()
                    self._upload_watch.stop()
                    tracker = getattr(self, "_upload_stability", None)
                    if tracker is not None:
                        tracker.stop()
                    return
                self._strm_recovery_blocked = False
        self._sync_life_monitor()
        self._sync_strm_watch()
        config = self._store.get_config()
        signature = self._upload_watch_config_signature(config)
        if (
            recovered_from_block
            or signature != getattr(self, "_upload_watch_signature", None)
        ):
            self._sync_upload_watch()
            self._upload_watch_signature = signature
        # cookie/token 等凭证变化不一定改变 watcher signature，但必须取消旧退避并补跑。
        wake_upload = getattr(self._api, "wake_pending_upload", None)
        if config.get("enabled") and callable(wake_upload):
            wake_upload()

    @staticmethod
    def _upload_watch_config_signature(config: Dict[str, Any]) -> tuple:
        """取全部会影响自动候选资格、路由与上传副作用的配置。"""
        mappings = []
        for mapping in config.get("upload_mappings") or []:
            if not isinstance(mapping, dict):
                continue
            try:
                revision = mapping_revision(mapping, config)
            except (OSError, RuntimeError, ValueError):
                revision = (str(mapping.get("source") or "").strip(),)
            mappings.append((str(mapping.get("id") or ""), revision))
        return bool(config.get("enabled")), tuple(sorted(mappings, key=repr))

    def _sync_life_monitor(self) -> None:
        if getattr(self, "_strm_recovery_blocked", False):
            self._life_monitor.stop()
            return
        config = self._store.get_config()
        mappings = [
            mapping
            for mapping in config.get("strm_mappings") or []
            if isinstance(mapping, dict) and mapping.get("enabled", True)
        ]
        if config.get("enabled") and config.get("life_monitor_enabled") and mappings:
            self._life_monitor.start()
        else:
            self._life_monitor.stop()

    def _sync_strm_watch(self) -> None:
        """按配置启停本地 STRM 实时监听。

        配置或目录变了就整体重建 —— 监听目录的增删改做增量 diff 收益不大、出错概率不小。
        """
        if getattr(self, "_strm_recovery_blocked", False):
            self._strm_watch.stop()
            return
        config = self._store.get_config()
        self._strm_watch.stop()
        if (
            config.get("enabled")
            and config.get("strm_delete_cloud_on_missing")
            and config.get("strm_delete_watch")
        ):
            self._strm_watch.start()

    def _sync_upload_watch(self) -> None:
        """同步启停 watcher/tracker，并清除配置重载后失效的文件候选。"""
        self._upload_watch.stop()
        tracker = getattr(self, "_upload_stability", None)
        if tracker is not None:
            tracker.stop()
        config = self._store.get_config()
        if tracker is not None:
            # 即使插件/映射刚被禁用也要清 tracker pending，不能等下一次 start。
            tracker.configure()
        valid: set[tuple[str, str, tuple]] = set()
        for mapping in config.get("upload_mappings") or []:
            if not isinstance(mapping, dict) or not mapping.get("enabled", True):
                continue
            source = str(mapping.get("source") or "").strip()
            if not source:
                continue
            try:
                root_path = Path(source).expanduser().resolve(strict=True)
                if not root_path.is_dir():
                    continue
                root = str(root_path)
                revision = mapping_revision(mapping, config, canonical_source=root)
            except (OSError, RuntimeError, ValueError):
                continue
            valid.add((str(mapping.get("id") or root), root, revision))
        clear_invalid = getattr(self._api, "clear_invalid_upload_candidates", None)
        if callable(clear_invalid):
            clear_invalid(valid)
        if getattr(self, "_strm_recovery_blocked", False):
            return
        if config.get("enabled") and valid:
            if tracker is not None:
                tracker.start()
            self._upload_watch.start()
            drain = getattr(self._api, "_drain_pending_upload", None)
            if callable(drain):
                drain()
        self._upload_watch_signature = self._upload_watch_config_signature(config)

    def _get_client(self) -> U115Client:
        config = self._store.get_config()
        client_type = str(config.get("login_client_type") or "")
        profile = str(config.get("rate_limit_profile") or "balanced").strip().lower()
        signature = (str(config.get("cookie") or ""), client_type, profile)
        if self._client is None or self._client_signature != signature:
            self._client = U115Client(
                cookie=signature[0],
                tokens=config.get("tokens") or {},
                client_type=signature[1],
                token_saver=self._save_client_tokens,
                rate_limit_profile=signature[2],
            )
            self._client_signature = signature
        return self._client

    def _save_client_tokens(self, tokens: Dict[str, Any]) -> None:
        self._store.update_config({"tokens": dict(tokens)})
        wake_upload = getattr(getattr(self, "_api", None), "wake_pending_upload", None)
        if callable(wake_upload):
            wake_upload()

    def get_state(self) -> bool:
        return bool(self._store.get_config().get("enabled"))

    @eventmanager.register(EventType.TransferComplete)
    def upload_after_transfer_complete(self, event: Event) -> None:
        """整理事件只在取得可靠本地文件路径时逐文件提交。"""
        if not event.event_data or not self._store.get_config().get("enabled"):
            return
        fileitem = event.event_data.get("fileitem")
        candidates = [
            event.event_data.get("target_path"),
            event.event_data.get("dest"),
        ]
        if isinstance(fileitem, dict):
            candidates.extend(fileitem.get(name) for name in ("target_path", "dest", "path"))
        elif fileitem is not None:
            candidates.extend(getattr(fileitem, name, None) for name in ("target_path", "dest", "path"))
        tried: set[str] = set()
        for value in candidates:
            path = str(value or "").strip()
            if not path or path in tried or not Path(path).is_absolute():
                continue
            tried.add(path)
            if self._upload_stability.submit_path(path, source="transfer"):
                logger.info(f"【目录上传】媒体整理完成，已提交单文件稳定性确认：{path}")
                return
        logger.debug("【目录上传】媒体整理完成事件没有可接受的可靠文件路径，跳过自动上传")

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_render_mode(self) -> Tuple[str, Optional[str]]:
        return "vue", "dist/assets"

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        config = self._store.get_config()
        config.pop("tokens", None)
        return None, config

    def get_page(self) -> Optional[List[dict]]:
        return []

    def get_sidebar_nav(self) -> List[Dict[str, Any]]:
        """侧栏全页入口。

        宿主只聚合「已启用 + vue 渲染」的插件（``app/core/plugin.py`` 的
        ``get_plugin_sidebar_nav``），所以插件停用时这一项会自己消失，不用另加判断。
        ``section`` 只认 start / discovery / subscribe / organize / system，
        ``permission`` 只认 subscribe / discovery / search / manage / admin。
        """
        return [
            {
                "nav_key": "main",
                "title": "115 轻量助手",
                "icon": "mdi-cloud-sync-outline",
                "section": "organize",
                "permission": "manage",
                "order": self.plugin_order,
            }
        ]

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {"path": "/config", "endpoint": self._api.get_config, "methods": ["GET"], "auth": "bear", "summary": "读取配置"},
            {"path": "/config", "endpoint": self._api.save_config, "methods": ["POST"], "auth": "bear", "summary": "保存配置"},
            {"path": "/qrcode", "endpoint": self._api.qrcode, "methods": ["POST"], "auth": "bear", "summary": "获取 115 登录二维码"},
            {"path": "/check-login", "endpoint": self._api.check_login, "methods": ["GET"], "auth": "bear", "summary": "检查 115 扫码状态"},
            {"path": "/browse-115", "endpoint": self._api.browse_115, "methods": ["GET"], "auth": "bear", "summary": "浏览 115 目录"},
            {"path": "/browse-local", "endpoint": self._api.browse_local, "methods": ["GET"], "auth": "bear", "summary": "浏览本地媒体库目录"},
            {"path": "/status", "endpoint": self._api.status, "methods": ["GET"], "auth": "bear", "summary": "获取运行状态"},
            {"path": "/task/cancel", "endpoint": self._api.cancel_task, "methods": ["POST"], "auth": "bear", "summary": "请求任务在安全检查点协作取消"},
            {"path": "/strm/sync", "endpoint": self._api.trigger_strm, "methods": ["POST"], "auth": "bear", "summary": "开始 STRM 同步"},
            {"path": "/strm/sweep", "endpoint": self._api.trigger_strm_sweep, "methods": ["POST"], "auth": "bear", "summary": "立即执行 STRM 反向删除"},
            {"path": "/strm/sweep/pending", "endpoint": self._api.strm_delete_pending, "methods": ["GET"], "auth": "bear", "summary": "读取待确认的反向删除批次"},
            {"path": "/strm/sweep/confirm", "endpoint": self._api.confirm_strm_delete, "methods": ["POST"], "auth": "bear", "summary": "确认执行一个反向删除批次"},
            {"path": "/strm/sweep/dismiss", "endpoint": self._api.dismiss_strm_delete, "methods": ["POST"], "auth": "bear", "summary": "驳回一个反向删除批次"},
            {"path": "/upload", "endpoint": self._api.trigger_upload, "methods": ["POST"], "auth": "bear", "summary": "开始目录上传"},
            {"path": "/upload/conflicts", "endpoint": self._api.upload_conflicts, "methods": ["GET"], "auth": "bear", "summary": "读取待处理的上传身份冲突"},
            {"path": "/upload/conflicts/resolve", "endpoint": self._api.resolve_upload_conflicts, "methods": ["POST"], "auth": "bear", "summary": "处理上传身份冲突"},
            {"path": "/checkin", "endpoint": self._api.run_checkin, "methods": ["POST"], "auth": "bear", "summary": "执行 115 签到"},
            {"path": "/test-notify", "endpoint": self._api.test_notify, "methods": ["POST"], "auth": "bear", "summary": "发送测试通知（走 MoviePilot 完整通知管道）"},
            {"path": "/history", "endpoint": self._api.history, "methods": ["GET"], "auth": "bear", "summary": "读取执行历史"},
            {"path": "/logs/tail", "endpoint": self._api.log_tail, "methods": ["GET"], "auth": "bear", "summary": "读插件日志尾部（任务台实时看）"},
            # 文件管理台：不建通道跑一次
            {"path": "/task/strm-once", "endpoint": self._api.task_strm_once, "methods": ["POST"], "auth": "bear", "summary": "给指定 115 目录生成一批 STRM"},
            {"path": "/task/gap-fill", "endpoint": self._api.task_gap_fill, "methods": ["POST"], "auth": "bear", "summary": "重新同步缺集媒体所属的 STRM 映射"},
            {"path": "/task/upload-once", "endpoint": self._api.task_upload_once, "methods": ["POST"], "auth": "bear", "summary": "把指定本地目录传到指定 115 目录"},
            # STRM 库体检
            {"path": "/ledger", "endpoint": self._api.media_ledger, "methods": ["GET"], "auth": "bear", "summary": "媒体清单（一部电影一行、一季剧一行）"},
            {"path": "/ledger/verify", "endpoint": self._api.ledger_verify, "methods": ["POST"], "auth": "bear", "summary": "核对网盘（按预算，撞限流即停）"},
            {"path": "/library/drop", "endpoint": self._api.library_drop, "methods": ["POST"], "auth": "bear", "summary": "删掉指定的本地 STRM 与记录"},
            {"path": "/source/drop", "endpoint": self._api.source_drop, "methods": ["POST"], "auth": "bear", "summary": "删掉指定的本地源文件（不可撤回）"},
            # 网盘管理
            {"path": "/disk/list", "endpoint": self._api.disk_list, "methods": ["GET"], "auth": "bear", "summary": "列 115 目录（含文件）"},
            {"path": "/disk/mkdir", "endpoint": self._api.disk_mkdir, "methods": ["POST"], "auth": "bear", "summary": "在 115 上新建目录"},
            {"path": "/disk/rename", "endpoint": self._api.disk_rename, "methods": ["POST"], "auth": "bear", "summary": "在 115 上改名"},
            {"path": "/disk/delete", "endpoint": self._api.disk_delete, "methods": ["POST"], "auth": "bear", "summary": "在 115 上删除（进回收站）"},
            {
                "path": "/redirect",
                "endpoint": self._api.redirect,
                "methods": ["GET", "POST", "HEAD"],
                # STRM 里的地址要交给播放器直接打开，带不了 MoviePilot 的 JWT，
                # 所以只能匿名。访问控制由逐文件 HMAC 签名 + 按来源 IP 限流承担。
                "allow_anonymous": True,
                "summary": "115 302 跳转",
            },
        ]

    _JOB_IDS = ("p115liteassistant_checkin", "p115liteassistant_strm_sweep")

    def get_service(self) -> List[Dict[str, Any]]:
        config = self._store.get_config()
        if not config.get("enabled"):
            return []
        services: List[Dict[str, Any]] = []
        if config.get("checkin_enabled"):
            try:
                services.append(
                    {
                        "id": "p115liteassistant_checkin",
                        "name": "115 轻量助手随机每日签到",
                        # 固定五分钟心跳，真正的签到时刻由 checkin_time_range 随机决定
                        "trigger": CronTrigger.from_crontab("*/5 * * * *"),
                        "func": self._api.run_scheduled_checkin,
                        "kwargs": {},
                    }
                )
            except Exception as err:  # noqa: BLE001
                logger.error(f"{self.plugin_name}: 签到定时任务注册失败: {err}")
        # 反向删除巡检：实时监听只是加速，真正兜底的是这条定时任务 ——
        # 容器重启、inotify 漏事件、网络挂载收不到通知都靠它补删。
        sweep_cron = str(config.get("strm_delete_sweep_cron") or "").strip()
        if config.get("strm_delete_cloud_on_missing") and sweep_cron:
            try:
                services.append(
                    {
                        "id": "p115liteassistant_strm_sweep",
                        "name": "115 轻量助手 STRM 反向删除巡检",
                        "trigger": CronTrigger.from_crontab(sweep_cron),
                        "func": self._api.run_scheduled_strm_sweep,
                        "kwargs": {},
                    }
                )
            except Exception as err:  # noqa: BLE001
                logger.error(f"{self.plugin_name}: 反向删除巡检定时任务注册失败: {err}")
        return services

    def stop_service(self) -> None:
        self._life_monitor.stop()
        self._strm_watch.stop()
        self._upload_watch.stop()
        self._upload_stability.stop()
        self._api.stop_upload_retry_scheduler(timeout=0.5)
        self._api.join_task_threads(timeout=0.5)
        for job_id in self._JOB_IDS:
            try:
                Scheduler().remove_plugin_job(job_id)
            except Exception:  # noqa: BLE001
                pass
        self._client = None
        self._client_signature = None
