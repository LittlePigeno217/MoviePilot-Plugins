from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional

from .log_utils import safe_error_text

try:  # 单元测试里没有 MoviePilot 运行时，缺了也要能导入
    from app.log import logger
except Exception:  # noqa: BLE001  # pragma: no cover
    logger = None  # type: ignore[assignment]

try:
    from app.schemas.types import NotificationType
except Exception:  # noqa: BLE001  # pragma: no cover
    NotificationType = None  # type: ignore[assignment]


DEFAULT_NOTIFY_TYPE = "Plugin"

# 资源入库通知类型（整理入库）。MoviePilot 的「通知模板 → 整理入库」模板
# 就是资源入库通知样式：STRM 通道 / 上传通道默认走这个模板，让入库类消息
# 与 MoviePilot 原生资源入库通知保持一致。
RESOURCE_NOTIFY_TYPE = "Organize"

# 可选的消息类型。MoviePilot 的通知渠道按类型分流，所以每条通道都能挑自己的类型，
# 比如签到发到「站点」，STRM 发到「插件」。名字对不上时统一退回 Plugin。
NOTIFY_TYPE_NAMES: tuple[str, ...] = (
    "Plugin",
    "Organize",
    "SiteMessage",
    "MediaServer",
    "Manual",
    "Other",
)

# 三条通道各自独立：键名、界面标签，互不共享开关。
CHANNELS: Dict[str, Dict[str, str]] = {
    "strm": {"enabled_key": "strm_notify", "type_key": "strm_notify_type", "label": "STRM 通道"},
    "upload": {"enabled_key": "upload_notify", "type_key": "upload_notify_type", "label": "上传通道"},
    "checkin": {"enabled_key": "checkin_notify", "type_key": "checkin_notify_type", "label": "每日签到"},
}


def normalize_notify_type(name: Any) -> str:
    """把界面传来的消息类型收敛到白名单内。"""
    candidate = str(name or "").strip()
    return candidate if candidate in NOTIFY_TYPE_NAMES else DEFAULT_NOTIFY_TYPE


def resolve_notify_type(name: Any) -> Any:
    """取 MoviePilot 的 NotificationType 枚举成员，运行时缺失时返回 None。"""
    if NotificationType is None:
        return None
    normalized = normalize_notify_type(name)
    return getattr(NotificationType, normalized, None) or getattr(NotificationType, "Plugin", None)


class Notifier:
    """按通道向 MoviePilot 发送执行结果通知。

    通知是附加动作，永远不能把任务本身搞挂：取配置、发消息的任何异常都在这里
    吞掉并记日志。
    """

    def __init__(
        self,
        config_provider: Callable[[], Dict[str, Any]],
        poster: Optional[Callable[..., Any]] = None,
        title_prefix: str = "115 轻量助手",
    ):
        self._config_provider = config_provider
        self._poster = poster
        self._title_prefix = title_prefix

    def bind(self, poster: Callable[..., Any]) -> None:
        """插件实例就绪后把 post_message 交进来。"""
        self._poster = poster

    def is_enabled(self, channel: str) -> bool:
        meta = CHANNELS.get(channel)
        if not meta or self._poster is None:
            return False
        try:
            config = self._config_provider() or {}
        except Exception as err:  # noqa: BLE001
            self._log_error(f"读取通知配置失败：{safe_error_text(err)}")
            return False
        return bool(config.get(meta["enabled_key"]))

    def notify(self, channel: str, headline: str, lines: Iterable[Any]) -> None:
        """发一条通道通知；通道未开启或宿主不可用时静默跳过。"""
        meta = CHANNELS.get(channel)
        if not meta or not self.is_enabled(channel):
            return
        body = self._compose(lines)
        title = f"{self._title_prefix} · {meta['label']}"
        if headline:
            title = f"{title} {headline}"
        try:
            config = self._config_provider() or {}
            mtype = resolve_notify_type(config.get(meta["type_key"]))
            kwargs: Dict[str, Any] = {"title": title, "text": body}
            if mtype is not None:
                kwargs["mtype"] = mtype
            self._poster(**kwargs)  # type: ignore[misc]
        except Exception as err:  # noqa: BLE001
            self._log_error(f"【{meta['label']}】发送通知失败：{safe_error_text(err)}")

    @staticmethod
    def _compose(lines: Iterable[Any]) -> str:
        kept: List[str] = []
        for line in lines or ():
            if line is None:
                continue
            text = str(line)
            if not text:
                if kept and kept[-1]:
                    kept.append("")
                continue
            kept.append(text.rstrip())
        # 去掉末尾空行
        while kept and not kept[-1]:
            kept.pop()
        return "\n".join(kept) or "-"

    @staticmethod
    def _log_error(message: str) -> None:
        if logger is not None:
            logger.error(message)
