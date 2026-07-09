# 115 媒体上传与刮削文件插件设计

## 结论

新插件采用 MoviePilot V2 Vue 模块联邦插件形态，插件后端独立内嵌 115 客户端能力，不依赖 DDSRem 的 `P115Disk` 或 `P115StrmHelper` 已安装状态。前端使用 Vue 前后端分离方式实现一个任务控制台，负责授权、配置、全量/增量上传、任务状态、日志和历史记录。

最小交付聚焦四件事：

1. 上传本地媒体文件到 115。
2. 支持全量上传和基于文件指纹的增量上传。
3. 支持上传本地已有附属文件，并可选择先调用 MoviePilot 刮削生成元数据文件再上传。
4. 支持 Cookie 与扫码两种 115 授权方式。

## 已确认需求

- 115 上传和秒传能力必须独立内嵌到新插件中。
- 需要参考 DDSRem 115 插件的秒传流程，但不能要求用户安装 DDSRem 115 插件。
- 文件来源同时支持：
  - 配置本地目录后扫描上传。
  - 监听 MoviePilot 整理完成事件作为自动增量入口。
- “刮削文件”包含两类，且都要有独立开关：
  - 上传本地已有附属文件，例如 `.nfo`、`.jpg`、`.png`、`.srt`、`.ass`、`.ssa`、`.sup`。
  - 上传前调用 MoviePilot 刮削能力生成 `.nfo`、海报、背景图等文件，再上传生成结果。
- 115 授权同时支持 Cookie 配置和扫码登录。
- UI 使用 Vue 前后端分离插件方式，不使用 Vuetify JSON 表单作为主界面。

## 不做范围

- 不做跨网盘同步。
- 不做 STRM 生成。
- 不实现媒体库删除同步。
- 不做复杂任务队列持久化恢复；本期只保留当前任务状态、最近历史和增量记录。
- 不新增 Python 依赖。MoviePilot 已有 `httpx`、`oss2`、`cryptography` 可满足 115 上传实现。

## 参考依据

- MoviePilot 内置 115 存储模块：`app/modules/filemanager/storages/u115.py`
  - 已有扫码登录、token 刷新、SHA1、115 上传初始化、二次认证、秒传判断、OSS 分片上传流程。
- MoviePilot 刮削入口：`app/chain/media.py`
  - `MediaChain.scrape_metadata(...)` 可生成 NFO 和图片元数据。
- MoviePilot 整理完成事件：`app/chain/transfer.py`
  - `EventType.TransferComplete` 携带 `fileitem`、`meta`、`mediainfo`、`transferinfo`。
- MoviePilot-Plugins Vue 模板：`templates/v2-vue-plugin`
  - `get_render_mode() -> ("vue", "dist/assets")`。

## 插件结构

插件目录建议为 `plugins/u115mediaupload`，后端类名建议为 `U115MediaUpload`。

```text
plugins/u115mediaupload/
├── __init__.py
├── client.py
├── scanner.py
├── records.py
├── scraper.py
├── package.json
├── vite.config.js
├── build-zip.js
├── index.html
└── src/
    ├── App.vue
    ├── main.js
    ├── utils/plugin.js
    └── components/
        ├── Config.vue
        ├── Page.vue
        ├── AppPage.vue
        ├── AuthPanel.vue
        ├── PathMappingEditor.vue
        ├── TaskConsole.vue
        └── HistoryTable.vue
```

### 后端模块

- `__init__.py`
  - 插件生命周期、配置读写、API 注册、定时任务、事件监听。
- `client.py`
  - 独立 115 客户端。负责 Cookie/token、扫码、目录创建、文件查询、秒传、OSS 上传。
- `scanner.py`
  - 根据路径映射扫描媒体文件和附属文件，生成上传计划。
- `records.py`
  - 管理增量记录、任务历史、失败记录。
- `scraper.py`
  - 调用 `MediaChain.scrape_metadata(...)`，并在刮削后收集新增或变更的元数据文件。

## 115 上传设计

上传流程参考 MoviePilot 内置 `U115Pan.upload()` 和 DDSRem 115 插件中的秒传判断：

1. 计算文件全量 SHA1。
2. 计算前 128MB SHA1 作为 `preid`。
3. 调用 115 上传初始化接口。
4. 如果返回需要二次认证，按 `sign_check` 指定范围计算 SHA1，再次初始化。
5. 如果返回秒传状态，记录为秒传成功并返回目标文件信息。
6. 如果不能秒传，获取 OSS 上传凭证。
7. 执行 OSS 分片上传。
8. 完成上传回调后查询目标文件信息。

Cookie 模式保存 Cookie 配置。扫码模式保存 `access_token`、`refresh_token`、`expires_in`、`refresh_time` 到插件自身配置或数据中，不写入 MoviePilot 全局 115 存储配置。

## 扫描与增量

路径映射配置为多组：

```json
[
  {
    "source": "D:/Media/Movies",
    "target": "/Media/Movies",
    "enabled": true
  }
]
```

全量上传：

- 扫描所有启用映射下的媒体文件。
- 根据配置决定是否包含已有附属文件。
- 根据配置决定是否先执行刮削并收集生成文件。
- 对扫描结果逐项上传。
- 成功后写入增量记录。

增量上传：

- 扫描同样的路径范围。
- 使用 `path + size + mtime` 作为基础指纹。
- 指纹不存在或变化则进入上传计划。
- 上传成功后更新记录。

事件触发：

- 监听 `EventType.TransferComplete`。
- 从事件数据读取整理后的目标目录和媒体信息。
- 将本次整理结果所在目录作为增量扫描范围。
- 字幕和音频不单独监听事件，作为同目录附属文件由扫描规则带出。

## 刮削设计

两个独立开关：

- `upload_existing_sidecars`
  - 上传本地已有附属文件。
- `scrape_before_upload`
  - 上传前调用 MoviePilot 刮削生成元数据文件。

执行顺序：

1. 扫描媒体文件。
2. 如果开启 `scrape_before_upload`，先对媒体文件或目录调用刮削。
3. 重新扫描附属文件扩展名，补充上传计划。
4. 上传媒体和附属文件。

刮削失败时：

- 媒体文件上传不因为刮削失败而中断。
- 失败信息进入任务结果。
- 生成文件缺失时只跳过对应附属文件。

## Vue UI 设计

UI 采用“传输台 / 调度台”风格，信息密度高、偏后台工具，不做展示型页面。

### 色彩

| 用途 | 色值 |
| --- | --- |
| 背景 | `#F6F8F7` |
| 主文本 | `#17201C` |
| 面板线 | `#D9E0DA` |
| 115 动作色 | `#167A5B` |
| 警告 | `#B7791F` |
| 错误 | `#B42318` |
| 数据强调 | `#245B7A` |

### 页面布局

```text
顶部栏
[115媒体上传] [授权状态] [运行状态]          [全量上传] [增量上传] [停止]

主体
┌ 左侧：任务控制 ─────────────┐ ┌ 右侧：执行状态 ─────────────┐
│ 授权方式：Cookie / 扫码     │ │ 当前任务进度                 │
│ 源目录 -> 115目标目录映射   │ │ 扫描/待传/秒传/上传/失败统计 │
│ 上传模式、定时、并发        │ │ 最近日志                     │
│ 刮削开关                   │ │ 失败列表                     │
└────────────────────────────┘ └────────────────────────────┘

底部
增量记录表 / 最近任务历史 / 路径映射详情
```

### 组件职责

- `Config.vue`
  - 插件启用、授权方式、路径映射、扩展名、刮削开关、定时配置。
- `Page.vue`
  - 插件详情页中的简版状态、手动全量/增量按钮、最近任务摘要。
- `AppPage.vue`
  - 侧栏全页控制台，承载完整任务控制、状态、历史和失败列表。
- `AuthPanel.vue`
  - Cookie 输入、二维码生成、登录检查、授权状态。
- `PathMappingEditor.vue`
  - 多组本地源目录和 115 目标目录映射编辑。
- `TaskConsole.vue`
  - 全量上传、增量上传、停止任务、当前阶段、统计计数。
- `HistoryTable.vue`
  - 展示任务历史、增量记录和失败项。

### 前端交互

- 授权方式使用分段控件：`Cookie` / `扫码登录`。
- 刮削设置使用两个独立开关。
- 任务按钮在运行中禁用，避免并发执行。
- 运行阶段显示为：`扫描中`、`刮削中`、`秒传检测`、`上传中`、`完成`、`失败`。
- 失败列表展示本地路径、115 目标路径、失败原因、时间。
- 空状态不展示说明性大段文字，只提供必要操作入口。

## API 设计

后端注册以下插件 API：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/config` | 获取配置 |
| POST | `/config` | 保存配置 |
| GET | `/status` | 获取运行状态 |
| POST | `/run_full` | 手动全量上传 |
| POST | `/run_incremental` | 手动增量上传 |
| POST | `/stop` | 请求停止当前任务 |
| POST | `/qrcode` | 生成 115 登录二维码 |
| GET | `/check_login` | 检查扫码登录状态 |
| GET | `/history` | 获取任务历史和失败记录 |
| POST | `/clear_records` | 清理增量记录 |

## 状态与数据

插件配置保存：

- 是否启用。
- 授权方式。
- Cookie。
- 115 token 信息。
- 路径映射。
- 媒体扩展名。
- 附属文件扩展名。
- 是否上传已有附属文件。
- 是否上传前刮削。
- 定时增量 cron。
- 并发数。

插件数据保存：

- 当前任务状态。
- 最近任务历史。
- 失败记录。
- 增量记录。

增量记录按本地路径保存：

```json
{
  "D:/Media/Movies/A.mkv": {
    "size": 123456,
    "mtime": 1783650000,
    "target": "/Media/Movies/A.mkv",
    "uploaded_at": "2026-07-10 10:00:00"
  }
}
```

## 错误处理

- 未授权：任务不启动，状态显示需要登录。
- 源目录不存在：该映射跳过并记录失败。
- 115 目录创建失败：当前文件失败，任务继续。
- 秒传失败：自动进入真实上传。
- 上传失败：记录失败项，任务继续处理后续文件。
- 刮削失败：记录刮削失败，媒体上传继续。
- 用户停止任务：当前文件完成或失败后停止后续计划。

## 测试计划

单元测试：

- 扫描器能按媒体扩展名和附属扩展名生成计划。
- 增量记录能识别新增、修改、未变化文件。
- 路径映射能正确生成 115 目标路径。
- 刮削开关组合能生成正确上传计划。
- 115 客户端上传流程中秒传分支、二次认证分支、OSS 上传分支可用 mock 覆盖。

集成验证：

- 插件能加载配置页和状态页。
- `/config`、`/status`、`/run_full`、`/run_incremental` 基础 API 返回结构正确。
- 使用临时目录验证全量和增量扫描。
- 不使用真实 115 账号做自动测试；真实上传只作为手动验证项。

## 交付标准

- 新插件能在 MoviePilot-Plugins 中构建。
- 前端为 Vue 模块联邦插件，`get_render_mode()` 返回 `("vue", "dist/assets")`。
- 配置页可保存路径映射、授权、刮削开关和定时配置。
- 状态页可触发全量、增量上传并查看任务结果。
- 后端具备独立 115 上传客户端，不依赖 DDSRem 插件安装。
- 增量记录可持久化，清理记录后可重新全量上传。
