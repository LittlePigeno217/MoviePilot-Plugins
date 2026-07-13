"""
115 媒体上传插件 - API 处理器
"""
from typing import Dict, Any, Optional, List
from pathlib import Path
from base64 import b64encode
from io import BytesIO
from datetime import datetime

try:
    from qrcode import make as qr_make
except ImportError:
    qr_make = None

from fastapi import Query, Body
try:
    from orjson import dumps, loads
except ImportError:
    import json
    dumps = lambda x: json.dumps(x).encode()
    loads = json.loads

try:
    from app.log import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

try:
    from app.core.config import settings
except ImportError:
    settings = type("Settings", (), {"LIBRARY_PATH": "/media"})()

from .records import PathMapping, PathMappingManager


class U115MediaUploadApiHandler:
    """115 媒体上传 API 处理器"""

    def __init__(self, client: Any, mapping_manager: PathMappingManager):
        self.client = client
        self.mapping_manager = mapping_manager

    def generate_qrcode(self) -> Dict[str, Any]:
        """
        生成 115 登录二维码

        Returns:
            {"success": true, "data": {"qrcode": "data:image/png;base64,...", "codeContent": "..."}}
        """
        try:
            if qr_make is None:
                return {"success": False, "msg": "qrcode 库未安装"}

            # 调用 client 获取二维码内容
            qr_data = self.client.generate_qrcode()
            if not qr_data.get("success"):
                return {"success": False, "msg": qr_data.get("message") or "获取二维码内容失败"}

            code_content = (qr_data.get("data") or {}).get("codeContent", "")

            if not code_content:
                return {"success": False, "msg": "获取二维码内容失败"}

            # 用 qrcode 库生成 PNG 图片
            img = qr_make(code_content)
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            base64_string = b64encode(buffered.getvalue()).decode("utf-8")

            logger.info(f"[115MediaUpload] 二维码生成成功")

            return {
                "success": True,
                "data": {
                    "qrcode": f"data:image/png;base64,{base64_string}",
                    "codeContent": code_content
                }
            }
        except Exception as e:
            logger.error(f"[115MediaUpload] 二维码生成失败: {e}")
            return {"success": False, "msg": f"二维码生成失败: {str(e)}"}

    def browse_local(self, path: str = "") -> Dict[str, Any]:
        """
        浏览本地目录（从媒体库根目录开始）

        Args:
            path: 相对于媒体库根目录的路径（如 "movies" 或 "tv"）

        Returns:
            {
                "success": true,
                "data": {
                    "base": "/media",
                    "current": "movies",
                    "items": [
                        {"name": "dir1", "path": "movies/dir1", "is_dir": true}
                    ]
                }
            }
        """
        try:
            base_path = Path(settings.LIBRARY_PATH or "/media")

            if not base_path.exists():
                return {"success": False, "msg": f"媒体库目录不存在: {base_path}"}

            # 构建目标路径
            target_path = base_path / path if path else base_path

            # 安全检查：确保 target_path 在 base_path 下
            try:
                target_path.relative_to(base_path)
            except ValueError:
                return {"success": False, "msg": "路径超出允许范围"}

            if not target_path.exists():
                return {"success": False, "msg": f"目录不存在: {target_path}"}

            if not target_path.is_dir():
                return {"success": False, "msg": f"目标不是目录: {target_path}"}

            # 列出所有子目录
            items = []
            try:
                for item in sorted(target_path.iterdir(), key=lambda x: x.name):
                    if item.is_dir() and not item.name.startswith("."):
                        rel_path = str(item.relative_to(base_path))
                        items.append({
                            "name": item.name,
                            "path": rel_path,
                            "is_dir": True
                        })
            except PermissionError:
                return {"success": False, "msg": f"无权限访问目录: {target_path}"}

            current = str(target_path.relative_to(base_path)) if target_path != base_path else ""

            return {
                "success": True,
                "data": {
                    "base": str(base_path),
                    "current": current,
                    "items": items
                }
            }
        except Exception as e:
            logger.error(f"[115MediaUpload] 浏览本地目录失败: {e}")
            return {"success": False, "msg": f"浏览本地目录失败: {str(e)}"}

    def browse_115(self, cid: str = "0", refresh: bool = False) -> Dict[str, Any]:
        """
        浏览 115 云盘目录（支持缓存和刷新）

        Args:
            cid: 115 目录 ID（"0" 表示根目录）
            refresh: 是否刷新缓存

        Returns:
            {
                "success": true,
                "data": {
                    "cid": "0",
                    "cached": false,
                    "items": [
                        {"name": "dir1", "cid": "123", "is_dir": true}
                    ]
                }
            }
        """
        try:
            if not self.client:
                return {"success": False, "msg": "115 客户端未初始化"}

            # 检查缓存
            cached = False
            if not refresh:
                cache_data = self.mapping_manager.get_115_cache(cid)
                if cache_data:
                    logger.debug(f"[115MediaUpload] 使用 115 目录缓存: {cid}")
                    return {
                        "success": True,
                        "data": {
                            "cid": cid,
                            "cached": True,
                            "items": cache_data.get("items", [])
                        }
                    }

            # 调用 115 API 获取目录列表
            items = self.client.get_dir_list(cid=cid)

            # 过滤出目录项
            dir_items = [
                {
                    "name": item.get("name", ""),
                    "cid": item.get("cid", ""),
                    "is_dir": item.get("type") == 1
                }
                for item in items if item.get("type") == 1  # 只返回目录
            ]

            # 缓存结果
            cache_content = {"items": dir_items}
            self.mapping_manager.set_115_cache(cid, cache_content, ttl_hours=24)

            logger.info(f"[115MediaUpload] 获取 115 目录成功: {cid}, 项数: {len(dir_items)}")

            return {
                "success": True,
                "data": {
                    "cid": cid,
                    "cached": False,
                    "items": dir_items
                }
            }
        except Exception as e:
            logger.error(f"[115MediaUpload] 浏览 115 目录失败: {e}")
            return {"success": False, "msg": f"浏览 115 目录失败: {str(e)}"}

    def save_path_mappings(self, mappings: List[Dict]) -> Dict[str, Any]:
        """
        保存路径映射配置

        Args:
            mappings: [
                {
                    "enabled": true,
                    "source": "/movies",
                    "sourceDesc": "movies",
                    "target": "/115/movies",
                    "targetCid": "123"
                }
            ]

        Returns:
            {"success": true, "msg": "映射保存成功"}
        """
        try:
            # 转换为 PathMapping 对象
            path_mappings = [
                PathMapping(
                    enabled=m.get("enabled", True),
                    source=m.get("source", ""),
                    sourceDesc=m.get("sourceDesc", ""),
                    target=m.get("target", ""),
                    targetCid=m.get("targetCid", "0")
                )
                for m in mappings
            ]

            # 保存到管理器
            if self.mapping_manager.save_mappings(path_mappings):
                logger.info(f"[115MediaUpload] 路径映射保存成功, 项数: {len(path_mappings)}")
                return {"success": True, "msg": "映射保存成功"}
            else:
                return {"success": False, "msg": "映射保存失败"}
        except Exception as e:
            logger.error(f"[115MediaUpload] 保存路径映射失败: {e}")
            return {"success": False, "msg": f"保存失败: {str(e)}"}
