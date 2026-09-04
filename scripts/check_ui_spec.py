#!/usr/bin/env python3
"""核对各插件的界面规范数值是否一致。

docs/Plugin_UI_Spec.md 第 2 节列的那些数字，两个插件必须逐字相同 —— 靠人记不住，
所以这里按正则从各自的 kit.scss 与组件里抠出来横向比一遍。

    python scripts/check_ui_spec.py

不一致就打印对照表并以 1 退出，可以直接挂到 CI 上。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: (项目, 文件, 正则)。正则第 1 组是要比对的值；文件名里的 * 由插件目录名替换。
CHECKS: list[tuple[str, str, str]] = [
    ("面板间距", "src/styles/kit.scss", r"\+ \.[\w-]+-panel \{\s*margin-top: ([^;]+);"),
    ("面板头内边距", "src/styles/kit.scss", r"-panel__head \{[^}]*?padding: ([^;]+);"),
    ("面板身内边距", "src/styles/kit.scss", r"-panel__body \{\s*padding: ([^;]+);"),
    ("空态内边距", "src/styles/kit.scss", r"-empty \{[^}]*?padding: ([^;]+);"),
    ("小标签字号", "src/styles/kit.scss", r"-label \{[^}]*?font-size: ([^;]+);"),
    ("小标签字距", "src/styles/kit.scss", r"-label \{[^}]*?letter-spacing: ([^;]+);"),
    ("读数丸内边距", "src/styles/kit.scss", r"-pill \{[^}]*?padding: ([^;]+);"),
    ("读数丸字号", "src/styles/kit.scss", r"-pill \{[^}]*?font-size: ([^;]+);"),
    ("圆角", "src/styles/kit.scss", r"--[\w-]+-radius: ([^;]+);"),
    ("小圆角", "src/styles/kit.scss", r"--[\w-]+-radius-sm: ([^;]+);"),
    ("缓动", "src/styles/kit.scss", r"--[\w-]+-ease: ([^;]+);"),
    ("入场时长", "src/styles/kit.scss", r"-enter \{\s*animation: [\w-]+ ([\dms]+)"),
    ("入场阶梯", "src/styles/kit.scss", r"-enter--2 \{\s*animation-delay: ([^;]+);"),
    ("记录卡栅格", "src/components/Page.vue", r"\.log-grid \{[^}]*?grid-template-columns: ([^;]+);"),
    ("记录卡间距", "src/components/Page.vue", r"\.log-grid \{[^}]*?gap: ([^;]+);"),
    ("记录卡内边距", "src/components/Page.vue", r"\.log-card \{[^}]*?padding: ([^;]+);"),
    ("记录卡结论字号", "src/components/Page.vue", r"\.log-card__kind \{[^}]*?font-size: ([^;]+);"),
    ("记录卡时间字号", "src/components/Page.vue", r"\.log-card__when \{[^}]*?font-size: ([^;]+);"),
    ("读数条栅格", "src/components/Page.vue", r"\.run__strip \{[^}]*?grid-template-columns: ([^;]+);"),
    ("运行台内边距", "src/components/Page.vue", r"\.run__body \{\s*padding: ([^;]+);"),
    ("设置页外壳", "src/components/Config.vue", r"\.cfg__shell \{[^}]*?grid-template-columns: ([^;]+);"),
    ("设置页间距", "src/components/Config.vue", r"\.cfg__shell \{[^}]*?gap: ([^;]+);"),
    ("导轨吸顶", "src/components/Config.vue", r"\.cfg__rail \{[^}]*?top: ([^;]+);"),
    ("分区按钮内边距", "src/components/Config.vue", r"\.cfg__tab \{[^}]*?padding: ([^;]+);"),
    ("分区标签字号", "src/components/Config.vue", r"\.cfg__tab-label \{[^}]*?font-size: ([^;]+);"),
    ("分区备注字号", "src/components/Config.vue", r"\.cfg__tab-note \{[^}]*?font-size: ([^;]+);"),
    ("设置页断点", "src/components/Config.vue", r"@media \(max-width: (\d+px)\) \{\s*\.cfg__shell"),
    ("标题栏状态断点", "src/components/ui/AppBar.vue", r"@media \(max-width: (\d+px)\)"),
    ("标题栏内边距", "src/components/ui/AppBar.vue", r"\.bar \{[^}]*?padding: ([^;]+);"),
]

#: 目标 = 各 Vue 联邦插件 + 模板。模板一起比是因为新插件都从它起手，它漂了就人人都漂。
#: 纯 get_form() 的插件没有自己的前端，不吃这套规范，靠有没有 kit.scss 判断。
TEMPLATE = REPO / "templates" / "v2-vue-plugin"


def targets() -> list[tuple[str, Path]]:
    found = [
        (path.parents[2].name, path.parents[2])
        for path in (REPO / "plugins").glob("*/src/styles/kit.scss")
    ]
    found.sort()
    if (TEMPLATE / "src" / "styles" / "kit.scss").is_file():
        found.append(("（模板）", TEMPLATE))
    return found


def read(root: Path, relative: str) -> str:
    path = root / relative
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def main() -> int:
    found = targets()
    if len(found) < 2:
        print(f"只找到 {len(found)} 份前端，没什么可比的")
        return 0
    plugins = [name for name, _root in found]
    roots = dict(found)

    rows: list[tuple[str, dict[str, str], bool]] = []
    for label, relative, pattern in CHECKS:
        values: dict[str, str] = {}
        for plugin in plugins:
            match = re.search(pattern, read(roots[plugin], relative), re.S)
            values[plugin] = " ".join(match.group(1).split()) if match else "—"
        found = [value for value in values.values() if value != "—"]
        same = len(set(found)) <= 1
        rows.append((label, values, same))

    # 列宽跟着最长的值走，不然 cubic-bezier 那种长值会和邻列糊在一起
    width = max(
        [len(name) for name in plugins]
        + [len(value) for _label, values, _same in rows for value in values.values()]
    ) + 2

    header = "项目".ljust(16) + "".join(name.ljust(width) for name in plugins)
    print(header)
    print("-" * len(header))
    bad = 0
    for label, values, same in rows:
        line = label.ljust(16) + "".join(values[name].ljust(width) for name in plugins)
        if not same:
            bad += 1
            line += "  ← 不一致"
        print(line)

    missing = sum(1 for _label, values, _same in rows if "—" in values.values())
    print()
    if bad:
        print(f"{bad} 项不一致。规范见 docs/Plugin_UI_Spec.md 第 2 节。")
        print("模板那一列也算：新插件都从 templates/v2-vue-plugin 起手，它漂了就人人都漂。")
        return 1
    print(f"{len(rows)} 项全部一致" + (f"（其中 {missing} 项有插件没这个部件，已跳过）" if missing else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
