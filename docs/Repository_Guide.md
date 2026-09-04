# 仓库指南

本仓库是 MoviePilot 第三方插件源码仓库与插件市场索引，约定对齐
[官方插件仓](https://github.com/jxxghp/MoviePilot-Plugins)。本文档说明目录约定、
版本规则、发布流程，以及与官方约定的有意差异。

## 1. 目录结构

```text
MoviePilot-Plugins/
├── plugins/             # 插件源码，一个插件一个目录，跨 V2 / V3 共用一套实现
├── package.json         # 插件市场索引
├── tests/               # 插件单测，按插件 ID 建子目录
├── pytest.ini
├── docs/                # 文档
├── scripts/             # 仓库维护脚本（generate_readme / nas / check_ui_spec）
├── templates/           # 插件开发模板
└── .github/workflows/   # 自动发布工作流
```

## 2. 索引与源码目录的对应关系

官方约定索引文件与源码目录严格对应，发布脚本按索引文件名后缀推导源码目录：

| 索引文件 | 源码目录 | 用途 |
|---|---|---|
| `package.json` | `plugins/` | 跨版本共用一套实现 —— **本仓库使用这种** |
| `package.v2.json` | `plugins.v2/` | 仅维护 V2 历史实现时使用 |
| `package.v3.json` | `plugins.v3/` | 依赖 V3 新合同的专用实现 |

本仓库的插件一套代码同时兼容 V2 与 V3，因此按官方规则使用 `plugins/ + package.json`，
并在每个条目上声明兼容标记：

```json
{
  "MyPlugin": {
    "version": "1.0.0",
    "release": true,
    "v2": true,
    "v3": true
  }
}
```

宿主的版本选择规则：

- V2 环境优先读 `package.v2.json`；无条目时回退到 `package.json` 中声明了 `"v2": true` 的实现。
- V3 环境优先读 `package.v3.json`；无条目时回退到未声明 `"v3": false` 的实现。

## 3. 插件目录约定

- 一个插件一个目录，目录名必须是插件类名（也即索引中插件 ID）的**小写**形式：
  `class Checkin` → `plugins/checkin/`。
- 插件主类必须定义在该目录的 `__init__.py` 中。
- 额外 Python 依赖写 `requirements.txt`。
- Vue 联邦构建产物放 `dist/assets/`，`get_render_mode()` 返回 `("vue", "dist/assets")`。
- 测试**不放在插件目录内**，统一放仓库根 `tests/<插件 ID 小写>/`。插件的市场下发与本地同步
  按整目录拷贝，放在里面会被一并下发到运行时副本。

单个插件目录的完整形态：

```text
plugins/<id>/
├── __init__.py        # 插件入口，含 plugin_version
├── *.py               # 其它后端模块
├── requirements.txt   # 可选
├── dist/assets/       # 前端构建产物
├── src/               # Vue 源码，不随发布包分发
├── index.html
├── vite.config.js
├── package.json
└── package-lock.json
```

## 4. 版本号规则

发布前必须核对三处一致，任一处不符发布任务会直接 `[Fatal]` 退出：

1. `package.json` 中该插件的 `version`
2. 插件 `__init__.py` 中的 `plugin_version`（若存在 `version.py` 的 `VERSION`，优先级更高）
3. `package.json` 的 `history` 中存在 `v<version>` 键，用作 Release 正文

同时该插件必须标记 `"release": true`。

`history` 必须以当前版本置顶并按语义版本降序排列。

## 5. 前端构建

发布工作流按「插件目录内是否有 `package.json`」判断是否需要构建前端，**与源码目录名无关**。
命中时在 CI 中执行 `npm install && npm run build:web`，再打包并剔除前端源码与开发配置
（`src/`、`node_modules/`、`package*.json`、`vite.config.*`、`index.html`、`build*.js`）。

由此产生两条硬约束：

- **`build:web` 脚本名不能改**，工作流按这个名字调用。
- **`package-lock.json` 必须提交**，`actions/setup-node` 的 npm 缓存以它为键，缺失会直接失败。
  （官方插件目录用 `.gitignore` 忽略它，本仓库因此有意保留。）

`dist/` 仍随代码提交：便于本地/离线安装、也让产物变更在 diff 中可见；正式发布包用的是
CI 重新构建的产物。改动前端后本地执行：

```bash
cd plugins/<id>
npm install
npm run build          # = vite build，产物落到 dist/assets/
```

## 6. 发布流程

- **自动**：向 `main` push 且改动匹配 `package*.json`，且某插件 `version` 发生变化。
- **手动**：`workflow_dispatch`，源码目录选 `plugins`，输入插件 ID。手动模式允许覆盖
  同名 Release/Tag，自动模式遇到同名会失败。
- Tag 格式 `插件ID_v版本号`，归档名 `插件目录小写_v版本号.zip`。

### 提交顺序注意

`.github/scripts/get_plugin_meta.py` 的 `handle_push()` 用一个 `try` 包住整个文件循环。
若同一个 commit 里既改了 `package.json`（版本升级）又改动/删除了其它 `package*.json`
文件，先处理的文件一旦抛异常，后续插件的发布检测会被一并跳过。

**版本升级请单独提交**，不要和其它 `package*.json` 变更混在一个 commit 里。

## 7. 与官方约定的有意差异

| 项 | 官方 | 本仓库 | 原因 |
|---|---|---|---|
| 插件目录 `package-lock.json` | `.gitignore` 忽略 | 提交 | 本仓工作流用它做 npm 缓存键 |
| 测试子目录层级 | `tests/v1`、`tests/v2`、`tests/v3` 分代 | `tests/<插件 ID>` 直接分插件 | 只有一个源码目录，代际层无意义 |
| `icons/` | 有 | 无 | 索引里的 `icon` 直接引用完整 HTTP URL |
| `system_version` | 推荐声明 | 未声明 | 尚未确定各插件的最低宿主版本 |
| `.githooks/`、`tests/ci/` 门禁 | 有 | 无 | 两个插件的规模用不上 |

## 8. 真机联调

`AGENTS.md` 要求插件必须在 NAS 上的 MoviePilot Docker Compose 里调试。入口是
[`scripts/nas.sh`](../scripts/nas.sh)：

```bash
scripts/nas.sh ver                                  # 本地 / 宿主 / 容器三处版本 + 内容指纹
scripts/nas.sh deploy checkin p115liteassistant     # 打包 → 推两处 → 清残留 → 重启 → 等加载
scripts/nas.sh log p115liteassistant -n 40          # 插件自己的日志
scripts/nas.sh replay probe.py                      # 用容器里的真运行时跑一段脚本
scripts/nas.sh psql query.sql                       # 配置与插件数据都在 Postgres
```

这台机器上有四件事必须知道，否则「部署完了行为没变」会反复出现：

**1. 运行时目录在容器内。** Python 真正 import 的是容器内 `/app/app/plugins/<id>/`；宿主挂载点
`…/MoviePilot-v2/plugins/<id>/` 只是 MoviePilot 的安装位置，不是任何 bind mount。只写一处，
跑的还是旧代码。`deploy` 一次写两处。

**2. 版本号比不出「同版本改了代码」。** 开发中间态不升版本号，只对 `plugin_version` 就会在容器
跑着旧代码时报「一致」。`ver` 因此按 `.py` / `requirements.txt` / `dist` 的内容算指纹，两边各自
列文件再比 —— 容器里残留的旧模块也会让指纹对不上。

**3. `tar` 只覆盖不删除。** 改名前的模块、上一版的 `remoteEntry`、早年放在插件目录里的
`tests/`（真机上确实躺着一份）会一直留在运行时副本里被 import。`deploy` 先清后铺：清掉所有
`.py` 与整个 `dist/`，`index.html`、`package.json` 这些市场安装留下的文件不动。

**4. 热重载不重绑 HTTP 路由。** 文件监控只调 `PluginManager().reload_plugin(pid)`，而重绑路由的
`_update_plugin_api_routes()` 只在 HTTP 重载端点和启动时调用。于是接口仍指向已销毁实例的
bound method，内存态（锁、任务集、探针）全是僵尸的，还会出现两个实例各持一把锁同时动同一批
数据。改了 `.py` 就必须重启容器（`deploy` 默认这么做），只改 `dist/` 才用 `--no-restart`。

另外：新增配置键要**先部署代码再写配置** —— 旧版本代码一次 `init_plugin` 就会把它不认识的键
按 `DEFAULT_CONFIG` 白名单洗掉。

## 9. 相关文档

- 插件界面规范：[Plugin_UI_Spec.md](Plugin_UI_Spec.md) —— 令牌、数值、两套外壳、词表与文案规矩
- 测试约定与运行方式：[../tests/README.md](../tests/README.md)
- 插件开发模板：[../templates/README.md](../templates/README.md)
- 插件目录说明：[../plugins/README.md](../plugins/README.md)
