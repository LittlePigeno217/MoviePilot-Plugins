from __future__ import annotations

import json
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken


def encrypt(plaintext: str, key: bytes) -> str:
    """用 Fernet 对称加密一段字符串，空串原样返回。"""
    if not plaintext:
        return ""
    return Fernet(key).encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str, key: bytes) -> Optional[str]:
    """解密 Fernet 密文。

    返回 None 表示这段内容不是本 key 能解的 Fernet 密文——可能是升级前遗留的
    明文，也可能是密钥变更或数据损坏。调用方据此决定是否保留原值。
    """
    if not ciphertext:
        return None
    try:
        return Fernet(key).decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return None


def encrypt_tokens(data: Dict[str, Any], key: bytes) -> str:
    """把 token 字典序列化成 JSON 后加密，空字典返回空串。"""
    if not data:
        return ""
    return encrypt(json.dumps(data, ensure_ascii=False, separators=(",", ":")), key)


def decrypt_tokens(ciphertext: str, key: bytes) -> Optional[Dict[str, Any]]:
    """解密 token 载荷还原成字典；无法解出时返回 None。"""
    plaintext = decrypt(ciphertext, key)
    if plaintext is None:
        return None
    try:
        parsed = json.loads(plaintext)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None
