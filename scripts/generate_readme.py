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
    "外部消息转发": "📢",
    "Lucky助手": "🍀",
    "群聊区": "💬",
    "朱雀助手": "🦅",
    "Cloudflare订阅": "☁️",
    "本地插件安装": "📥",
    "象岛传说竞技场": "🎮",
    "织梦勋章套装奖励": "🏆",
    "勋章墙": "🏅",
    "NAT类型检测": "🌐",
    "Sun-Panel助手": "🌞",
    "直连模式": "🌐",
    "中兴问天Hosts": "🛜",
}

FEATURES_MAP = {
    "MsgNotify": [
        "🔄 支持 POST/GET 两种 API 接口方式",
        "🔐 内置 API 令牌校验机制",
        "📝 支持自定义消息格式",
        "🔌 适配多种外部应用（群晖、QD 框架、Lucky 等）",
    ],
    "LuckyHelper": [
        "⏰ 支持定时自动备份",
        "📁 智能备份文件管理",
        "📨 备份状态实时通知",
        "⚙️ 支持自定义备份周期",
        "💾 新增本地备份开关，支持 WebDAV 备份",
    ],
    "GroupChatZone": [
        "🌐 支持多站点喊话管理",
        "🤖 智能识别特殊喊话内容",
        "📊 自动获取站点反馈",
        "⏱️ 动态注册定时任务",
        "⏭️ 支持消息跳过机制",
    ],
    "ZhuqueHelper": [
        "⚡ 支持技能自动释放",
        "⬆️ 一键角色升级功能",
        "📈 收益统计图表展示",
        "⏲️ 支持释放时间微调",
        "📱 移动端优化显示",
        "📋 完整的执行记录追踪",
    ],
    "CloudflaresSubscribe": [
        "📦 支持批量订阅管理",
        "🔄 自动 DNS 服务更新",
        "🔁 订阅失败自动重试",
        "⏰ 定时任务自动执行",
        "🌐 支持自定义 Hosts 配置",
    ],
    "LocalPluginInstall": [
        "📦 支持本地 ZIP 包安装",
        "🖥️ 简单的安装界面",
        "🚀 快速插件部署",
        "🛠️ 支持自定义插件包",
        "🤖 智能依赖处理，自动检测并安装插件依赖",
        "🗜️ 支持自动创建 ZIP 备份并跳过 `__pycache__`",
        "♻️ 支持安装失败后自动回滚恢复",
        "🧰 支持从备份列表恢复安装与删除历史备份",
        "🗂️ 支持按插件中文名分组展示备份并标记最新备份",
        "🌙 支持拟态提示/确认弹窗与深色模式适配",
        "🧩 支持 Vue 联邦插件 ZIP 结构安装",
    ],
    "VicomoVS": [
        "🎯 对战次数统计",
        "📜 历史记录追踪",
        "📤 优化的消息输出",
        "🤖 自动对战功能",
        "🔄 失败重试机制",
        "⚙️ 代理启用开关",
    ],
    "ZmedalRwd": [
        "🎖️ 支持勋章系列开关",
        "⏰ 动态定时器组件",
        "📱 适配 V1/V2 版本",
    ],
    "MedalWall": [
        "🔔 勋章购买提醒",
        "📊 勋章统计展示",
        "⏰ 定时任务自动执行",
        "🔄 支持多站点管理",
    ],
    "NATdetect": [
        "🔍 独立检测方法，不依赖外部服务",
        "🎯 精准识别网络 NAT 类型",
        "📱 优化的界面显示",
        "⚡ 快速检测响应",
    ],
    "SpanelHelper": [
        "🔄 一键同步站点",
        "📂 指定分组管理",
        "🔗 支持站点链接跳转",
    ],
    "NoProxy": [
        "🎯 自动将 `MP_SERVER_HOST` 加入直连白名单",
        "🌍 支持额外域名、完整 URL 与通配符域名配置",
        "🔀 支持兼容模式，直连失败后自动回退系统代理",
        "🐞 支持输出白名单命中、补丁注入、直连失败与回退流程等 debug 日志",
        "♻️ 支持热切换，启用或禁用后补丁实时注入或回滚",
        "🧩 适用于全局代理环境下少量站点仍需直连的场景",
    ],
    "ZTEHosts": [
        "🛜 支持自动登录中兴问天路由后台并同步自定义 Hosts",
        "🔐 支持管理密码密文输入与浏览器仿真登录",
        "⏰ 支持定时同步与立即运行一次",
        "📨 支持统一收口的任务通知消息",
    ],
}

INACTIVE_PLUGINS = {"VicomoVS", "MedalWall"}


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
        for version, desc in history.items():
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
