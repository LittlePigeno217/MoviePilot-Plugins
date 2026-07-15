from __future__ import annotations

import re


_SENSITIVE_VALUE = re.compile(
    r"(?i)\b(?P<key>uid|cid|seid|kid|cookie|access_token|refresh_token|authorization|apikey|pickcode)"
    r"(?P<separator>\s*['\"]?\s*[:=]\s*['\"]?(?:bearer\s+)?)"
    r"(?P<value>[^;,\s'\"&}]+)"
)


def safe_error_text(error: BaseException, limit: int = 500) -> str:
    text = " ".join(str(error).split())
    text = _SENSITIVE_VALUE.sub(
        lambda match: f"{match.group('key')}{match.group('separator')}***",
        text,
    )
    if len(text) > limit:
        text = f"{text[:limit]}..."
    return text or error.__class__.__name__
