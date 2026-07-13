"""单元测试 - records.py"""
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import TestCase

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from records import (
    IncrementalRecordStore,
    TaskHistory,
    PathMapping,
    P115DirCache,
    PathMappingManager,
    orjson,
)


class TestPathMapping(TestCase):
    """PathMapping 数据类测试"""

    def test_path_mapping_creation(self):
        """测试路径映射对象创建"""
        mapping = PathMapping(
            enabled=True,
            source="/source/path",
            sourceDesc="Source Description",
            target="/target/path",
            targetCid="123456",
        )
        self.assertTrue(mapping.enabled)
        self.assertEqual(mapping.source, "/source/path")
        self.assertEqual(mapping.sourceDesc, "Source Description")
        self.assertEqual(mapping.target, "/target/path")
        self.assertEqual(mapping.targetCid, "123456")
        self.assertIsNone(mapping.id)
        self.assertIsNone(mapping.createdAt)
        self.assertIsNone(mapping.updatedAt)

    def test_path_mapping_with_timestamps(self):
        """测试包含时间戳的路径映射"""
        now = datetime.now()
        mapping = PathMapping(
            enabled=True,
            source="/source",
            sourceDesc="Desc",
            target="/target",
            targetCid="123",
            id=1,
            createdAt=now,
            updatedAt=now,
        )
        self.assertEqual(mapping.id, 1)
        self.assertEqual(mapping.createdAt, now)
        self.assertEqual(mapping.updatedAt, now)

    def test_path_mapping_to_dict(self):
        """测试路径映射转字典"""
        now = datetime.now()
        mapping = PathMapping(
            enabled=True,
            source="/source",
            sourceDesc="Desc",
            target="/target",
            targetCid="123",
            createdAt=now,
            updatedAt=now,
        )
        data = mapping.to_dict()
        self.assertIsInstance(data, dict)
        self.assertEqual(data["source"], "/source")
        self.assertEqual(data["enabled"], True)
        # Check that datetime is converted to ISO format string
        self.assertIsInstance(data["createdAt"], str)
        self.assertIsInstance(data["updatedAt"], str)


class TestP115DirCache(TestCase):
    """P115DirCache 数据类测试"""

    def test_cache_creation(self):
        """测试缓存对象创建"""
        now = datetime.now()
        future = now + timedelta(hours=24)
        cache = P115DirCache(
            cid="folder123",
            data={"subdir1": {}, "subdir2": {}},
            cachedAt=now,
            expireAt=future,
        )
        self.assertEqual(cache.cid, "folder123")
        self.assertIsInstance(cache.data, dict)
        self.assertEqual(cache.data["subdir1"], {})

    def test_cache_is_expired_false(self):
        """测试缓存未过期"""
        now = datetime.now()
        future = now + timedelta(hours=24)
        cache = P115DirCache(
            cid="folder123",
            data={},
            cachedAt=now,
            expireAt=future,
        )
        self.assertFalse(cache.is_expired())

    def test_cache_is_expired_true(self):
        """测试缓存已过期"""
        now = datetime.now()
        past = now - timedelta(hours=1)
        cache = P115DirCache(
            cid="folder123",
            data={},
            cachedAt=past,
            expireAt=past,
        )
        self.assertTrue(cache.is_expired())

    def test_cache_to_dict(self):
        """测试缓存转字典"""
        now = datetime.now()
        future = now + timedelta(hours=24)
        cache = P115DirCache(
            cid="folder123",
            data={"key": "value"},
            cachedAt=now,
            expireAt=future,
        )
        data = cache.to_dict()
        self.assertEqual(data["cid"], "folder123")
        self.assertEqual(data["data"], {"key": "value"})
        self.assertIsInstance(data["cachedAt"], str)
        self.assertIsInstance(data["expireAt"], str)


class TestPathMappingManager(TestCase):
    """PathMappingManager 管理器测试"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = PathMappingManager(self.temp_dir)

    def tearDown(self):
        """清理测试环境"""
        import shutil
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_manager_initialization(self):
        """测试管理器初始化"""
        self.assertTrue(self.manager.mappings_file.exists())
        self.assertTrue(self.manager.cache_file.exists())

    def test_save_and_get_mappings(self):
        """测试保存和获取路径映射"""
        mapping1 = PathMapping(
            enabled=True,
            source="/source1",
            sourceDesc="Source 1",
            target="/target1",
            targetCid="123",
        )
        mapping2 = PathMapping(
            enabled=False,
            source="/source2",
            sourceDesc="Source 2",
            target="/target2",
            targetCid="456",
        )
        mappings = [mapping1, mapping2]
        self.assertTrue(self.manager.save_mappings(mappings))

        # Retrieve and verify
        retrieved = self.manager.get_mappings()
        self.assertEqual(len(retrieved), 2)
        self.assertEqual(retrieved[0].source, "/source1")
        self.assertTrue(retrieved[0].enabled)
        self.assertEqual(retrieved[1].source, "/source2")
        self.assertFalse(retrieved[1].enabled)

    def test_get_mappings_empty(self):
        """测试获取空路径映射"""
        mappings = self.manager.get_mappings()
        self.assertEqual(len(mappings), 0)
        self.assertIsInstance(mappings, list)

    def test_save_and_get_115_cache(self):
        """测试保存和获取 115 缓存"""
        cache_data = {
            "subdir1": {"cid": "sub123", "name": "Subdir 1"},
            "subdir2": {"cid": "sub456", "name": "Subdir 2"},
        }
        self.assertTrue(self.manager.set_115_cache("folder123", cache_data, ttl_hours=24))

        # Retrieve and verify
        retrieved = self.manager.get_115_cache("folder123")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["subdir1"]["cid"], "sub123")
        self.assertEqual(retrieved["subdir2"]["name"], "Subdir 2")

    def test_get_115_cache_not_found(self):
        """测试获取不存在的缓存"""
        result = self.manager.get_115_cache("nonexistent")
        self.assertIsNone(result)

    def test_clear_cache(self):
        """测试清除缓存"""
        cache_data = {"key": "value"}
        self.manager.set_115_cache("folder123", cache_data)
        self.assertIsNotNone(self.manager.get_115_cache("folder123"))

        # Clear and verify
        self.assertTrue(self.manager.clear_cache("folder123"))
        self.assertIsNone(self.manager.get_115_cache("folder123"))

    def test_clear_expired_caches(self):
        """测试清除过期缓存"""
        # Set two caches: one current, one expired
        current_data = {"data": "value"}
        expired_data = {"key": "value"}

        # Set current cache with 24-hour TTL
        self.manager.set_115_cache("current", current_data, ttl_hours=24)

        # Set cache that will immediately be marked as expired
        self.manager.set_115_cache("expired", expired_data, ttl_hours=24)

        # Manually expire the "expired" cache by modifying the file
        cache_file_data = orjson.loads(self.manager.cache_file.read_text())
        # Set expiry to 1 hour in the past
        cache_file_data["expired"]["expireAt"] = (
            datetime.now() - timedelta(hours=1)
        ).isoformat()
        self.manager.cache_file.write_text(orjson.dumps(cache_file_data).decode())

        # Clear expired caches
        count = self.manager.clear_expired_caches()

        # Verify one cache was removed
        self.assertEqual(count, 1)

        # Verify expired cache is gone
        self.assertIsNone(self.manager.get_115_cache("expired"))

        # Verify current cache still exists
        self.assertIsNotNone(self.manager.get_115_cache("current"))

    def test_cache_expiration(self):
        """测试缓存自动过期"""
        # Set cache with short TTL
        cache_data = {"key": "value"}
        self.manager.set_115_cache("folder123", cache_data, ttl_hours=0)

        # Manually expire the cache
        cache_file_data = orjson.loads(self.manager.cache_file.read_text())
        cache_file_data["folder123"]["expireAt"] = (
            datetime.now() - timedelta(seconds=1)
        ).isoformat()
        self.manager.cache_file.write_text(orjson.dumps(cache_file_data).decode())

        # Try to get expired cache
        result = self.manager.get_115_cache("folder123")
        self.assertIsNone(result)


class TestIncrementalRecordStore(TestCase):
    """IncrementalRecordStore 测试（验证现有功能）"""

    def test_incremental_record_store(self):
        """测试增量记录存储"""
        store = IncrementalRecordStore()

        # Create a test file
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"test content")
            tmp_path = Path(tmp.name)

        try:
            # Check file is marked as changed
            self.assertTrue(store.has_changed(tmp_path))

            # Mark as uploaded
            store.mark_uploaded(tmp_path, "/target/path")

            # Check file is no longer marked as changed
            self.assertFalse(store.has_changed(tmp_path))

            # Check data serialization
            data = store.to_dict()
            self.assertIn(str(tmp_path), data)
        finally:
            tmp_path.unlink()


class TestTaskHistory(TestCase):
    """TaskHistory 测试（验证现有功能）"""

    def test_task_history(self):
        """测试任务历史"""
        history = TaskHistory(limit=50)

        # Add items
        for i in range(100):
            history.add({"id": i, "status": "completed"})

        # Verify limit
        items = history.to_list()
        self.assertEqual(len(items), 50)

        # Verify order (most recent first)
        self.assertEqual(items[0]["id"], 99)
        self.assertEqual(items[-1]["id"], 50)
