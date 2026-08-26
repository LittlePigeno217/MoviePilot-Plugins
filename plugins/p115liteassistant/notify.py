from __future__ import annotations

import json
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

# 飞书 SDK 与 MoviePilot 通知配置（运行环境可用时导入；缺失不影响其它平台文本通知）
try:  # pragma: no cover
    import lark_oapi as _lark
    from lark_oapi.api.im.v1 import (
        CreateImageRequest as _CreateImageRequest,
        CreateImageRequestBody as _CreateImageRequestBody,
        CreateMessageRequest as _CreateMessageRequest,
        CreateMessageRequestBody as _CreateMessageRequestBody,
    )
    _LARK_OK = True
except Exception:  # noqa: BLE001  # pragma: no cover
    _lark = None  # type: ignore[assignment]
    _CreateImageRequest = None  # type: ignore[assignment]
    _CreateImageRequestBody = None  # type: ignore[assignment]
    _CreateMessageRequest = None  # type: ignore[assignment]
    _CreateMessageRequestBody = None  # type: ignore[assignment]
    _LARK_OK = False

try:  # pragma: no cover
    from app.runtime.extensions.service_config import ServiceConfigHelper
    from app.core.config import settings as _mp_settings
    _MP_HELPER_OK = True
except Exception:  # noqa: BLE001  # pragma: no cover
    ServiceConfigHelper = None  # type: ignore[assignment]
    _mp_settings = None  # type: ignore[assignment]
    _MP_HELPER_OK = False


DEFAULT_NOTIFY_TYPE = "Plugin"

# 资源入库通知类型（整理入库）。MoviePilot 的「通知模板 → 整理入库」模板
# 就是资源入库通知样式：STRM 通道 / 上传通道默认走这个模板，让入库类消息
# 与 MoviePilot 原生资源入库通知保持一致。
RESOURCE_NOTIFY_TYPE = "Organize"

# 可选的消息类型。MoviePilot 的通知渠道按类型分流，所以每条通道都能挑自己的类型。
# 以下均从 MoviePilot 的 MessageType 枚举**动态派生**（NotificationType 是其兼容别名），
# 保证与 MoviePilot 通知渠道 switchs 分流用的中文 value 永远一致，避免硬编码失步：
#   - NOTIFY_TYPE_NAMES         = 枚举成员名元组（英文，白名单）
#   - NOTIFY_TYPE_SWITCHS_NAMES = 枚举成员名 → value（中文，渠道 switchs 匹配用）
# MoviePilot 不可用（如单元测试/独立脚本）时回退到一份与当前版本一致的核对静态备份。
_NOTIFY_TYPE_BACKUP = {
    "Download": "资源下载",
    "Organize": "整理入库",
    "Subscribe": "订阅",
    "SiteMessage": "站点",
    "MediaServer": "媒体服务器",
    "Manual": "手动处理",
    "Plugin": "插件",
    "Agent": "智能体",
    "Other": "其它",
}


def _derive_notify_types() -> tuple[tuple[str, ...], dict[str, str]]:
    """从 MoviePilot MessageType 枚举派生类型列表与 switch 中文映射。

    NotificationType 是 MessageType 的兼容别名（见 manifest.py SymbolAlias），
    成员名即英文值，成员 value 即渠道 switchs 中文值。无法导入时返回静态备份。
    """
    src = NotificationType
    if src is None:
        names = tuple(_NOTIFY_TYPE_BACKUP)
        return names, dict(_NOTIFY_TYPE_BACKUP)
    try:
        names = tuple(member.name for member in src)
        mapping = {member.name: str(member.value) for member in src}
        if not mapping:
            raise RuntimeError("枚举为空")
        return names, mapping
    except Exception:  # noqa: BLE001
        names = tuple(_NOTIFY_TYPE_BACKUP)
        return names, dict(_NOTIFY_TYPE_BACKUP)


NOTIFY_TYPE_NAMES: tuple[str, ...]
NOTIFY_TYPE_SWITCHS_NAMES: dict[str, str]
NOTIFY_TYPE_NAMES, NOTIFY_TYPE_SWITCHS_NAMES = _derive_notify_types()

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

    def notify(self, channel: str, headline: str, lines: Iterable[Any], image: str = "") -> None:
        """发一条通道通知；通道未开启或宿主不可用时静默跳过。"""
        meta = CHANNELS.get(channel)
        if not meta or not self.is_enabled(channel):
            return
        body = self._compose(lines)
        # 上传通道标题：115 网盘・{媒体标题} 已入库（不带通道名）
        if channel == "upload":
            title = f"115 网盘・{headline}" if headline else "115 网盘"
        else:
            title = f"{self._title_prefix} · {meta['label']}"
            if headline:
                title = f"{title} {headline}"
        try:
            config = self._config_provider() or {}
            mtype = resolve_notify_type(config.get(meta["type_key"]))
            kwargs: Dict[str, Any] = {"title": title, "text": body}
            if mtype is not None:
                kwargs["mtype"] = mtype
            if image:
                kwargs["image"] = image
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

    # ---------- 飞书美化卡片（仅上传通道） ----------

    @staticmethod
    def _feishu_channels(mtype: str = "") -> list[dict]:
        """读取 MoviePilot 内置启用的飞书通知渠道，返回 [{app_id, app_secret, chat_id}]。

        mtype 传消息类型名（如 "Organize" / "Plugin"）时，只返回 switchs
        包含该类型对应中文名的渠道；不传则返回全部启用的飞书渠道。
        """
        raw_configs: Any = None
        try:  # 优先直接读数据库 systemconfig，不依赖启动期注入的 reader
            from app.db.oper.systemconfig import SystemConfigOper
            try:
                from app.schemas.types import SystemConfigKey
            except Exception:  # noqa: BLE001
                from app.runtime.enums import SystemConfigKey  # type: ignore[no-redef]  # pragma: no cover
            op = SystemConfigOper()
            key = getattr(SystemConfigKey, "Notifications", None)
            raw_configs = op.get(key.value if key else "Notifications")
        except Exception as err:  # noqa: BLE001
            Notifier._log_error(f"读取通知渠道配置失败：{safe_error_text(err)}")
            return []
        if not raw_configs and _MP_HELPER_OK and ServiceConfigHelper is not None:
            try:
                raw_configs = [
                    c.model_dump() if hasattr(c, "model_dump") else vars(c)
                    for c in ServiceConfigHelper.get_notification_configs()
                ]
            except Exception:  # noqa: BLE001
                raw_configs = None
        if not raw_configs:
            return []
        # mtype 对应渠道分流中文名
        switch_name = NOTIFY_TYPE_SWITCHS_NAMES.get(mtype, "") if mtype else ""
        channels: list[dict] = []
        seen: set[tuple] = set()
        for conf in raw_configs:
            if not isinstance(conf, dict):
                continue
            if conf.get("type") != "feishu" or not conf.get("enabled"):
                continue
            # 按消息类型分流：渠道的 switchs 必须包含对应中文名
            if switch_name:
                switchs = conf.get("switchs") or []
                if not any(str(s).strip() == switch_name for s in switchs):
                    continue
            cfg = conf.get("config") or {}
            app_id = str(cfg.get("FEISHU_APP_ID") or "").strip()
            app_secret = str(cfg.get("FEISHU_APP_SECRET") or "").strip()
            chat_id = str(cfg.get("FEISHU_CHAT_ID") or "").strip()
            if not app_id or not app_secret or not chat_id:
                continue
            key = (app_id, app_secret, chat_id)
            if key in seen:
                continue
            seen.add(key)
            channels.append(
                {"app_id": app_id, "app_secret": app_secret, "chat_id": chat_id}
            )
        return channels

    @staticmethod
    def _upload_feishu_image(
        client: Any, image_url: str,
    ) -> Optional[str]:
        """下载远端图片上传到飞书，返回 image_key；失败返回 None。"""
        if not image_url or _CreateImageRequest is None or _CreateImageRequestBody is None:
            return None
        try:
            import requests
            import tempfile
            from pathlib import Path as _Path
            resp = requests.get(image_url, timeout=10)
            if resp.status_code != 200:
                return None
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as fp:
                fp.write(resp.content)
                temp_path = _Path(fp.name)
            try:
                with temp_path.open("rb") as fp:
                    req = _CreateImageRequest.builder().request_body(
                        _CreateImageRequestBody.builder()
                        .image_type("message")
                        .image(fp)
                        .build()
                    ).build()
                    result = client.im.v1.image.create(req)
                return getattr(result.data, "image_key", None) if result.success() else None
            finally:
                temp_path.unlink(missing_ok=True)
        except Exception as err:  # noqa: BLE001
            Notifier._log_error(f"飞书海报上传失败：{safe_error_text(err)}")
            return None

    def send_upload_feishu_card(
        self,
        title: str,
        body_elements: list[dict],
        image_url: str = "",
        mtype: str = "",
    ) -> bool:
        """发送「115 网盘」美化卡片（schema 2.0 column_set 布局）。

        读取 MoviePilot 内置飞书渠道配置直发；任何异常返回 False 由调用方回退文本。
        mtype 传消息类型名（如 "Organize"）时只发送到该类型对应的渠道。
        """
        if not _LARK_OK or _lark is None or _CreateMessageRequest is None or _CreateMessageRequestBody is None:
            return False
        channels = self._feishu_channels(mtype)
        if not channels:
            return False
        sent_any = False
        for chan in channels:
            try:
                client = _lark.Client.builder() \
                    .app_id(chan["app_id"]) \
                    .app_secret(chan["app_secret"]) \
                    .build()
                image_key = self._upload_feishu_image(client, image_url)
                elements: list[dict] = []
                if image_key:
                    elements.append({
                        "tag": "img",
                        "img_key": image_key,
                        "alt": {"tag": "plain_text", "content": "海报"},
                        "mode": "fit_horizontal",
                    })
                elements.append({
                    "tag": "markdown",
                    "content": f"**{title}**",
                    "text_size": "heading",
                    "margin": "16px 16px 0px 16px",
                })
                elements.append({"tag": "hr", "margin": "8px 16px 4px 16px"})
                elements.extend(body_elements)
                card = {
                    "schema": "2.0",
                    "config": {
                        "wide_screen_mode": True,
                        "enable_forward": True,
                        "update_multi": True,
                        "summary": {"content": title or "115 网盘"},
                    },
                    "body": {
                        "direction": "vertical",
                        "padding": "0px 0px 0px 0px",
                        "elements": elements,
                    },
                }
                body = _CreateMessageRequestBody.builder() \
                    .receive_id(chan["chat_id"]) \
                    .msg_type("interactive") \
                    .content(json.dumps(card, ensure_ascii=False)) \
                    .build()
                req = _CreateMessageRequest.builder() \
                    .receive_id_type("chat_id") \
                    .request_body(body) \
                    .build()
                resp = client.im.v1.message.create(req)
                if resp.success():
                    sent_any = True
            except Exception as err:  # noqa: BLE001
                Notifier._log_error(f"飞书美化卡片发送失败：{safe_error_text(err)}")
        return sent_any
