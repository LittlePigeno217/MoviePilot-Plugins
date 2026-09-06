"""还在做种的本地文件。

这一维存在的意义不是显示，是**拦人**：还在做种的源文件删掉就掉种，有 H&R 的站会出事。
所以它必须诚实——任何一个下载器答不上来，都要如实说「不知道」，绝不能在界面上把
「拿不到种子列表」显示成「没在做种」，那正好会放开本该拦住的那个按钮。

走宿主配置的下载器（``DownloaderHelper``），和仓库里「清理无效做种」同一条路：一次把种子
全拉下来，拿每个种子的内容路径建索引，再按路径归属去匹配媒体。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Set, Tuple

from .media_ledger import identity, locate

from app.log import logger

from .log_utils import safe_error_text


def _torrent_content_path(torrent: Any) -> str:
    """取一个种子在本地落地的路径。

    qBittorrent 直接给 ``content_path``；Transmission 得用 ``download_dir`` 拼 ``name``。
    两个都取不到就跳过这个种子 —— 宁可漏判一个，也不要拿错路径去拦无关的文件。
    """
    content = getattr(torrent, "content_path", None)
    if content:
        return str(content)
    directory = getattr(torrent, "download_dir", None)
    name = getattr(torrent, "name", None)
    if directory and name:
        return str(Path(str(directory)) / str(name))
    return ""


def collect_seeding_paths() -> Tuple[Set[str], Dict[str, int], int, str]:
    """返回 ``(内容路径集合, 哈希计数, 种子数, 出错说明)``。

    出错说明非空时调用方必须把「做种」这一维标成不可用，而不是当成「都没在做种」。
    哈希那份给 :func:`seeding_identities` 用：路径对不上的媒体只能靠哈希对回去。
    """
    try:
        from app.helper.downloader import DownloaderHelper
    except Exception as err:  # noqa: BLE001
        return set(), {}, 0, f"宿主没有下载器模块：{safe_error_text(err)}"

    try:
        services: Dict[str, Any] = DownloaderHelper().get_services() or {}
    except Exception as err:  # noqa: BLE001
        return set(), {}, 0, f"读不到下载器配置：{safe_error_text(err)}"
    if not services:
        return set(), {}, 0, "MoviePilot 里还没有配置下载器"

    paths: Set[str] = set()
    hashes: Dict[str, int] = {}
    total = 0
    failures: list[str] = []
    for name, service in services.items():
        downloader = getattr(service, "instance", None)
        if downloader is None:
            failures.append(f"{name} 没有实例")
            continue
        try:
            if downloader.is_inactive():
                failures.append(f"{name} 连不上")
                continue
        except Exception:  # noqa: BLE001
            failures.append(f"{name} 连不上")
            continue
        try:
            torrents, error = downloader.get_torrents()
        except Exception as err:  # noqa: BLE001
            failures.append(f"{name}：{safe_error_text(err)}")
            continue
        if error:
            failures.append(f"{name} 取种子列表失败")
            continue
        for torrent in torrents or []:
            total += 1
            value = str(getattr(torrent, "hash", "") or getattr(torrent, "hashString", "") or "")
            if value:
                hashes[value] = hashes.get(value, 0) + 1
            content = _torrent_content_path(torrent)
            if not content:
                continue
            paths.add(content)
            try:
                paths.add(str(Path(content).resolve()))
            except (OSError, RuntimeError, ValueError):
                pass

    note = "；".join(failures)
    if failures and not paths and not hashes:
        # 一个都没拉到：这时候说「没在做种」就是把不知道说成没有
        return set(), {}, 0, note
    if failures:
        logger.warning(f"【做种】部分下载器没答上来：{note}")
    return paths, hashes, total, ""


def _history_identity(history: Any) -> str:
    """一条转移历史 → 这部片在清单里的行 id。

    优先按整理后的落地路径解析（和清单用的是同一个 ``locate``，naming 一致就一定对得上），
    对不上时退回用历史自己记的 标题 / 年份 / 类型 / 季 拼一个。
    """
    dest = str(getattr(history, "dest", "") or "")
    if dest:
        spot = locate(dest)
        if spot:
            return identity(spot)
    title = str(getattr(history, "title", "") or "").strip()
    if not title:
        return ""
    kind = "movie" if str(getattr(history, "type", "") or "") == "电影" else "tv"
    season = ""
    if kind == "tv":
        raw = str(getattr(history, "seasons", "") or "").strip()
        digits = "".join(char for char in raw if char.isdigit())
        season = str(int(digits)) if digits else ""
    year = str(getattr(history, "year", "") or "").strip()
    return f"{kind}|{title}|{year}|{season}"


def seeding_identities(hashes: Dict[str, int]) -> Dict[str, int]:
    """种子哈希 → 这部片还有几个种子在做。

    靠 MoviePilot 的转移历史把哈希对回媒体，**不猜发布名**：种子的内容路径长的是
    ``A.Movie.2019.BluRay.1080p...mkv`` 这种发布名，硬解析出来的标题跟清单里
    ``某片名 (2019)`` 对不上；而转移历史里本来就存着「这个哈希整理成了哪部片」。
    """
    if not hashes:
        return {}
    try:
        from app.db.transferhistory_oper import TransferHistoryOper
    except Exception as err:  # noqa: BLE001
        logger.warning(f"【做种】读不到转移历史，只能按路径判做种：{safe_error_text(err)}")
        return {}
    oper = TransferHistoryOper()
    counted: Dict[str, int] = {}
    for value, count in hashes.items():
        try:
            histories = oper.list_by_hash(value) or []
        except Exception as err:  # noqa: BLE001
            logger.debug(f"【做种】哈希 {value[:8]} 查转移历史失败：{safe_error_text(err)}")
            continue
        for history in histories:
            key = _history_identity(history)
            if not key:
                continue
            counted[key] = counted.get(key, 0) + count
            break
    return counted
