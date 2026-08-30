# 插件仓单测

测试统一放在仓库根 `tests/`，**不放在插件目录内** —— 插件的市场下发与本地同步按整目录
拷贝，插件目录内的测试会被一并下发到运行时副本。

## 目录结构

```
tests/
├─ _bootstrap.py   薄壳：定位 MoviePilot 后端入 sys.path，并把 plugins/ 暴露为 app.plugins
├─ conftest.py     pytest 引导：收集用例前准备插件环境
├─ checkin/
└─ p115liteassistant/
```

每个插件按插件 ID 建子目录。本仓插件在单一 `plugins/` 目录下开发、跨 V2 / V3 共用一套实现，
因此测试不做代际分层。

## 导入约定

必须通过生产命名空间导入插件及其子模块：

```python
from app.plugins.p115liteassistant.client import U115Client
```

不要把插件目录加入 `sys.path` 后用顶层包名导入 —— 那会让同一份源码产生两个模块身份，
导致事件订阅、类状态或插件实例重复创建。

## 运行

```bash
pytest                        # 全量，需要后端与插件依赖齐备
pytest tests/checkin          # 单个插件
```

配置见仓库根 `pytest.ini`。后端或插件依赖缺失时，`pytest` 会在收集阶段因导入失败中断整个
会话；此时按插件目录单独运行自带宿主桩的用例。

## 依赖

- `tests/checkin/` 自带 MoviePilot 宿主桩，只用标准库，任何环境可直接运行。
- `tests/p115liteassistant/` 需要 `httpx`、`fastapi`、`apscheduler`、`p115pickcode`
  以及 MoviePilot 后端的 `app` 包。

后端定位顺序：环境变量 `MOVIEPILOT_BACKEND_PATH`，其次是工作区同级目录
`<workspace>/MoviePilot`。后端缺失时引导不会中断收集，只有真正需要 `app.*` 的用例
会失败。
