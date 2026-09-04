from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
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
            errors.append("FLZT 还没填邮箱")
        if not site_config.get("password"):
            errors.append("FLZT 还没填密码")
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
    """恩山无线论坛（Discuz + erling_qd 零点签到插件）。

    签到就是一次 AJAX：``POST plugin.php?id=erling_qd:action&action=sign``，带页面上的
    formhash，回一段 JSON ``{"success":…,"credit":…,"continuous_days":…,"message":…}``。
    页面上那个按钮的 JS 干的就是这件事，这里照着发同一个请求、读同一份 JSON —— 不再去
    正文里捞关键词猜状态，站点改个版就全盘失灵。

    两条历史教训写在这儿，别再踩：

    1. **Discuz 的重写地址 ``<插件>-<模块>.html`` 等价于 ``plugin.php?id=<插件>:<模块>``。**
       所以 ``erling_qd-sign_in.html`` 的模块名是 ``sign_in``。以前代码里的回退地址写成
       ``?id=erling_qd:sign``（少了 ``_in``），站点一直老实回「指定的插件模块文件
       ./source/plugin/erling_qd/sign.inc.php 不存在」，那条回退从来没起过作用。
    2. **重写那条地址被站点的人机验证挡着。** 2026-09 起 ``erling_qd-sign_in.html`` 返回
       HTTP 200 加一个只有 CSS 和 JS 的挑战页（``_waf_is_mobile`` / ``CF_APP_WAF``），
       于是失败原因被截成一句 ``body,div,html,p,span{margin:0…``。plugin.php 那条不挡，
       所以主用它，重写那条只留作回退，并且认出挑战页时说人话。
    """

    site_key = "right_forum"
    site_name = "恩山无线论坛"
    mode = "Cookie"
    base_url = "https://www.right.com.cn/forum"
    sign_page = "/plugin.php?id=erling_qd:sign_in"
    sign_page_rewrite = "/erling_qd-sign_in.html"
    sign_action = "/plugin.php?id=erling_qd:action&action=sign"
    forum_page = "/forum.php"

    # 人机验证挑战页的指纹。它是 HTTP 200，正文只有一段重置 CSS 和一大坨 JS，
    # 任何关键词都命中不了 —— 不认出来就会把这坨东西当成「失败原因」报给用户。
    _CHALLENGE_MARKERS = ("_waf_is_mobile", "CF_APP_WAF", '"sceneId"', 'id="renderData"')

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
            errors.append("恩山无线论坛还没填 Cookie")
            return errors
        if len(cookie) < 20:
            errors.append("恩山无线论坛的 Cookie 太短，请粘贴完整的那一串")
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
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cookie": cookie,
        }
        if referer:
            headers["Referer"] = referer
            headers["Origin"] = self.base_url
        if ajax:
            # 页面上那段 JS 用的是 jQuery $.ajax，这两个头是它带的；缺了会被判「请求来源验证失败」
            headers["X-Requested-With"] = "XMLHttpRequest"
            headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        return headers

    @classmethod
    def _is_challenge(cls, text: str) -> bool:
        return any(marker in (text or "") for marker in cls._CHALLENGE_MARKERS)

    def _ensure_usable(self, text: str) -> None:
        """这一页能不能用来干活。挡在前面的三种情况各有各的下一步。"""
        if self._is_challenge(text):
            raise RuntimeError("站点的人机验证挡住了这次请求，过一会儿再试，或在浏览器里过一次验证后更新 Cookie")
        if "请先登录" in text or "您需要登录后才能使用签到功能" in text or ("立即登录" in text and "签到功能" in text):
            raise RuntimeError("Cookie 已失效，去设置里重新粘一份")
        if "安全验证" in text or "滑块" in text:
            raise RuntimeError("站点要求安全验证，在浏览器里过一次再更新 Cookie")
        if "不存在或存在语法错误" in text:
            raise RuntimeError("站点的签到插件当前不可用，等站点修好再试")

    def _fetch_sign_page(self, cookie: str, site_config: Dict[str, Any]) -> Tuple[str, str, str]:
        """拿签到页：先 plugin.php，再重写地址。返回 (formhash, 正文, 用上的路径)。"""
        last_error: Optional[Exception] = None
        for path in (self.sign_page, self.sign_page_rewrite):
            try:
                text = self.plugin._request_text(
                    "GET",
                    self.base_url,
                    path,
                    use_proxy=site_config.get("use_proxy", False),
                    headers=self._headers(cookie, referer=f"{self.base_url}{self.forum_page}"),
                )
                self._ensure_usable(text)
                if formhash := self.plugin._extract_formhash(text):
                    return formhash, text, path
                last_error = RuntimeError("签到页里没有 formhash")
            except Exception as err:  # noqa: BLE001
                last_error = err
                logger.warning(f"{self.plugin.plugin_name}: 恩山签到页取不到（{path}）：{err}")
        raise RuntimeError(str(last_error) if last_error else "签到页打不开")

    def _extract_right_forum_stats(self, text: str) -> str:
        """把页面上那三行读数拼成一句。签到成功后 `今日积分` 才会出现在这一块里。"""
        if not text:
            return ""
        cleaned = self.plugin._clean_text(text)
        patterns = [
            ("今日积分", r"今日积分[:：]\s*(\d+)"),
            ("连续签到", r"连续签到[:：]\s*(\d+)\s*天"),
            ("总签到天数", r"总签到天数[:：]\s*(\d+)\s*天"),
        ]
        parts: List[str] = []
        for label, pattern in patterns:
            match = re.search(pattern, cleaned)
            if not match:
                continue
            suffix = " 天" if label != "今日积分" else ""
            parts.append(f"{label}：{match.group(1)}{suffix}")
        return "；".join(parts)

    def _with_right_forum_stats(self, message: str, text: str) -> str:
        stats = self._extract_right_forum_stats(text)
        return stats or message

    @staticmethod
    def _credit_of(payload: Dict[str, Any]) -> float:
        """这次到手多少积分。取不到就当 0 —— 签到不为一个脏值罢工。"""
        try:
            return max(0.0, float(str(payload.get("credit") or 0).strip() or 0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _stats_from_payload(payload: Dict[str, Any], page_stats: str) -> str:
        """把 JSON 里的读数拼成通知层认得的那句话。

        `今日积分：N` 是通知里「+N 积分」的来源（见 `_POINTS_PATTERNS`），所以优先用 JSON
        里的 credit —— 它就是这一次到手的分，比事后再拉一遍页面准，也省一个请求。
        """
        parts: List[str] = []
        credit = payload.get("credit")
        if credit is not None and str(credit).strip() not in {"", "0"}:
            parts.append(f"今日积分：{credit}")
        days = payload.get("continuous_days")
        if days is not None and str(days).strip():
            parts.append(f"连续签到：{days} 天")
        if parts:
            # 总签到天数只有页面上有，能捞到就带上
            if match := re.search(r"总签到天数：\d+ 天", page_stats or ""):
                parts.append(match.group(0))
            return "；".join(parts)
        return page_stats

    def run_checkin(self, site_config: Dict[str, Any]) -> Dict[str, Any]:
        cookie = (site_config.get("cookie") or "").strip()
        if not cookie:
            raise ValueError("请先配置恩山无线论坛 Cookie")

        formhash, page_text, page_path = self._fetch_sign_page(cookie, site_config)
        page_stats = self._extract_right_forum_stats(page_text)

        # 直接发签到，不先按页面猜「今天签过没有」：页面上那句「今日已签到：2818 人」是
        # 全站今天签到的人数，拿它当自己的状态会让插件一天都不真发请求。重复发是安全的，
        # 站点会回 success=false + 已签到。
        raw = self.plugin._request_text(
            "POST",
            self.base_url,
            self.sign_action,
            use_proxy=site_config.get("use_proxy", False),
            headers=self._headers(cookie, referer=f"{self.base_url}{page_path}", ajax=True),
            data={"formhash": formhash},
        )
        self._ensure_usable(raw)
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            raise RuntimeError(
                f"签到接口没回 JSON：{self.plugin._clean_text(raw)[:60] or '空响应'}"
            ) from None
        if not isinstance(payload, dict):
            raise RuntimeError("签到接口回了意料之外的内容")

        message = str(payload.get("message") or "").strip()
        if payload.get("success"):
            # 站点对重复签到也回 success=true、message 还是「签到成功」，只有 credit 归零：
            # 当天第一次是 {"credit":1,...}，之后每次都是 {"credit":0,...}。所以「这次到底
            # 有没有拿到东西」看 credit，不看 success —— 只认 success 会天天报「已签到，+0」。
            status_text = "签到成功" if self._credit_of(payload) > 0 else "今日已签到"
        elif self.plugin._is_already_checked_in(message):
            status_text = "今日已签到"
        elif "请求来源验证失败" in message:
            raise RuntimeError("站点拒了这次请求（来源校验失败），Cookie 可能是另一个域名下复制的")
        else:
            raise RuntimeError(message or "站点没说原因")

        return {
            "site": self.site_key,
            "site_name": self.site_name,
            "status": status_text,
            "message": self._stats_from_payload(payload, page_stats) or message or status_text,
            "reward_mb": "-",
            "total_traffic": "-",
            "account": "Cookie 登录态",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def test_connection(self, site_config: Dict[str, Any]) -> Dict[str, Any]:
        cookie = (site_config.get("cookie") or "").strip()
        if not cookie:
            raise ValueError("请先配置恩山无线论坛 Cookie")
        _formhash, page_text, page_path = self._fetch_sign_page(cookie, site_config)
        stats = self._extract_right_forum_stats(page_text)
        return {
            "site": self.site_key,
            "site_name": self.site_name,
            "message": f"Cookie 有效，签到页正常（{page_path}）" + (f"，{stats}" if stats else ""),
        }


class YpojieSiteAdapter(BaseSiteAdapter):
    site_key = "ypojie"
    site_name = "易破解"
    mode = "账号密码"
    base_url = "https://www.ypojie.com"
    # 余额 / 签到入口如今在 /vip 的「充值」标签页下
    vip_path = "/vip?pd=money"
    login_path = "/wp-login.php"
    ajax_path = "/wp-admin/admin-ajax.php"

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
            errors.append("易破解还没填账号")
        if not site_config.get("password"):
            errors.append("易破解还没填密码")
        return errors

    def get_account_label(self, site_config: Dict[str, Any]) -> str:
        return self.plugin._mask_email(site_config.get("email") or "")

    def _login_headers(self, referer: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "User-Agent": self.plugin.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": referer or f"{self.base_url}{self.login_path}",
        }
        return headers

    def _ajax_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self.plugin.USER_AGENT,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}{self.vip_path}",
            "X-Requested-With": "XMLHttpRequest",
        }

    def _session_get_text(self, session: requests.Session, path: str, site_config: Dict[str, Any], **kwargs) -> str:
        response = session.get(
            f"{self.base_url}{path}",
            timeout=self.plugin._timeout,
            proxies=self.plugin._get_proxies(site_config.get("use_proxy", False)),
            **kwargs,
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        return response.text

    def _validate_login_page(self, page: str) -> None:
        if "Hi," not in page and "今日签到" not in page and "个人中心" not in page:
            if "wp-login.php" in page or "用户名或电子邮件地址" in page or "登录" in page:
                raise RuntimeError("易破解登录失败，请检查账号或密码")
            raise RuntimeError("易破解登录状态未确认，请检查账号密码或站点登录限制")

    def _extract_balance(self, page: str) -> Optional[Decimal]:
        cleaned = self.plugin._clean_text(page)
        match = re.search(r"可用余额\s*([0-9]+(?:\.[0-9]+)?)\s*积分", cleaned)
        if not match:
            return None
        try:
            return Decimal(match.group(1))
        except InvalidOperation:
            return None

    @staticmethod
    def _format_points(value: Decimal) -> str:
        normalized = value.quantize(Decimal("0.01")).normalize()
        return format(normalized, "f")

    def _format_checkin_reward(self, before_page: str, after_page: str) -> str:
        before_balance = self._extract_balance(before_page)
        after_balance = self._extract_balance(after_page)
        if before_balance is None or after_balance is None:
            return ""
        diff = after_balance - before_balance
        if diff < 0:
            return ""
        return f"本次签到增加：{self._format_points(diff)}积分"

    @staticmethod
    def _extract_slider_data(page: str) -> Dict[str, Any]:
        """从登录页提取滑块验证码参数；取不到时返回 {verified:False}，由调用方决定是否回退。"""
        token_m = re.search(r'name="slider_token"\s+value="([^"]+)"', page)
        nonce_m = re.search(r'name="slider_nonce"\s+value="([^"]+)"', page)
        ver_m = re.search(r'id="slider_verified"\s+name="slider_verified"\s+value="([^"]*)"', page)
        if not token_m or not nonce_m:
            return {"verified": False, "slider_token": "", "slider_nonce": ""}
        return {
            "verified": ver_m is not None,
            "slider_token": token_m.group(1),
            "slider_nonce": nonce_m.group(1),
        }

    def _login(self, site_config: Dict[str, Any]) -> Tuple[requests.Session, str]:
        account = site_config.get("email") or ""
        password = site_config.get("password") or ""
        if not account or not password:
            raise ValueError("请先配置易破解账号和密码")

        session = requests.Session()
        use_proxy = site_config.get("use_proxy", False)
        login_url = f"{self.base_url}{self.login_path}"
        vip_url = f"{self.base_url}{self.vip_path}"
        try:
            login_page = session.get(
                login_url,
                timeout=self.plugin._timeout,
                proxies=self.plugin._get_proxies(use_proxy),
                headers=self._login_headers(),
            )
            login_page.raise_for_status()
            login_page.encoding = login_page.apparent_encoding or login_page.encoding or "utf-8"
            slider = self._extract_slider_data(login_page.text)

            post_data: Dict[str, Any] = {
                "log": account,
                "pwd": password,
                "rememberme": "forever",
                "wp-submit": "登录",
                "redirect_to": vip_url,
                "testcookie": "1",
            }
            if slider["verified"]:
                # 站点 2024 年后加了滑块验证：POST 必须带  verified=1 + 页面上一次性 token/nonce
                post_data.update(
                    {
                        "slider_verified": "1",
                        "slider_token": slider["slider_token"],
                        "slider_nonce": slider["slider_nonce"],
                        "_wp_http_referer": self.login_path,
                    }
                )
            response = session.post(
                login_url,
                timeout=self.plugin._timeout,
                proxies=self.plugin._get_proxies(use_proxy),
                headers={
                    **self._login_headers(referer=login_url),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data=post_data,
                allow_redirects=True,
            )
            response.raise_for_status()
            page = self._session_get_text(session, self.vip_path, site_config, headers=self._login_headers(referer=vip_url))
            self._validate_login_page(page)
            return session, page
        except RequestException as err:
            raise RuntimeError(f"易破解登录请求失败：{self.plugin._format_request_error(err, use_proxy)}") from err

    def _check_in(self, session: requests.Session, site_config: Dict[str, Any]) -> Dict[str, Any]:
        use_proxy = site_config.get("use_proxy", False)
        response = session.post(
            f"{self.base_url}{self.ajax_path}",
            timeout=self.plugin._timeout,
            proxies=self.plugin._get_proxies(use_proxy),
            headers=self._ajax_headers(),
            data={"action": "epd_checkin"},
        )
        if response.status_code != 400:
            response.raise_for_status()
        result = response.json()
        return result

    def run_checkin(self, site_config: Dict[str, Any]) -> Dict[str, Any]:
        session, before_page = self._login(site_config)
        try:
            result = self._check_in(session, site_config)
        except RequestException as err:
            raise RuntimeError(f"易破解签到请求失败：{self.plugin._format_request_error(err, site_config.get('use_proxy', False))}") from err
        after_page = self._session_get_text(session, self.vip_path, site_config, headers=self._login_headers(referer=f"{self.base_url}{self.vip_path}"))
        reward_message = self._format_checkin_reward(before_page, after_page)
        status_code = result.get("status")
        message = result.get("msg") or result.get("message") or ""
        if status_code == 200:
            status_text = "签到成功"
            final_message = reward_message or message or "签到成功"
        elif message and self.plugin._is_already_checked_in(message):
            status_text = "今日已签到"
            final_message = reward_message or message
        else:
            raise RuntimeError(message or f"易破解签到失败（status={status_code}）")

        return {
            "site": self.site_key,
            "site_name": self.site_name,
            "status": status_text,
            "message": final_message,
            "reward_mb": "-",
            "total_traffic": "-",
            "account": self.get_account_label(site_config),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def test_connection(self, site_config: Dict[str, Any]) -> Dict[str, Any]:
        self._login(site_config)
        return {
            "site": self.site_key,
            "site_name": self.site_name,
            "message": "登录测试成功，可用于签到",
        }


class Checkin(_PluginBase):
    plugin_name = "自用签到工具"
    plugin_desc = "用于自用站点签到的统一工具，支持自动登录、Cookie 签到、通知与历史记录。"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/signin.png"
    plugin_version = "1.7.0"
    plugin_author = "LittlePigeno"
    author_url = "https://github.com/jxxghp/MoviePilot-Plugins"
    plugin_config_prefix = "checkin_"
    plugin_order = 36
    auth_level = 1

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    # ── 定时任务的两条腿 ────────────────────────────────────────────────
    #
    # 签到只在乎「今天签上了没有」，不在乎精确到哪一分钟。所以注册两条任务：
    #
    #   checkin          用户配的 cron，期望的执行时刻
    #   checkin_catchup  每 30 分钟的巡检，只做一件事：今天该签、还没签成，就补
    #
    # 为什么必须有第二条：APScheduler 默认 misfire_grace_time=1，触发时刻起 1 秒
    # 内没被执行器领走就整次丢弃，只在日志里留一句 "Run time of job ... was
    # missed"。NAS 定时休眠、容器被宿主抢 CPU、MoviePilot 恰好在这一刻重启、NTP
    # 把时钟往前拨——任何一种都够让当天彻底不执行。放宽 misfire 窗口只能救「晚了
    # 一会儿」，救不了「那段时间机器根本没在跑」，后者只能靠醒来之后补。
    JOB_ID = "checkin"
    CATCHUP_JOB_ID = "checkin_catchup"
    CATCHUP_CRON = "*/30 * * * *"
    # 错过触发时刻后仍允许立刻补跑的窗口。取值与巡检同频：30 分钟内的错过由
    # APScheduler 自己补，更久的交给巡检——那条路径带「今天签成了没有」的判断，
    # 不会重复签。
    MISFIRE_GRACE_TIME = 1800
    # 当天最多补几次。已经全部成功就不再补；仍有站点失败时留几次机会等网络恢复，
    # 但不能无限重试，否则一天下来会对站点发几十次请求。
    CATCHUP_MAX_PER_DAY = 5

    # 启动兜底的延迟秒数。MoviePilot 启动时批量注册插件服务，那批注册和插件加载是
    # 交错进行的：加载完成得晚的插件会被整个漏掉。等这么久是为了让 PluginManager
    # 先把实例登记完 —— 它没登记完的话，update_plugin_job() 里的
    # run_plugin_method(pid, "get_service") 什么都拿不到，注册会静默失败。
    BOOT_REGISTER_DELAY = 20

    # 一次执行落到哪一档。站点级（签到成功 / 今日已签到）和汇总级（全部成功 /
    # 部分成功）的状态词混在一张表里，因为通知和打卡带都要同时吃这两种。
    RANK_SIGNED = 3
    RANK_PARTIAL = 2
    RANK_FAILED = 1
    _STATUS_RANK = {
        "全部成功": RANK_SIGNED,
        "签到成功": RANK_SIGNED,
        "今日已签到": RANK_SIGNED,
        "部分成功": RANK_PARTIAL,
        "执行失败": RANK_FAILED,
    }
    # 打卡带的四种刻痕。挑的都是 CJK 字体必备的字符 —— emoji 方块在部分通知渠道
    # 会变成豆腐块或宽度不一，这四个到哪儿都是等宽的。
    _TAPE_MARKS = {RANK_SIGNED: "■", RANK_PARTIAL: "▣", RANK_FAILED: "□", 0: "·"}
    # 通知标题里的自称。比 plugin_name 短四个字：标题是「前缀 · 结论」，前缀每多两个
    # 字，结论就少两个字的位置，而锁屏上常常只看得到这一行。「工具」在这里是废字。
    NOTIFY_TITLE = "自用签到"
    # 通知里最多逐行列几个站点，再多就折叠 —— 锁屏上看不完那么长
    NOTIFY_SITE_LIMIT = 8
    # 失败原因在通知里的截断长度
    NOTIFY_REASON_LIMIT = 24
    # 短于这个长度的分句不算「说完了一句话」，截断时会接着往下取
    REASON_MIN_CLAUSE = 4

    # 类级互斥：定时、巡检、手动三条入口都可能同时进来，签到接口经不起并发重放。
    # 放在类上而不是实例上，是为了插件重载换了实例之后仍然互斥。
    _run_lock = threading.Lock()
    # 同理放在类上：插件重载会换实例，旧实例挂起的兜底定时器得能被新实例取消。
    _boot_timer: Optional[threading.Timer] = None

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
            YpojieSiteAdapter.site_key: YpojieSiteAdapter(self),
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
            or "今天已经签过" in text
            or "今天已经签过到" in text
            or "签过到" in text
            or "明儿再来" in text
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
        self._arm_boot_registration()

    def _migrate_legacy_config_prefix(self):
        try:
            if getattr(self, "plugin_config_prefix", None) == LEGACY_PLUGIN_CONFIG_PREFIX:
                return
            if hasattr(self, "systemconfig") and self.systemconfig:
                system_config = self.systemconfig.all() or {}
                legacy_keys = [
                    key for key in list(system_config.keys())
                    if isinstance(key, str) and key.startswith(LEGACY_PLUGIN_CONFIG_PREFIX)
                ]
                for legacy_key in legacy_keys:
                    new_key = legacy_key.replace(LEGACY_PLUGIN_CONFIG_PREFIX, self.plugin_config_prefix, 1)
                    if new_key not in system_config:
                        self.systemconfig.set(new_key, self.systemconfig.get(legacy_key))
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

    def _build_trigger(self, cron: str) -> Optional[CronTrigger]:
        """按 MoviePilot 的时区解析 cron。

        from_crontab() 不传 timezone 时会 fallback 到 get_localzone()，那读的是
        **容器的** /etc/localtime，不是 MoviePilot 的 settings.TZ。镜像里这两者经常
        不一致（只设了 MoviePilot 的 TZ、没设系统时区），于是任务按 UTC 触发：配
        08:10 实际在北京时间 16:10 跑。显式传 settings.TZ 消掉这个偏差，也让插件的
        触发时刻和调度器自身的时区（BackgroundScheduler(timezone=settings.TZ)）对齐。
        """
        cron = (cron or "").strip()
        if not cron:
            return None
        tz = getattr(settings, "TZ", None) or None
        if tz:
            try:
                return CronTrigger.from_crontab(cron, timezone=tz)
            except Exception as err:
                logger.warning(f"{self.plugin_name}: 按 TZ={tz} 解析 cron 失败，回退容器时区: {err}")
        try:
            return CronTrigger.from_crontab(cron)
        except Exception as err:
            logger.error(f"{self.plugin_name}: cron 表达式无法解析（{cron}）: {err}")
            return None

    def get_service(self) -> List[Dict[str, Any]]:
        if not self._enabled:
            return []
        trigger = self._build_trigger(self._cron)
        if not trigger:
            return []

        # 这里的 kwargs 会被 MoviePilot 原样展开进 APScheduler 的 add_job()，所以放的
        # 是调度参数而不是业务参数：
        #   misfire_grace_time  错过触发时刻后仍允许补跑的窗口（默认 1 秒，太短）
        #   coalesce            积压的多次触发合并成一次，避免醒来后连签好几遍
        #   max_instances       上一次还没跑完就不再起第二个实例
        job_kwargs = {
            "misfire_grace_time": self.MISFIRE_GRACE_TIME,
            "coalesce": True,
            "max_instances": 1,
        }

        services: List[Dict[str, Any]] = [{
            "id": self.JOB_ID,
            "name": self.plugin_name,
            "trigger": trigger,
            "func": self._scheduled_run,
            "kwargs": dict(job_kwargs),
        }]

        catchup_trigger = self._build_trigger(self.CATCHUP_CRON)
        if catchup_trigger:
            services.append({
                "id": self.CATCHUP_JOB_ID,
                "name": f"{self.plugin_name} 漏签补跑",
                "trigger": catchup_trigger,
                "func": self._catchup_run,
                "kwargs": dict(job_kwargs),
            })
        return services

    def stop_service(self):
        """插件停用 / 重载时摘掉定时任务。

        remove_plugin_job() 的入参是**插件 id**（也就是类名 Checkin），不是 job id ——
        它遍历自己的 _jobs 找 service["pid"] == pid 的项。这里以前传的是类名的小写
        形式，永远匹配不上，于是「停用插件」和「改 cron」都不会真的摘掉旧任务。
        """
        timer, Checkin._boot_timer = Checkin._boot_timer, None
        if timer:
            # 不取消的话，停用插件之后它还会把任务装回去
            timer.cancel()
        try:
            Scheduler().remove_plugin_job(self.__class__.__name__)
        except Exception as err:
            logger.debug(f"{self.plugin_name}: 移除定时任务时忽略异常: {err}")

    def _arm_boot_registration(self) -> None:
        """启动路径的兜底：过一会儿自己把定时任务装回调度器。

        MoviePilot 启动时的批量注册和插件加载是交错跑的，加载完成得晚的插件整个被
        跳过 —— 本插件在真机上就一直被跳过：容器重启后 /api/v1/dashboard/schedule2
        里找不到 checkin 的任何任务，直到有人保存一次配置才补上。于是「重启过的那
        几天不签到」，而日志里一句异常都没有。

        官方插件 brushflow 也是自己调 update_plugin_job() 保证任务在位，只是它挂在
        PluginReload 事件上 —— 那条路径覆盖不到启动。这里改用延迟触发，启动、热重载、
        保存配置三条路径都能兜住；update_plugin_job() 本身是先摘再装，重复调用无害。
        """
        timer, Checkin._boot_timer = Checkin._boot_timer, None
        if timer:
            timer.cancel()
        if not self._enabled:
            return
        timer = threading.Timer(self.BOOT_REGISTER_DELAY, self._register_if_absent)
        timer.daemon = True
        Checkin._boot_timer = timer
        timer.start()

    def _scheduler_job_ids(self) -> set:
        """主任务在 Scheduler().list() 里可能出现的 id。

        MoviePilot 2.15.6 的 job id 是 `{pid}_{service_id}`（如 Checkin_checkin），更早的版本
        直接用 service_id。两种都认，免得换个 MoviePilot 版本就把「已注册」误判成「没注册」，
        白白多摘装一轮，还刷一条会误导人的 WARNING。
        """
        return {self.JOB_ID, f"{self.__class__.__name__}_{self.JOB_ID}"}

    def _register_if_absent(self) -> None:
        """兜底定时器的落点：确认调度器里有主任务，没有就装上。"""
        Checkin._boot_timer = None
        wanted = self._scheduler_job_ids()
        try:
            registered = any(getattr(task, "id", "") in wanted for task in Scheduler().list())
        except Exception as err:
            logger.debug(f"{self.plugin_name}: 查询定时任务失败，直接重新注册: {err}")
            registered = False
        if registered:
            return
        logger.warning(f"{self.plugin_name}: 调度器里没有本插件的定时任务，正在补注册")
        self._reschedule()

    def _reschedule(self) -> None:
        """把改动后的 cron 真正推给调度器。

        插件配置走的是自己的 /config 接口，MoviePilot 不经手，所以框架不会像标准配置
        表单那样帮我们调 update_plugin_job()。不主动调一次的话，调度器里跑的仍是保存
        前那份 cron、绑的仍是上一个插件实例的方法：用户看到「配置已保存」，却发现改
        时间没生效、关了插件定时任务还在跑、改了账号定时执行还用旧账号。
        """
        try:
            Scheduler().update_plugin_job(self.__class__.__name__)
            logger.info(f"{self.plugin_name}: 定时任务已按新配置重新注册（cron={self._cron}）")
        except Exception as err:
            logger.error(f"{self.plugin_name}: 重新注册定时任务失败: {err}")

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
        # init_plugin() 只摘任务不装任务，装回去要靠这一步
        self._reschedule()
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
            # 运行台的站点行要和通知里那几行说同一句话，所以原始读数一起下发
            "reward_mb": last_result.get("reward_mb") or "-",
            "total_traffic": last_result.get("total_traffic") or "-",
        }

    @staticmethod
    def _spaced_duration(text: Any) -> str:
        """把宿主给的 `9小时30分钟` 排成 `9 小时 30 分钟`。

        数字两边留一个空格是这一仓的中文排版惯例（通知里「近 7 天」「+128 MB」都这么
        写），运行台上那格读数不该是唯一的例外。
        """
        spaced = re.sub(r"(\d+)\s*(小时|分钟|分|秒|天)", r"\1 \2 ", str(text or ""))
        return re.sub(r"\s+", " ", spaced).strip()

    def _get_status(self) -> Dict[str, Any]:
        history = self._normalize_history()
        last_result = self.get_data("last_result") or {}
        site_last_results = self.get_data("site_last_results") or {}
        next_run_time = "未配置定时任务"
        task_status = "未启用"

        if self._enabled and self._cron:
            try:
                task_status = "未找到任务"
                next_run_time = f"按 {self._cron} 执行"
                # 现在有两条任务（主任务 + 漏签补跑），只认主任务那条：
                # 按 provider 匹配会撞上补跑巡检，报出来的「下次」就变成几分钟后的巡检时间。
                tasks = list(Scheduler().list())
                wanted = self._scheduler_job_ids()
                task = next((item for item in tasks if getattr(item, "id", "") in wanted), None)
                if task is None:
                    task = next((item for item in tasks if getattr(item, "provider", "") == self.plugin_name), None)
                if task is not None:
                    task_status = getattr(task, "status", "未知")
                    next_run = getattr(task, "next_run", None)
                    if next_run:
                        next_run_time = next_run if isinstance(next_run, str) else str(next_run)
                        if isinstance(next_run_time, str) and re.match(r'^(\d+小时)?(\d+分钟)?(\d+秒)?$', next_run_time):
                            next_run_time = f"{self._spaced_duration(next_run_time)}后"
                    elif task_status == "正在运行":
                        next_run_time = "正在运行"
                    else:
                        next_run_time = "等待执行"
            except Exception as err:
                logger.warning(f"{self.plugin_name}: 获取定时任务状态失败: {err}")
                task_status = "获取失败"

        site_statuses = [self._build_site_status(key, cfg, site_last_results) for key, cfg in self._sites.items()]
        enabled_sites = [item for item in site_statuses if item.get("enabled")]
        configured_site_count = len([item for item in enabled_sites if item.get("configured")])

        # 补跑视图：让运行台能说清「今天那一次到底跑了没有」
        now, fire = self._today_schedule()
        today = (now or datetime.now()).strftime("%Y-%m-%d")
        signed_today = self._fully_signed_today(today)
        catchup = {
            "cron": self.CATCHUP_CRON,
            "due_at": fire.strftime("%H:%M") if fire else "",
            "used": self._catchup_used(today),
            "max": self.CATCHUP_MAX_PER_DAY,
            # 该签、已过点、还没签成 —— 巡检会在下一个半点接手
            "pending": bool(self._enabled and fire and now and now >= fire and not signed_today),
        }

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
                "catchup": catchup,
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
        # 每句都是「结论（代理状态），再给建议」：通知里只留得下第一句，那一句必须
        # 自己说得完整，而且是人话 —— 「认证失败」得再想一层才知道该去改什么
        if isinstance(err, ConnectTimeout):
            return f"连不上站点（{proxy_text}），检查一下网络，或者把超时调大一点"
        if isinstance(err, ReadTimeout):
            return f"站点响应太慢（{proxy_text}），等一会儿再试，或者把超时调大一点"
        if isinstance(err, RequestsConnectionError):
            detail = str(err)
            if "10054" in detail or "Connection reset" in detail or "Connection aborted" in detail:
                return f"站点把连接掐断了（{proxy_text}），可能是风控、网络不稳或者代理异常"
            return f"连不上站点（{proxy_text}）：{detail}"
        if isinstance(err, HTTPError):
            response = getattr(err, "response", None)
            status_code = getattr(response, "status_code", None)
            if status_code == 400:
                return "账号或密码不对（站点返回 400）"
            if status_code == 401:
                return "登录态失效或账号密码不对，去设置里重新填一次"
            if status_code == 403:
                return "站点拒绝了这次访问，可能是被风控了"
            if status_code == 429:
                return "站点限流了，先歇一会儿再试"
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

    @classmethod
    def _rank_of(cls, status: Any) -> int:
        return cls._STATUS_RANK.get(str(status or "").strip(), 0)

    # ── 通知的排版语法 ──────────────────────────────────────────────────
    #
    # 通知是这个插件唯一会主动找上门的界面：锁屏上只有一个标题加两三行正文。所以两个
    # 插件共用一套语法，一条通知从上往下最多四段，段与段之间只隔一个空行：
    #
    #   ① 清单   ✅/❌ 名称  拿到了什么，或者为什么没成    失败排前面，超限折叠
    #   ② 小计   读数 · 读数                              无行首符号，退出清单那一列
    #   ③ 下一步 一句话                                    只在需要人动手时出现
    #   ④ 落款   打卡带  读数                              全篇唯一的装饰
    #
    # 不写 Markdown（微信 / Bark 会把 `**` 原样显示），不画长横线（窄屏会折行），
    # 不拿空格对齐列（各渠道字体宽度不同，空格对齐到手机上就散了）。数字两边留一个
    # 空格，数字和单位之间也留一个：「近 7 天」「+128 MB」「累计 32.50 GB」。

    def _tape_marks(self, days: int = 7) -> str:
        """最近几天的打卡带 —— 运行台那条 30 格刻痕的通知版。

        只返回记号，读数由 _notify_record_line() 接在同一行：数字给记号当图例，一行
        同时给出同一件事的两个分辨率。一条历史都没有时返回空串 —— 整条都是点，没有
        信息量，不值得占锁屏上的一行。
        """
        best: Dict[str, int] = {}
        for entry in self._normalize_history():
            day = str(entry.get("time") or "")[:10]
            if len(day) == 10:
                best[day] = max(best.get(day, 0), self._rank_of(entry.get("status")))
        if not best:
            return ""
        today = datetime.now()
        return "".join(
            self._TAPE_MARKS.get(
                best.get((today - timedelta(days=back)).strftime("%Y-%m-%d"), 0), "·"
            )
            for back in range(days - 1, -1, -1)
        )

    def _streak_days(self) -> int:
        """连续签上的天数。今天还没签就从昨天数起，和运行台的算法一致。"""
        signed = set()
        for entry in self._normalize_history():
            if self._rank_of(entry.get("status")) >= self.RANK_PARTIAL or int(entry.get("success_count") or 0) > 0:
                day = str(entry.get("time") or "")[:10]
                if len(day) == 10:
                    signed.add(day)
        if not signed:
            return 0
        cursor = datetime.now()
        if cursor.strftime("%Y-%m-%d") not in signed:
            cursor -= timedelta(days=1)
        days = 0
        while cursor.strftime("%Y-%m-%d") in signed:
            days += 1
            cursor -= timedelta(days=1)
        return days

    @staticmethod
    def _looks_like_markup(text: str) -> bool:
        """这段「原因」其实是页面源码吗？

        站点报错时拿不到弹窗文案，适配器就退回整页正文的前 120 字，于是真机上出现过
        `body,div,html,p,span{margin:0;padding:0;...}` 这种货 —— 压缩到通知里只剩一个
        「body…」。花括号、尖括号、`属性: 值;` 这三样正常人话里都不会出现，见到就当没原因。
        """
        return bool(re.search(r"[{}<>]|[A-Za-z-]+\s*:\s*[^;]{1,20};", text))

    @classmethod
    def _short_reason(cls, message: Any, name: str = "") -> str:
        """把失败原因压成一句读得完的话。

        站点原话多是「结论，加一串通用建议」——「认证失败，请检查账号、密码或登录态」。
        通知里要的是结论，所以在第一个说得完整的分句处收住；分句短到不成话（「失败」
        这种）就接着往下取，取到上限为止。省下来的位置留给别的站点那几行。
        """
        text = re.sub(r"\s+", " ", str(message or "").strip())
        if not text or text == "-" or cls._looks_like_markup(text):
            return "没给原因，去插件运行台看这次的记录"
        # 站点自己的校验话术带着站点名（「FLZT 还没填密码」），可这一行行首已经写了站点
        # 名，再来一遍就是把同一个词说两次
        if name and text.startswith(name):
            text = text[len(name):].lstrip(" ：:的") or text
        head = text[: cls.NOTIFY_REASON_LIMIT]
        cut = next(
            (
                index
                for index, char in enumerate(head)
                if char in "，。；！？,;." and index >= cls.REASON_MIN_CLAUSE
            ),
            -1,
        )
        if cut < 0:
            return text if len(text) <= cls.NOTIFY_REASON_LIMIT else f"{head}…"
        return text[:cut] if cut == len(text) - 1 else f"{text[:cut]}…"

    # 站点把「这次拿到了什么」各写在自己的回执里，三家的写法互不相同：
    #   FLZT     结构化字段 reward_mb / total_traffic
    #   恩山     message =「今日积分：5；连续签到：4 天；总签到天数：126 天」
    #   易破解   message =「本次签到增加：2.5积分」
    # 以前只认 FLZT 那两个字段，另外两家签上了也只写一句「签上了」—— 签到的意义就是
    # 拿到东西，那一行偏偏把东西丢了。这里把三种写法收敛成同一种读数。
    _POINTS_PATTERNS = (
        r"今日积分\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)",
        r"本次签到增加\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*积分",
        r"(?:获得|奖励|增加)\s*([0-9]+(?:\.[0-9]+)?)\s*积分",
    )

    @staticmethod
    def _trim_number(text: str) -> str:
        """2.50 → 2.5，2.0 → 2。小数点后的零在读数里是噪音。"""
        value = str(text or "").strip()
        return value.rstrip("0").rstrip(".") if "." in value else value

    @classmethod
    def _points_gained(cls, message: Any) -> str:
        """从站点回执里取出这次到手的积分；取不到返回空串。"""
        text = str(message or "")
        for pattern in cls._POINTS_PATTERNS:
            if match := re.search(pattern, text):
                value = cls._trim_number(match.group(1))
                return "" if value in {"", "0"} else value
        return ""

    @staticmethod
    def _traffic_mb(item: Dict[str, Any]) -> float:
        """这次到手多少 MB；取不到或为零返回 0.0 —— 通知不为一个脏值罢工。"""
        try:
            return max(0.0, float(str(item.get("reward_mb") or "").strip() or 0))
        except ValueError:
            return 0.0

    @classmethod
    def _traffic_text(cls, megabytes: float) -> str:
        """流量读数。真机上 FLZT 一次给一两个 G，写成「+1025.83 MB」既长又要读的人自己换算；
        过了 1 GB 就换单位，小数点后那两位 MB 是噪音，一并收掉。"""
        if megabytes <= 0:
            return ""
        if megabytes >= 1024:
            return f"{megabytes / 1024:.2f} GB"
        return f"{megabytes:.0f} MB" if megabytes >= 10 else f"{cls._trim_number(f'{megabytes:.1f}')} MB"

    def _site_gain_notes(self, item: Dict[str, Any]) -> List[str]:
        """一个站点这次到手的读数，一项一格，由调用方用「·」串起来。

        单位就是读数本身（`+1.00 GB`、`+5 积分`），不再补一个「流量」——
        八个站点各写一遍「流量」，那两个字就成了噪音；要点明数的是什么，
        交给下面那行小计。到手 0 也不写：真机上易破解每天回一句「本次签到增加：0积分」，
        `+0 积分` 占一格却什么都没说。
        """
        notes: List[str] = []
        if traffic := self._traffic_text(self._traffic_mb(item)):
            notes.append(f"+{traffic}")
        if points := self._points_gained(item.get("message")):
            notes.append(f"+{points} 积分")
        stock = str(item.get("total_traffic") or "").strip()
        if stock and stock not in {"-", "0", "0.00 GB"}:
            notes.append(f"累计 {stock}")
        return notes

    def _notify_site_line(self, item: Dict[str, Any], terse: bool = False) -> str:
        """一个站点一行：成没成、拿到了什么，或者为什么没成。

        行首那个状态位自己对齐成一列 —— 不拿空格填充，各家通知渠道字体宽度不同，空格
        对齐到手机上就散了。名称与结果之间空两格，并列的读数用「·」隔开。
        站点签上了又确实没给出任何读数时，这一行就到名称为止 —— 补一句「签上了」是把
        行首那个勾说第二遍，宁可留白。
        ``terse`` 由调用方在「所有站点都是早就签过了」时打开：那句话标题已经说了，
        三行各抄一遍就是把同一句话说四次。
        """
        name = item.get("site_name") or item.get("site") or "-"
        status = str(item.get("status") or "").strip()
        if self._rank_of(status) != self.RANK_SIGNED:
            return f"❌ {name}  {self._short_reason(item.get('message'), name)}"
        notes = self._site_gain_notes(item)
        if status == "今日已签到" and not terse:
            return f"✅ {name}  今天已经签过了"
        # terse 只收掉那句会被复述四遍的话，到手的东西照报 —— 恩山「早就签过了」那条
        # 记录里仍然带着当天的积分
        return f"✅ {name}  {' · '.join(notes)}" if notes else f"✅ {name}"

    def _notify_total_line(self, details: List[Dict[str, Any]]) -> str:
        """小计：今天一共到手多少。

        同一种货币要有三个以上站点给了才值一行：两个数字读者自己就加完了，第三个
        才开始需要合计。流量和积分不同币，各自结算，不相加。
        这一行不带行首符号，视觉上退出站点那一列，一看就是小计。
        """
        signed = [
            item for item in details
            if self._rank_of(item.get("status")) == self.RANK_SIGNED
        ]
        traffic = [
            value for value in (self._traffic_mb(item) for item in signed) if value > 0
        ]
        points = [
            float(value)
            for value in (self._points_gained(item.get("message")) for item in signed)
            if value
        ]
        cells: List[str] = []
        if len(traffic) >= 3:
            cells.append(f"+{self._traffic_text(sum(traffic))} 流量")
        if len(points) >= 3:
            cells.append(f"+{self._trim_number(f'{sum(points):.2f}')} 积分")
        return f"今天到手 {' · '.join(cells)}" if cells else ""

    def _notify_verdict(
        self,
        success: int,
        failure: int,
        fallback: Any = "",
        details: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """标题里那句结论。锁屏上常常只看得到这一行，所以话要说完整。"""
        total = success + failure
        if not total:
            return str(fallback or "这次没有执行")
        if not failure:
            # 全是「今日已签到」就说清是早就签过了，别让人以为这一次真拿到了什么
            if details and all(
                str(item.get("status") or "").strip() == "今日已签到" for item in details
            ):
                return "今天都已经签过了" if total > 1 else "今天已经签过了"
            return f"{total} 个站点都签上了" if total > 1 else "签上了"
        if not success:
            return "一个都没签上" if total > 1 else "没签上"
        return f"{failure} 个没签上，{success} 个签上了"

    def _notify_record_line(self, success: int) -> str:
        """落款：打卡带和读数合成一行，这是整条通知里唯一的装饰。

        数字给记号当图例 —— 数一数右端连着几个 ■，正好是「连续签上 N 天」的那个 N，
        认一次就再也不用猜。今天一个都没签上时说「这之前连着签了」而不是「连续 N 天」，
        后者会让人误以为今天也算进去了。读数的说法和运行台那条 30 格刻痕保持一致。
        """
        tape = self._tape_marks()
        streak = self._streak_days()
        if streak >= 2:
            reading = f"连续签上 {streak} 天" if success else f"这之前连着签了 {streak} 天"
        elif tape:
            signed = sum(
                1
                for mark in tape
                if mark in {self._TAPE_MARKS[self.RANK_SIGNED], self._TAPE_MARKS[self.RANK_PARTIAL]}
            )
            reading = f"{len(tape)} 天里签上 {signed} 天"
        else:
            return ""
        return f"{tape}  {reading}" if tape else reading

    def _notify_next_step(self, failure: int) -> str:
        """结尾那句「接下来会怎样」。没失败就不必说话。"""
        if not failure:
            return ""
        left = self.CATCHUP_MAX_PER_DAY - self._catchup_used(datetime.now().strftime("%Y-%m-%d"))
        if left > 0:
            return f"没签上的每半小时自动再试一次，今天还剩 {left} 次"
        return "今天的自动重试用完了，处理完原因可以手动跑一次"

    def _notify_summary(self, summary: Dict[str, Any]) -> None:
        """推一条能在锁屏上一眼读完的通知。

        排版规矩见本节开头那段语法说明。这里只补两条本插件特有的：
          失败排在成功前面 —— 站点多到要折叠时，被折掉的必须是「都好」的那几个，
          不能让唯一一个出事的站点掉到折叠线下面去；
          小计紧跟明细不隔空行，像小票上的小计那样。
        """
        if not self._notify:
            return
        # 复制一份再排序：summary 还要进历史，那边保持配置顺序
        details = [item for item in (summary.get("details") or []) if isinstance(item, dict)]
        success = int(summary.get("success_count") or 0)
        failure = int(summary.get("failure_count") or 0)
        details.sort(key=lambda item: self._rank_of(item.get("status")) == self.RANK_SIGNED)

        # 全是「今日已签到」时标题已经把这句话说了，明细行不再逐行复述
        all_already = bool(details) and all(
            str(item.get("status") or "").strip() == "今日已签到" for item in details
        )
        lines: List[str] = [
            self._notify_site_line(item, terse=all_already)
            for item in details[: self.NOTIFY_SITE_LIMIT]
        ]
        if len(details) > self.NOTIFY_SITE_LIMIT:
            lines.append(f"另外 {len(details) - self.NOTIFY_SITE_LIMIT} 个站点见插件运行台")
        if total_line := self._notify_total_line(details):
            lines.append(total_line)
        if not details:
            # 一个站点都没跑起来：原因已经在标题里，这里只说下一步
            lines.append("去插件设置里打开一个站点、填好账号，明早就会自动签")

        tail = [
            text
            for text in (self._notify_next_step(failure), self._notify_record_line(success))
            if text
        ]
        if tail:
            lines.append("")
            lines.extend(tail)

        self.post_message(
            mtype=NotificationType.Plugin,
            title=(
                f"{self.NOTIFY_TITLE} · "
                f"{self._notify_verdict(success, failure, summary.get('message'), details)}"
            ),
            text="\n".join(lines),
        )

    def _run_checkin(self) -> Dict[str, Any]:
        enabled_sites = [(site_key, site_config) for site_key, site_config in self._sites.items() if self._to_bool(site_config.get("enabled", False))]
        if not enabled_sites:
            raise RuntimeError("还没有启用任何站点")

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
                    raise RuntimeError("站点的账号还没填完")
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

    def _today_schedule(self) -> Tuple[Optional[datetime], Optional[datetime]]:
        """返回（调度时区下的此刻，今天 cron 应该触发的时刻）。今天不该触发时后者为 None。"""
        trigger = self._build_trigger(self._cron)
        if not trigger:
            return None, None
        tz = getattr(trigger, "timezone", None)
        now = datetime.now(tz) if tz else datetime.now()
        try:
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            # previous_fire_time=None 表示「当作从没跑过」，于是返回 >= midnight 的第一个触发点
            fire = trigger.get_next_fire_time(None, midnight)
        except Exception as err:
            logger.warning(f"{self.plugin_name}: 推算今日触发时刻失败: {err}")
            return now, None
        return now, fire if fire and fire.date() == now.date() else None

    def _fully_signed_today(self, day: str) -> bool:
        """今天有没有过一次「签上了站点、且一个都没失败」的执行。

        看 success/failure 而不是 site_count：整次失败的记录（details 为空）经过
        _build_history_entry() 会被算成 site_count=0、failure_count=0，用 site_count
        判断会把「全军覆没」误读成「没有失败」，于是当天再也不补。
        """
        for entry in self._normalize_history():
            if not str(entry.get("time") or "").startswith(day):
                continue
            if int(entry.get("failure_count") or 0) == 0 and int(entry.get("success_count") or 0) > 0:
                return True
        return False

    def _catchup_used(self, day: str) -> int:
        state = self.get_data("catchup_state") or {}
        return int(state.get("count") or 0) if state.get("day") == day else 0

    def _catchup_run(self) -> None:
        """漏签补跑：今天该签、时刻已过、还没签成 —— 补一次。

        这条巡检是幂等的，判断顺序就是它敢每 30 分钟跑一次的理由：cron 今天不触发
        不补、还没到点不补、今天已经全签上不补、当天补够次数不补。
        """
        if not self._enabled:
            return
        now, fire = self._today_schedule()
        if not now or not fire:
            return
        if now < fire:
            return
        day = now.strftime("%Y-%m-%d")
        if self._fully_signed_today(day):
            return
        used = self._catchup_used(day)
        if used >= self.CATCHUP_MAX_PER_DAY:
            return
        if not self._run_lock.acquire(blocking=False):
            logger.info(f"{self.plugin_name}: 已有签到在执行，跳过这次补跑")
            return
        try:
            self.save_data("catchup_state", {"day": day, "count": used + 1})
            logger.info(
                f"{self.plugin_name}: 今天 {fire.strftime('%H:%M')} 那次签到没有完成，"
                f"开始第 {used + 1}/{self.CATCHUP_MAX_PER_DAY} 次补跑"
            )
            self._run_checkin()
        except Exception as err:
            logger.error(f"{self.plugin_name}: 补跑失败: {err}")
        finally:
            self._run_lock.release()

    def _scheduled_run(self) -> None:
        if not self._run_lock.acquire(blocking=False):
            logger.info(f"{self.plugin_name}: 上一次签到还在执行，跳过这次定时触发")
            return
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
        finally:
            self._run_lock.release()

    def _run_once_api(self) -> Dict[str, Any]:
        # 手动触发抢不到锁时要明确回话，不能像定时那样静默跳过 —— 用户正等着看结果
        if not self._run_lock.acquire(blocking=False):
            return {"success": False, "message": "已有一次签到正在执行，请稍后再试"}
        try:
            result = self._run_checkin()
            success = result.get("failure_count", 0) == 0 or result.get("success_count", 0) > 0
            return {"success": success, "message": result.get("message") or result.get("status"), "data": result}
        except Exception as err:
            logger.error(f"{self.plugin_name}: 手动签到失败: {err}")
            return {"success": False, "message": str(err)}
        finally:
            self._run_lock.release()

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
                    raise RuntimeError("站点的账号还没填完")
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
