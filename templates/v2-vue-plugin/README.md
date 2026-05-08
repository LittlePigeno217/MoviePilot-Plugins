# MoviePilot V2 Vue 插件模板

这是一个适用于当前 `MoviePilot-Plugins` 仓库的 **V2 Vue 模块联邦插件模板**。

## 目录说明

```text
v2-vue-plugin/
├── __init__.py
├── package.json
├── vite.config.js
├── build-zip.js
├── index.html
├── README.md
└── src/
    ├── App.vue
    ├── main.js
    ├── utils/
    │   └── plugin.js
    └── components/
        ├── Config.vue
        └── Page.vue
```

## 使用方式

1. 复制整个目录到 `plugins.v2/<你的插件目录名>/`
2. 修改 `__init__.py` 中的：
   - 类名
   - `plugin_name`
   - `plugin_desc`
   - `plugin_icon`
   - `plugin_version`
   - `plugin_author`
   - `author_url`
   - `plugin_config_prefix`
3. 修改 `src/utils/plugin.js` 中的 `PLUGIN_ID`，保持与后端类名一致
4. 修改 `vite.config.js` 中的联邦名称
5. 在仓库根目录 `package.v2.json` 中新增插件元数据
6. 安装依赖并构建：
   - `yarn`
   - `yarn build`

## 模板特性

- Vue 联邦模式：`get_render_mode() -> ("vue", "dist/assets")`
- 内置配置页 `Config.vue`
- 内置状态页 `Page.vue`
- 提供基础 API：
  - `/config`
  - `/status`
  - `/run`
- 包含 ZIP 打包脚本

## 注意事项

- `PLUGIN_ID` 必须与 Python 插件类名一致
- 最终安装包至少应包含：`__init__.py` 和 `dist/`
- 如果你需要定时任务，可在 `get_service()` 中返回 `CronTrigger`
- 如果你需要侧栏全页入口，可补充 `get_sidebar_nav()` 与 `AppPage.vue`
