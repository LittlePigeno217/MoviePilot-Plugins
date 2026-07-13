# Task 2 Review Package

## Commit Range
7994ea2..66a16bb

## Changed Files
 plugins/u115mediaupload/__init__.py                |  37 ++-
 plugins/u115mediaupload/api_handlers.py            | 261 +++++++++++++++++++++
 plugins/u115mediaupload/client.py                  |  14 ++
 plugins/u115mediaupload/tests/test_api_handlers.py | 185 +++++++++++++++
 4 files changed, 495 insertions(+), 2 deletions(-)

## Full Diff
```diff
diff --git a/plugins/u115mediaupload/__init__.py b/plugins/u115mediaupload/__init__.py
index 37eafaa..92cf02f 100644
--- a/plugins/u115mediaupload/__init__.py
+++ b/plugins/u115mediaupload/__init__.py
@@ -40,23 +40,24 @@ except Exception:  # pragma: no cover
         @staticmethod
         def register(*args, **kwargs):
             def decorator(func):
                 return func
 
             return decorator
 
     eventmanager = _EventManager()
 
 from .client import U115AuthError, U115Client
-from .records import IncrementalRecordStore, TaskHistory
+from .records import IncrementalRecordStore, TaskHistory, PathMappingManager
 from .scanner import MediaScanner, UploadPlanItem
 from .scraper import MetadataScraper
+from .api_handlers import U115MediaUploadApiHandler
 
 
 DEFAULT_CONFIG: Dict[str, Any] = {
     "enabled": False,
     "auth_mode": "cookie",
     "cookie": "",
     "tokens": {},
     "path_mappings": [],
     "media_extensions": [
         ".mkv",
@@ -100,20 +101,24 @@ class U115MediaUpload(_PluginBase):
     plugin_order = 51
     auth_level = 1
 
     def __init__(self):
         super().__init__()
         self._config: Dict[str, Any] = dict(DEFAULT_CONFIG)
         self._task_lock = threading.Lock()
         self._stop_event = threading.Event()
         self._task_thread: Optional[threading.Thread] = None
         self._status: Dict[str, Any] = self._default_status()
+        self._mapping_manager = PathMappingManager(
+            config_path=str(self.get_plugin_config_path())
+        )
+        self._api_handler: Optional[U115MediaUploadApiHandler] = None
 
     def init_plugin(self, config: dict = None):
         self._config = self._merge_config(config or self.get_config() or {})
         self._status = self.get_data("last_status") or self._default_status()
         self._stop_event.clear()
 
     def get_state(self) -> bool:
         return bool(self._config.get("enabled"))
 
     @staticmethod
@@ -160,20 +165,23 @@ class U115MediaUpload(_PluginBase):
             {"path": "/config", "endpoint": self._get_config_api, "methods": ["GET"], "auth": "bear", "summary": "获取配置"},
             {"path": "/config", "endpoint": self._save_config_api, "methods": ["POST"], "auth": "bear", "summary": "保存配置"},
             {"path": "/status", "endpoint": self._get_status_api, "methods": ["GET"], "auth": "bear", "summary": "获取状态"},
             {"path": "/run_full", "endpoint": self._run_full_api, "methods": ["POST"], "auth": "bear", "summary": "执行全量上传"},
             {"path": "/run_incremental", "endpoint": self._run_incremental_api, "methods": ["POST"], "auth": "bear", "summary": "执行增量上传"},
             {"path": "/stop", "endpoint": self._stop_api, "methods": ["POST"], "auth": "bear", "summary": "停止任务"},
             {"path": "/qrcode", "endpoint": self._qrcode_api, "methods": ["POST"], "auth": "bear", "summary": "生成 115 登录二维码"},
             {"path": "/check_login", "endpoint": self._check_login_api, "methods": ["GET"], "auth": "bear", "summary": "检查 115 登录状态"},
             {"path": "/history", "endpoint": self._history_api, "methods": ["GET"], "auth": "bear", "summary": "获取历史"},
             {"path": "/clear_records", "endpoint": self._clear_records_api, "methods": ["POST"], "auth": "bear", "summary": "清理增量记录"},
+            {"path": "/browse_local", "endpoint": self._browse_local_api, "methods": ["GET"], "auth": "bear", "summary": "浏览本地目录"},
+            {"path": "/browse_115", "endpoint": self._browse_115_api, "methods": ["GET"], "auth": "bear", "summary": "浏览 115 云盘目录"},
+            {"path": "/path_mappings", "endpoint": self._save_path_mappings_api, "methods": ["POST"], "auth": "bear", "summary": "保存路径映射"},
         ]
 
     def stop_service(self):
         self._stop_event.set()
 
     @eventmanager.register(EventType.TransferComplete)
     def transfer_complete(self, event):
         if not self.get_state() or not self._config.get("event_incremental"):
             return
         event_data = getattr(event, "event_data", None) or {}
@@ -202,31 +210,56 @@ class U115MediaUpload(_PluginBase):
 
     def _run_incremental_api(self) -> Dict[str, Any]:
         return self._start_task("incremental")
 
     def _stop_api(self) -> Dict[str, Any]:
         self._stop_event.set()
         return {"success": True, "message": "已请求停止任务", "data": self._status_payload()}
 
     def _qrcode_api(self) -> Dict[str, Any]:
         client = self._make_client(require_cookie=False)
-        return client.generate_qrcode()
+        if not self._api_handler:
+            self._api_handler = U115MediaUploadApiHandler(client, self._mapping_manager)
+        return self._api_handler.generate_qrcode()
 
     def _check_login_api(self) -> Dict[str, Any]:
         client = self._make_client(require_cookie=False)
         result = client.check_login()
         if result.get("success") and (result.get("data") or {}).get("status") == 2:
             self._config["tokens"] = client.export_tokens()
             self._config["auth_mode"] = "qrcode"
             self.update_config(self._config)
         return result
 
+    def _browse_local_api(self, path: str = "") -> Dict[str, Any]:
+        """浏览本地目录 API"""
+        if not self._api_handler:
+            client = self._make_client(require_cookie=False)
+            self._api_handler = U115MediaUploadApiHandler(client, self._mapping_manager)
+        return self._api_handler.browse_local(path)
+
+    def _browse_115_api(self, cid: str = "0", refresh: bool = False) -> Dict[str, Any]:
+        """浏览 115 目录 API"""
+        if not self._api_handler:
+            client = self._make_client(require_cookie=False)
+            self._api_handler = U115MediaUploadApiHandler(client, self._mapping_manager)
+        return self._api_handler.browse_115(cid, refresh)
+
+    def _save_path_mappings_api(self, mappings: List[Dict] = None) -> Dict[str, Any]:
+        """保存路径映射 API"""
+        if not mappings:
+            mappings = []
+        if not self._api_handler:
+            client = self._make_client(require_cookie=False)
+            self._api_handler = U115MediaUploadApiHandler(client, self._mapping_manager)
+        return self._api_handler.save_path_mappings(mappings)
+
     def _history_api(self) -> Dict[str, Any]:
         return {
             "success": True,
             "data": {
                 "history": self.get_data("history") or [],
                 "failures": self.get_data("failures") or [],
                 "records": self.get_data("records") or {},
             },
         }
 
diff --git a/plugins/u115mediaupload/api_handlers.py b/plugins/u115mediaupload/api_handlers.py
new file mode 100644
index 0000000..9fb1fbf
--- /dev/null
+++ b/plugins/u115mediaupload/api_handlers.py
@@ -0,0 +1,261 @@
+"""
+115 媒体上传插件 - API 处理器
+"""
+from typing import Dict, Any, Optional, List
+from pathlib import Path
+from base64 import b64encode
+from io import BytesIO
+from datetime import datetime
+
+try:
+    from qrcode import make as qr_make
+except ImportError:
+    qr_make = None
+
+from fastapi import Query, Body
+try:
+    from orjson import dumps, loads
+except ImportError:
+    import json
+    dumps = lambda x: json.dumps(x).encode()
+    loads = json.loads
+
+try:
+    from app.log import logger
+except ImportError:
+    import logging
+    logger = logging.getLogger(__name__)
+
+try:
+    from app.core.config import settings
+except ImportError:
+    settings = type("Settings", (), {"LIBRARY_PATH": "/media"})()
+
+from .records import PathMapping, PathMappingManager
+
+
+class U115MediaUploadApiHandler:
+    """115 媒体上传 API 处理器"""
+
+    def __init__(self, client: Any, mapping_manager: PathMappingManager):
+        self.client = client
+        self.mapping_manager = mapping_manager
+
+    def generate_qrcode(self) -> Dict[str, Any]:
+        """
+        生成 115 登录二维码
+
+        Returns:
+            {"success": true, "data": {"qrcode": "data:image/png;base64,...", "codeContent": "..."}}
+        """
+        try:
+            if qr_make is None:
+                return {"success": False, "msg": "qrcode 库未安装"}
+
+            # 调用 client 获取二维码内容
+            qr_data = self.client.generate_qrcode()
+            if not qr_data.get("success"):
+                return {"success": False, "msg": qr_data.get("message") or "获取二维码内容失败"}
+
+            code_content = (qr_data.get("data") or {}).get("codeContent", "")
+
+            if not code_content:
+                return {"success": False, "msg": "获取二维码内容失败"}
+
+            # 用 qrcode 库生成 PNG 图片
+            img = qr_make(code_content)
+            buffered = BytesIO()
+            img.save(buffered, format="PNG")
+            base64_string = b64encode(buffered.getvalue()).decode("utf-8")
+
+            logger.info(f"[115MediaUpload] 二维码生成成功")
+
+            return {
+                "success": True,
+                "data": {
+                    "qrcode": f"data:image/png;base64,{base64_string}",
+                    "codeContent": code_content
+                }
+            }
+        except Exception as e:
+            logger.error(f"[115MediaUpload] 二维码生成失败: {e}")
+            return {"success": False, "msg": f"二维码生成失败: {str(e)}"}
+
+    def browse_local(self, path: str = "") -> Dict[str, Any]:
+        """
+        浏览本地目录（从媒体库根目录开始）
+
+        Args:
+            path: 相对于媒体库根目录的路径（如 "movies" 或 "tv"）
+
+        Returns:
+            {
+                "success": true,
+                "data": {
+                    "base": "/media",
+                    "current": "movies",
+                    "items": [
+                        {"name": "dir1", "path": "movies/dir1", "is_dir": true}
+                    ]
+                }
+            }
+        """
+        try:
+            base_path = Path(settings.LIBRARY_PATH or "/media")
+
+            if not base_path.exists():
+                return {"success": False, "msg": f"媒体库目录不存在: {base_path}"}
+
+            # 构建目标路径
+            target_path = base_path / path if path else base_path
+
+            # 安全检查：确保 target_path 在 base_path 下
+            try:
+                target_path.relative_to(base_path)
+            except ValueError:
+                return {"success": False, "msg": "路径超出允许范围"}
+
+            if not target_path.exists():
+                return {"success": False, "msg": f"目录不存在: {target_path}"}
+
+            if not target_path.is_dir():
+                return {"success": False, "msg": f"目标不是目录: {target_path}"}
+
+            # 列出所有子目录
+            items = []
+            try:
+                for item in sorted(target_path.iterdir(), key=lambda x: x.name):
+                    if item.is_dir() and not item.name.startswith("."):
+                        rel_path = str(item.relative_to(base_path))
+                        items.append({
+                            "name": item.name,
+                            "path": rel_path,
+                            "is_dir": True
+                        })
+            except PermissionError:
+                return {"success": False, "msg": f"无权限访问目录: {target_path}"}
+
+            current = str(target_path.relative_to(base_path)) if target_path != base_path else ""
+
+            return {
+                "success": True,
+                "data": {
+                    "base": str(base_path),
+                    "current": current,
+                    "items": items
+                }
+            }
+        except Exception as e:
+            logger.error(f"[115MediaUpload] 浏览本地目录失败: {e}")
+            return {"success": False, "msg": f"浏览本地目录失败: {str(e)}"}
+
+    def browse_115(self, cid: str = "0", refresh: bool = False) -> Dict[str, Any]:
+        """
+        浏览 115 云盘目录（支持缓存和刷新）
+
+        Args:
+            cid: 115 目录 ID（"0" 表示根目录）
+            refresh: 是否刷新缓存
+
+        Returns:
+            {
+                "success": true,
+                "data": {
+                    "cid": "0",
+                    "cached": false,
+                    "items": [
+                        {"name": "dir1", "cid": "123", "is_dir": true}
+                    ]
+                }
+            }
+        """
+        try:
+            if not self.client:
+                return {"success": False, "msg": "115 客户端未初始化"}
+
+            # 检查缓存
+            cached = False
+            if not refresh:
+                cache_data = self.mapping_manager.get_115_cache(cid)
+                if cache_data:
+                    logger.debug(f"[115MediaUpload] 使用 115 目录缓存: {cid}")
+                    return {
+                        "success": True,
+                        "data": {
+                            "cid": cid,
+                            "cached": True,
+                            "items": cache_data.get("items", [])
+                        }
+                    }
+
+            # 调用 115 API 获取目录列表
+            items = self.client.get_dir_list(cid=cid)
+
+            # 过滤出目录项
+            dir_items = [
+                {
+                    "name": item.get("name", ""),
+                    "cid": item.get("cid", ""),
+                    "is_dir": item.get("type") == 1
+                }
+                for item in items if item.get("type") == 1  # 只返回目录
+            ]
+
+            # 缓存结果
+            cache_content = {"items": dir_items}
+            self.mapping_manager.set_115_cache(cid, cache_content, ttl_hours=24)
+
+            logger.info(f"[115MediaUpload] 获取 115 目录成功: {cid}, 项数: {len(dir_items)}")
+
+            return {
+                "success": True,
+                "data": {
+                    "cid": cid,
+                    "cached": False,
+                    "items": dir_items
+                }
+            }
+        except Exception as e:
+            logger.error(f"[115MediaUpload] 浏览 115 目录失败: {e}")
+            return {"success": False, "msg": f"浏览 115 目录失败: {str(e)}"}
+
+    def save_path_mappings(self, mappings: List[Dict]) -> Dict[str, Any]:
+        """
+        保存路径映射配置
+
+        Args:
+            mappings: [
+                {
+                    "enabled": true,
+                    "source": "/movies",
+                    "sourceDesc": "movies",
+                    "target": "/115/movies",
+                    "targetCid": "123"
+                }
+            ]
+
+        Returns:
+            {"success": true, "msg": "映射保存成功"}
+        """
+        try:
+            # 转换为 PathMapping 对象
+            path_mappings = [
+                PathMapping(
+                    enabled=m.get("enabled", True),
+                    source=m.get("source", ""),
+                    sourceDesc=m.get("sourceDesc", ""),
+                    target=m.get("target", ""),
+                    targetCid=m.get("targetCid", "0")
+                )
+                for m in mappings
+            ]
+
+            # 保存到管理器
+            if self.mapping_manager.save_mappings(path_mappings):
+                logger.info(f"[115MediaUpload] 路径映射保存成功, 项数: {len(path_mappings)}")
+                return {"success": True, "msg": "映射保存成功"}
+            else:
+                return {"success": False, "msg": "映射保存失败"}
+        except Exception as e:
+            logger.error(f"[115MediaUpload] 保存路径映射失败: {e}")
+            return {"success": False, "msg": f"保存失败: {str(e)}"}
diff --git a/plugins/u115mediaupload/client.py b/plugins/u115mediaupload/client.py
index c061f56..0fcfe0e 100644
--- a/plugins/u115mediaupload/client.py
+++ b/plugins/u115mediaupload/client.py
@@ -465,13 +465,27 @@ class U115Client:
             "storage": "u115",
             "fileid": str(info.get("file_id") or info.get("fid") or ""),
             "path": path,
             "type": "file" if category == "1" else "dir",
             "name": info.get("file_name") or PurePosixPath(path).name,
             "pickcode": info.get("pick_code") or info.get("pickcode"),
             "size": info.get("size_byte") or info.get("size"),
             "modify_time": info.get("utime") or info.get("modify_time"),
         }
 
+    def get_dir_list(self, cid: str = "0") -> list:
+        """获取 115 目录列表"""
+        result = self._request(
+            "POST",
+            "/open/folder/list",
+            data={"cid": cid},
+            no_error=True,
+        )
+        data = self._response_data(result)
+        if not data:
+            return []
+        items = data.get("items", []) if isinstance(data, dict) else data
+        return list(items) if isinstance(items, list) else []
+
     def _log_warning(self, message: str) -> None:
         if self.logger and hasattr(self.logger, "warning"):
             self.logger.warning(message)
diff --git a/plugins/u115mediaupload/tests/test_api_handlers.py b/plugins/u115mediaupload/tests/test_api_handlers.py
new file mode 100644
index 0000000..cf057b8
--- /dev/null
+++ b/plugins/u115mediaupload/tests/test_api_handlers.py
@@ -0,0 +1,185 @@
+import pytest
+from pathlib import Path
+from unittest.mock import Mock, MagicMock, patch
+from plugins.u115mediaupload.api_handlers import U115MediaUploadApiHandler
+from plugins.u115mediaupload.records import PathMappingManager
+
+
+def test_generate_qrcode():
+    """测试二维码生成"""
+    client = Mock()
+    client.generate_qrcode.return_value = {
+        "success": True,
+        "data": {"codeContent": "https://115.com/qrcode/test"}
+    }
+
+    manager = Mock(spec=PathMappingManager)
+    handler = U115MediaUploadApiHandler(client, manager)
+
+    result = handler.generate_qrcode()
+
+    assert result["success"] is True
+    assert "qrcode" in result["data"]
+    assert result["data"]["qrcode"].startswith("data:image/png;base64,")
+    assert result["data"]["codeContent"] == "https://115.com/qrcode/test"
+
+
+def test_browse_local_root(tmp_path):
+    """测试浏览本地目录根目录"""
+    # 创建测试目录结构
+    (tmp_path / "movie1").mkdir()
+    (tmp_path / "movie2").mkdir()
+    (tmp_path / ".hidden").mkdir()
+
+    client = Mock()
+    manager = Mock(spec=PathMappingManager)
+    handler = U115MediaUploadApiHandler(client, manager)
+
+    # 模拟 settings.LIBRARY_PATH
+    with patch("plugins.u115mediaupload.api_handlers.settings") as mock_settings:
+        mock_settings.LIBRARY_PATH = str(tmp_path)
+
+        result = handler.browse_local("")
+
+        assert result["success"] is True
+        assert result["data"]["base"] == str(tmp_path)
+        assert result["data"]["current"] == ""
+        assert len(result["data"]["items"]) == 2
+        assert result["data"]["items"][0]["name"] == "movie1"
+        assert result["data"]["items"][0]["is_dir"] is True
+
+
+def test_browse_local_subdirectory(tmp_path):
+    """测试浏览本地子目录"""
+    # 创建测试目录结构
+    movies_dir = tmp_path / "movies"
+    movies_dir.mkdir()
+    (movies_dir / "movie1").mkdir()
+    (movies_dir / "movie2").mkdir()
+
+    client = Mock()
+    manager = Mock(spec=PathMappingManager)
+    handler = U115MediaUploadApiHandler(client, manager)
+
+    with patch("plugins.u115mediaupload.api_handlers.settings") as mock_settings:
+        mock_settings.LIBRARY_PATH = str(tmp_path)
+
+        result = handler.browse_local("movies")
+
+        assert result["success"] is True
+        assert result["data"]["current"] == "movies"
+        assert len(result["data"]["items"]) == 2
+
+
+def test_browse_115_with_cache(tmp_path):
+    """测试 115 目录浏览和缓存"""
+    client = Mock()
+    client.get_dir_list.return_value = [
+        {"name": "folder1", "cid": "123", "type": 1},
+        {"name": "folder2", "cid": "124", "type": 1},
+    ]
+
+    manager = PathMappingManager(config_path=str(tmp_path))
+    handler = U115MediaUploadApiHandler(client, manager)
+
+    # 第一次调用（无缓存）
+    result1 = handler.browse_115("0", refresh=False)
+    assert result1["success"] is True
+    assert result1["data"]["cached"] is False
+    assert len(result1["data"]["items"]) == 2
+
+    # 第二次调用（有缓存）
+    result2 = handler.browse_115("0", refresh=False)
+    assert result2["success"] is True
+    assert result2["data"]["cached"] is True
+
+    # 调用刷新
+    client.get_dir_list.return_value = [
+        {"name": "folder1", "cid": "123", "type": 1},
+    ]
+    result3 = handler.browse_115("0", refresh=True)
+    assert result3["success"] is True
+    assert result3["data"]["cached"] is False
+    assert len(result3["data"]["items"]) == 1
+
+
+def test_save_path_mappings(tmp_path):
+    """测试保存路径映射"""
+    client = Mock()
+    manager = PathMappingManager(config_path=str(tmp_path))
+    handler = U115MediaUploadApiHandler(client, manager)
+
+    mappings = [
+        {
+            "enabled": True,
+            "source": "/movies",
+            "sourceDesc": "movies",
+            "target": "/115/movies",
+            "targetCid": "123"
+        },
+        {
+            "enabled": False,
+            "source": "/tv",
+            "sourceDesc": "tv",
+            "target": "/115/tv",
+            "targetCid": "124"
+        }
+    ]
+
+    result = handler.save_path_mappings(mappings)
+
+    assert result["success"] is True
+
+    # 验证保存结果
+    saved = manager.get_mappings()
+    assert len(saved) == 2
+    assert saved[0].source == "/movies"
+    assert saved[1].enabled is False
+
+
+def test_browse_115_no_client():
+    """测试 115 目录浏览无客户端情况"""
+    manager = Mock(spec=PathMappingManager)
+    handler = U115MediaUploadApiHandler(None, manager)
+
+    result = handler.browse_115("0")
+
+    assert result["success"] is False
+    assert "未初始化" in result["msg"]
+
+
+def test_browse_local_invalid_path(tmp_path):
+    """测试浏览本地无效路径"""
+    client = Mock()
+    manager = Mock(spec=PathMappingManager)
+    handler = U115MediaUploadApiHandler(client, manager)
+
+    with patch("plugins.u115mediaupload.api_handlers.settings") as mock_settings:
+        mock_settings.LIBRARY_PATH = str(tmp_path)
+
+        result = handler.browse_local("nonexistent")
+
+        assert result["success"] is False
+        assert "不存在" in result["msg"]
+
+
+def test_browse_115_filters_directories():
+    """测试 115 目录浏览过滤非目录项"""
+    client = Mock()
+    client.get_dir_list.return_value = [
+        {"name": "folder1", "cid": "123", "type": 1},  # 目录
+        {"name": "file1.txt", "cid": "124", "type": 0},  # 文件
+        {"name": "folder2", "cid": "125", "type": 1},  # 目录
+    ]
+
+    manager = Mock(spec=PathMappingManager)
+    manager.get_115_cache.return_value = None
+    manager.set_115_cache.return_value = True
+    handler = U115MediaUploadApiHandler(client, manager)
+
+    result = handler.browse_115("0")
+
+    assert result["success"] is True
+    # 应该只返回 2 个目录，文件被过滤掉
+    assert len(result["data"]["items"]) == 2
+    assert all(item["is_dir"] for item in result["data"]["items"])
```
