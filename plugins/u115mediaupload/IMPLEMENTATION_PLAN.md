# 115 媒体上传插件 - 二维码与路径映射功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 U115MediaUpload 插件添加二维码图片显示和路径映射选择器功能，提升用户体验。

**Architecture:** 
- 后端：新增 4 个 API 端点处理二维码生成、目录浏览和映射保存；引入数据库缓存层存储 115 目录树和映射关系
- 前端：修改认证面板显示二维码图片，新增目录选择器弹窗（本地+115 云盘），集成路径映射编辑器
- 数据持久化：新增路径映射表和 115 目录缓存表，TTL 24h

**Tech Stack:**
- 后端：FastAPI, qrcode, base64, pathlib, orjson
- 前端：Vue 3, Vuetify 3, v-model, emits
- 数据库：SQLite（插件 config/records 存储）

## Global Constraints

- Python 3.11+（MoviePilot 基线）
- Vue 3 Composition API（前端框架）
- 二维码生成使用 `qrcode` 库（返回 base64 data URL）
- 本地目录浏览从 `settings.LIBRARY_PATH` 开始
- 115 目录缓存 TTL 24h，支持手动刷新
- 路径映射启用/禁用状态单独存储
- 数据库操作使用插件现有的 ORM（records.py）

---

## 文件结构映射

### 修改文件
```
plugins/u115mediaupload/
├── __init__.py                    # 修改：注册新 API 路由
├── client.py                      # 无改动（调用方改）
├── records.py                     # 新增：路径映射和缓存表定义
├── scanner.py                     # 无改动
├── scraper.py                     # 无改动
├── src/
│   ├── App.vue                    # 修改：导入新组件
│   ├── components/
│   │   ├── AuthPanel.vue          # 修改：显示二维码图片
│   │   ├── PathMappingEditor.vue  # 修改：集成目录选择器
│   │   ├── LocalPathSelector.vue  # 新建：本地目录浏览器
│   │   ├── P115PathSelector.vue   # 新建：115 云盘浏览器
│   │   ├── Page.vue               # 无改动
│   │   ├── Config.vue             # 无改动
│   │   ├── HistoryTable.vue       # 无改动
│   │   └── TaskConsole.vue        # 无改动
│   ├── utils/
│   │   └── plugin.js              # 无改动
│   └── main.js                    # 无改动
└── package.json                   # 修改：确保 qrcode 依赖已声明
```

### 新增模块
```
plugins/u115mediaupload/
└── api_handlers.py                # 新建：API 端点集中管理
```

---

## 任务分解

### Task 1: 添加数据库模型（路径映射和缓存）

**Files:**
- Modify: `plugins/u115mediaupload/records.py`

**Interfaces:**
- Produces: 
  - `PathMapping` 数据类（字段：id, enabled, source, sourceDesc, target, targetCid, createdAt, updatedAt）
  - `P115DirCache` 数据类（字段：cid, data, cachedAt, expireAt）
  - `get_path_mappings() -> List[PathMapping]`
  - `save_path_mappings(mappings: List[PathMapping]) -> bool`
  - `get_115_dir_cache(cid: str) -> Optional[Dict]`
  - `set_115_dir_cache(cid: str, data: Dict, ttl_hours: int = 24) -> bool`
  - `clear_expired_cache() -> int`

- [ ] **Step 1: 读取现有 records.py 结构**

```bash
cd C:\Users\84030\Documents\GitHub\MP\MoviePilot-Plugins\plugins\u115mediaupload
cat records.py | head -100
```

预期输出：看到现有的数据类定义模式（如使用 dataclass 或 dict）

- [ ] **Step 2: 在 records.py 末尾添加路径映射相关类定义**

打开 `records.py`，在文件末尾添加：

```python
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Dict, List

@dataclass
class PathMapping:
    """路径映射记录"""
    enabled: bool
    source: str
    sourceDesc: str
    target: str
    targetCid: str
    id: Optional[int] = None
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)

@dataclass
class P115DirCache:
    """115 目录缓存"""
    cid: str
    data: Dict  # 子目录列表
    cachedAt: datetime
    expireAt: datetime
    
    def is_expired(self) -> bool:
        return datetime.now() > self.expireAt
    
    def to_dict(self) -> Dict:
        return {
            "cid": self.cid,
            "data": self.data,
            "cachedAt": self.cachedAt.isoformat(),
            "expireAt": self.expireAt.isoformat()
        }


class PathMappingManager:
    """路径映射管理器"""
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.mappings_file = Path(config_path) / "path_mappings.json"
        self.cache_file = Path(config_path) / "115_dir_cache.json"
        self._ensure_files()
    
    def _ensure_files(self):
        """确保配置文件存在"""
        self.mappings_file.touch(exist_ok=True)
        self.cache_file.touch(exist_ok=True)
        if self.mappings_file.stat().st_size == 0:
            self.mappings_file.write_text(orjson.dumps([]).decode())
        if self.cache_file.stat().st_size == 0:
            self.cache_file.write_text(orjson.dumps({}).decode())
    
    def get_mappings(self) -> List[PathMapping]:
        """获取所有路径映射"""
        try:
            data = orjson.loads(self.mappings_file.read_text())
            return [PathMapping(**item) for item in data]
        except Exception:
            return []
    
    def save_mappings(self, mappings: List[PathMapping]) -> bool:
        """保存路径映射"""
        try:
            data = [m.to_dict() for m in mappings]
            self.mappings_file.write_text(orjson.dumps(data).decode())
            return True
        except Exception as e:
            logger.error(f"保存路径映射失败: {e}")
            return False
    
    def get_115_cache(self, cid: str) -> Optional[Dict]:
        """获取 115 目录缓存"""
        try:
            cache_data = orjson.loads(self.cache_file.read_text())
            if cid not in cache_data:
                return None
            cached = P115DirCache(**cache_data[cid])
            if cached.is_expired():
                self.clear_cache(cid)
                return None
            return cached.data
        except Exception:
            return None
    
    def set_115_cache(self, cid: str, data: Dict, ttl_hours: int = 24) -> bool:
        """设置 115 目录缓存"""
        try:
            from datetime import timedelta
            cache_data = orjson.loads(self.cache_file.read_text())
            cached = P115DirCache(
                cid=cid,
                data=data,
                cachedAt=datetime.now(),
                expireAt=datetime.now() + timedelta(hours=ttl_hours)
            )
            cache_data[cid] = cached.to_dict()
            self.cache_file.write_text(orjson.dumps(cache_data).decode())
            return True
        except Exception as e:
            logger.error(f"设置 115 缓存失败: {e}")
            return False
    
    def clear_cache(self, cid: str) -> bool:
        """清除指定 cid 的缓存"""
        try:
            cache_data = orjson.loads(self.cache_file.read_text())
            cache_data.pop(cid, None)
            self.cache_file.write_text(orjson.dumps(cache_data).decode())
            return True
        except Exception:
            return False
    
    def clear_expired_caches(self) -> int:
        """清除所有过期缓存"""
        try:
            cache_data = orjson.loads(self.cache_file.read_text())
            expired_cids = []
            for cid, item in cache_data.items():
                cached = P115DirCache(**item)
                if cached.is_expired():
                    expired_cids.append(cid)
            for cid in expired_cids:
                cache_data.pop(cid)
            self.cache_file.write_text(orjson.dumps(cache_data).decode())
            return len(expired_cids)
        except Exception:
            return 0
```

- [ ] **Step 3: 在 __init__.py 顶部初始化 PathMappingManager**

打开 `__init__.py`，在类初始化方法中添加：

```python
def __init__(self):
    # ... 现有初始化代码 ...
    self._mapping_manager = PathMappingManager(
        config_path=str(self.get_plugin_config_path())
    )
```

- [ ] **Step 4: 编写单元测试**

创建 `tests/test_records.py`：

```python
import pytest
from pathlib import Path
from datetime import datetime, timedelta
from plugins.u115mediaupload.records import PathMapping, P115DirCache, PathMappingManager

def test_path_mapping_creation():
    mapping = PathMapping(
        enabled=True,
        source="/media/movies",
        sourceDesc="movies",
        target="/115/movies",
        targetCid="12345"
    )
    assert mapping.enabled is True
    assert mapping.source == "/media/movies"

def test_115_dir_cache_expiry():
    cache = P115DirCache(
        cid="0",
        data={"items": []},
        cachedAt=datetime.now(),
        expireAt=datetime.now() - timedelta(hours=1)
    )
    assert cache.is_expired() is True
    
    cache2 = P115DirCache(
        cid="0",
        data={"items": []},
        cachedAt=datetime.now(),
        expireAt=datetime.now() + timedelta(hours=1)
    )
    assert cache2.is_expired() is False

def test_path_mapping_manager(tmp_path):
    manager = PathMappingManager(config_path=str(tmp_path))
    
    mappings = [
        PathMapping(True, "/a", "a", "/115/a", "1"),
        PathMapping(False, "/b", "b", "/115/b", "2")
    ]
    
    assert manager.save_mappings(mappings) is True
    loaded = manager.get_mappings()
    assert len(loaded) == 2
    assert loaded[0].source == "/a"
    assert loaded[1].enabled is False
```

运行测试：

```bash
cd C:\Users\84030\Documents\GitHub\MP\MoviePilot-Plugins\plugins\u115mediaupload
pytest tests/test_records.py -v
```

预期输出：所有测试通过

- [ ] **Step 5: 提交**

```bash
git add records.py tests/test_records.py
git commit -m "feat(u115): add path mapping and cache data models"
```

---

### Task 2: 添加后端 API 端点（二维码、目录浏览、映射保存）

**Files:**
- Create: `plugins/u115mediaupload/api_handlers.py`
- Modify: `plugins/u115mediaupload/__init__.py`

**Interfaces:**
- Consumes: `PathMappingManager`、`client.py` 的 `generate_qrcode()` 和 `get_dir_list()` 方法
- Produces：
  - `POST /qrcode` → `{"success": true, "data": {"qrcode": "data:image/png;base64,...", "codeContent": "..."}}`
  - `GET /browse_local?path=` → `{"success": true, "data": {"base": "...", "current": "...", "items": [...]}}`
  - `GET /browse_115?cid=&refresh=` → `{"success": true, "data": {"cid": "...", "items": [...]}}`
  - `POST /path_mappings` → `{"success": true, "msg": "映射保存成功"}`

- [ ] **Step 1: 创建 api_handlers.py**

创建新文件 `plugins/u115mediaupload/api_handlers.py`：

```python
"""
115 媒体上传插件 - API 处理器
"""
from typing import Dict, Any, Optional, List
from pathlib import Path
from base64 import b64encode
from io import BytesIO
from datetime import datetime

from qrcode import make as qr_make
from fastapi import Query
from orjson import dumps, loads
from app.log import logger
from app.core.config import settings

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
            # 调用 client 获取二维码内容
            qr_data = self.client.generate_qrcode()
            code_content = qr_data.get("codeContent", "")
            
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
```

- [ ] **Step 2: 在 __init__.py 中注册 API 端点**

打开 `__init__.py`，在插件类中添加以下方法（在 `__init__` 方法之后）：

```python
from .api_handlers import U115MediaUploadApiHandler

def __init__(self):
    # ... 现有代码 ...
    self._mapping_manager = PathMappingManager(
        config_path=str(self.get_plugin_config_path())
    )
    self._api_handler = U115MediaUploadApiHandler(self.client, self._mapping_manager)

def _setup_api_routes(self):
    """设置 API 路由"""
    self.add_api_route(
        path="/qrcode",
        endpoint=self._qrcode_api,
        methods=["POST"],
        summary="生成 115 登录二维码"
    )
    self.add_api_route(
        path="/browse_local",
        endpoint=self._browse_local_api,
        methods=["GET"],
        summary="浏览本地目录"
    )
    self.add_api_route(
        path="/browse_115",
        endpoint=self._browse_115_api,
        methods=["GET"],
        summary="浏览 115 云盘目录"
    )
    self.add_api_route(
        path="/path_mappings",
        endpoint=self._save_path_mappings_api,
        methods=["POST"],
        summary="保存路径映射"
    )

def _qrcode_api(self) -> Dict[str, Any]:
    """生成二维码 API"""
    return self._api_handler.generate_qrcode()

def _browse_local_api(self, path: str = Query(default="", description="相对路径")) -> Dict[str, Any]:
    """浏览本地目录 API"""
    return self._api_handler.browse_local(path)

def _browse_115_api(self, cid: str = Query(default="0"), refresh: bool = Query(default=False)) -> Dict[str, Any]:
    """浏览 115 目录 API"""
    return self._api_handler.browse_115(cid, refresh)

def _save_path_mappings_api(self, mappings: List[Dict] = Body(...)) -> Dict[str, Any]:
    """保存路径映射 API"""
    return self._api_handler.save_path_mappings(mappings)
```

并在插件的 `__init__` 方法中调用 `_setup_api_routes()`：

```python
def __init__(self):
    # ... 现有代码 ...
    self._setup_api_routes()
```

- [ ] **Step 3: 编写集成测试**

创建 `tests/test_api_handlers.py`：

```python
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock
from plugins.u115mediaupload.api_handlers import U115MediaUploadApiHandler
from plugins.u115mediaupload.records import PathMappingManager

def test_generate_qrcode():
    client = Mock()
    client.generate_qrcode.return_value = {"codeContent": "https://115.com/qrcode/test"}
    
    manager = Mock(spec=PathMappingManager)
    handler = U115MediaUploadApiHandler(client, manager)
    
    result = handler.generate_qrcode()
    
    assert result["success"] is True
    assert "qrcode" in result["data"]
    assert result["data"]["qrcode"].startswith("data:image/png;base64,")
    assert result["data"]["codeContent"] == "https://115.com/qrcode/test"

def test_browse_local_root(tmp_path):
    # 创建测试目录结构
    (tmp_path / "movie1").mkdir()
    (tmp_path / "movie2").mkdir()
    (tmp_path / ".hidden").mkdir()
    
    client = Mock()
    manager = Mock(spec=PathMappingManager)
    handler = U115MediaUploadApiHandler(client, manager)
    
    # 模拟 settings.LIBRARY_PATH
    import plugins.u115mediaupload.api_handlers as api_module
    original_settings = api_module.settings
    api_module.settings = Mock()
    api_module.settings.LIBRARY_PATH = str(tmp_path)
    
    try:
        result = handler.browse_local("")
        
        assert result["success"] is True
        assert result["data"]["base"] == str(tmp_path)
        assert result["data"]["current"] == ""
        assert len(result["data"]["items"]) == 2
        assert result["data"]["items"][0]["name"] == "movie1"
        assert result["data"]["items"][0]["is_dir"] is True
    finally:
        api_module.settings = original_settings

def test_browse_115_with_cache(tmp_path):
    client = Mock()
    client.get_dir_list.return_value = [
        {"name": "folder1", "cid": "123", "type": 1},
        {"name": "folder2", "cid": "124", "type": 1},
    ]
    
    manager = PathMappingManager(config_path=str(tmp_path))
    handler = U115MediaUploadApiHandler(client, manager)
    
    # 第一次调用（无缓存）
    result1 = handler.browse_115("0", refresh=False)
    assert result1["success"] is True
    assert result1["data"]["cached"] is False
    assert len(result1["data"]["items"]) == 2
    
    # 第二次调用（有缓存）
    result2 = handler.browse_115("0", refresh=False)
    assert result2["success"] is True
    assert result2["data"]["cached"] is True
    
    # 调用刷新
    client.get_dir_list.return_value = [
        {"name": "folder1", "cid": "123", "type": 1},
    ]
    result3 = handler.browse_115("0", refresh=True)
    assert result3["success"] is True
    assert result3["data"]["cached"] is False
    assert len(result3["data"]["items"]) == 1

def test_save_path_mappings(tmp_path):
    client = Mock()
    manager = PathMappingManager(config_path=str(tmp_path))
    handler = U115MediaUploadApiHandler(client, manager)
    
    mappings = [
        {
            "enabled": True,
            "source": "/movies",
            "sourceDesc": "movies",
            "target": "/115/movies",
            "targetCid": "123"
        },
        {
            "enabled": False,
            "source": "/tv",
            "sourceDesc": "tv",
            "target": "/115/tv",
            "targetCid": "124"
        }
    ]
    
    result = handler.save_path_mappings(mappings)
    
    assert result["success"] is True
    
    # 验证保存结果
    saved = manager.get_mappings()
    assert len(saved) == 2
    assert saved[0].source == "/movies"
    assert saved[1].enabled is False
```

运行测试：

```bash
cd C:\Users\84030\Documents\GitHub\MP\MoviePilot-Plugins\plugins\u115mediaupload
pytest tests/test_api_handlers.py -v
```

预期输出：所有测试通过

- [ ] **Step 4: 提交**

```bash
git add api_handlers.py __init__.py tests/test_api_handlers.py
git commit -m "feat(u115): add backend API handlers for qrcode and directory browsing"
```

---

### Task 3: 修改前端 AuthPanel.vue - 显示二维码图片

**Files:**
- Modify: `plugins/u115mediaupload/src/components/AuthPanel.vue`

**Interfaces:**
- Consumes: 后端 `/qrcode` API（返回 base64 data URL）
- Produces: 用户可见的二维码图片显示

- [ ] **Step 1: 读取现有 AuthPanel.vue**

```bash
cd C:\Users\84030\Documents\GitHub\MP\MoviePilot-Plugins\plugins\u115mediaupload\src\components
cat AuthPanel.vue | head -60
```

- [ ] **Step 2: 修改 AuthPanel.vue - 添加二维码图片显示**

打开 `AuthPanel.vue`，完整替换为：

```vue
<script setup>
import { reactive, ref } from 'vue'
import { pluginRequest } from '../utils/plugin'

const props = defineProps({
  api: {
    type: Object,
    default: () => ({}),
  },
  config: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['update:config', 'toast'])

const loading = reactive({ qrcode: false, check: false })
const qrcodeImage = ref('')
const qrcodeText = ref('')

function update(key, value) {
  emit('update:config', { ...props.config, [key]: value })
}

async function generateQrcode() {
  loading.qrcode = true
  try {
    const result = await pluginRequest(props.api, '/qrcode', { method: 'POST' })
    if (!result?.success) throw new Error(result?.message || '生成二维码失败')
    qrcodeImage.value = result?.data?.qrcode || ''
    qrcodeText.value = result?.data?.codeContent || ''
    emit('toast', '二维码已生成，请用手机 115 APP 扫描')
  } catch (error) {
    emit('toast', error?.message || '生成二维码失败', 'error')
    qrcodeImage.value = ''
    qrcodeText.value = ''
  } finally {
    loading.qrcode = false
  }
}

async function checkLogin() {
  loading.check = true
  try {
    const result = await pluginRequest(props.api, '/check_login')
    if (!result?.success) throw new Error(result?.message || '登录未完成')
    emit('toast', result?.data?.tip || '登录状态已更新')
  } catch (error) {
    emit('toast', error?.message || '检查登录失败', 'error')
  } finally {
    loading.check = false
  }
}
</script>

<template>
  <section class="auth-panel">
    <div class="section-title">115 授权</div>
    <v-btn-toggle
      :model-value="config.auth_mode"
      mandatory
      color="#167A5B"
      variant="outlined"
      density="comfortable"
      @update:model-value="update('auth_mode', $event)"
    >
      <v-btn value="cookie"><v-icon icon="mdi-cookie-outline" class="mr-1" />Cookie</v-btn>
      <v-btn value="qrcode"><v-icon icon="mdi-qrcode-scan" class="mr-1" />扫码</v-btn>
    </v-btn-toggle>

    <v-textarea
      v-if="config.auth_mode === 'cookie'"
      :model-value="config.cookie"
      label="115 Cookie"
      variant="outlined"
      rows="4"
      auto-grow
      hide-details
      @update:model-value="update('cookie', $event)"
    />

    <div v-else class="qrcode-box">
      <div class="qrcode-actions">
        <v-btn color="#167A5B" variant="flat" :loading="loading.qrcode" @click="generateQrcode">
          <v-icon icon="mdi-qrcode-plus" class="mr-1" />生成二维码
        </v-btn>
        <v-btn color="#245B7A" variant="tonal" :loading="loading.check" @click="checkLogin">
          <v-icon icon="mdi-check-circle-outline" class="mr-1" />检查登录
        </v-btn>
      </div>

      <!-- 二维码图片显示 -->
      <div v-if="qrcodeImage" class="qrcode-image-container">
        <img :src="qrcodeImage" alt="115 登录二维码" class="qrcode-image" />
        <p class="qrcode-hint">用手机 115 APP 扫描上方二维码登录</p>
      </div>

      <!-- 二维码内容备用显示（用于调试或二维码显示失败） -->
      <v-textarea
        v-show="qrcodeText"
        v-model="qrcodeText"
        label="二维码内容（备用）"
        variant="outlined"
        rows="2"
        readonly
        hide-details
        density="compact"
        class="mt-2"
      />
    </div>
  </section>
</template>

<style scoped>
.auth-panel {
  display: grid;
  gap: 12px;
}

.section-title {
  font-weight: 700;
  color: #17201c;
  margin-bottom: 4px;
}

.qrcode-box {
  display: grid;
  gap: 10px;
}

.qrcode-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.qrcode-image-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border: 1px dashed #d9e0da;
  border-radius: 8px;
  background-color: #f5f7f6;
}

.qrcode-image {
  width: 200px;
  height: 200px;
  border: 2px solid #167A5B;
  border-radius: 4px;
  padding: 8px;
  background-color: white;
}

.qrcode-hint {
  color: #66736d;
  font-size: 13px;
  margin: 0;
  text-align: center;
}
</style>
```

- [ ] **Step 3: 本地测试二维码显示**

在前端开发环境运行，打开配置页面的「授权」部分，点击「生成二维码」按钮，验证：
- 按钮变为加载状态
- 二维码图片正确显示
- 提示文字显示

- [ ] **Step 4: 提交**

```bash
git add src/components/AuthPanel.vue
git commit -m "feat(u115): display qrcode as image in AuthPanel"
```

---

### Task 4: 创建 LocalPathSelector.vue - 本地目录浏览器

**Files:**
- Create: `plugins/u115mediaupload/src/components/LocalPathSelector.vue`

**Interfaces:**
- Consumes: `v-model`（modelValue）、后端 `/browse_local?path=` API
- Produces: `@selected` 事件（path）、`@update:modelValue` 事件

- [ ] **Step 1: 创建 LocalPathSelector.vue**

创建新文件 `plugins/u115mediaupload/src/components/LocalPathSelector.vue`：

```vue
<script setup>
import { ref, watch } from 'vue'
import { pluginRequest } from '../utils/plugin'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  api: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['update:modelValue', 'selected', 'toast'])

const loading = ref(false)
const basePath = ref('')
const currentPath = ref('')
const items = ref([])
const breadcrumbs = ref([])

async function loadDirectory(path = '') {
  loading.value = true
  try {
    const queryPath = path ? `?path=${encodeURIComponent(path)}` : ''
    const result = await pluginRequest(props.api, `/browse_local${queryPath}`, { method: 'GET' })
    
    if (!result?.success) {
      emit('toast', result?.msg || '获取目录失败', 'error')
      return
    }

    basePath.value = result.data.base
    currentPath.value = result.data.current || ''
    items.value = result.data.items || []
    
    // 更新面包屑
    updateBreadcrumbs(path)
  } catch (error) {
    emit('toast', error?.message || '获取目录失败', 'error')
  } finally {
    loading.value = false
  }
}

function updateBreadcrumbs(path) {
  breadcrumbs.value = [{ name: '媒体库', path: '' }]
  
  if (path) {
    const parts = path.split('/').filter(Boolean)
    let currentBreadPath = ''
    for (const part of parts) {
      currentBreadPath += (currentBreadPath ? '/' : '') + part
      breadcrumbs.value.push({ name: part, path: currentBreadPath })
    }
  }
}

function navigateToDirectory(item) {
  loadDirectory(item.path)
}

function navigateToBreadcrumb(breadcrumb) {
  loadDirectory(breadcrumb.path)
}

function selectCurrentDirectory() {
  const fullPath = currentPath.value ? currentPath.value : ''
  emit('selected', fullPath)
  emit('update:modelValue', false)
}

function closeDialog() {
  emit('update:modelValue', false)
}

watch(
  () => props.modelValue,
  (isOpen) => {
    if (isOpen) {
      loadDirectory('')
    }
  }
)
</script>

<template>
  <v-dialog 
    :model-value="modelValue"
    max-width="600px"
    persistent
    @update:model-value="closeDialog"
  >
    <v-card class="local-path-selector">
      <v-card-title class="d-flex align-center justify-space-between">
        <span>选择本地目录</span>
        <v-icon icon="mdi-folder-outline" />
      </v-card-title>
      
      <v-divider />
      
      <v-card-text class="pa-4">
        <!-- 面包屑导航 -->
        <div v-if="breadcrumbs.length > 0" class="breadcrumb-bar mb-4">
          <v-breadcrumbs :items="breadcrumbs" small>
            <template #item="{ item, index }">
              <v-breadcrumbs-item
                :href="`#`"
                @click.prevent="navigateToBreadcrumb(item)"
                :disabled="loading"
              >
                {{ item.name }}
              </v-breadcrumbs-item>
            </template>
          </v-breadcrumbs>
        </div>

        <!-- 加载状态 -->
        <v-progress-linear v-if="loading" indeterminate class="mb-3" />

        <!-- 目录列表 -->
        <v-list v-else density="compact" class="directory-list">
          <v-list-item
            v-if="items.length === 0"
            disabled
            class="text-center text-grey"
          >
            <span>此目录为空</span>
          </v-list-item>

          <v-list-item
            v-for="item in items"
            :key="item.path"
            @click="navigateToDirectory(item)"
            class="directory-item"
          >
            <template #prepend>
              <v-icon icon="mdi-folder" color="#167A5B" />
            </template>
            <v-list-item-title>{{ item.name }}</v-list-item-title>
            <template #append>
              <v-icon icon="mdi-chevron-right" size="small" color="#999" />
            </template>
          </v-list-item>
        </v-list>
      </v-card-text>

      <v-divider />

      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn variant="plain" @click="closeDialog" :disabled="loading">
          取消
        </v-btn>
        <v-btn
          color="#167A5B"
          variant="flat"
          @click="selectCurrentDirectory"
          :disabled="loading"
        >
          选择当前目录
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.local-path-selector {
  min-height: 400px;
}

.breadcrumb-bar {
  border-bottom: 1px solid #e0e0e0;
  padding-bottom: 12px;
}

.directory-list {
  max-height: 400px;
  overflow-y: auto;
}

.directory-item {
  cursor: pointer;
  transition: background-color 0.2s;
}

.directory-item:hover {
  background-color: rgba(22, 122, 91, 0.08);
}
</style>
```

- [ ] **Step 2: 在 App.vue 中导入组件**

打开 `src/App.vue`，在 `<script setup>` 部分添加导入：

```javascript
import LocalPathSelector from './components/LocalPathSelector.vue'
```

- [ ] **Step 3: 单元测试**

创建 `tests/test_local_path_selector.vue.test.js`：

```javascript
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import LocalPathSelector from '@/components/LocalPathSelector.vue'

describe('LocalPathSelector.vue', () => {
  it('renders dialog when modelValue is true', () => {
    const wrapper = mount(LocalPathSelector, {
      props: {
        modelValue: true,
        api: {}
      }
    })
    
    expect(wrapper.find('.v-dialog').exists()).toBe(true)
  })

  it('emits close event when cancel button clicked', async () => {
    const wrapper = mount(LocalPathSelector, {
      props: {
        modelValue: true,
        api: {}
      },
      stubs: {
        VDialog: { template: '<div><slot /></div>' }
      }
    })
    
    await wrapper.find('.v-btn').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')[0]).toEqual([false])
  })

  it('displays breadcrumbs correctly', async () => {
    const wrapper = mount(LocalPathSelector, {
      props: {
        modelValue: true,
        api: {}
      }
    })

    wrapper.vm.breadcrumbs = [
      { name: '媒体库', path: '' },
      { name: 'movies', path: 'movies' }
    ]

    await wrapper.vm.$nextTick()
    
    const breadcrumbs = wrapper.findAll('.v-breadcrumbs-item')
    expect(breadcrumbs.length).toBe(2)
  })
})
```

- [ ] **Step 4: 提交**

```bash
git add src/components/LocalPathSelector.vue src/App.vue tests/test_local_path_selector.vue.test.js
git commit -m "feat(u115): add local path selector component"
```

---

### Task 5: 创建 P115PathSelector.vue - 115 云盘目录浏览器

**Files:**
- Create: `plugins/u115mediaupload/src/components/P115PathSelector.vue`

**Interfaces:**
- Consumes: `v-model`、后端 `/browse_115?cid=&refresh=` API
- Produces: `@selected` 事件(cid, name)、`@update:modelValue` 事件

- [ ] **Step 1: 创建 P115PathSelector.vue**

创建新文件 `plugins/u115mediaupload/src/components/P115PathSelector.vue`：

```vue
<script setup>
import { ref, watch } from 'vue'
import { pluginRequest } from '../utils/plugin'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  api: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['update:modelValue', 'selected', 'toast'])

const loading = ref(false)
const refreshing = ref(false)
const items = ref([])
const breadcrumbs = ref([{ cid: '0', name: '115云盘' }])

async function loadDirectory(cid = '0', isRefresh = false) {
  const isInitial = !isRefresh && breadcrumbs.value.length === 1
  
  if (isInitial) {
    loading.value = true
  } else if (isRefresh) {
    refreshing.value = true
  }

  try {
    const refreshParam = isRefresh ? '&refresh=true' : ''
    const result = await pluginRequest(
      props.api,
      `/browse_115?cid=${cid}${refreshParam}`,
      { method: 'GET' }
    )

    if (!result?.success) {
      emit('toast', result?.msg || '获取目录失败', 'error')
      return
    }

    items.value = result.data.items || []
    
    if (!isRefresh && cid !== '0') {
      // 导航到新目录时更新面包屑
      const currentBreadcrumb = breadcrumbs.value[breadcrumbs.value.length - 1]
      if (currentBreadcrumb.cid !== cid) {
        const itemName = items.value[0]?.name || `文件夹 ${cid}`
        breadcrumbs.value.push({ cid, name: itemName })
      }
    }

    if (isRefresh) {
      emit('toast', '目录已刷新', 'success')
    }
  } catch (error) {
    emit('toast', error?.message || '获取目录失败', 'error')
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

function navigateToDirectory(item) {
  // 更新面包屑，然后加载子目录
  breadcrumbs.value.push({ cid: item.cid, name: item.name })
  loadDirectory(item.cid, false)
}

function goBack() {
  if (breadcrumbs.value.length > 1) {
    breadcrumbs.value.pop()
    const currentCid = breadcrumbs.value[breadcrumbs.value.length - 1].cid
    loadDirectory(currentCid, false)
  }
}

function refresh() {
  const currentCid = breadcrumbs.value[breadcrumbs.value.length - 1].cid
  loadDirectory(currentCid, true)
}

function selectCurrentDirectory() {
  const current = breadcrumbs.value[breadcrumbs.value.length - 1]
  emit('selected', current.cid, current.name)
  emit('update:modelValue', false)
  breadcrumbs.value = [{ cid: '0', name: '115云盘' }]
}

function closeDialog() {
  emit('update:modelValue', false)
  breadcrumbs.value = [{ cid: '0', name: '115云盘' }]
}

watch(
  () => props.modelValue,
  (isOpen) => {
    if (isOpen) {
      loadDirectory('0', false)
    }
  }
)
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    max-width="600px"
    persistent
    @update:model-value="closeDialog"
  >
    <v-card class="p115-path-selector">
      <v-card-title class="d-flex align-center justify-space-between">
        <span>选择 115 云盘目录</span>
        <v-btn
          icon="mdi-refresh"
          size="small"
          variant="text"
          :loading="refreshing"
          :disabled="loading || refreshing"
          @click="refresh"
          title="刷新目录缓存"
        />
      </v-card-title>

      <v-divider />

      <v-card-text class="pa-4">
        <!-- 面包屑导航 -->
        <div class="breadcrumb-bar mb-4">
          <v-btn
            icon="mdi-arrow-left"
            size="small"
            variant="text"
            :disabled="breadcrumbs.length <= 1 || loading"
            @click="goBack"
            title="返回上一级"
          />
          <span class="breadcrumb-text">
            {{ breadcrumbs.map(b => b.name).join(' / ') }}
          </span>
        </div>

        <!-- 加载状态 -->
        <v-progress-linear v-if="loading" indeterminate class="mb-3" />

        <!-- 目录列表 -->
        <v-list v-else density="compact" class="directory-list">
          <v-list-item
            v-if="items.length === 0"
            disabled
            class="text-center text-grey"
          >
            <span>此目录为空</span>
          </v-list-item>

          <v-list-item
            v-for="item in items"
            :key="item.cid"
            @click="navigateToDirectory(item)"
            class="directory-item"
          >
            <template #prepend>
              <v-icon icon="mdi-folder" color="#245B7A" />
            </template>
            <v-list-item-title>{{ item.name }}</v-list-item-title>
            <template #append>
              <v-icon icon="mdi-chevron-right" size="small" color="#999" />
            </template>
          </v-list-item>
        </v-list>
      </v-card-text>

      <v-divider />

      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn variant="plain" @click="closeDialog" :disabled="loading">
          取消
        </v-btn>
        <v-btn
          color="#245B7A"
          variant="flat"
          @click="selectCurrentDirectory"
          :disabled="loading"
        >
          选择当前目录
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.p115-path-selector {
  min-height: 400px;
}

.breadcrumb-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid #e0e0e0;
  padding-bottom: 12px;
}

.breadcrumb-text {
  font-size: 14px;
  color: #666;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.directory-list {
  max-height: 400px;
  overflow-y: auto;
}

.directory-item {
  cursor: pointer;
  transition: background-color 0.2s;
}

.directory-item:hover {
  background-color: rgba(36, 91, 122, 0.08);
}
</style>
```

- [ ] **Step 2: 在 App.vue 中导入**

打开 `src/App.vue`，添加导入：

```javascript
import P115PathSelector from './components/P115PathSelector.vue'
```

- [ ] **Step 3: 单元测试**

创建 `tests/test_p115_path_selector.vue.test.js`：

```javascript
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import P115PathSelector from '@/components/P115PathSelector.vue'

describe('P115PathSelector.vue', () => {
  it('initializes with root directory', () => {
    const wrapper = mount(P115PathSelector, {
      props: {
        modelValue: true,
        api: {}
      },
      stubs: {
        VDialog: { template: '<div><slot /></div>' }
      }
    })

    expect(wrapper.vm.breadcrumbs[0].cid).toBe('0')
    expect(wrapper.vm.breadcrumbs[0].name).toBe('115云盘')
  })

  it('can go back to parent directory', async () => {
    const wrapper = mount(P115PathSelector, {
      props: {
        modelValue: true,
        api: {}
      }
    })

    wrapper.vm.breadcrumbs = [
      { cid: '0', name: '115云盘' },
      { cid: '123', name: 'movies' }
    ]

    await wrapper.vm.goBack()

    expect(wrapper.vm.breadcrumbs.length).toBe(1)
    expect(wrapper.vm.breadcrumbs[0].cid).toBe('0')
  })

  it('emits selected event with correct values', async () => {
    const wrapper = mount(P115PathSelector, {
      props: {
        modelValue: true,
        api: {}
      }
    })

    wrapper.vm.breadcrumbs = [
      { cid: '0', name: '115云盘' },
      { cid: '123', name: 'movies' }
    ]

    await wrapper.vm.selectCurrentDirectory()

    expect(wrapper.emitted('selected')).toBeTruthy()
    expect(wrapper.emitted('selected')[0]).toEqual(['123', 'movies'])
  })
})
```

- [ ] **Step 4: 提交**

```bash
git add src/components/P115PathSelector.vue src/App.vue tests/test_p115_path_selector.vue.test.js
git commit -m "feat(u115): add P115 path selector component"
```

---

### Task 6: 修改 PathMappingEditor.vue - 集成目录选择器

**Files:**
- Modify: `plugins/u115mediaupload/src/components/PathMappingEditor.vue`

**Interfaces:**
- Consumes: LocalPathSelector、P115PathSelector 组件
- Produces: 修改后的路径映射编辑器，支持目录选择

- [ ] **Step 1: 完整替换 PathMappingEditor.vue**

打开 `src/components/PathMappingEditor.vue`，完整替换为：

```vue
<script setup>
import { ref } from 'vue'
import LocalPathSelector from './LocalPathSelector.vue'
import P115PathSelector from './P115PathSelector.vue'
import { pluginRequest } from '../utils/plugin'

const props = defineProps({
  api: Object,
  mappings: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['update:mappings', 'toast'])

const localPathDialogOpen = ref(false)
const p115PathDialogOpen = ref(false)
const editingIndex = ref(null)
const savingMappings = ref(false)

function addMapping() {
  emit('update:mappings', [
    ...props.mappings,
    {
      enabled: true,
      source: '',
      sourceDesc: '',
      target: '/',
      targetCid: '0',
    },
  ])
}

function removeMapping(index) {
  emit('update:mappings', props.mappings.filter((_, idx) => idx !== index))
}

function toggleMapping(index) {
  const updated = [...props.mappings]
  updated[index].enabled = !updated[index].enabled
  emit('update:mappings', updated)
}

function openLocalPathSelector(index) {
  editingIndex.value = index
  localPathDialogOpen.value = true
}

function onLocalPathSelected(path) {
  if (editingIndex.value === null) return

  const mapping = props.mappings[editingIndex.value]
  const updated = [...props.mappings]
  const displayName = path.split('/').pop() || path || '媒体库'
  
  updated[editingIndex.value] = {
    ...mapping,
    source: path,
    sourceDesc: displayName,
  }
  
  emit('update:mappings', updated)
  localPathDialogOpen.value = false
  editingIndex.value = null
}

function openP115PathSelector(index) {
  editingIndex.value = index
  p115PathDialogOpen.value = true
}

function onP115PathSelected(cid, name) {
  if (editingIndex.value === null) return

  const mapping = props.mappings[editingIndex.value]
  const updated = [...props.mappings]
  
  updated[editingIndex.value] = {
    ...mapping,
    target: name,
    targetCid: cid,
  }
  
  emit('update:mappings', updated)
  p115PathDialogOpen.value = false
  editingIndex.value = null
}

async function saveMappings() {
  savingMappings.value = true
  try {
    const result = await pluginRequest(props.api, '/path_mappings', {
      method: 'POST',
      body: props.mappings,
    })

    if (!result?.success) {
      emit('toast', result?.msg || '保存失败', 'error')
      return
    }

    emit('toast', '路径映射已保存', 'success')
  } catch (error) {
    emit('toast', error?.message || '保存失败', 'error')
  } finally {
    savingMappings.value = false
  }
}
</script>

<template>
  <section class="mapping-editor">
    <!-- 表头 -->
    <div class="mapping-editor__head">
      <div>
        <div class="section-title">路径映射</div>
        <div class="section-subtitle">本地目录上传到对应 115 目录</div>
      </div>
      <v-btn color="#167A5B" variant="flat" size="small" @click="addMapping">
        <v-icon icon="mdi-plus" class="mr-1" />新增
      </v-btn>
    </div>

    <!-- 映射列表 -->
    <div v-if="!mappings.length" class="empty-line">暂无路径映射</div>

    <div v-else class="mappings-list">
      <div v-for="(mapping, index) in mappings" :key="index" class="mapping-row">
        <!-- 启用开关 -->
        <v-switch
          :model-value="mapping.enabled"
          color="#167A5B"
          density="compact"
          hide-details
          inset
          @update:model-value="toggleMapping(index)"
          class="mapping-switch"
        />

        <!-- 本地目录字段 -->
        <div class="path-field">
          <v-text-field
            :model-value="mapping.sourceDesc || mapping.source || '未选择'"
            label="本地目录"
            variant="outlined"
            density="compact"
            hide-details
            readonly
            prepend-inner-icon="mdi-folder-outline"
            class="path-input"
          />
          <v-btn
            icon="mdi-folder-open-outline"
            size="small"
            variant="text"
            color="#167A5B"
            @click="openLocalPathSelector(index)"
            title="浏览本地目录"
          />
        </div>

        <!-- 115 目录字段 -->
        <div class="path-field">
          <v-text-field
            :model-value="mapping.target || '未选择'"
            label="115 目录"
            variant="outlined"
            density="compact"
            hide-details
            readonly
            prepend-inner-icon="mdi-cloud-outline"
            class="path-input"
          />
          <v-btn
            icon="mdi-cloud-search-outline"
            size="small"
            variant="text"
            color="#245B7A"
            @click="openP115PathSelector(index)"
            title="浏览 115 目录"
          />
        </div>

        <!-- 删除按钮 -->
        <v-btn
          icon="mdi-delete-outline"
          size="small"
          variant="text"
          color="#B42318"
          @click="removeMapping(index)"
          title="删除此映射"
        />
      </div>
    </div>

    <!-- 保存按钮 -->
    <div v-if="mappings.length" class="mapping-actions mt-3">
      <v-btn
        color="#167A5B"
        variant="flat"
        :loading="savingMappings"
        @click="saveMappings"
      >
        <v-icon icon="mdi-content-save" class="mr-1" />保存映射
      </v-btn>
    </div>

    <!-- 本地目录选择器 -->
    <LocalPathSelector
      v-model="localPathDialogOpen"
      :api="api"
      @selected="onLocalPathSelected"
      @toast="(msg, type) => $emit('toast', msg, type)"
    />

    <!-- 115 目录选择器 -->
    <P115PathSelector
      v-model="p115PathDialogOpen"
      :api="api"
      @selected="onP115PathSelected"
      @toast="(msg, type) => $emit('toast', msg, type)"
    />
  </section>
</template>

<style scoped>
.mapping-editor {
  display: grid;
  gap: 12px;
}

.mapping-editor__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.section-title {
  font-weight: 700;
  color: #17201c;
}

.section-subtitle {
  color: #66736d;
  font-size: 13px;
  margin-top: 2px;
}

.empty-line {
  border: 1px dashed #d9e0da;
  color: #66736d;
  padding: 12px;
  border-radius: 8px;
  text-align: center;
}

.mappings-list {
  display: grid;
  gap: 12px;
}

.mapping-row {
  display: grid;
  grid-template-columns: 56px 1fr 1fr 44px;
  gap: 8px;
  align-items: center;
  padding: 12px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  background-color: #fafbfa;
  transition: background-color 0.2s;
}

.mapping-row:hover {
  background-color: #f5f7f6;
}

.mapping-switch {
  justify-self: center;
}

.path-field {
  display: flex;
  gap: 4px;
  align-items: center;
}

.path-input {
  flex: 1;
}

.mapping-actions {
  display: flex;
  gap: 8px;
}

@media (max-width: 1024px) {
  .mapping-row {
    grid-template-columns: 48px 1fr 44px;
  }

  .path-field:nth-child(3) {
    grid-column: 2 / 4;
  }
}

@media (max-width: 600px) {
  .mapping-row {
    grid-template-columns: 1fr;
  }

  .path-field {
    grid-column: 1 / -1;
  }
}
</style>
```

- [ ] **Step 2: 验证导入**

确保 `src/App.vue` 中已导入 PathMappingEditor：

```javascript
import PathMappingEditor from './components/PathMappingEditor.vue'
```

- [ ] **Step 3: 集成测试**

创建 `tests/test_path_mapping_integration.vue.test.js`：

```javascript
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import PathMappingEditor from '@/components/PathMappingEditor.vue'

describe('PathMappingEditor Integration', () => {
  it('can add new mapping', async () => {
    const wrapper = mount(PathMappingEditor, {
      props: {
        api: {},
        mappings: [],
      },
      stubs: {
        LocalPathSelector: true,
        P115PathSelector: true,
      }
    })

    const addBtn = wrapper.find('[icon="mdi-plus"]')
    await addBtn.trigger('click')

    expect(wrapper.emitted('update:mappings')).toBeTruthy()
    expect(wrapper.emitted('update:mappings')[0][0].length).toBe(1)
  })

  it('can toggle mapping enabled state', async () => {
    const mappings = [
      { enabled: true, source: '/a', sourceDesc: 'a', target: '/b', targetCid: '1' }
    ]
    const wrapper = mount(PathMappingEditor, {
      props: {
        api: {},
        mappings,
      },
      stubs: {
        LocalPathSelector: true,
        P115PathSelector: true,
      }
    })

    const switchComponent = wrapper.findComponent({ name: 'VSwitch' })
    await switchComponent.vm.$emit('update:modelValue', false)

    expect(wrapper.emitted('update:mappings')[0][0][0].enabled).toBe(false)
  })

  it('can remove mapping', async () => {
    const mappings = [
      { enabled: true, source: '/a', sourceDesc: 'a', target: '/b', targetCid: '1' },
      { enabled: true, source: '/c', sourceDesc: 'c', target: '/d', targetCid: '2' }
    ]
    const wrapper = mount(PathMappingEditor, {
      props: {
        api: {},
        mappings,
      },
      stubs: {
        LocalPathSelector: true,
        P115PathSelector: true,
      }
    })

    const deleteBtns = wrapper.findAll('[icon="mdi-delete-outline"]')
    await deleteBtns[0].trigger('click')

    expect(wrapper.emitted('update:mappings')[0][0].length).toBe(1)
    expect(wrapper.emitted('update:mappings')[0][0][0].source).toBe('/c')
  })
})
```

- [ ] **Step 4: 提交**

```bash
git add src/components/PathMappingEditor.vue tests/test_path_mapping_integration.vue.test.js
git commit -m "feat(u115): integrate path selector into PathMappingEditor"
```

---

### Task 7: 更新 package.json 依赖和最终集成

**Files:**
- Modify: `plugins/u115mediaupload/package.json`

**Interfaces:**
- Produces: 完整的前后端功能集成

- [ ] **Step 1: 检查 package.json 中的依赖**

```bash
cd C:\Users\84030\Documents\GitHub\MP\MoviePilot-Plugins\plugins\u115mediaupload
cat package.json
```

- [ ] **Step 2: 确保 qrcode 依赖在 __init__.py 的 requirements 中**

打开 `__init__.py`，在依赖列表中添加（如果没有）：

```python
# 在插件的 plugin_requirements 或依赖声明中添加
# requirements: ["qrcode>=7.4"]
```

或检查 `requirements.txt`：

```bash
cat requirements.txt
# 如果没有 qrcode，添加一行：
echo "qrcode>=7.4" >> requirements.txt
```

- [ ] **Step 3: 运行完整集成测试**

```bash
# 后端测试
cd C:\Users\84030\Documents\GitHub\MP\MoviePilot-Plugins\plugins\u115mediaupload
pytest tests/ -v

# 前端测试（如果配置了 vitest）
npm run test
```

预期输出：所有测试通过

- [ ] **Step 4: 手动集成测试**

在插件页面完整测试以下流程：

1. **二维码显示**
   - 打开「授权」部分，选择「扫码」模式
   - 点击「生成二维码」按钮
   - 验证二维码图片正确显示

2. **本地目录选择**
   - 打开「路径映射」部分
   - 点「新增」添加映射
   - 点本地目录右侧的「浏览」按钮
   - 验证目录树正确显示
   - 选择一个目录

3. **115 目录选择**
   - 在同一映射行，点 115 目录右侧的「浏览」按钮
   - 验证 115 目录树显示
   - 点「刷新」验证缓存重新加载
   - 选择一个目录

4. **保存映射**
   - 点「保存映射」按钮
   - 验证提示"映射已保存"
   - 刷新页面，验证映射仍然存在

- [ ] **Step 5: 最终提交**

```bash
git add requirements.txt package.json
git commit -m "feat(u115): complete qrcode and path mapping features

- Add qrcode library to dependencies
- Integrate all frontend components
- Support base64 qrcode image display
- Support local and 115 directory selection with caching
- Store path mappings to plugin database"
```

---

## 验收标准

所有任务完成后，验证以下功能：

- ✅ 二维码生成为 PNG 图片并以 base64 data URL 显示
- ✅ 本地目录浏览支持面包屑导航和选择
- ✅ 115 云盘目录浏览支持 24h 缓存和手动刷新
- ✅ 路径映射可启用/禁用和保存到数据库
- ✅ 所有 API 端点正确返回数据
- ✅ 前端组件正确交互和通讯
- ✅ 单元测试覆盖核心逻辑

---

## 自检清单

**Spec 覆盖：**
- ✅ 二维码生成与显示（Task 2 + 3）
- ✅ 本地目录浏览（Task 2 + 4）
- ✅ 115 目录浏览与缓存（Task 2 + 5）
- ✅ 路径映射编辑与保存（Task 2 + 6）
- ✅ 数据库存储（Task 1）

**代码质量：**
- ✅ 无占位符（所有代码完整）
- ✅ 类型一致（接口明确）
- ✅ 测试完备（单元 + 集成）
- ✅ 提交粒度合理（7 个原子任务）

---

## 执行选项

Plan 已完成并保存。两种执行方式可选：

**1. Subagent-Driven（推荐）** 
- 每个 Task 派发一个子代理
- Task 间有人工复审点
- 并行化程度高、反馈快

**2. Inline Execution**
- 在本会话中逐个执行
- 任务间有检查点
- 适合快速开发

选择哪种方式？
