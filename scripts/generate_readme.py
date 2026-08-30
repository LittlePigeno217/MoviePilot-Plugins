from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE_FILE = ROOT / "package.json"
README_FILE = ROOT / "README.md"

REPO_TITLE = "# 🎬 MoviePilot-Plugins"
REPO_DESC = "MoviePilot 第三方插件库，提供了一系列实用插件来增强 MoviePilot 的功能。"
REPO_NOTE = "> ⚠️ 注意：本插件库为个人维护，代码结构参考了其他开源项目。推荐优先使用[官方插件库](https://github.com/jxxghp/MoviePilot-Plugins)。"
GENERATED_NOTE = "> [!NOTE]\n> 本文件由 `scripts/generate_readme.py` 根据 `package.json` 自动生成，请优先修改数据源而不是直接手改本文件。"

EMOJI_MAP = {
    "自用签到工具": "✅",
    "115 轻量助手": "☁️",
}

FEATURES_MAP = {
    "Checkin": [
        "🔐 支持 Cookie 签到与账号密码自动登录",
        "🧩 已适配站点：FLZT、恩山无线论坛、易破解",
        "⏰ 支持定时签到与手动立即签到",
        "📨 签到结果统一通知，仅上报各站点签到状态",
        "📋 30 天打卡带与卡片式执行记录",
        "🎨 配色跟随 MoviePilot 注入的 Vuetify 主题变量，明暗与紫色主题自动适配",
    ],
    "P115LiteAssistant": [
        "📱 支持 115 扫码登录，Cookie 落盘加密存储",
        "👀 115 生活事件监控，自动同步本地 STRM",
        "🎬 STRM 生成与 302 直链播放，支持多端",
        "⬆️ 目录上传与秒传，监听整理完成事件自动增量上传",
        "🗂️ 通道式目录映射编辑器与目录选择器",
        "🔔 STRM / 上传 / 签到各自独立通知开关与消息类型",
        "🖼️ 入库通知走飞书卡片，海报与季集信息取自整理历史",
        "🚦 302 取链限流，请求失败自动重试",
    ],
}

INACTIVE_PLUGINS: set[str] = set()


def version_sort_key(item: tuple[str, str]) -> tuple[int, ...]:
    """把 "v1.2.10" 解析成可比较的数字元组，让更新历史按版本号倒序展示。"""
    version = item[0].lstrip("v")
    parts = []
    for chunk in version.split("."):
        parts.append(int(chunk) if chunk.isdigit() else 0)
    return tuple(parts)


def format_name(key: str, plugin: dict) -> str:
    name = plugin["name"]
    emoji = EMOJI_MAP.get(name, "🔌")
    text = f"{emoji} {name} ({key})"
    if key in INACTIVE_PLUGINS:
        text = f"~~{text}~~"
    return text


def anchor(index: int, key: str, plugin: dict) -> str:
    name = plugin["name"]
    slug = f"{index}--{name.lower()}-{key.lower()}"
    return slug.replace(" ", "-")


def build_table(plugins: list[tuple[str, dict]]) -> list[str]:
    lines = [
        "| 序号 | 插件名称 | 版本 | 功能描述 | 标签 |",
        "|------|----------|------|----------|------|",
    ]
    for idx, (key, plugin) in enumerate(plugins, start=1):
        lines.append(
            f"| {idx} | [{format_name(key, plugin)}](#{anchor(idx, key, plugin)}) | "
            f"v{plugin['version']} | {plugin['description'].rstrip('。')} | {plugin['labels']} |"
        )
    return lines


def build_section(index: int, key: str, plugin: dict) -> list[str]:
    lines = [
        f"### {index}. {format_name(key, plugin)}",
        f"- 版本：v{plugin['version']}",
        f"- 功能：{plugin['description']}",
        f"- 标签：{plugin['labels']}",
    ]

    features = FEATURES_MAP.get(key)
    if features:
        lines.append("- 特点：")
        lines.extend([f"  - {item}" for item in features])

    history = plugin.get("history", {})
    if history:
        lines.extend(
            [
                "- 更新说明：",
                "  <details>",
                "  <summary>点击查看更新历史</summary>",
                "  ",
            ]
        )
        for version, desc in sorted(history.items(), key=version_sort_key, reverse=True):
            lines.append(f"  - {version}: {desc}")
        lines.append("  </details>")

    return lines


def build_readme(data: dict[str, dict]) -> str:
    plugins = list(data.items())
    sections: list[str] = [
        REPO_TITLE,
        "",
        REPO_DESC,
        "",
        REPO_NOTE,
        "",
        GENERATED_NOTE,
        "",
        "## 📦 插件列表",
        "",
        "以下内容已按当前 `package.json` 中实际登记的插件自动生成。",
        "",
        *build_table(plugins),
        "",
    ]

    for idx, (key, plugin) in enumerate(plugins, start=1):
        sections.extend(build_section(idx, key, plugin))
        sections.append("")

    sections.extend(
        [
            "## 📖 使用说明",
            "",
            "1. 在 MoviePilot 中安装插件",
            "2. 根据插件说明配置相关参数",
            "3. 启用插件并设置定时任务（如需要）",
            "",
            "## ⚠️ 注意事项",
            "",
            "1. 本插件库中的插件均为个人维护，使用前请仔细阅读说明",
            "2. 部分插件需要特定权限或配置才能正常使用",
            "3. 如遇到问题，请先查看插件说明或提交 Issue",
            "4. 建议定期更新插件以获取最新功能和修复",
            "",
            "## 🛠 开发",
            "",
            "| 文档 | 内容 |",
            "|------|------|",
            "| [docs/Repository_Guide.md](docs/Repository_Guide.md) | 目录约定、版本规则、发布流程 |",
            "| [tests/README.md](tests/README.md) | 测试目录结构、导入约定与运行方式 |",
            "| [plugins/README.md](plugins/README.md) | 插件目录说明 |",
            "| [templates/README.md](templates/README.md) | 插件开发模板与新增插件步骤 |",
            "",
            "## 🤝 贡献",
            "",
            "欢迎提交 Issue 和 Pull Request 来帮助改进插件。",
            "",
            "## 📄 许可证",
            "",
            "本项目采用 MIT 许可证，详见 [LICENSE](LICENSE) 文件。",
            "",
        ]
    )
    return "\n".join(sections)


def main() -> None:
    data = json.loads(PACKAGE_FILE.read_text(encoding="utf-8"))
    readme = build_readme(data)
    README_FILE.write_text(readme, encoding="utf-8", newline="\n")
    print(f"Generated {README_FILE}")


if __name__ == "__main__":
    main()
