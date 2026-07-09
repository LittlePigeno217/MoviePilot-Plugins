# 115 媒体上传与刮削文件插件实现计划

## 目标

基于已确认的 `2026-07-10-u115-media-upload-design.md`，实现一个 MoviePilot V2 Vue 模块联邦插件：

- 插件后端独立内嵌 115 上传客户端。
- 支持 Cookie 与扫码登录。
- 支持本地目录全量上传、增量上传、整理完成事件触发增量上传。
- 支持上传媒体文件、本地已有附属文件，以及调用 MoviePilot 刮削后上传生成的元数据文件。
- 前端使用 Vue 分离式 UI，提供配置页、状态页和任务控制台。

## 实施顺序

### 1. 搭建插件骨架

新增目录 `plugins/u115mediaupload/`，从 `templates/v2-vue-plugin` 复制并改造：

- `__init__.py`
- `package.json`
- `vite.config.js`
- `build-zip.js`
- `index.html`
- `src/App.vue`
- `src/main.js`
- `src/utils/plugin.js`
- `src/components/Config.vue`
- `src/components/Page.vue`

同时更新 `package.json` 插件元数据，新增 `U115MediaUpload` 条目。

验收点：

- 后端类名为 `U115MediaUpload`。
- `get_render_mode()` 返回 `("vue", "dist/assets")`。
- 基础 API `/config`、`/status` 可返回稳定结构。

### 2. 实现配置和状态模型

在 `__init__.py` 中实现配置读写和运行状态：

- `enabled`
- `auth_mode`
- `cookie`
- `tokens`
- `path_mappings`
- `media_extensions`
- `sidecar_extensions`
- `upload_existing_sidecars`
- `scrape_before_upload`
- `cron`
- `concurrency`

插件数据保存：

- `records`
- `history`
- `failures`
- `last_status`

验收点：

- 保存配置后重新初始化插件，状态保持一致。
- 不把 115 token 写入 MoviePilot 全局存储配置。

### 3. 实现扫描与增量记录

新增 `scanner.py` 和 `records.py`：

- 扫描启用的路径映射。
- 识别媒体文件扩展名。
- 按开关识别附属文件扩展名。
- 将本地路径映射为 115 目标路径。
- 使用 `path + size + mtime` 判断增量变化。
- 支持清空增量记录。

验收点：

- 全量模式返回所有匹配文件。
- 增量模式只返回新增或变更文件。
- Windows 路径能稳定映射到 115 POSIX 路径。

### 4. 实现 115 客户端

新增 `client.py`，参考 MoviePilot 内置 `U115Pan` 和 DDSRem 115 插件实现：

- Cookie 请求模式。
- 扫码登录、登录检查、token 刷新。
- 115 目录查询和递归创建。
- 文件 SHA1 与前 128MB SHA1 计算。
- 上传初始化。
- 二次认证。
- 秒传判断。
- OSS 分片上传。
- 上传后查询文件信息。

验收点：

- 秒传分支和真实上传分支代码路径可被 mock 测试覆盖。
- 未授权时返回明确错误，不启动任务。
- 上传失败只影响当前文件，任务继续处理后续文件。

### 5. 实现刮削编排

新增 `scraper.py`：

- 包装 `MediaChain.scrape_metadata(...)`。
- 在 `scrape_before_upload` 开启时先执行刮削。
- 刮削后重新扫描附属文件。
- 刮削失败记录到任务结果，但不中断媒体上传。

验收点：

- 两个开关互不影响：
  - 上传已有附属文件。
  - 先刮削再上传生成文件。
- 刮削失败时媒体文件仍进入上传计划。

### 6. 实现任务执行与事件触发

在 `__init__.py` 中实现：

- `/run_full`
- `/run_incremental`
- `/stop`
- `/history`
- `/clear_records`
- 定时增量服务。
- 监听 `EventType.TransferComplete`。

任务状态包含：

- `idle`
- `scanning`
- `scraping`
- `uploading`
- `completed`
- `failed`
- `stopped`

统计包含：

- 扫描数。
- 待上传数。
- 秒传成功数。
- 上传成功数。
- 失败数。

验收点：

- 同一时间只允许一个任务运行。
- 手动停止后不再处理新文件。
- `TransferComplete` 事件只触发相关目录的增量上传。

### 7. 实现 Vue UI

改造前端组件：

- `Config.vue`
  - 基础配置、路径映射、扩展名、刮削开关、定时配置。
- `Page.vue`
  - 简版状态、手动全量/增量、最近结果。
- `AppPage.vue`
  - 完整控制台。
- `AuthPanel.vue`
  - Cookie / 扫码登录。
- `PathMappingEditor.vue`
  - 多路径映射编辑。
- `TaskConsole.vue`
  - 任务按钮、阶段、统计、日志。
- `HistoryTable.vue`
  - 历史和失败记录。

验收点：

- 任务运行中按钮禁用。
- 授权状态可见。
- 配置保存后 UI 与后端状态一致。
- 移动端不出现文字重叠。

### 8. 测试与验证

优先补充测试：

- `tests/test_u115mediaupload_scanner.py`
- `tests/test_u115mediaupload_records.py`
- `tests/test_u115mediaupload_client.py`
- `tests/test_u115mediaupload_plugin.py`

验证命令：

```powershell
python -m pytest tests/test_u115mediaupload_scanner.py tests/test_u115mediaupload_records.py tests/test_u115mediaupload_client.py tests/test_u115mediaupload_plugin.py
npm install
npm run build
```

如本地 MoviePilot 后端可用，再做手动验证：

- 插件能加载。
- 配置能保存。
- 全量/增量 API 返回正常。
- 使用临时目录模拟扫描和增量记录。

真实 115 上传不纳入自动测试，只做手动验证。

## 风险与处理

- 115 接口可能变化：客户端错误信息需要保留原始响应摘要。
- Cookie 模式和 token 模式鉴权头不同：客户端内部按 `auth_mode` 分支处理。
- 刮削生成文件依赖 MoviePilot 元数据配置：失败只记录，不阻塞媒体上传。
- 大文件真实上传耗时长：任务状态必须能持续展示当前文件和计数。
