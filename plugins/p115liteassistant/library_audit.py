"""从 STRM 记录里挑出两样清单要用的东西。

原先这里还有重复生成 / 集号不连续 / 取不到链三项检查，现在它们都由 :mod:`media_ledger`
在聚合的时候顺手算出来当行标记 —— 同一件事算两遍迟早算出两个答案，所以那三个函数连带
它们自己那份集号解析一起删了。留下的两个是清单确实要调的：

``media_records``  只要媒体记录，把刮削文件剔出去
``find_untracked`` 输出目录里存在、但记录里没有的 .strm
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


def media_records(records: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """只要媒体记录，刮削文件不参与 —— 它们没有集号，也不该算进「几个文件」。"""
    picked = []
    for key, record in (records or {}).items():
        if not isinstance(record, dict):
            continue
        _mapping_id, _, rest = str(key).partition(":")
        if rest.startswith("sidecar:"):
            continue
        picked.append((str(key), record))
    return picked


def find_untracked(target_dirs: Iterable[str], known_paths: set[str]) -> List[Dict[str, Any]]:
    """输出目录里存在、但记录里没有的 .strm。

    这些文件反向删除看不见（``decide()`` 是从记录出发的），所以本地删掉它们不会联动网盘。
    一次性任务、手工拷进去的、改过通道输出目录后残留的，都会落在这里。
    """
    rows = []
    for raw_dir in target_dirs:
        value = str(raw_dir or "").strip()
        if not value:
            continue
        try:
            base = Path(value).expanduser().resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        if not base.is_dir():
            continue
        try:
            for entry in base.rglob("*.strm"):
                resolved = str(entry.resolve())
                if resolved in known_paths:
                    continue
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0
                rows.append({"path": resolved, "size": int(size), "root": str(base)})
        except OSError:
            continue
    rows.sort(key=lambda row: row["path"])
    return rows
