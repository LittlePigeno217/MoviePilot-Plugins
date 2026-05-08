# MoviePilot V2 Vuetify 插件模板

这是一个适用于当前 `MoviePilot-Plugins` 仓库的 **V2 Vuetify JSON 插件模板**。

## 目录说明

```text
v2-vuetify-plugin/
├── __init__.py
└── README.md
```

## 使用方式

1. 复制整个目录到 `plugins/` 或 `plugins.v2/` 下的目标目录
2. 修改 `__init__.py` 中的：
   - 类名
   - `plugin_name`
   - `plugin_desc`
   - `plugin_icon`
   - `plugin_version`
   - `plugin_author`
   - `author_url`
   - `plugin_config_prefix`
3. 在仓库根目录 `package.json` 或 `package.v2.json` 中新增插件元数据
4. 如需定时任务，可补充 `get_service()`
5. 如需 API，可补充 `get_api()`

## 模板特性

- 默认 `vuetify` 渲染模式
- 内置 `get_form()` 配置页示例
- 内置 `get_page()` 状态页示例
- 内置 `/config`、`/status`、`/run` 三个基础 API
- 无前端构建依赖，适合轻量插件

## 适用场景

适合以下插件：
- 简单签到类
- 配置管理类
- 状态展示类
- 轻量任务执行类

## 注意事项

- 如果不需要 API，可以直接删除 `get_api()` 中的示例接口
- `get_form()` 返回值为：`(页面 JSON, 默认模型)`
- `get_page()` 返回值为：`页面 JSON`
- 若需 V2 兼容元数据，请优先维护 `package.v2.json`
