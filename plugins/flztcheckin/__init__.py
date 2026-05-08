from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests
from apscheduler.triggers.cron import CronTrigger

from app.log import logger
from app.core.config import settings
from app.plugins import _PluginBase
from app.scheduler import Scheduler
from app.schemas import NotificationType


class FlztCheckin(_PluginBase):
    plugin_name = "Vue-FLZT自动签到"
    plugin_desc = "为 FLZT 提供自动登录、签到、通知与历史记录能力。"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/signin.png"
    plugin_version = "1.0.0"
    plugin_author = "LittlePigeno"
    author_url = "https://github.com/jxxghp/MoviePilot-Plugins"
    plugin_config_prefix = "flztcheckin_"
    plugin_order = 36
    auth_level = 1

    BASE_URL = "https://flzt.org"
    LOGIN_PATH = "/api/v1/passport/auth/login"
    CHECKIN_PATH = "/api/v1/user/checkIn"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    _enabled: bool = False
    _notify: bool = True
    _use_proxy: bool = False
    _cron: str = "10 8 * * *"
    _email: str = ""
    _password: str = ""
    _timeout: int = 10
    _retry_count: int = 3
    _last_status: str = "未执行"

    def __init__(self):
        super().__init__()

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
        return "already checked in" in text or "已签到" in text

    def init_plugin(self, config: dict = None):
        config = config or {}
        self.stop_service()
        self._enabled = self._to_bool(config.get("enabled", False))
        self._notify = self._to_bool(config.get("notify", True))
        self._use_proxy = self._to_bool(config.get("use_proxy", False))
        self._cron = (config.get("cron") or "10 8 * * *").strip()
        self._email = (config.get("email") or "").strip()
        self._password = config.get("password") or ""
        self._timeout = max(5, self._to_int(config.get("timeout"), 10))
        self._retry_count = max(1, self._to_int(config.get("retry_count"), 3))
        self._last_status = self.get_data("last_status") or "未执行"
        logger.info(
            f"{self.plugin_name}: 初始化完成 enabled={self._enabled}, cron={self._cron}, notify={self._notify}"
        )

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
            {
                "path": "/config",
                "endpoint": self._get_config,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取插件配置",
            },
            {
                "path": "/config",
                "endpoint": self._save_config,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "保存插件配置",
            },
            {
                "path": "/status",
                "endpoint": self._get_status,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取插件状态",
            },
            {
                "path": "/run",
                "endpoint": self._run_once_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "立即执行签到",
            },
            {
                "path": "/test-login",
                "endpoint": self._test_login_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "测试登录",
            },
            {
                "path": "/history",
                "endpoint": self._get_history,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取签到历史",
            },
            {
                "path": "/history/clear",
                "endpoint": self._clear_history,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "清空签到历史",
            },
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        if not self._enabled or not self._cron:
            return []
        try:
            return [
                {
                    "id": self.__class__.__name__.lower(),
                    "name": "FLZT自动签到",
                    "trigger": CronTrigger.from_crontab(self._cron),
                    "func": self._scheduled_run,
                    "kwargs": {},
                }
            ]
        except Exception as err:
            logger.error(f"{self.plugin_name}: 注册定时任务失败: {err}")
            return []

    def stop_service(self):
        try:
            Scheduler().remove_plugin_job(self.__class__.__name__.lower())
        except Exception:
            pass

    def _get_config(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "notify": self._notify,
            "use_proxy": self._use_proxy,
            "cron": self._cron or "",
            "email": self._email or "",
            "password": self._password or "",
            "timeout": self._timeout,
            "retry_count": self._retry_count,
        }

    def _save_config(self, config_payload: dict = None) -> Dict[str, Any]:
        config_payload = config_payload or {}
        self._enabled = self._to_bool(config_payload.get("enabled", self._enabled))
        self._notify = self._to_bool(config_payload.get("notify", self._notify))
        self._use_proxy = self._to_bool(config_payload.get("use_proxy", self._use_proxy))
        self._cron = (config_payload.get("cron") or self._cron or "10 8 * * *").strip()
        self._email = (config_payload.get("email") or self._email or "").strip()
        password = config_payload.get("password")
        if password is not None:
            self._password = password
        self._timeout = max(5, self._to_int(config_payload.get("timeout", self._timeout), self._timeout))
        self._retry_count = max(1, self._to_int(config_payload.get("retry_count", self._retry_count), self._retry_count))

        new_config = {
            "enabled": self._enabled,
            "notify": self._notify,
            "use_proxy": self._use_proxy,
            "cron": self._cron,
            "email": self._email,
            "password": self._password,
            "timeout": self._timeout,
            "retry_count": self._retry_count,
        }
        self.update_config(new_config)
        self.init_plugin(new_config)
        return {"success": True, "message": "配置已保存", "data": self._get_config()}

    def _get_status(self) -> Dict[str, Any]:
        history = self.get_data("history") or []
        last_result = self.get_data("last_result") or {}
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

        return {
            "success": True,
            "data": {
                "enabled": self._enabled,
                "notify": self._notify,
                "use_proxy": self._use_proxy,
                "cron": self._cron,
                "email": self._mask_email(self._email),
                "configured": bool(self._email and self._password),
                "last_status": self.get_data("last_status") or self._last_status,
                "last_run": self.get_data("last_run"),
                "last_result": last_result,
                "history": history,
                "history_count": len(history),
                "next_run_time": next_run_time,
                "task_status": task_status,
            },
        }

    def _get_headers(self, token: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json, text/plain, */*",
        }
        if token:
            headers["authorization"] = token
        return headers

    def _get_proxies(self) -> Optional[dict]:
        return settings.PROXY if self._use_proxy else None

    def _request_json(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        url = f"{self.BASE_URL}{path}"
        last_error: Optional[Exception] = None
        for attempt in range(1, self._retry_count + 1):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    timeout=self._timeout,
                    proxies=self._get_proxies(),
                    **kwargs,
                )
                response.raise_for_status()
                return response.json()
            except Exception as err:
                last_error = err
                logger.warning(f"{self.plugin_name}: 请求失败 {url}，重试 {attempt}/{self._retry_count}: {err}")
        raise RuntimeError(str(last_error) if last_error else "请求失败")

    def _login(self, email: str, password: str) -> str:
        if not email or not password:
            raise ValueError("请先配置 FLZT 账号和密码")
        result = self._request_json(
            "POST",
            self.LOGIN_PATH,
            headers={**self._get_headers(), "Content-Type": "application/json"},
            json={"email": email, "password": password},
        )
        if result.get("status") != "success" or not ((result.get("data") or {}).get("auth_data")):
            raise RuntimeError(result.get("message") or "登录失败")
        return result["data"]["auth_data"]

    def _check_in(self, token: str) -> Dict[str, Any]:
        result = self._request_json(
            "GET",
            self.CHECKIN_PATH,
            headers=self._get_headers(token),
        )
        if result.get("status") not in {"success", "fail"}:
            raise RuntimeError(result.get("message") or "签到返回异常")
        return result

    @staticmethod
    def _format_traffic(total_bytes: Any) -> str:
        try:
            value = float(total_bytes or 0)
        except Exception:
            return "0.00 GB"
        return f"{value / 1024 / 1024 / 1024:.2f} GB"

    def _build_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        message = result.get("message") or ""
        data = result.get("data") or {}
        reward_mb = str(data.get("reward_mb") or data.get("reward") or "0")
        total_text = self._format_traffic(data.get("total_checkin_traffic"))

        if result.get("status") == "success":
            status_text = "签到成功"
        elif self._is_already_checked_in(message):
            status_text = "今日已签到"
        else:
            raise RuntimeError(message or "签到失败")

        return {
            "status": status_text,
            "message": message or status_text,
            "reward_mb": reward_mb,
            "total_traffic": total_text,
            "email": self._mask_email(self._email),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _append_history(self, item: Dict[str, Any]) -> None:
        history = self.get_data("history") or []
        history.insert(0, item)
        self.save_data("history", history[:30])

    def _notify_result(self, result: Dict[str, Any]) -> None:
        if not self._notify:
            return
        self.post_message(
            mtype=NotificationType.Plugin,
            title=f"{self.plugin_name} - {result.get('status', '执行完成')}",
            text=(
                f"账号：{result.get('email', '-') }\n"
                f"结果：{result.get('message', '-') }\n"
                f"奖励：{result.get('reward_mb', '0')} MB\n"
                f"累计：{result.get('total_traffic', '-') }\n"
                f"时间：{result.get('time', '-') }"
            ),
        )

    def _run_checkin(self) -> Dict[str, Any]:
        token = self._login(self._email, self._password)
        checkin_result = self._check_in(token)
        result = self._build_result(checkin_result)
        self._last_status = result.get("status") or "已完成"
        self.save_data("last_status", self._last_status)
        self.save_data("last_result", result)
        self.save_data("last_run", result.get("time"))
        self._append_history(result)
        self._notify_result(result)
        return result

    def _scheduled_run(self) -> None:
        try:
            logger.info(f"{self.plugin_name}: 开始执行定时签到")
            self._run_checkin()
        except Exception as err:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            error_result = {
                "status": "执行失败",
                "message": str(err),
                "reward_mb": "0",
                "total_traffic": "-",
                "email": self._mask_email(self._email),
                "time": now,
            }
            self._last_status = "执行失败"
            self.save_data("last_status", self._last_status)
            self.save_data("last_result", error_result)
            self.save_data("last_run", now)
            self._append_history(error_result)
            logger.error(f"{self.plugin_name}: 定时签到失败: {err}")
            if self._notify:
                self.post_message(
                    mtype=NotificationType.Plugin,
                    title=f"{self.plugin_name} - 执行失败",
                    text=f"账号：{self._mask_email(self._email)}\n错误：{err}\n时间：{now}",
                )

    def _run_once_api(self) -> Dict[str, Any]:
        try:
            result = self._run_checkin()
            return {"success": True, "message": result.get("message") or result.get("status"), "data": result}
        except Exception as err:
            logger.error(f"{self.plugin_name}: 手动签到失败: {err}")
            return {"success": False, "message": str(err)}

    def _test_login_api(self) -> Dict[str, Any]:
        try:
            token = self._login(self._email, self._password)
            return {
                "success": True,
                "message": "登录测试成功",
                "data": {
                    "token_preview": f"{token[:24]}..." if len(token) > 24 else token,
                    "email": self._mask_email(self._email),
                },
            }
        except Exception as err:
            logger.error(f"{self.plugin_name}: 登录测试失败: {err}")
            return {"success": False, "message": str(err)}

    def _get_history(self) -> Dict[str, Any]:
        history = self.get_data("history") or []
        return {"success": True, "data": history}

    def _clear_history(self) -> Dict[str, Any]:
        self.save_data("history", [])
        return {"success": True, "message": "历史记录已清空", "data": []}
