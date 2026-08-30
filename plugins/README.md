# plugins 目录说明

插件源码目录，与仓库根 `package.json` 索引配对。这里的插件一套代码同时兼容 V2 与 V3，
因此不拆分 `plugins.v2/` / `plugins.v3/`。完整约定见
[../docs/Repository_Guide.md](../docs/Repository_Guide.md)。

## 当前插件

| 目录 | 插件 ID | 名称 |
|---|---|---|
| `checkin/` | `Checkin` | 自用签到工具 |
| `p115liteassistant/` | `P115LiteAssistant` | 115 轻量助手 |

## 要点

- 目录名 = 插件类名（索引中插件 ID）的小写形式。
- 索引条目需声明 `"v2": true` 与 `"v3": true`，表示两代宿主均可使用。
- 前端产物放 `dist/assets/`，`get_render_mode()` 返回 `("vue", "dist/assets")`。
- `package-lock.json` 必须提交（工作流的 npm 缓存键）。
- 测试放仓库根 `tests/<插件 ID 小写>/`，不要放在插件目录内。
- 新增插件从 [../templates/](../templates/) 复制模板起步。
