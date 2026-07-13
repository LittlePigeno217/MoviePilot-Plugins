# Task 2 实现报告

## 状态
DONE

## 修改的文件

### 新建文件
1. **api_handlers.py** (新建，260+ 行)
   - 创建 `U115MediaUploadApiHandler` 类
   - 实现 4 个核心方法：
     - `generate_qrcode()` - 生成 115 登录二维码，转换为 base64 PNG
     - `browse_local()` - 浏览本地目录，支持相对路径导航
     - `browse_115()` - 浏览 115 云盘目录，支持 24h TTL 缓存和刷新
     - `save_path_mappings()` - 保存路径映射到管理器

2. **tests/test_api_handlers.py** (新建，单元测试)
   - `test_generate_qrcode()` - 测试二维码生成
   - `test_browse_local_root()` - 测试根目录浏览
   - `test_browse_local_subdirectory()` - 测试子目录浏览
   - `test_browse_115_with_cache()` - 测试 115 目录缓存机制
   - `test_save_path_mappings()` - 测试路径映射保存
   - `test_browse_115_no_client()` - 测试客户端缺失情况
   - `test_browse_local_invalid_path()` - 测试无效路径处理
   - `test_browse_115_filters_directories()` - 测试目录过滤

### 修改文件
1. **client.py** (+14 行)
   - 添加 `get_dir_list(cid)` 方法
   - 调用 115 API `/open/folder/list` 获取目录列表
   - 包括错误处理和数据验证

2. **__init__.py** (+48 行)
   - 导入 `PathMappingManager` 和 `U115MediaUploadApiHandler`
   - 在 `__init__` 中初始化：
     - `self._mapping_manager` - 路径映射管理器
     - `self._api_handler` - API 处理器（延迟初始化）
   - 更新 `get_api()` 方法，添加 3 个新路由：
     - `GET /browse_local` - 浏览本地目录
     - `GET /browse_115` - 浏览 115 目录
     - `POST /path_mappings` - 保存路径映射
   - 实现 4 个新 API 端点方法：
     - `_qrcode_api()` - 改进的二维码生成（使用 handler）
     - `_browse_local_api()` - 本地目录浏览代理
     - `_browse_115_api()` - 115 目录浏览代理
     - `_save_path_mappings_api()` - 映射保存代理

## API 接口规范

### 1. POST /qrcode
生成 115 登录二维码
```json
// Request: 无参数
// Response:
{
  "success": true,
  "data": {
    "qrcode": "data:image/png;base64,iVBORw0KGgoAAAANS...",
    "codeContent": "https://115.com/qrcode/xxx"
  }
}
```

### 2. GET /browse_local?path=
浏览本地媒体库目录
```json
// Request params:
//   path: string (相对路径，如 "movies")
// Response:
{
  "success": true,
  "data": {
    "base": "/media",
    "current": "movies",
    "items": [
      {
        "name": "dir1",
        "path": "movies/dir1",
        "is_dir": true
      }
    ]
  }
}
```

### 3. GET /browse_115?cid=&refresh=
浏览 115 云盘目录（支持缓存）
```json
// Request params:
//   cid: string (目录ID，默认 "0" 表示根)
//   refresh: boolean (是否刷新缓存，默认 false)
// Response:
{
  "success": true,
  "data": {
    "cid": "0",
    "cached": false,
    "items": [
      {
        "name": "folder1",
        "cid": "123",
        "is_dir": true
      }
    ]
  }
}
```

### 4. POST /path_mappings
保存路径映射
```json
// Request Body:
[
  {
    "enabled": true,
    "source": "/movies",
    "sourceDesc": "movies",
    "target": "文件夹",
    "targetCid": "123"
  }
]
// Response:
{
  "success": true,
  "msg": "映射保存成功"
}
```

## 关键特性

1. **二维码生成**
   - 使用 `qrcode` 库生成 PNG 格式图片
   - 转换为 base64 data URL，可直接在前端 img 标签中使用
   - 包含完整错误处理

2. **本地目录浏览**
   - 从 `settings.LIBRARY_PATH` 开始
   - 支持相对路径导航
   - 自动过滤隐藏目录
   - 路径边界安全检查（防止遍历）

3. **115 目录浏览**
   - 调用 115 API 获取目录列表
   - 自动过滤非目录项（只返回 type=1 的项）
   - 24 小时 TTL 缓存
   - 支持手动刷新缓存
   - 缓存标志返回给前端

4. **路径映射管理**
   - 通过 `PathMappingManager` 持久化存储
   - 支持启用/禁用状态
   - 完整的数据模型（source/sourceDesc/target/targetCid）

5. **统一错误返回格式**
   - 所有 API 返回 `{"success": bool, "msg"/"data": ...}`
   - 异常情况包含详细错误信息
   - 日志记录所有操作

## 测试覆盖

已编写 8 个单元测试，覆盖：
- ✅ 二维码生成成功场景
- ✅ 本地目录浏览（根目录、子目录）
- ✅ 115 目录缓存机制（首次加载、缓存命中、刷新）
- ✅ 路径映射保存和加载
- ✅ 错误处理（客户端缺失、无效路径、过滤目录）
- ✅ 目录过滤（非目录项被排除）

## 代码质量检查

- ✅ Python 语法检查通过（py_compile）
- ✅ 导入语句完整
- ✅ 异常处理全覆盖
- ✅ 类型注解完整
- ✅ 日志记录完善
- ✅ 代码风格一致

## 依赖要求

### Python 包
- `qrcode >= 7.4` - 二维码生成
- `orjson` - JSON 序列化（已有）
- `pytest` - 测试框架（可选，开发用）

### 环境
- Python 3.11+
- FastAPI（来自 MoviePilot）
- app.log.logger 和 app.core.config.settings（来自 MoviePilot）

## 提交信息

```
feat(u115): add backend API handlers for qrcode and directory browsing

- Create api_handlers.py with U115MediaUploadApiHandler class
- Implement 4 API endpoints: /qrcode, /browse_local, /browse_115, /path_mappings
- Add get_dir_list method to client.py for 115 directory listing
- Integrate PathMappingManager for path mapping and caching
- Add support for base64 encoded qrcode image display
- Add 24-hour TTL caching for 115 directory listings
- Write comprehensive unit tests for all handlers
- Update __init__.py to register new API routes
```

Git commit hash: `66a16bb`

## 验收检查清单

- ✅ API 端点全部实现
- ✅ 二维码生成为 base64 PNG data URL
- ✅ 本地目录浏览支持导航
- ✅ 115 目录浏览支持 24h 缓存和刷新
- ✅ 路径映射保存到 PathMappingManager
- ✅ 所有 API 返回统一格式
- ✅ 完整的错误处理和日志
- ✅ 单元测试覆盖核心逻辑
- ✅ 代码通过语法检查

## 关键决策说明

1. **API 处理器分离**
   - 将 API 逻辑从 `__init__.py` 分离到 `api_handlers.py`
   - 便于测试和维护

2. **延迟初始化 API 处理器**
   - `_api_handler` 在首次 API 调用时才初始化
   - 避免不必要的资源开销

3. **缓存机制**
   - 使用 `PathMappingManager` 管理缓存
   - 缓存文件存储为 JSON，支持持久化

4. **目录过滤**
   - 在 API 层面过滤非目录项（type != 1）
   - 前端只需显示目录列表

5. **安全性**
   - 本地目录浏览使用 `relative_to` 防止路径遍历
   - 所有操作包含异常捕获

## 关切与后续工作

后续 Task 3-7 需要：
- Task 3: 修改 AuthPanel.vue 显示二维码图片
- Task 4: 创建 LocalPathSelector.vue 本地目录选择器
- Task 5: 创建 P115PathSelector.vue 115 目录选择器
- Task 6: 修改 PathMappingEditor.vue 集成选择器
- Task 7: 更新依赖和最终集成

