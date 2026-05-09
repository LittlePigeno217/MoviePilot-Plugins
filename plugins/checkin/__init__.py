from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests import RequestException
from requests.exceptions import ConnectTimeout, ConnectionError as RequestsConnectionError, HTTPError, ReadTimeout
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.log import logger
from app.plugins import _PluginBase
from app.scheduler import Scheduler
from app.schemas import NotificationType


LEGACY_PLUGIN_CONFIG_PREFIX = "flztcheckin_"


class BaseSiteAdapter:
    site_key = ""
    site_name = ""
    mode = ""

    def __init__(self, plugin: "Checkin"):
        self.plugin = plugin

    def default_config(self) -> Dict[str, Any]:
        raise NotImplementedError

    def is_configured(self, site_config: Dict[str, Any]) -> bool:
        raise NotImplementedError

    def validate_config(self, site_config: Dict[str, Any]) -> List[str]:
        return []

    def get_account_label(self, site_config: Dict[str, Any]) -> str:
        return "-"

    def run_checkin(self, site_config: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def test_connection(self, site_config: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def build_error_result(self, message: str) -> Dict[str, Any]:
        return {
            "site": self.site_key,
            "site_name": self.site_name,
            "status": "执行失败",
            "message": message,
            "reward_mb": "-",
            "total_traffic": "-",
            "account": self.get_account_label({}),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


class FlztSiteAdapter(BaseSiteAdapter):
    site_key = "flzt"
    site_name = "FLZT"
    mode = "账号密码"
    base_url = "https://flzt.club"
    login_path = "/api/v1/passport/auth/login"
    checkin_path = "/api/v1/user/checkIn"

    def default_config(self) -> Dict[str, Any]:
        return {
            "enabled": False,
            "use_proxy": False,
            "email": "",
            "password": "",
        }

    def is_configured(self, site_config: Dict[str, Any]) -> bool:
        return bool(site_config.get("email") and site_config.get("password"))

    def validate_config(self, site_config: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        if not self.plugin._to_bool(site_config.get("enabled", False)):
            return errors
        if not site_config.get("email"):
            errors.append("FLZT 已启用但未填写邮箱")
        if not site_config.get("password"):
            errors.append("FLZT 已启用但未填写密码")
        return errors

    def get_account_label(self, site_config: Dict[str, Any]) -> str:
        return self.plugin._mask_email(site_config.get("email") or "")

    def _login(self, site_config: Dict[str, Any]) -> str:
        email = site_config.get("email") or ""
        password = site_config.get("password") or ""
        if not email or not password:
            raise ValueError("请先配置 FLZT 账号和密码")
        try:
            result = self.plugin._request_json(
                "POST",
                self.base_url,
                self.login_path,
                use_proxy=site_config.get("use_proxy", False),
                headers={**self.plugin._get_headers(), "Content-Type": "application/json"},
                json={"email": email, "password": password},
            )
        except Exception as err:
            raise RuntimeError(f"FLZT 登录请求失败：{err}") from err
        if result.get("status") != "success" or not ((result.get("data") or {}).get("auth_data")):
            raise RuntimeError(result.get("message") or "登录失败")
        return result["data"]["auth_data"]

    def _check_in(self, token: str, site_config: Dict[str, Any]) -> Dict[str, Any]:
        try:
            result = self.plugin._request_json(
                "GET",
                self.base_url,
                self.checkin_path,
                use_proxy=site_config.get("use_proxy", False),
                headers=self.plugin._get_headers(token),
                allow_400_json=True,
            )
        except Exception as err:
            raise RuntimeError(f"FLZT 签到请求失败：{err}") from err
        if result.get("status") not in {"success", "fail"}:
            raise RuntimeError(result.get("message") or "签到返回异常")
        return result

    def run_checkin(self, site_config: Dict[str, Any]) -> Dict[str, Any]:
        token = self._login(site_config)
        result = self._check_in(token, site_config)
        message = result.get("message") or ""
        data = result.get("data") or {}
        reward_mb = str(data.get("reward_mb") or data.get("reward") or "0")
        total_text = self.plugin._format_traffic(data.get("total_checkin_traffic"))

        if result.get("status") == "success":
            status_text = "签到成功"
        elif self.plugin._is_already_checked_in(message):
            status_text = "今日已签到"
        else:
            raise RuntimeError(message or "签到失败")

        return {
            "site": self.site_key,
            "site_name": self.site_name,
            "status": status_text,
            "message": message or status_text,
            "reward_mb": reward_mb,
            "total_traffic": total_text,
            "account": self.get_account_label(site_config),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def test_connection(self, site_config: Dict[str, Any]) -> Dict[str, Any]:
        token = self._login(site_config)
        return {
            "site": self.site_key,
            "site_name": self.site_name,
            "message": f"登录测试成功，Token 预览：{token[:24]}..." if len(token) > 24 else "登录测试成功",
        }


class RightForumSiteAdapter(BaseSiteAdapter):
    site_key = "right_forum"
    site_name = "恩山无线论坛"
    mode = "Cookie"
    base_url = "https://www.right.com.cn/forum"
    sign_page = "/erling_qd-sign_in.html"
    sign_action = "/plugin.php?id=erling_qd:action&action=sign"
    forum_page = "/forum.php"

    def default_config(self) -> Dict[str, Any]:
        return {
            "enabled": False,
            "use_proxy": False,
            "cookie": "",
        }

    def is_configured(self, site_config: Dict[str, Any]) -> bool:
        return bool(site_config.get("cookie"))

    def validate_config(self, site_config: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        if not self.plugin._to_bool(site_config.get("enabled", False)):
            return errors
        cookie = (site_config.get("cookie") or "").strip()
        if not cookie:
            errors.append("恩山无线论坛已启用但未填写 Cookie")
            return errors
        if len(cookie) < 20:
            errors.append("恩山无线论坛 Cookie 长度过短，请粘贴完整浏览器 Cookie")
        if "=" not in cookie or ";" not in cookie:
            errors.append("恩山无线论坛 Cookie 格式异常，应类似 key=value; key2=value2")
        required_tokens = ["auth", "saltkey", "sid"]
        if not any(token in cookie.lower() for token in required_tokens):
            errors.append("恩山无线论坛 Cookie 缺少常见登录字段，可能不是登录后的完整 Cookie")
        return errors

    def get_account_label(self, site_config: Dict[str, Any]) -> str:
        return "已配置 Cookie" if site_config.get("cookie") else "-"

    def _headers(self, cookie: str, referer: Optional[str] = None, ajax: bool = False) -> Dict[str, str]:
        headers = {
            "User-Agent": self.plugin.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Cookie": cookie,
        }
        if referer:
            headers["Referer"] = referer
        if ajax:
            headers["X-Requested-With"] = "XMLHttpRequest"
        return headers

    def _fetch_sign_page(self, cookie: str, site_config: Dict[str, Any]) -> Tuple[str, str]:
        referer = f"{self.base_url}{self.sign_page}"
        text = self.plugin._request_text(
            "GET",
            self.base_url,
            self.sign_page,
            use_proxy=site_config.get("use_proxy", False),
            headers=self._headers(cookie, referer=referer),
        )
        if "请先登录" in text or "您需要登录后才能使用签到功能" in text or ("立即登录" in text and "签到功能" in text):
            raise RuntimeError("右键论坛 Cookie 无效或已过期，请重新从浏览器复制")
        if "安全验证" in text or "滑块" in text:
            raise RuntimeError("右键论坛触发安全验证，请在浏览器中重新完成验证后更新 Cookie")

        formhash = self.plugin._extract_formhash(text)
        if not formhash:
            forum_text = self.plugin._request_text(
                "GET",
                self.base_url,
                self.forum_page,
                use_proxy=site_config.get("use_proxy", False),
                headers=self._headers(cookie, referer=referer),
            )
            formhash = self.plugin._extract_formhash(forum_text)
        if not formhash:
            raise RuntimeError("未能获取右键论坛 formhash，请检查 Cookie 是否有效")
        return formhash, text

    def _evaluate_response(self, text: str) -> Dict[str, str]:
        message = self.plugin._extract_dialog_message(text) or self.plugin._clean_text(text)[:120]
        lower_text = (text or "").lower()
        if any(keyword in text for keyword in ["今日已签", "今天已签", "已经签到", "您今天已经签到过了"]) or self.plugin._is_already_checked_in(message):
            return {"status": "今日已签到", "message": message or "今日已签到"}
        if any(keyword in text for keyword in ["签到成功", "恭喜", "奖励", "获得", "签到完成"]):
            return {"status": "签到成功", "message": message or "签到成功"}
        if "安全验证" in text or "滑块" in text:
            raise RuntimeError("右键论坛触发安全验证，请在浏览器中重新完成验证后更新 Cookie")
        if "未登录" in text or "请先登录" in text or ("cookie" in lower_text and "失效" in text):
            raise RuntimeError("右键论坛 Cookie 无效或已过期，请重新复制")
        raise RuntimeError(message or "右键论坛签到失败")

    def run_checkin(self, site_config: Dict[str, Any]) -> Dict[str, Any]:
        cookie = (site_config.get("cookie") or "").strip()
        if not cookie:
            raise ValueError("请先配置右键论坛 Cookie")

        sign_page_url = f"{self.base_url}{self.sign_page}"
        formhash, _ = self._fetch_sign_page(cookie, site_config)
        candidate_requests = [
            {"path": self.sign_action, "data": {"formhash": formhash}},
            {
                "path": self.sign_page,
                "data": {
                    "formhash": formhash,
                    "submit": "立即签到",
                    "mod": "plugin",
                    "id": "erling_qd:sign_in",
                },
            },
            {
                "path": self.sign_page,
                "data": {
                    "formhash": formhash,
                    "operation": "qiandao",
                    "submit": "立即签到",
                },
            },
        ]

        last_error: Optional[Exception] = None
        for candidate in candidate_requests:
            try:
                text = self.plugin._request_text(
                    "POST",
                    self.base_url,
                    candidate["path"],
                    use_proxy=site_config.get("use_proxy", False),
                    headers=self._headers(cookie, referer=sign_page_url, ajax=True),
                    data=candidate["data"],
                )
                evaluation = self._evaluate_response(text)
                return {
                    "site": self.site_key,
                    "site_name": self.site_name,
                    "status": evaluation["status"],
                    "message": evaluation["message"],
                    "reward_mb": "-",
                    "total_traffic": "-",
                    "account": "Cookie 登录态",
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            except Exception as err:
                last_error = err
        raise RuntimeError(str(last_error) if last_error else "右键论坛签到失败")

    def test_connection(self, site_config: Dict[str, Any]) -> Dict[str, Any]:
        cookie = (site_config.get("cookie") or "").strip()
        if not cookie:
            raise ValueError("请先配置右键论坛 Cookie")
        formhash, _ = self._fetch_sign_page(cookie, site_config)
        return {
            "site": self.site_key,
            "site_name": self.site_name,
            "message": f"Cookie 校验成功，formhash：{formhash}",
        }


class Checkin(_PluginBase):
    plugin_name = "自用签到工具"
    plugin_desc = "用于自用站点签到的统一工具，支持自动登录、Cookie 签到、通知与历史记录。"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/signin.png"
    plugin_version = "1.2.0"
    plugin_author = "LittlePigeno"
    author_url = "https://github.com/jxxghp/MoviePilot-Plugins"
    plugin_config_prefix = "checkin_"
    plugin_order = 36
    auth_level = 1

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    _enabled: bool = False
    _notify: bool = True
    _cron: str = "10 8 * * *"
    _timeout: int = 10
    _retry_count: int = 3
    _last_status: str = "未执行"
    _sites: Dict[str, Dict[str, Any]] = {}
    _adapters: Dict[str, BaseSiteAdapter] = {}

    def __init__(self):
        super().__init__()
        self._adapters = {
            FlztSiteAdapter.site_key: FlztSiteAdapter(self),
            RightForumSiteAdapter.site_key: RightForumSiteAdapter(self),
        }

    @staticmethod
    def _to_bool(val: Any) -> bool:
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.strip().lower() in {"1", "true", "yes", "on"}
        return bool(val)

    @staticmethod
    def _to_int(val: Any, default: int) -> int:
        try:
            return int(val)
        except Exception:
            return default

    @staticmethod
    def _mask_email(email: str) -> str:
        if not email or "@" not in email:
            return email or "-"
        name, domain = email.split("@", 1)
        if len(name) <= 2:
            masked = "*" * len(name)
        else:
            masked = f"{name[0]}{'*' * max(len(name) - 2, 1)}{name[-1]}"
        return f"{masked}@{domain}"

    @staticmethod
    def _is_already_checked_in(message: str) -> bool:
        text = (message or "").strip().lower()
        return (
            "already checked in" in text
            or "已签到" in text
            or "今日已签" in text
            or "今天已签" in text
        )

    @staticmethod
    def _clean_text(text: str) -> str:
        cleaned = re.sub(r"<[^>]+>", " ", text or "")
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    @staticmethod
    def _extract_formhash(text: str) -> Optional[str]:
        if not text:
            return None
        match = re.search(r'name="formhash"\s+value="([^"]+)"', text)
        if match:
            return match.group(1)
        match = re.search(r"formhash=([0-9a-zA-Z]+)", text)
        return match.group(1) if match else None

    @staticmethod
    def _extract_dialog_message(text: str) -> str:
        if not text:
            return ""
        for pattern in [
            r"showDialog\('([^']+)'",
            r'data-message="([^"]+)"',
            r"<div[^>]*class=\"alert_error\"[^>]*>(.*?)</div>",
            r"<div[^>]*class=\"alert_info\"[^>]*>(.*?)</div>",
        ]:
            match = re.search(pattern, text, re.S)
            if match:
                return Checkin._clean_text(match.group(1))
        return ""

    @staticmethod
    def _format_traffic(total_bytes: Any) -> str:
        try:
            value = float(total_bytes or 0)
        except Exception:
            return "0.00 GB"
        return f"{value / 1024 / 1024 / 1024:.2f} GB"

    def _get_site_meta(self) -> Dict[str, Dict[str, str]]:
        return {
            key: {"name": adapter.site_name, "mode": adapter.mode}
            for key, adapter in self._adapters.items()
        }

    def _default_sites_config(self) -> Dict[str, Dict[str, Any]]:
        return {key: adapter.default_config() for key, adapter in self._adapters.items()}

    def _normalize_sites_config(self, config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        sites = self._default_sites_config()
        incoming_sites = config.get("sites") or {}
        legacy_use_proxy = self._to_bool(config.get("use_proxy", False))

        for key, defaults in sites.items():
            site_payload = incoming_sites.get(key) or {}
            merged = {**defaults, **site_payload}
            merged["enabled"] = self._to_bool(merged.get("enabled", False))
            merged["use_proxy"] = self._to_bool(merged.get("use_proxy", legacy_use_proxy))
            for field, value in list(merged.items()):
                if field not in {"enabled", "use_proxy"} and isinstance(value, str):
                    merged[field] = value.strip()
            sites[key] = merged

        if not incoming_sites and "flzt" in sites:
            sites["flzt"]["email"] = (config.get("email") or sites["flzt"].get("email") or "").strip()
            sites["flzt"]["password"] = config.get("password") or sites["flzt"].get("password") or ""

        return sites

    def _validate_sites_config(self, sites_config: Dict[str, Dict[str, Any]]) -> List[str]:
        errors: List[str] = []
        for site_key, site_config in sites_config.items():
            adapter = self._adapters.get(site_key)
            if adapter:
                errors.extend(adapter.validate_config(site_config))
        return errors

    def init_plugin(self, config: dict = None):
        config = config or {}
        self._migrate_legacy_config_prefix()
        self.stop_service()
        self._enabled = self._to_bool(config.get("enabled", False))
        self._notify = self._to_bool(config.get("notify", True))
        self._cron = (config.get("cron") or "10 8 * * *").strip()
        self._timeout = max(5, self._to_int(config.get("timeout"), 10))
        self._retry_count = max(1, self._to_int(config.get("retry_count"), 3))
        self._sites = self._normalize_sites_config(config)
        self._last_status = self.get_data("last_status") or "未执行"
        logger.info(
            f"{self.plugin_name}: 初始化完成 enabled={self._enabled}, cron={self._cron}, sites={list(self._sites.keys())}"
        )

    def _migrate_legacy_config_prefix(self):
        try:
            if getattr(self, "plugin_config_prefix", None) == LEGACY_PLUGIN_CONFIG_PREFIX:
                return
            if hasattr(self, "systemconfig") and self.systemconfig:
                legacy_keys = [
                    key for key in list(self.systemconfig.keys())
                    if isinstance(key, str) and key.startswith(LEGACY_PLUGIN_CONFIG_PREFIX)
                ]
                for legacy_key in legacy_keys:
                    new_key = legacy_key.replace(LEGACY_PLUGIN_CONFIG_PREFIX, self.plugin_config_prefix, 1)
                    if new_key not in self.systemconfig:
                        self.systemconfig[new_key] = self.systemconfig.get(legacy_key)
        except Exception as err:
            logger.warning(f"{self.plugin_name}: 迁移旧配置前缀失败: {err}")

    def get_state(self) -> bool:
        return bool(self._enabled)

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_render_mode(self) -> Tuple[str, Optional[str]]:
        return "vue", "dist/assets"

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        return None, self._get_config()

    def get_page(self) -> List[dict]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {"path": "/config", "endpoint": self._get_config, "methods": ["GET"], "auth": "bear", "summary": "获取插件配置"},
            {"path": "/config", "endpoint": self._save_config, "methods": ["POST"], "auth": "bear", "summary": "保存插件配置"},
            {"path": "/status", "endpoint": self._get_status, "methods": ["GET"], "auth": "bear", "summary": "获取插件状态"},
            {"path": "/run", "endpoint": self._run_once_api, "methods": ["POST"], "auth": "bear", "summary": "立即执行签到"},
            {"path": "/test-login", "endpoint": self._test_login_api, "methods": ["POST"], "auth": "bear", "summary": "测试站点连通性"},
            {"path": "/history", "endpoint": self._get_history, "methods": ["GET"], "auth": "bear", "summary": "获取签到历史"},
            {"path": "/history/clear", "endpoint": self._clear_history, "methods": ["POST"], "auth": "bear", "summary": "清空签到历史"},
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        if not self._enabled or not self._cron:
            return []
        try:
            return [{
                "id": self.__class__.__name__.lower(),
                "name": self.plugin_name,
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self._scheduled_run,
                "kwargs": {},
            }]
        except Exception as err:
            logger.error(f"{self.plugin_name}: 注册定时任务失败: {err}")
            return []

    def stop_service(self):
        try:
            Scheduler().remove_plugin_job(self.__class__.__name__.lower())
        except Exception:
            pass

    def _is_site_configured(self, site_key: str, site_config: Optional[Dict[str, Any]] = None) -> bool:
        adapter = self._adapters.get(site_key)
        cfg = site_config or self._sites.get(site_key) or {}
        return adapter.is_configured(cfg) if adapter else False

    def _get_config(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "notify": self._notify,
            "cron": self._cron or "",
            "timeout": self._timeout,
            "retry_count": self._retry_count,
            "sites": self._sites,
        }

    def _save_config(self, config_payload: dict = None) -> Dict[str, Any]:
        config_payload = config_payload or {}
        normalized_sites = self._normalize_sites_config(config_payload)
        validation_errors = self._validate_sites_config(normalized_sites)
        if validation_errors:
            return {"success": False, "message": "；".join(validation_errors), "data": {"sites": normalized_sites}}

        self._enabled = self._to_bool(config_payload.get("enabled", self._enabled))
        self._notify = self._to_bool(config_payload.get("notify", self._notify))
        self._cron = (config_payload.get("cron") or self._cron or "10 8 * * *").strip()
        self._timeout = max(5, self._to_int(config_payload.get("timeout", self._timeout), self._timeout))
        self._retry_count = max(1, self._to_int(config_payload.get("retry_count", self._retry_count), self._retry_count))
        self._sites = normalized_sites

        new_config = {
            "enabled": self._enabled,
            "notify": self._notify,
            "cron": self._cron,
            "timeout": self._timeout,
            "retry_count": self._retry_count,
            "sites": self._sites,
        }
        self.update_config(new_config)
        self.init_plugin(new_config)
        return {"success": True, "message": "配置已保存", "data": self._get_config()}

    def _build_site_status(self, site_key: str, site_config: Dict[str, Any], site_last_results: Dict[str, Any]) -> Dict[str, Any]:
        adapter = self._adapters.get(site_key)
        last_result = site_last_results.get(site_key) or {}
        return {
            "key": site_key,
            "name": adapter.site_name if adapter else site_key,
            "mode": adapter.mode if adapter else "未知",
            "enabled": self._to_bool(site_config.get("enabled", False)),
            "use_proxy": self._to_bool(site_config.get("use_proxy", False)),
            "configured": self._is_site_configured(site_key, site_config),
            "account": adapter.get_account_label(site_config) if adapter else "-",
            "last_status": last_result.get("status") or "未执行",
            "last_message": last_result.get("message") or "-",
            "last_run": last_result.get("time") or "-",
        }

    def _get_status(self) -> Dict[str, Any]:
        history = self._normalize_history()
        last_result = self.get_data("last_result") or {}
        site_last_results = self.get_data("site_last_results") or {}
        next_run_time = "未配置定时任务"
        task_status = "未启用"

        if self._enabled and self._cron:
            try:
                task_status = "未找到任务"
                next_run_time = f"按配置执行: {self._cron}"
                for task in Scheduler().list():
                    if task.provider == self.plugin_name:
                        task_status = getattr(task, "status", "未知")
                        next_run = getattr(task, "next_run", None)
                        if next_run:
                            next_run_time = next_run if isinstance(next_run, str) else str(next_run)
                            if isinstance(next_run_time, str) and re.match(r'^(\d+小时)?(\d+分钟)?(\d+秒)?$', next_run_time):
                                next_run_time += "后"
                        elif task_status == "正在运行":
                            next_run_time = "正在运行中"
                        else:
                            next_run_time = "等待执行"
                        break
            except Exception as err:
                logger.warning(f"{self.plugin_name}: 获取定时任务状态失败: {err}")
                task_status = "获取失败"

        site_statuses = [self._build_site_status(key, cfg, site_last_results) for key, cfg in self._sites.items()]
        enabled_sites = [item for item in site_statuses if item.get("enabled")]
        configured_site_count = len([item for item in enabled_sites if item.get("configured")])

        return {
            "success": True,
            "data": {
                "enabled": self._enabled,
                "notify": self._notify,
                "cron": self._cron,
                "configured": bool(enabled_sites) and configured_site_count == len(enabled_sites),
                "enabled_site_count": len(enabled_sites),
                "configured_site_count": configured_site_count,
                "last_status": self.get_data("last_status") or self._last_status,
                "last_run": self.get_data("last_run"),
                "last_result": last_result,
                "sites": site_statuses,
                "history": history,
                "history_count": len(history),
                "next_run_time": next_run_time,
                "task_status": task_status,
            },
        }

    def _get_headers(self, token: Optional[str] = None) -> Dict[str, str]:
        headers = {"User-Agent": self.USER_AGENT, "Accept": "application/json, text/plain, */*"}
        if token:
            headers["authorization"] = token
        return headers

    def _get_proxies(self, use_proxy: Optional[bool] = None) -> Optional[dict]:
        return settings.PROXY if self._to_bool(use_proxy) else None

    def _format_request_error(self, err: Exception, use_proxy: Optional[bool] = None) -> str:
        proxy_text = "已启用代理" if self._to_bool(use_proxy) else "未启用代理"
        if isinstance(err, ConnectTimeout):
            return f"连接超时（{proxy_text}），请检查站点连通性或适当增大超时设置"
        if isinstance(err, ReadTimeout):
            return f"响应超时（{proxy_text}），站点返回过慢，请稍后重试或增大超时设置"
        if isinstance(err, RequestsConnectionError):
            detail = str(err)
            if "10054" in detail or "Connection reset" in detail or "Connection aborted" in detail:
                return f"连接被远端重置（{proxy_text}），可能触发风控、网络不稳定或代理异常"
            return f"连接失败（{proxy_text}）：{detail}"
        if isinstance(err, HTTPError):
            response = getattr(err, "response", None)
            status_code = getattr(response, "status_code", None)
            if status_code == 400:
                return "请求参数无效或账号密码错误"
            if status_code == 401:
                return "认证失败，请检查账号、密码或登录态"
            if status_code == 403:
                return "访问被拒绝，可能触发站点风控"
            if status_code == 429:
                return "请求过于频繁，站点已限流，请稍后再试"
            if status_code:
                return f"站点返回 HTTP {status_code}"
        return str(err) or "请求失败"

    def _request_json(self, method: str, base_url: str, path: str, use_proxy: Optional[bool] = None, allow_400_json: bool = False, **kwargs) -> Dict[str, Any]:
        url = f"{base_url}{path}"
        last_error: Optional[Exception] = None
        for attempt in range(1, self._retry_count + 1):
            try:
                response = requests.request(method=method, url=url, timeout=self._timeout, proxies=self._get_proxies(use_proxy), **kwargs)
                if allow_400_json and response.status_code == 400:
                    return response.json()
                response.raise_for_status()
                return response.json()
            except HTTPError as err:
                last_error = err
                status_code = getattr(getattr(err, "response", None), "status_code", None)
                logger.warning(f"{self.plugin_name}: 请求失败 {url}，重试 {attempt}/{self._retry_count}: {err}")
                if status_code == 400:
                    break
            except RequestException as err:
                last_error = err
                logger.warning(f"{self.plugin_name}: 请求失败 {url}，重试 {attempt}/{self._retry_count}: {err}")
            except Exception as err:
                last_error = err
                logger.warning(f"{self.plugin_name}: 请求失败 {url}，重试 {attempt}/{self._retry_count}: {err}")
            if attempt < self._retry_count:
                time.sleep(min(2 ** (attempt - 1), 4))
        raise RuntimeError(self._format_request_error(last_error, use_proxy) if last_error else "请求失败")

    def _request_text(self, method: str, base_url: str, path: str, use_proxy: Optional[bool] = None, **kwargs) -> str:
        url = f"{base_url}{path}"
        last_error: Optional[Exception] = None
        for attempt in range(1, self._retry_count + 1):
            try:
                response = requests.request(method=method, url=url, timeout=self._timeout, proxies=self._get_proxies(use_proxy), **kwargs)
                response.raise_for_status()
                response.encoding = response.apparent_encoding or response.encoding or "utf-8"
                return response.text
            except HTTPError as err:
                last_error = err
                logger.warning(f"{self.plugin_name}: 请求失败 {url}，重试 {attempt}/{self._retry_count}: {err}")
            except RequestException as err:
                last_error = err
                logger.warning(f"{self.plugin_name}: 请求失败 {url}，重试 {attempt}/{self._retry_count}: {err}")
            except Exception as err:
                last_error = err
                logger.warning(f"{self.plugin_name}: 请求失败 {url}，重试 {attempt}/{self._retry_count}: {err}")
            if attempt < self._retry_count:
                time.sleep(min(2 ** (attempt - 1), 4))
        raise RuntimeError(self._format_request_error(last_error, use_proxy) if last_error else "请求失败")

    def _normalize_history_detail(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "site": item.get("site") or "-",
            "site_name": item.get("site_name") or item.get("site") or "-",
            "status": item.get("status") or "未执行",
            "message": item.get("message") or "-",
            "account": item.get("account") or "-",
            "reward_mb": item.get("reward_mb") or "-",
            "total_traffic": item.get("total_traffic") or "-",
            "time": item.get("time") or "-",
        }

    def _build_history_entry(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        details = [self._normalize_history_detail(item) for item in (summary.get("details") or [])]
        success_count = summary.get("success_count")
        failure_count = summary.get("failure_count")
        if success_count is None or failure_count is None:
            success_count = len([item for item in details if item.get("status") in {"签到成功", "今日已签到"}])
            failure_count = max(len(details) - success_count, 0)
        return {
            "version": 2,
            "time": summary.get("time") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": summary.get("status") or "未执行",
            "message": summary.get("message") or "-",
            "success_count": int(success_count or 0),
            "failure_count": int(failure_count or 0),
            "site_count": len(details),
            "details": details,
        }

    def _normalize_history(self, history: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        records = history if history is not None else (self.get_data("history") or [])
        normalized: List[Dict[str, Any]] = []
        for item in records or []:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("details"), list):
                normalized.append(self._build_history_entry(item))
                continue
            detail = self._normalize_history_detail(item)
            normalized.append({
                "version": 1,
                "time": detail.get("time") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": detail.get("status") or "未执行",
                "message": detail.get("message") or "-",
                "success_count": 1 if detail.get("status") in {"签到成功", "今日已签到"} else 0,
                "failure_count": 0 if detail.get("status") in {"签到成功", "今日已签到"} else 1,
                "site_count": 1,
                "details": [detail],
            })
        return normalized[:50]

    def _append_history(self, summary: Dict[str, Any]) -> None:
        history = self._normalize_history()
        history = [self._build_history_entry(summary)] + history
        self.save_data("history", history[:50])

    def _notify_summary(self, summary: Dict[str, Any]) -> None:
        if not self._notify:
            return
        details = summary.get("details") or []
        detail_text = "\n".join([f"{item.get('site_name', item.get('site', '-'))}：{item.get('status', '-')}（{item.get('message', '-')}）" for item in details])
        self.post_message(
            mtype=NotificationType.Plugin,
            title=f"{self.plugin_name} - {summary.get('status', '执行完成')}",
            text=(f"结果：{summary.get('message', '-') }\n" f"时间：{summary.get('time', '-') }\n" f"详情：\n{detail_text or '-'}"),
        )

    def _run_checkin(self) -> Dict[str, Any]:
        enabled_sites = [(site_key, site_config) for site_key, site_config in self._sites.items() if self._to_bool(site_config.get("enabled", False))]
        if not enabled_sites:
            raise RuntimeError("请先启用至少一个签到站点")

        site_last_results = self.get_data("site_last_results") or {}
        results: List[Dict[str, Any]] = []
        success_count = 0
        failure_count = 0

        for site_key, site_config in enabled_sites:
            adapter = self._adapters.get(site_key)
            try:
                if not adapter:
                    raise RuntimeError(f"未找到站点适配器：{site_key}")
                validation_errors = adapter.validate_config(site_config)
                if validation_errors:
                    raise RuntimeError("；".join(validation_errors))
                if not adapter.is_configured(site_config):
                    raise RuntimeError("站点已启用但配置不完整")
                result = adapter.run_checkin(site_config)
                success_count += 1
            except Exception as err:
                failure_count += 1
                result = adapter.build_error_result(str(err)) if adapter else {
                    "site": site_key,
                    "site_name": site_key,
                    "status": "执行失败",
                    "message": str(err),
                    "reward_mb": "-",
                    "total_traffic": "-",
                    "account": "-",
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                logger.error(f"{self.plugin_name}: {result.get('site_name', site_key)} 执行失败: {err}")
            results.append(result)
            site_last_results[site_key] = result

        total_count = len(enabled_sites)
        if failure_count == 0:
            status_text = "全部成功"
            summary_message = f"已完成 {total_count} 个站点签到"
        elif success_count == 0:
            status_text = "执行失败"
            summary_message = f"{total_count} 个站点全部执行失败"
        else:
            status_text = "部分成功"
            summary_message = f"成功 {success_count} 个，失败 {failure_count} 个"

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        summary = {
            "status": status_text,
            "message": summary_message,
            "reward_mb": "-",
            "total_traffic": "-",
            "time": now,
            "details": results,
            "success_count": success_count,
            "failure_count": failure_count,
        }

        self._last_status = status_text
        self.save_data("last_status", self._last_status)
        self.save_data("last_result", summary)
        self.save_data("last_run", now)
        self.save_data("site_last_results", site_last_results)
        self._append_history(summary)
        self._notify_summary(summary)
        return summary

    def _scheduled_run(self) -> None:
        try:
            logger.info(f"{self.plugin_name}: 开始执行定时签到")
            self._run_checkin()
        except Exception as err:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            error_result = {"status": "执行失败", "message": str(err), "reward_mb": "-", "total_traffic": "-", "time": now, "details": []}
            self._last_status = "执行失败"
            self.save_data("last_status", self._last_status)
            self.save_data("last_result", error_result)
            self.save_data("last_run", now)
            self._append_history(error_result)
            logger.error(f"{self.plugin_name}: 定时签到失败: {err}")
            self._notify_summary(error_result)

    def _run_once_api(self) -> Dict[str, Any]:
        try:
            result = self._run_checkin()
            success = result.get("failure_count", 0) == 0 or result.get("success_count", 0) > 0
            return {"success": success, "message": result.get("message") or result.get("status"), "data": result}
        except Exception as err:
            logger.error(f"{self.plugin_name}: 手动签到失败: {err}")
            return {"success": False, "message": str(err)}

    def _test_login_api(self) -> Dict[str, Any]:
        enabled_sites = [(site_key, site_config) for site_key, site_config in self._sites.items() if self._to_bool(site_config.get("enabled", False))]
        if not enabled_sites:
            return {"success": False, "message": "请先启用至少一个站点"}

        messages: List[str] = []
        failed = False
        details: List[Dict[str, Any]] = []
        for site_key, site_config in enabled_sites:
            adapter = self._adapters.get(site_key)
            try:
                if not adapter:
                    raise RuntimeError(f"未找到站点适配器：{site_key}")
                validation_errors = adapter.validate_config(site_config)
                if validation_errors:
                    raise RuntimeError("；".join(validation_errors))
                if not adapter.is_configured(site_config):
                    raise RuntimeError("站点已启用但配置不完整")
                result = adapter.test_connection(site_config)
                details.append(result)
                messages.append(f"{result.get('site_name')}: {result.get('message')}")
            except Exception as err:
                failed = True
                site_name = adapter.site_name if adapter else site_key
                messages.append(f"{site_name}: {err}")

        return {"success": not failed, "message": "；".join(messages) if messages else "测试完成", "data": details}

    def _get_history(self) -> Dict[str, Any]:
        history = self._normalize_history()
        return {"success": True, "data": history}

    def _clear_history(self) -> Dict[str, Any]:
        self.save_data("history", [])
        return {"success": True, "message": "历史记录已清空", "data": []}