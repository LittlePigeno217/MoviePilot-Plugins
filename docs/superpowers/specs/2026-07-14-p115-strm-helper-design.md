# 115 STRM 助手（P115StrmHelper）设计文档

> 状态：已确认，待转实现计划
> 日期：2026-07-14
> 灵感来源：DDSRem-Dev/MoviePilot-Plugins 的 p115strmhelper（GPL-3.0）。本插件为**原创实现**，仅借鉴其成熟做法，复用作者本人先前 U115MediaUpload 的手写 115 客户端代码；遵循 GPL-3.0 并致谢。

## 1. 背景与目标

为 MoviePilot 提供一个**聚焦、可维护**的 115 网盘 STRM 助手：扫描 115 网盘目录中的媒体，在本地生成 `.strm` 文件，供 Emby/Jellyfin 等媒体服务器**流式播放**（不下载媒体本体）。播放采用 **115 302 重定向**方案——`.strm` 指向插件的重定向端点，播放时实时换取 115 短时效直链并跳转，链接永不过期。

**明确不做**（与 p115strmhelper 区别）：不含 Rust 工具、打包 wheels、数据库迁移、MCP 集成、阿里云盘等重型/旁支功能。

## 2. 范围（v1.0.0）

### 核心基线
- **授权**：扫码（二维码图片）+ Cookie 两种方式
- **目录选择**：浏览器式选择 115 源目录、本地 `.strm` 输出目录
- **STRM 生成**：递归扫描 115 源目录中的媒体文件，生成 `.strm`（内容为指向重定向端点的 URL）
- **重定向端点**：播放时用 115 换取直链并 302 跳转
- **手动触发** + **生成历史/日志**

### 增强（v1.0.0 全部包含）
- **定时自动同步**：基于 MoviePilot 调度器，按 cron 自动扫描生成
- **增量同步**：仅处理新增/变化文件，跳过已生成的 `.strm`
- **刮削文件同步**：将 115 中的 nfo/海报/背景/字幕一并下载到本地，与 `.strm` 并列
- **多目录映射**：支持多组「115 源目录 → 本地输出目录」

## 3. 插件标识

| 项 | 值 |
|----|----|
| 插件 ID | `P115StrmHelper` |
| 名称 | 115 STRM 助手 |
| 版本 | 1.0.0 |
| 前端 | 联邦式 Vue 3 + Vuetify 3（沿用既有构建方式） |
| 图标 | 复用官方 cloud 图标或自备 |
| level | 1（公开可见） |

## 4. 架构

### 4.1 后端模块（关注点分离，每文件 ≤300 行、函数 ≤50 行）

```
plugins/p115strmhelper/
├── __init__.py     # 插件类：元数据、配置读写、API 路由表、调度注册、生命周期
├── client.py       # 115 开放平台客户端：扫码/登录轮询/token 刷新/目录列表/取直链
├── models.py       # dataclass：Mapping / SyncRecord / HistoryEntry
├── store.py        # 持久化：映射、增量状态、历史（经 _PluginBase.save_data/get_data）
├── strm.py         # STRM 生成：遍历 115 目录 → 媒体过滤 → 写 .strm → 增量比对
├── metadata.py     # 刮削同步：下载 nfo/海报/背景/字幕
├── redirect.py     # 302 解析：pickcode → 直链
├── api.py          # API 处理器：前端接口 + 重定向端点
├── requirements.txt
└── src/            # 前端（见 4.4）
```

### 4.2 115 客户端（复用作者旧代码 + 扩展）

从 git 历史（提交 `c5fcc5f~1`）取回作者手写的 `client.py`：
- **保留**：`generate_qrcode()`、`check_login()`、`refresh_access_token()`、`get_dir_list(cid)`、`get_folder()`、`get_item()`、token 管理
- **删除**：所有上传相关方法（`upload_file`、`_oss_upload`、`_init_upload`、`calc_sha1` 等 STRM 场景不需要的部分）
- **新增**：
  - `get_download_url(pickcode: str) -> str`：调用 115 开放平台取指定文件的短时效下载直链
  - `iter_files(cid, recursive=True) -> Iterator[dict]`：递归遍历目录，产出文件项（含 `name`、`pickcode`、`sha1`/`size`、相对路径），供 STRM 与增量使用

客户端与 115 的交互沿用既有的开放平台方式（`proapi.115.com` / `passportapi.115.com` / `qrcodeapi.115.com`），不引入 `p115client` 依赖。

### 4.3 数据模型（models.py）

```python
@dataclass
class Mapping:
    id: str                 # 稳定标识（生成时分配）
    enabled: bool
    source_cid: str         # 115 源目录的 cid
    source_path: str        # 115 源目录展示路径
    target_dir: str         # 本地 .strm 输出根目录（绝对路径）

@dataclass
class SyncRecord:
    file_key: str           # 唯一键：mapping_id + 115 相对路径
    pickcode: str
    sha1: str               # 或 size，用于判定"是否变化"
    strm_path: str          # 已生成的本地 .strm 路径

@dataclass
class HistoryEntry:
    time: str               # ISO 格式
    mapping_id: str
    added: int
    updated: int
    skipped: int
    errors: int
    duration_ms: int
    message: str
```

### 4.4 前端组件（src/components/）

| 组件 | 职责 |
|------|------|
| `AuthPanel.vue` | 扫码（二维码图片，base64 PNG）+ Cookie 输入 |
| `MappingEditor.vue` | 多组映射编辑 + 调起目录选择器 + 启用开关 |
| `Dir115Picker.vue` | 115 目录浏览弹窗（面包屑、进入子目录、选择当前目录） |
| `LocalDirPicker.vue` | 本地目录浏览弹窗（从 MoviePilot 媒体库根开始） |
| `SyncSettings.vue` | schedule cron、增量开关、刮削开关、`moviepilot_url` |
| `HistoryTable.vue` | 同步历史列表 |
| `Dashboard.vue` | 状态概览 + 手动触发同步按钮 |

前端经既有 `pluginRequest` 工具调用后端 API；构建产物 `dist/` 随插件发布。

## 5. 播放链路（302 核心）

### 5.1 `.strm` 内容
每个 `.strm` 文件写入单行 URL：
```
http://{moviepilot_url}/api/v1/plugin/P115StrmHelper/redirect?pickcode={pickcode}&apikey={API_TOKEN}
```
- `moviepilot_url`：用户配置的、**媒体服务器能访问到**的 MoviePilot 地址（如 `http://10.10.10.3:3001`）
- `pickcode`：115 文件稳定标识
- `apikey`：MoviePilot 的 `API_TOKEN`，使端点可被媒体服务器免登录访问

### 5.2 重定向端点
`GET /redirect?pickcode=&apikey=`：
1. 校验 `apikey`（经 MoviePilot 的 apikey 校验依赖）
2. `client.get_download_url(pickcode)` 取新直链
3. 返回 `RedirectResponse(url, status_code=302)`
4. 异常（pickcode 失效、未授权、取链失败）返回明确的 4xx/5xx，便于排查

### 5.3 端点认证
重定向端点使用 apikey 查询参数认证（媒体服务器无法做 Bearer 登录）；前端管理类 API 使用 Bearer 认证。

## 6. 生成流程（strm.py）

```
对每个 enabled 的 Mapping:
    遍历 client.iter_files(source_cid, recursive=True)
    对每个媒体文件（按扩展名过滤：mkv/mp4/ts/... 可配置默认集）:
        计算本地 .strm 路径 = target_dir / (115相对路径，扩展名换为 .strm)
        若 incremental 且 SyncRecord 存在且 sha1/size 未变 且 .strm 存在:
            skipped += 1; continue
        写入 .strm（含重定向 URL）
        更新 SyncRecord
        added/updated += 1
        若 sync_metadata:
            metadata.sync_sidecar(该媒体对应的 nfo/海报/背景/字幕 → 本地并列位置)
    追加 HistoryEntry
```

- 媒体扩展名默认集：`.mkv .mp4 .ts .m2ts .avi .mov .wmv .iso .rmvb .flv`
- 刮削并列文件：同名 `.nfo`、`poster.jpg`/`fanart.jpg`、`{basename}.zh.srt`/`.ass` 等；`metadata.py` 负责从 115 下载这些 sidecar 到 `.strm` 同目录

## 7. 调度（__init__.py）

- 读取 config 的 `schedule_cron`
- 经 MoviePilot 调度器注册周期任务，触发同步（全量或增量取决于 `incremental`）
- 手动触发通过 API `POST /sync` 立即执行（异步线程，避免阻塞请求）

## 8. API 端点清单

| 路径 | 方法 | 认证 | 说明 |
|------|------|------|------|
| `/qrcode` | POST | Bearer | 生成二维码（base64 PNG） |
| `/check_login` | GET | Bearer | 轮询扫码登录状态 |
| `/browse_115` | GET | Bearer | 浏览 115 目录（cid 导航） |
| `/browse_local` | GET | Bearer | 浏览本地目录（媒体库根起） |
| `/config` | GET/POST | Bearer | 读写配置（含 mappings、cron、开关、moviepilot_url） |
| `/sync` | POST | Bearer | 手动触发同步 |
| `/history` | GET | Bearer | 读取同步历史 |
| `/redirect` | GET | apikey | 302 重定向到 115 直链 |

统一响应格式：`{"success": bool, "message": str, "data": {...}}`（redirect 端点除外，直接 302）。

## 9. 持久化（store.py）

经 `_PluginBase.save_data(key, value)` / `get_data(key)` 存取三类数据：
- `config`（含 mappings 列表）
- `sync_state`（file_key → SyncRecord 的字典）
- `history`（HistoryEntry 列表，保留最近 N 条，如 100）

> 核对点：`_PluginBase` 实际提供 `get_data_path()`、`save_data()`、`get_data()`、`get_config()`（已在 MoviePilot 源码 `app/plugins/__init__.py` 确认）。**不得臆造方法名。**

## 10. 测试策略

Python 单元测试（保留真实有效的后端测试，不产出无法运行的前端测试）：
- `test_client.py`：mock HTTP，验证扫码返回结构、目录列表解析、`get_download_url` 组装
- `test_strm.py`：tmp 目录，验证 .strm 路径映射、内容格式、增量跳过逻辑
- `test_store.py`：验证 config/sync_state/history 存取与序列化
- `test_redirect.py`：mock client，验证 302 目标与 apikey 校验、异常码

完成后在**本地 MP 实例**（`PLUGIN_LOCAL_REPO_PATHS` 已指向本仓库）做运行时验证：加载插件不报错、扫码显示、目录选择、生成 .strm、302 可跳转。

## 11. 许可与致谢

- 插件遵循 GPL-3.0
- README 标注：灵感来源 DDSRem-Dev/MoviePilot-Plugins 的 p115strmhelper；115 客户端复用作者本人 U115MediaUpload 代码

## 12. 已知风险 / 待验证

- 115 开放平台直链可能与请求来源绑定：302 跳转到短时效签名 URL，媒体服务器跟随通常可播；极少数播放器可能需处理 UA。首版按标准 302 实现，遇兼容问题再加 UA 处理。
- `moviepilot_url` 配置错误会导致 .strm 不可播——UI 需明确提示"填媒体服务器能访问到的 MP 地址"。
- 大目录首次全量遍历耗时：手动触发走异步线程，避免阻塞；增量同步缓解后续重扫。
