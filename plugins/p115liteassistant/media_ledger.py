"""媒体清单：把逐文件的记录聚合成「一部电影一行、一季剧一行」的总账。

**口径**：以网盘为库。在网盘上的算已入库，还在本地没传上去的算未入库。所以清单有两个
来源，缺一个「未入库」就永远是 0：

    已入库  ← STRM 记录（这些东西一定在网盘上）
    未入库  ← 上传通道的源目录里扫出来的媒体，对着上传记录比，没传过的就是它

两侧都是纯本地判断，不发一个 115 请求，所以清单能随时重算。

还有一类是「输出目录里有 .strm、记录里没有」的，它们的入库状态**判不出来**（网盘上可能
有也可能没有），所以单独标成 unknown 而不是硬塞进已入库或未入库 —— 猜一个会把筛选的
计数全带偏。

季集完整只按**集号连续**判（用户选的口径 A）：手上有 1、2、4 就报缺 3。整段缺在末尾看不
出来，那需要外部元数据，这一版不接。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

#: 季目录的几种写法。命中就说明标题在上一层。
_SEASON_DIR = (
    re.compile(r"^season\s*(\d{1,3})$", re.IGNORECASE),
    re.compile(r"^s(\d{1,3})$", re.IGNORECASE),
    re.compile(r"^第\s*(\d{1,3})\s*季$"),
)

#: 目录名里的年份：`某剧 (2024)`、`某剧（2024）`
_TITLE_YEAR = re.compile(r"^(.*?)[\s._]*[\(（](\d{4})[\)）]")

#: 集号，与 library_audit 同一套写法
_EPISODE = (
    re.compile(r"[Ss](\d{1,3})[\s._-]*[Ee](\d{1,4})"),
    re.compile(r"(?<![A-Za-z0-9])[Ee](\d{1,4})(?![A-Za-z0-9])"),
    re.compile(r"第\s*(\d{1,4})\s*[集话話]"),
)


def parse_episode(name: str) -> Optional[Tuple[int, int]]:
    """从文件名解析 ``(季, 集)``；解析不出来说明是电影。"""
    text = str(name or "")
    matched = _EPISODE[0].search(text)
    if matched:
        return int(matched.group(1)), int(matched.group(2))
    for pattern in _EPISODE[1:]:
        matched = pattern.search(text)
        if matched:
            return 1, int(matched.group(1))
    return None


def season_of_dir(name: str) -> Optional[int]:
    for pattern in _SEASON_DIR:
        matched = pattern.match(str(name or "").strip())
        if matched:
            return int(matched.group(1))
    return None


def split_title(name: str) -> Tuple[str, str]:
    """目录名 → ``(标题, 年份)``。没有年份就整段当标题，不猜。"""
    text = str(name or "").strip()
    matched = _TITLE_YEAR.match(text)
    if matched:
        return matched.group(1).strip(" .-_"), matched.group(2)
    return text, ""


def locate(raw_path: str) -> Optional[Dict[str, Any]]:
    """一个媒体文件的路径 → 它属于哪一行。

    电影：所在目录就是一行。
    剧集：文件名里有集号才算剧集；季号优先取**目录**上的（``Season 01``），目录没写才用
    文件名里的 —— 目录是刮削器排的，比文件名可靠。命中季目录时标题取上一层。
    """
    value = str(raw_path or "").strip()
    if not value:
        return None
    path = Path(value)
    folder = path.parent
    dir_season = season_of_dir(folder.name)
    parsed = parse_episode(path.name)

    if parsed is None and dir_season is None:
        title, year = split_title(folder.name)
        return {
            "kind": "movie",
            "title": title or folder.name,
            "year": year,
            "season": None,
            "episode": None,
            "folder": folder.as_posix(),
            "key": f"movie::{folder.as_posix()}",
        }

    season = dir_season if dir_season is not None else parsed[0]
    episode = parsed[1] if parsed else None
    holder = folder.parent if dir_season is not None else folder
    title, year = split_title(holder.name)
    return {
        "kind": "tv",
        "title": title or holder.name,
        "year": year,
        "season": season,
        "episode": episode,
        "folder": folder.as_posix(),
        "key": f"tv::{holder.as_posix()}::{season}",
    }


def seed_count(local_paths: Iterable[str], content_paths: Set[str]) -> int:
    """这些本地文件里有几个正被某个种子占着。

    种子的内容路径可能就是这个文件，也可能是它上面的某一层目录（整季一个种子），
    所以要顺着父目录往上找。
    """
    if not content_paths:
        return 0
    hits = 0
    for raw in local_paths or ():
        value = str(raw or "")
        if not value:
            continue
        if value in content_paths:
            hits += 1
            continue
        try:
            candidate = Path(value)
        except (OSError, ValueError):
            continue
        if any(str(parent) in content_paths for parent in candidate.parents):
            hits += 1
    return hits


def identity(spot: Dict[str, Any]) -> str:
    """一部片的身份。**不用目录当主键**：同一部片在网盘、本地 STRM、本地源目录里的路径都不同，
    按目录归组会变成三行，那就没法在一行上同时提供「删 STRM / 删源文件 / 删网盘」三个动作。
    """
    return f"{spot['kind']}|{spot['title']}|{spot['year']}|{spot['season'] if spot['season'] is not None else ''}"


def _blank_row(spot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": identity(spot),
        "kind": spot["kind"],
        "title": spot["title"],
        "year": spot["year"],
        "season": spot["season"],
        "channel": "",
        "channel_id": "",
        # in_library 在收尾时按「三处各有没有东西」推出来，不在这里定
        "in_library": "unknown",
        "files": 0,
        "size": 0,
        "episodes": [],
        "missing": [],
        "span": "",
        "strm_gone": 0,
        "flags": [],
        # 三处各自的清单，对应三个删除动作
        "strm_paths": [],
        "source_paths": [],
        "file_ids": [],
        "pickcodes": [],
        # 展示用：优先给网盘路径，没有就给本地目录
        "cloud_folder": "",
        "folder": "",
        "source_folder": "",
        "upload_target": "",
        "source_uploaded": 0,
        "source_pending": 0,
        # 本地源文件总字节（传过的也算）。「已经传上网盘、本地还占着」那部分是可回收的地方。
        "source_size": 0,
        # 入库时间：这一部**最早**那个文件落到网盘上的时刻（epoch 秒），0 = 还没入库。
        # 取最早而不是最新，因为清单默认按它升序排 —— 要回答的是「哪些在库里待得最久」。
        "library_at": 0,
        # 还在做种的源文件个数。>0 时「删除源文件」要锁住 —— 删了就掉种。
        "seeds": 0,
        "seeding": False,
    }


def _finish(
    rows: Dict[str, Dict[str, Any]],
    duplicate_tokens: set[str],
    seeding_paths: Set[str],
    seeding_identities: Dict[str, int],
) -> List[Dict[str, Any]]:
    """收尾：算集号跨度与缺号，推出入库状态，挂上标记。"""
    finished = []
    for row in rows.values():
        episodes = sorted({number for number in row["episodes"] if isinstance(number, int)})
        row["episodes"] = episodes
        if row["kind"] == "tv" and len(episodes) >= 2:
            low, high = episodes[0], episodes[-1]
            row["span"] = f"{low}-{high}"
            row["missing"] = [n for n in range(low, high + 1) if n not in episodes]

        # 在网盘上有东西就算已入库；只有本地源文件、还没传上去的算未入库；
        # 剩下的（输出目录里有 .strm 但记录里没有）判不出来。
        if row["file_ids"] or row["pickcodes"] or row["cloud_folder"]:
            row["in_library"] = "yes"
        elif row["source_pending"]:
            row["in_library"] = "no"
        elif row["strm_paths"]:
            row["in_library"] = "unknown"
        else:
            row["in_library"] = "no"

        row["folder"] = row["cloud_folder"] or row["source_folder"] or row["folder"]
        row["files"] = len(row["strm_paths"]) or len(row["source_paths"])

        flags = list(row["flags"])
        if row["missing"]:
            flags.append("season_gap")
        if row["strm_gone"]:
            flags.append("strm_gone")
        if duplicate_tokens & set(row["pickcodes"]):
            flags.append("duplicate")
        # 已经传上网盘、本地源文件还占着地方 —— 这一条正是「删除源文件」要处理的
        if row["in_library"] == "yes" and row["source_uploaded"]:
            flags.append("source_left")

        # 做种有两条线索：
        #   ① 源文件本身就在某个种子里（上传通道源目录下的那批）
        #   ② 这部片的**原始下载**还在做种 —— 文件在别的盘上，路径对不上，但经
        #      MoviePilot 整理过，所以能靠转移历史把种子哈希对回这部片
        # 取两者的并集：只看①的话，下载目录不在上传通道里的媒体永远判成没做种。
        row["seeds"] = max(
            seed_count(row["source_paths"], seeding_paths),
            int(seeding_identities.get(row["id"], 0)),
        )
        row["seeding"] = row["seeds"] > 0
        row["flags"] = sorted(set(flags))
        finished.append(row)
    finished.sort(key=lambda item: (-int(item["size"] or 0), item["title"]))
    return finished


def build_ledger(
    *,
    records: Dict[str, Any],
    strm_mappings: List[Dict[str, Any]],
    upload_mappings: List[Dict[str, Any]],
    upload_records: Dict[str, Any],
    pending_paths: set[str],
    media_extensions: Iterable[str],
    untracked: Iterable[Dict[str, Any]] = (),
    seeding_paths: Optional[Set[str]] = None,
    seeding_identities: Optional[Dict[str, int]] = None,
) -> List[Dict[str, Any]]:
    """三个来源拼一本总账，同一部片合成一行。零 115 请求。

    ``seeding_paths`` 是下载器里那些种子在本地落地的路径；给空集合就等于不判做种。
    """
    channels: Dict[str, str] = {}
    for index, mapping in enumerate(strm_mappings or []):
        if not isinstance(mapping, dict):
            continue
        mapping_id = str(mapping.get("id") or mapping.get("source_cid") or "default")
        channels[mapping_id] = f"STRM 通道 {index + 1}"

    rows: Dict[str, Dict[str, Any]] = {}
    token_seen: Dict[str, int] = {}

    def bucket(spot: Dict[str, Any]) -> Dict[str, Any]:
        return rows.setdefault(identity(spot), _blank_row(spot))

    # ① 网盘侧：STRM 记录。刮削文件不参与聚合 —— 它们没有集号，也不该算进「几个文件」。
    for key, record in (records or {}).items():
        if not isinstance(record, dict):
            continue
        mapping_id, _, rest = str(key).partition(":")
        if rest.startswith("sidecar:"):
            continue
        raw_path = str(record.get("path") or "")
        spot = locate(raw_path)
        if not spot:
            continue
        row = bucket(spot)
        if not row["channel"]:
            row["channel_id"] = mapping_id
            row["channel"] = channels.get(mapping_id) or (
                "一次性任务" if mapping_id.startswith("once") else mapping_id or "未知通道"
            )
        row["size"] += int(record.get("size") or 0)
        if spot["episode"] is not None:
            row["episodes"].append(spot["episode"])
        row["strm_paths"].append(raw_path)
        try:
            mtime = int(record.get("mtime") or 0)
        except (TypeError, ValueError):
            mtime = 0
        if mtime > 0 and (row["library_at"] == 0 or mtime < row["library_at"]):
            row["library_at"] = mtime
        file_id = str(record.get("file_id") or "").strip()
        if file_id:
            row["file_ids"].append(file_id)
        pickcode = str(record.get("pickcode") or "").strip().lower()
        if pickcode:
            row["pickcodes"].append(pickcode)
            token_seen[pickcode] = token_seen.get(pickcode, 0) + 1
        if not row["cloud_folder"]:
            cloud_path = str(record.get("cloud_path") or "")
            if cloud_path:
                row["cloud_folder"] = Path(cloud_path).parent.as_posix()
        if raw_path in pending_paths and "pending_delete" not in row["flags"]:
            row["flags"].append("pending_delete")
        if not file_id and not pickcode and "unlinkable" not in row["flags"]:
            row["flags"].append("unlinkable")
        try:
            if not Path(raw_path).exists():
                row["strm_gone"] += 1
        except OSError:
            pass

    # ② 本地源文件侧：只扫上传通道配置里的那几个源目录（用户定的范围）。
    #    传过的也要收进来 —— 「删除源文件」管的正是「已经传上去、本地还占着地方」那批。
    suffixes = {str(value).lower() for value in media_extensions if str(value).strip()}
    uploaded = {
        str(path)
        for path, record in (upload_records or {}).items()
        if isinstance(record, dict) and str(record.get("uploaded_at") or "").strip()
    }
    for index, mapping in enumerate(upload_mappings or []):
        if not isinstance(mapping, dict):
            continue
        source = str(mapping.get("source") or "").strip()
        if not source:
            continue
        try:
            base = Path(source).expanduser().resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        if not base.is_dir():
            continue
        label = f"上传通道 {index + 1}"
        target_root = str(mapping.get("target") or "").strip().replace("\\", "/").rstrip("/")
        try:
            entries = list(base.rglob("*"))
        except OSError:
            continue
        for entry in entries:
            try:
                if not entry.is_file() or entry.suffix.lower() not in suffixes:
                    continue
                size = int(entry.stat().st_size)
            except OSError:
                continue
            resolved = str(entry)
            spot = locate(resolved)
            if not spot:
                continue
            row = bucket(spot)
            row["source_paths"].append(resolved)
            row["source_size"] += size
            if resolved in uploaded:
                row["source_uploaded"] += 1
            else:
                row["source_pending"] += 1
                # 没传过的才算进体积与集号：传过的那部分已经由网盘侧记进去了
                row["size"] += size
                if spot["episode"] is not None:
                    row["episodes"].append(spot["episode"])
            if not row["source_folder"]:
                row["source_folder"] = Path(resolved).parent.as_posix()
                try:
                    relative = Path(row["source_folder"]).relative_to(base).as_posix()
                except ValueError:
                    relative = ""
                row["upload_target"] = f"{target_root}/{relative}" if relative else target_root
            if not row["channel"]:
                row["channel_id"] = str(mapping.get("id") or source)
                row["channel"] = label

    # ③ 判不出来的：输出目录里有 .strm、记录里没有。网盘上有没有这东西无从得知。
    for item in untracked or ():
        raw_path = str((item or {}).get("path") or "")
        spot = locate(raw_path)
        if not spot:
            continue
        row = bucket(spot)
        row["strm_paths"].append(raw_path)
        row["size"] += int((item or {}).get("size") or 0)
        if spot["episode"] is not None:
            row["episodes"].append(spot["episode"])
        if not row["channel"]:
            row["channel_id"] = "untracked"
            row["channel"] = "记录外"
        if "untracked" not in row["flags"]:
            row["flags"].append("untracked")

    duplicates = {token for token, count in token_seen.items() if count > 1}
    return _finish(rows, duplicates, seeding_paths or set(), seeding_identities or {})
