# MoviePilot 插件模板索引

当前仓库已提供以下插件开发模板，便于快速创建新插件。

## 模板列表

### 1. `v2-vue-plugin`
位置：`templates/v2-vue-plugin/`

适用场景：
- 需要 Vue 模块联邦页面
- 需要复杂交互界面
- 需要自定义前端组件
- 需要独立构建前端产物

包含内容：
- 后端插件入口 `__init__.py`
- Vue 联邦前端骨架
- `Config.vue` / `Page.vue`
- `vite.config.js`
- `package.json`

特点：
- `get_render_mode() -> ("vue", "dist/assets")`
- 适合中大型 V2 插件

---

### 2. `v2-vuetify-plugin`
位置：`templates/v2-vuetify-plugin/`

适用场景：
- 轻量配置类插件
- 简单状态展示插件
- 无需独立前端构建的插件
- 仅使用宿主 Vuetify JSON 渲染

包含内容：
- 后端插件入口 `__init__.py`
- `get_form()` 配置页示例
- `get_page()` 状态页示例
- 基础 API 示例

特点：
- 默认 `vuetify` 渲染模式
- 无需 `vite` / `npm run build`
- 适合快速开发简单插件

---

## 如何选择

如果你的插件：
- 需要复杂页面、表格、弹窗、图表、上传、联邦远程组件 → 选 `v2-vue-plugin`
- 只需要简单表单、开关、文本配置、状态展示 → 选 `v2-vuetify-plugin`

## 通用开发步骤

1. 复制模板到 `plugins/<插件 ID 小写>/`
2. 修改插件类名与元信息（`plugin_name` / `plugin_version` 等）
3. 修改配置前缀，避免与已有插件冲突
4. 在根 `package.json` 中新增插件元数据：`version`、`release: true`、`v2: true`、`v3: true`、`history` 中的 `v<version>` 键（当前版本置顶、按语义版本降序）
5. 在根 `tests/<插件 ID 小写>/` 下添加测试，通过 `app.plugins.<插件 ID 小写>` 导入，不要放在插件目录内
6. 校验 Python 语法并运行 `pytest`
7. 如使用 Vue 模板，执行 `npm run build` 生成 `dist/assets/` **并连同 `package-lock.json` 提交进 Git**

发布相关的硬性要求见 [../docs/Repository_Guide.md](../docs/Repository_Guide.md)，测试约定见
[../tests/README.md](../tests/README.md)。

## 建议

- 轻量插件优先使用 `v2-vuetify-plugin`
- 复杂交互插件优先使用 `v2-vue-plugin`
- 插件类名、前端 `PLUGIN_ID`、索引元数据三者必须保持一致
- 插件源码目录固定为 `plugins/`，索引固定为根 `package.json`；一套实现兼容 V2 与 V3，不拆分代际目录
