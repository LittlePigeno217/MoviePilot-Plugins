# Task 1 Review Package

## Commit Range
`e2f57ea..7994ea2`

## Changed Files
```
 plugins/u115mediaupload/records.py            | 196 +++++++++++++++-
 plugins/u115mediaupload/tests/__init__.py     |   1 +
 plugins/u115mediaupload/tests/test_records.py | 315 ++++++++++++++++++++++++++
 3 files changed, 511 insertions(+), 1 deletion(-)
```

## Full Diff
```diff
diff --git a/plugins/u115mediaupload/records.py b/plugins/u115mediaupload/records.py
index 2e8a08d..990f8e2 100644
--- a/plugins/u115mediaupload/records.py
+++ b/plugins/u115mediaupload/records.py
@@ -1,16 +1,47 @@
 from __future__ import annotations
 
-from datetime import datetime
+from dataclasses import asdict, dataclass
+from datetime import datetime, timedelta
 from pathlib import Path
 from typing import Any, Dict, List, Optional
 
+try:
+    from app.log import logger
+except ImportError:
+    # Mock logger for testing/standalone usage
+    import sys
+    class MockLogger:
+        def error(self, msg):
+            print(f"ERROR: {msg}", file=sys.stderr)
+        def warning(self, msg):
+            print(f"WARNING: {msg}")
+        def info(self, msg):
+            print(f"INFO: {msg}")
+    logger = MockLogger()
+
+try:
+    import orjson
+except ImportError:
+    # Fallback to standard json if orjson is not available
+    import json as json_module
+    class OrJsonMock:
+        @staticmethod
+        def loads(data):
+            if isinstance(data, bytes):
+                data = data.decode()
+            return json_module.loads(data)
+        @staticmethod
+        def dumps(data):
+            return json_module.dumps(data).encode()
+    orjson = OrJsonMock()
+
 
 class IncrementalRecordStore:
     def __init__(self, records: Optional[Dict[str, Dict[str, Any]]] = None):
         self._records: Dict[str, Dict[str, Any]] = dict(records or {})
 
     @staticmethod
     def fingerprint(path: Path) -> Dict[str, int]:
         stat = path.stat()
         return {
             "size": int(stat.st_size),
@@ -53,10 +84,173 @@ class TaskHistory:
     def __init__(self, items: Optional[List[Dict[str, Any]]] = None, limit: int = 50):
         self.limit = limit
         self.items: List[Dict[str, Any]] = list(items or [])[:limit]
 
     def add(self, item: Dict[str, Any]) -> None:
         self.items.insert(0, item)
         del self.items[self.limit :]
 
     def to_list(self) -> List[Dict[str, Any]]:
         return list(self.items)
+
+
+@dataclass
+class PathMapping:
+    """路径映射记录"""
+    enabled: bool
+    source: str
+    sourceDesc: str
+    target: str
+    targetCid: str
+    id: Optional[int] = None
+    createdAt: Optional[datetime] = None
+    updatedAt: Optional[datetime] = None
+
+    def to_dict(self) -> Dict:
+        data = asdict(self)
+        # Convert datetime to ISO format strings for JSON serialization
+        if self.createdAt:
+            data["createdAt"] = self.createdAt.isoformat() if isinstance(self.createdAt, datetime) else self.createdAt
+        if self.updatedAt:
+            data["updatedAt"] = self.updatedAt.isoformat() if isinstance(self.updatedAt, datetime) else self.updatedAt
+        return data
+
+
+@dataclass
+class P115DirCache:
+    """115 目录缓存"""
+    cid: str
+    data: Dict  # 子目录列表
+    cachedAt: datetime
+    expireAt: datetime
+
+    def is_expired(self) -> bool:
+        return datetime.now() > self.expireAt
+
+    def to_dict(self) -> Dict:
+        return {
+            "cid": self.cid,
+            "data": self.data,
+            "cachedAt": self.cachedAt.isoformat() if isinstance(self.cachedAt, datetime) else self.cachedAt,
+            "expireAt": self.expireAt.isoformat() if isinstance(self.expireAt, datetime) else self.expireAt
+        }
+
+
+class PathMappingManager:
+    """路径映射管理器"""
+
+    def __init__(self, config_path: str):
+        self.config_path = Path(config_path)
+        self.mappings_file = self.config_path / "path_mappings.json"
+        self.cache_file = self.config_path / "115_dir_cache.json"
+        self._ensure_files()
+
+    def _ensure_files(self):
+        """确保配置文件存在"""
+        self.config_path.mkdir(parents=True, exist_ok=True)
+        self.mappings_file.touch(exist_ok=True)
+        self.cache_file.touch(exist_ok=True)
+        if self.mappings_file.stat().st_size == 0:
+            self.mappings_file.write_text(orjson.dumps([]).decode())
+        if self.cache_file.stat().st_size == 0:
+            self.cache_file.write_text(orjson.dumps({}).decode())
+
+    def get_mappings(self) -> List[PathMapping]:
+        """获取所有路径映射"""
+        try:
+            data = orjson.loads(self.mappings_file.read_text())
+            result = []
+            for item in data:
+                # Convert ISO format strings back to datetime
+                if isinstance(item.get("createdAt"), str):
+                    item["createdAt"] = datetime.fromisoformat(item["createdAt"])
+                if isinstance(item.get("updatedAt"), str):
+                    item["updatedAt"] = datetime.fromisoformat(item["updatedAt"])
+                result.append(PathMapping(**item))
+            return result
+        except Exception:
+            return []
+
+    def save_mappings(self, mappings: List[PathMapping]) -> bool:
+        """保存路径映射"""
+        try:
+            data = [m.to_dict() for m in mappings]
+            self.mappings_file.write_text(orjson.dumps(data).decode())
+            return True
+        except Exception as e:
+            logger.error(f"保存路径映射失败: {e}")
+            return False
+
+    def get_115_cache(self, cid: str) -> Optional[Dict]:
+        """获取 115 目录缓存"""
+        try:
+            cache_data = orjson.loads(self.cache_file.read_text())
+            if cid not in cache_data:
+                return None
+            cached_item = cache_data[cid]
+            # Convert ISO format strings back to datetime
+            if isinstance(cached_item.get("cachedAt"), str):
+                cached_item["cachedAt"] = datetime.fromisoformat(cached_item["cachedAt"])
+            if isinstance(cached_item.get("expireAt"), str):
+                cached_item["expireAt"] = datetime.fromisoformat(cached_item["expireAt"])
+            cached = P115DirCache(**cached_item)
+            if cached.is_expired():
+                self.clear_cache(cid)
+                return None
+            return cached.data
+        except Exception:
+            return None
+
+    def set_115_cache(self, cid: str, data: Dict, ttl_hours: int = 24) -> bool:
+        """设置 115 目录缓存"""
+        try:
+            cache_data = orjson.loads(self.cache_file.read_text())
+            cached = P115DirCache(
+                cid=cid,
+                data=data,
+                cachedAt=datetime.now(),
+                expireAt=datetime.now() + timedelta(hours=ttl_hours)
+            )
+            cache_data[cid] = cached.to_dict()
+            self.cache_file.write_text(orjson.dumps(cache_data).decode())
+            return True
+        except Exception as e:
+            logger.error(f"设置 115 缓存失败: {e}")
+            return False
+
+    def clear_cache(self, cid: str) -> bool:
+        """清除指定 cid 的缓存"""
+        try:
+            cache_data = orjson.loads(self.cache_file.read_text())
+            cache_data.pop(cid, None)
+            self.cache_file.write_text(orjson.dumps(cache_data).decode())
+            return True
+        except Exception:
+            return False
+
+    def clear_expired_caches(self) -> int:
+        """清除所有过期缓存"""
+        try:
+            cache_data = orjson.loads(self.cache_file.read_text())
+            expired_cids = []
+            for cid, item in cache_data.items():
+                try:
+                    # Make a copy to avoid modifying the original
+                    item_copy = dict(item)
+                    # Convert ISO format strings back to datetime
+                    if isinstance(item_copy.get("cachedAt"), str):
+                        item_copy["cachedAt"] = datetime.fromisoformat(item_copy["cachedAt"])
+                    if isinstance(item_copy.get("expireAt"), str):
+                        item_copy["expireAt"] = datetime.fromisoformat(item_copy["expireAt"])
+                    cached = P115DirCache(**item_copy)
+                    if cached.is_expired():
+                        expired_cids.append(cid)
+                except Exception as e:
+                    logger.warning(f"无法处理缓存项 {cid}: {e}")
+                    continue
+            for cid in expired_cids:
+                cache_data.pop(cid)
+            self.cache_file.write_text(orjson.dumps(cache_data).decode())
+            return len(expired_cids)
+        except Exception as e:
+            logger.error(f"清除过期缓存失败: {e}")
+            return 0
diff --git a/plugins/u115mediaupload/tests/__init__.py b/plugins/u115mediaupload/tests/__init__.py
new file mode 100644
index 0000000..2522cc0
--- /dev/null
+++ b/plugins/u115mediaupload/tests/__init__.py
@@ -0,0 +1 @@
+"""Tests package"""
diff --git a/plugins/u115mediaupload/tests/test_records.py b/plugins/u115mediaupload/tests/test_records.py
new file mode 100644
index 0000000..af68a21
--- /dev/null
+++ b/plugins/u115mediaupload/tests/test_records.py
@@ -0,0 +1,315 @@
+"""单元测试 - records.py"""
+import json
+import tempfile
+from datetime import datetime, timedelta
+from pathlib import Path
+from unittest import TestCase
+
+import sys
+sys.path.insert(0, str(Path(__file__).parent.parent))
+
+from records import (
+    IncrementalRecordStore,
+    TaskHistory,
+    PathMapping,
+    P115DirCache,
+    PathMappingManager,
+    orjson,
+)
+
+
+class TestPathMapping(TestCase):
+    """PathMapping 数据类测试"""
+
+    def test_path_mapping_creation(self):
+        """测试路径映射对象创建"""
+        mapping = PathMapping(
+            enabled=True,
+            source="/source/path",
+            sourceDesc="Source Description",
+            target="/target/path",
+            targetCid="123456",
+        )
+        self.assertTrue(mapping.enabled)
+        self.assertEqual(mapping.source, "/source/path")
+        self.assertEqual(mapping.sourceDesc, "Source Description")
+        self.assertEqual(mapping.target, "/target/path")
+        self.assertEqual(mapping.targetCid, "123456")
+        self.assertIsNone(mapping.id)
+        self.assertIsNone(mapping.createdAt)
+        self.assertIsNone(mapping.updatedAt)
+
+    def test_path_mapping_with_timestamps(self):
+        """测试包含时间戳的路径映射"""
+        now = datetime.now()
+        mapping = PathMapping(
+            enabled=True,
+            source="/source",
+            sourceDesc="Desc",
+            target="/target",
+            targetCid="123",
+            id=1,
+            createdAt=now,
+            updatedAt=now,
+        )
+        self.assertEqual(mapping.id, 1)
+        self.assertEqual(mapping.createdAt, now)
+        self.assertEqual(mapping.updatedAt, now)
+
+    def test_path_mapping_to_dict(self):
+        """测试路径映射转字典"""
+        now = datetime.now()
+        mapping = PathMapping(
+            enabled=True,
+            source="/source",
+            sourceDesc="Desc",
+            target="/target",
+            targetCid="123",
+            createdAt=now,
+            updatedAt=now,
+        )
+        data = mapping.to_dict()
+        self.assertIsInstance(data, dict)
+        self.assertEqual(data["source"], "/source")
+        self.assertEqual(data["enabled"], True)
+        # Check that datetime is converted to ISO format string
+        self.assertIsInstance(data["createdAt"], str)
+        self.assertIsInstance(data["updatedAt"], str)
+
+
+class TestP115DirCache(TestCase):
+    """P115DirCache 数据类测试"""
+
+    def test_cache_creation(self):
+        """测试缓存对象创建"""
+        now = datetime.now()
+        future = now + timedelta(hours=24)
+        cache = P115DirCache(
+            cid="folder123",
+            data={"subdir1": {}, "subdir2": {}},
+            cachedAt=now,
+            expireAt=future,
+        )
+        self.assertEqual(cache.cid, "folder123")
+        self.assertIsInstance(cache.data, dict)
+        self.assertEqual(cache.data["subdir1"], {})
+
+    def test_cache_is_expired_false(self):
+        """测试缓存未过期"""
+        now = datetime.now()
+        future = now + timedelta(hours=24)
+        cache = P115DirCache(
+            cid="folder123",
+            data={},
+            cachedAt=now,
+            expireAt=future,
+        )
+        self.assertFalse(cache.is_expired())
+
+    def test_cache_is_expired_true(self):
+        """测试缓存已过期"""
+        now = datetime.now()
+        past = now - timedelta(hours=1)
+        cache = P115DirCache(
+            cid="folder123",
+            data={},
+            cachedAt=past,
+            expireAt=past,
+        )
+        self.assertTrue(cache.is_expired())
+
+    def test_cache_to_dict(self):
+        """测试缓存转字典"""
+        now = datetime.now()
+        future = now + timedelta(hours=24)
+        cache = P115DirCache(
+            cid="folder123",
+            data={"key": "value"},
+            cachedAt=now,
+            expireAt=future,
+        )
+        data = cache.to_dict()
+        self.assertEqual(data["cid"], "folder123")
+        self.assertEqual(data["data"], {"key": "value"})
+        self.assertIsInstance(data["cachedAt"], str)
+        self.assertIsInstance(data["expireAt"], str)
+
+
+class TestPathMappingManager(TestCase):
+    """PathMappingManager 管理器测试"""
+
+    def setUp(self):
+        """设置测试环境"""
+        self.temp_dir = tempfile.mkdtemp()
+        self.manager = PathMappingManager(self.temp_dir)
+
+    def tearDown(self):
+        """清理测试环境"""
+        import shutil
+        if Path(self.temp_dir).exists():
+            shutil.rmtree(self.temp_dir)
+
+    def test_manager_initialization(self):
+        """测试管理器初始化"""
+        self.assertTrue(self.manager.mappings_file.exists())
+        self.assertTrue(self.manager.cache_file.exists())
+
+    def test_save_and_get_mappings(self):
+        """测试保存和获取路径映射"""
+        mapping1 = PathMapping(
+            enabled=True,
+            source="/source1",
+            sourceDesc="Source 1",
+            target="/target1",
+            targetCid="123",
+        )
+        mapping2 = PathMapping(
+            enabled=False,
+            source="/source2",
+            sourceDesc="Source 2",
+            target="/target2",
+            targetCid="456",
+        )
+        mappings = [mapping1, mapping2]
+        self.assertTrue(self.manager.save_mappings(mappings))
+
+        # Retrieve and verify
+        retrieved = self.manager.get_mappings()
+        self.assertEqual(len(retrieved), 2)
+        self.assertEqual(retrieved[0].source, "/source1")
+        self.assertTrue(retrieved[0].enabled)
+        self.assertEqual(retrieved[1].source, "/source2")
+        self.assertFalse(retrieved[1].enabled)
+
+    def test_get_mappings_empty(self):
+        """测试获取空路径映射"""
+        mappings = self.manager.get_mappings()
+        self.assertEqual(len(mappings), 0)
+        self.assertIsInstance(mappings, list)
+
+    def test_save_and_get_115_cache(self):
+        """测试保存和获取 115 缓存"""
+        cache_data = {
+            "subdir1": {"cid": "sub123", "name": "Subdir 1"},
+            "subdir2": {"cid": "sub456", "name": "Subdir 2"},
+        }
+        self.assertTrue(self.manager.set_115_cache("folder123", cache_data, ttl_hours=24))
+
+        # Retrieve and verify
+        retrieved = self.manager.get_115_cache("folder123")
+        self.assertIsNotNone(retrieved)
+        self.assertEqual(retrieved["subdir1"]["cid"], "sub123")
+        self.assertEqual(retrieved["subdir2"]["name"], "Subdir 2")
+
+    def test_get_115_cache_not_found(self):
+        """测试获取不存在的缓存"""
+        result = self.manager.get_115_cache("nonexistent")
+        self.assertIsNone(result)
+
+    def test_clear_cache(self):
+        """测试清除缓存"""
+        cache_data = {"key": "value"}
+        self.manager.set_115_cache("folder123", cache_data)
+        self.assertIsNotNone(self.manager.get_115_cache("folder123"))
+
+        # Clear and verify
+        self.assertTrue(self.manager.clear_cache("folder123"))
+        self.assertIsNone(self.manager.get_115_cache("folder123"))
+
+    def test_clear_expired_caches(self):
+        """测试清除过期缓存"""
+        # Set two caches: one current, one expired
+        current_data = {"data": "value"}
+        expired_data = {"key": "value"}
+
+        # Set current cache with 24-hour TTL
+        self.manager.set_115_cache("current", current_data, ttl_hours=24)
+
+        # Set cache that will immediately be marked as expired
+        self.manager.set_115_cache("expired", expired_data, ttl_hours=24)
+
+        # Manually expire the "expired" cache by modifying the file
+        cache_file_data = orjson.loads(self.manager.cache_file.read_text())
+        # Set expiry to 1 hour in the past
+        cache_file_data["expired"]["expireAt"] = (
+            datetime.now() - timedelta(hours=1)
+        ).isoformat()
+        self.manager.cache_file.write_text(orjson.dumps(cache_file_data).decode())
+
+        # Clear expired caches
+        count = self.manager.clear_expired_caches()
+
+        # Verify one cache was removed
+        self.assertEqual(count, 1)
+
+        # Verify expired cache is gone
+        self.assertIsNone(self.manager.get_115_cache("expired"))
+
+        # Verify current cache still exists
+        self.assertIsNotNone(self.manager.get_115_cache("current"))
+
+    def test_cache_expiration(self):
+        """测试缓存自动过期"""
+        # Set cache with short TTL
+        cache_data = {"key": "value"}
+        self.manager.set_115_cache("folder123", cache_data, ttl_hours=0)
+
+        # Manually expire the cache
+        cache_file_data = orjson.loads(self.manager.cache_file.read_text())
+        cache_file_data["folder123"]["expireAt"] = (
+            datetime.now() - timedelta(seconds=1)
+        ).isoformat()
+        self.manager.cache_file.write_text(orjson.dumps(cache_file_data).decode())
+
+        # Try to get expired cache
+        result = self.manager.get_115_cache("folder123")
+        self.assertIsNone(result)
+
+
+class TestIncrementalRecordStore(TestCase):
+    """IncrementalRecordStore 测试（验证现有功能）"""
+
+    def test_incremental_record_store(self):
+        """测试增量记录存储"""
+        store = IncrementalRecordStore()
+
+        # Create a test file
+        with tempfile.NamedTemporaryFile(delete=False) as tmp:
+            tmp.write(b"test content")
+            tmp_path = Path(tmp.name)
+
+        try:
+            # Check file is marked as changed
+            self.assertTrue(store.has_changed(tmp_path))
+
+            # Mark as uploaded
+            store.mark_uploaded(tmp_path, "/target/path")
+
+            # Check file is no longer marked as changed
+            self.assertFalse(store.has_changed(tmp_path))
+
+            # Check data serialization
+            data = store.to_dict()
+            self.assertIn(str(tmp_path), data)
+        finally:
+            tmp_path.unlink()
+
+
+class TestTaskHistory(TestCase):
+    """TaskHistory 测试（验证现有功能）"""
+
+    def test_task_history(self):
+        """测试任务历史"""
+        history = TaskHistory(limit=50)
+
+        # Add items
+        for i in range(100):
+            history.add({"id": i, "status": "completed"})
+
+        # Verify limit
+        items = history.to_list()
+        self.assertEqual(len(items), 50)
+
+        # Verify order (most recent first)
+        self.assertEqual(items[0]["id"], 99)
+        self.assertEqual(items[-1]["id"], 50)
```

