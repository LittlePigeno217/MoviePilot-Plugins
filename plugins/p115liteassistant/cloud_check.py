"""网盘核对：这部片在网盘上到底还在不在。

这是**唯一一处为了填清单而主动打 115 接口的地方**，所以它按限流的实际情况办事：

* 只在你点了才跑，绝不藏在一次 GET 里。全库 385 行要 385 次请求，按客户端自己
  ``directory_request_interval``（1/3 秒）的节流也得两分钟 —— 那种耗时不该出现在打开页面时。
* 一次有预算上限。选中一批就核对这一批，没选就核对**最久没核对过的**那几行。
* 撞上访问上限立刻停，把已经问出来的结果存下来，并如实说停在第几行、为什么。
  之后进入冷却期，冷却没过就不再打接口，界面上说清还要等多久。
* 结果带时间戳存着，所以「还在」「没了」「还没核对」是三种状态而不是两种 ——
  没问过就说没问过，不猜。

只问目录在不在（``/open/folder/get_info`` 一次一行），不数里面几个文件：那要再多一次列目录，
预算直接翻倍，而「网盘上没了」这个答案本身已经够用。
"""

from __future__ import annotations

from time import time
from typing import Any, Callable, Dict, List, Tuple

from app.log import logger

from .client import U115AccessLimitError
from .log_utils import safe_error_text

#: 一次核对最多问多少行。385 行按 1/3 秒节流是两分钟，60 行是 20 秒 —— 一次点击能等的量。
CHECK_BUDGET = 60

#: 撞上访问上限后多久之内不再打接口。115 自己的退避是 70 秒，这里放宽到 10 分钟：
#: 已经被限流了还接着试只会把限流拖得更长。
COOLDOWN_SECONDS = 600


def pick_rows(rows: List[Dict[str, Any]], cache: Dict[str, Any], budget: int) -> List[Dict[str, Any]]:
    """没指定行时，挑最久没核对过的那几行。没核对过的排最前。"""
    known = cache.get("rows") or {}

    def age(row: Dict[str, Any]) -> float:
        entry = known.get(row.get("id")) or {}
        try:
            return float(entry.get("checked_at") or 0)
        except (TypeError, ValueError):
            return 0.0

    candidates = [row for row in rows if row.get("cloud_folder")]
    candidates.sort(key=age)
    return candidates[:budget]


def check_rows(
    client_provider: Callable[[], Any],
    rows: List[Dict[str, Any]],
    budget: int = CHECK_BUDGET,
) -> Tuple[Dict[str, Dict[str, Any]], str]:
    """逐行问一次「这个目录在网盘上还在不在」。

    返回 ``({行 id: {state, checked_at}}, 停下的原因)``。``state`` 是 ``yes`` / ``no``；
    问不出来的行不写进结果 —— 宁可留着「还没核对」，不要把一次失败记成「没了」，
    那会让人照着删网盘上其实还在的东西。
    """
    targets = [row for row in rows[:budget] if row.get("cloud_folder")]
    if not targets:
        return {}, ""

    client = client_provider()
    state = client.new_access_limit_state()
    results: Dict[str, Dict[str, Any]] = {}
    stopped = ""

    def work() -> None:
        nonlocal stopped
        for index, row in enumerate(targets):
            folder = str(row.get("cloud_folder") or "")
            try:
                item = client.get_item(folder)
            except U115AccessLimitError:
                raise
            except Exception as err:  # noqa: BLE001
                # 一个错就停：同一个毛病重复问几十次只会更快撞上限流
                stopped = (
                    f"问到第 {index + 1} 行时出错，先停下了（已核对 {len(results)} 行）："
                    f"{safe_error_text(err)}"
                )
                return
            results[str(row.get("id"))] = {
                "state": "yes" if item else "no",
                "checked_at": int(time()),
                "folder": folder,
            }

    try:
        client.run_with_access_limit_state(state, work)
    except U115AccessLimitError as err:
        stopped = (
            f"115 报了访问上限，已核对 {len(results)} 行就停下了，"
            f"{COOLDOWN_SECONDS // 60} 分钟内不再试：{safe_error_text(err)}"
        )
        logger.warning(f"【网盘核对】{stopped}")
    return results, stopped


def merge(cache: Dict[str, Any], results: Dict[str, Dict[str, Any]], limited: bool) -> Dict[str, Any]:
    """把这一轮的结果并进缓存；撞了限流就记下冷却到什么时候。"""
    known = dict(cache.get("rows") or {})
    known.update(results)
    merged: Dict[str, Any] = {"rows": known}
    if limited:
        merged["cooldown_until"] = int(time()) + COOLDOWN_SECONDS
    elif cache.get("cooldown_until"):
        merged["cooldown_until"] = cache["cooldown_until"]
    return merged


def cooldown_left(cache: Dict[str, Any]) -> int:
    """冷却还剩几秒。0 表示可以问了。"""
    try:
        until = int(cache.get("cooldown_until") or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, until - int(time()))
