"""反向删除：本地 STRM 被删除后清理 115 云端对应的媒体、刮削文件与空目录。

设计上把「判定」和「执行」严格分开：

* :meth:`ReverseDeleter.decide` 只读本地文件系统与插件记录，**一个 115 请求都不打**。
  所有护栏都在这一步 —— 媒体库没挂上、挂载点被空目录顶替、缺失比例过高，都必须在
  发出任何删除请求之前拦住。反过来说，护栏也不能等到反查云端 ID 之后才生效，否则
  掉盘时会先对着几万条记录各打一次接口，然后才决定整轮跳过。
* :meth:`ReverseDeleter.execute` 才碰网络：反查并校验文件 ID、按云端父目录成组删除、
  枚举目录清掉属于已删媒体的刮削文件、目录空了再向上级联。

删除走 115 回收站（``client.delete_file``），可以在 115 侧人工还原；即便如此，超过
阈值的批量删除仍然先进待确认队列，等人在运行台点过再执行。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from secrets import token_hex
from time import monotonic, sleep
from typing import Any, Callable, Dict, Iterable, NamedTuple, Optional

from app.log import logger

from .client import U115AccessLimitError, U115AuthError
from .file_types import DEFAULT_MEDIA_EXTENSIONS, DEFAULT_SIDECAR_EXTENSIONS, parse_extensions
from .log_utils import safe_error_text
from .resilience import TtlCache, retry_call
from .strm import normalize_cloud_path


LOG_TAG = "【STRM反向删除】"

MEDIA_EXTENSIONS = frozenset(DEFAULT_MEDIA_EXTENSIONS)

#: 记录数低于这个值不做比例熔断 —— 否则「只放一两部片」的映射永远删不掉。
REVERSE_DELETE_GUARD_MIN_RECORDS = 5
#: 缺失比例达到即整轮放弃：正常使用不会一次删掉九成媒体，更像是掉盘或换了输出目录。
REVERSE_DELETE_GUARD_MAX_RATIO = 0.9
#: 云端空目录向上级联删除的最大层数。
CLOUD_DIR_CASCADE_MAX_DEPTH = 16
#: 115 的目录删除是异步的：刚删掉子目录就删父目录会被「删除[X]操作尚未执行完成」
#: 挡下来，所以目录删除要留几次重试。文件删除是同步的，不需要。
CLOUD_DIR_DELETE_ATTEMPTS = 4
CLOUD_DIR_DELETE_DELAY = 2.0
#: 出现这些字样说明目标本来就不在了 —— 对删除来说等同于成功。
ALREADY_MISSING_MARKERS = ("不存在", "已删除", "未找到", "找不到")
#: 单次待删媒体数超过它就先进待确认队列。
DEFAULT_CONFIRM_THRESHOLD = 20
#: 待确认批次的保留天数与单批明细上限。
STRM_DELETE_PENDING_TTL_DAYS = 7
STRM_DELETE_PENDING_MAX_ITEMS = 2000
#: 待确认批次的数量上限。每次超阈值的新发现都独立成一张，方便逐批审查；
#: 攒到这个数还没人处理，新发现就并进最旧的那一张，免得队列无上限增长。
STRM_DELETE_PENDING_MAX_BATCHES = 20
#: 刚删过的 pickcode 记多久：115 列表接口有延迟，紧接着的正向同步可能还看得到
#: 已删的文件，照着它重建就等于把用户删掉的 STRM 又写回去。
RECENT_DELETE_TTL = 600.0

#: 识别云端刮削产物用的扩展名。刻意与「是否把刮削文件下载到本地」解耦：云端往往
#: 存在从未回传到本地的 nfo / 海报 / 字幕，只靠本地记录会整批漏删。
SCRAPE_ARTIFACT_EXTENSIONS = frozenset(
    {
        ".nfo",
        ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tbn",
        ".srt", ".ass", ".ssa", ".sup", ".vtt", ".sub", ".idx", ".smi", ".lrc",
    }
)
#: 关联刮削文件允许的名字分隔符：Film-poster.jpg / Film.zh-CN.srt / Film_thumb.jpg
SCRAPE_NAME_SEPARATORS = ("-", ".", "_", " ")

#: decide() 的判定结论
ACTION_DELETE = "delete"
ACTION_PENDING = "pending"
ACTION_SKIPPED = "skipped"


def cloud_item_name(item: Dict[str, Any]) -> str:
    """兼容 115 各接口（open / web / iter_files 归一化后）的文件名字段。"""
    for key in ("fn", "file_name", "n", "name", "category_name"):
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def cloud_item_is_dir(item: Dict[str, Any]) -> bool:
    """判断列表项是否是目录。115 的 fc 字段 "0" 表示目录、"1" 表示文件。"""
    category = item.get("fc", item.get("file_category"))
    if category not in (None, ""):
        return str(category) == "0"
    if str(item.get("type") or "").strip().lower() == "dir":
        return True
    return item.get("cid") is not None and item.get("fid") is None


def cloud_item_id(item: Dict[str, Any]) -> str:
    """取列表项自身的 ID。

    文件只认 ``fid`` / ``file_id`` / ``fileid``：115 列表里文件的 ``cid`` 是**父目录**
    ID，回退到它就会拿父目录当自己，删除时连整个目录一起删掉。
    """
    if cloud_item_is_dir(item):
        keys = ("cid", "category_id", "file_id", "fid", "fileid")
    else:
        keys = ("fid", "file_id", "fileid")
    for key in keys:
        value = item.get(key)
        if value in (None, "", 0, "0"):
            continue
        return str(value)
    return ""


def media_name_stem(name: str) -> str:
    """去掉媒体扩展名：``Film.mkv`` -> ``Film``；不是媒体扩展名则原样返回。"""
    text = str(name or "")
    suffix = PurePosixPath(text).suffix.lower()
    if suffix and suffix in MEDIA_EXTENSIONS:
        return text[: len(text) - len(suffix)]
    return text


def is_scrape_artifact(
    name: str,
    extra_extensions: Iterable[str] = (),
) -> bool:
    """名字是否像刮削产物（含字幕）。"""
    suffix = PurePosixPath(str(name or "")).suffix.lower()
    if not suffix:
        return False
    return suffix in SCRAPE_ARTIFACT_EXTENSIONS or suffix in set(extra_extensions)


def associated_media_name(candidate: str, media_names: Iterable[str]) -> str:
    """返回刮削文件归属的媒体文件名（同目录里最具体的那个），没有则空串。

    刮削器的命名方式很多：``Film.nfo``、``Film-poster.jpg``、``Film.zh-CN.srt``、
    ``Film.mkv.nfo``。只比 stem 相等会漏掉后三种；只比前缀又会把 ``Film 2.nfo``
    错判给 ``Film.mkv``。所以在同目录的媒体名集合里挑**锚点最长**的那个归属：
    ``Film 2.mkv`` 存在时 ``Film 2.nfo`` 自然归它，不会被 ``Film.mkv`` 抢走。
    """
    text = str(candidate or "")
    suffix = PurePosixPath(text).suffix
    base = (text[: len(text) - len(suffix)] if suffix else text).lower()
    if not base:
        return ""
    owner = ""
    owner_anchor = -1
    for media_name in media_names:
        media_name = str(media_name or "")
        if not media_name:
            continue
        for anchor in {media_name.lower(), media_name_stem(media_name).lower()}:
            if not anchor or len(anchor) <= owner_anchor:
                continue
            if base == anchor or (
                base.startswith(anchor)
                and len(base) > len(anchor)
                and base[len(anchor)] in SCRAPE_NAME_SEPARATORS
            ):
                owner_anchor = len(anchor)
                owner = media_name
    return owner


def is_protected_cloud_dir(
    dir_id: str,
    dir_cloud_path: str,
    protected_ids: Iterable[str],
) -> bool:
    """云端目录是否禁止删除。

    除 115 根目录与映射自己配置的源目录外，一级目录（``/Movies``）也一律保留 ——
    与 MoviePilot ``StorageChain.delete_media_file`` 里 ``len(parts) <= 2`` 同一条界，
    避免「最后一部片被删」顺手带走整个媒体库目录。
    """
    if not dir_id or dir_id in set(protected_ids):
        return True
    if dir_cloud_path:
        return len(PurePosixPath(normalize_cloud_path(dir_cloud_path)).parts) <= 2
    return False


def normalize_confirm_threshold(value: Any) -> int:
    """阈值归一：0 表示永不拦人，负数与非法值回退默认值。"""
    try:
        threshold = int(value)
    except (TypeError, ValueError):
        return DEFAULT_CONFIRM_THRESHOLD
    if threshold < 0:
        return DEFAULT_CONFIRM_THRESHOLD
    return threshold


class SweepDecision(NamedTuple):
    """一次映射巡检的判定结果 —— 删与不删都要能解释清楚。

    :param action: ``delete`` 可以删、``pending`` 超量待人工确认、``skipped`` 本轮放弃。
    :param reason: 跳过或入队的原因，直接进日志与通知。
    :param targets: 待删媒体条目（不可变元组），每条 ``{record_key, path, cloud_path, file_id,
        parent_id, name}``；``file_id`` 在判定阶段可能为空，由执行阶段反查。
    :param total_records: 本映射的媒体记录总数。
    :param missing_total: **全集**缺失数 —— 熔断依据，不受 ``only_paths`` 收窄影响。
    :param queued_total: 本轮缺失里已经挂在待确认队列上的个数，它们只能经确认删除。
    """

    action: str
    reason: str = ""
    targets: tuple[Dict[str, Any], ...] = ()
    total_records: int = 0
    missing_total: int = 0
    queued_total: int = 0


class ReverseDeleter:
    """把「本地 STRM 不见了」翻译成「删掉 115 上对应的东西」。"""

    def __init__(
        self,
        client_provider: Callable[[], Any],
        store: Any,
        recent_deletes: Optional[TtlCache] = None,
        sleeper: Optional[Callable[[float], None]] = None,
    ):
        self._client_provider = client_provider
        self._store = store
        #: 目录删除重试时的等待函数，单测注入空实现即可
        self._sleeper = sleeper or sleep
        #: 刚删过的 pickcode，供正向同步跳过重建；由调用方共享同一个实例
        self._recent_deletes = recent_deletes

    @property
    def _client(self) -> Any:
        return self._client_provider()

    # ---- 判定阶段：只读本地，零 115 请求 ----

    @staticmethod
    def mapping_prefixes(mapping: Dict[str, Any]) -> tuple[str, str, str]:
        """返回 ``(mapping_id, 媒体记录前缀, 附属记录前缀)``。"""
        mapping_id = str(mapping.get("id") or mapping.get("source_cid") or "default")
        return mapping_id, f"{mapping_id}:", f"{mapping_id}:sidecar:"

    @staticmethod
    def _media_records(
        records: Dict[str, Any],
        media_prefix: str,
        sidecar_prefix: str,
    ) -> list[tuple[str, Dict[str, Any]]]:
        """挑出本映射的媒体记录（排除 sidecar）。"""
        result: list[tuple[str, Dict[str, Any]]] = []
        for record_key, record in list(records.items()):
            key_text = str(record_key)
            if not isinstance(record, dict):
                continue
            if not key_text.startswith(media_prefix) or key_text.startswith(sidecar_prefix):
                continue
            if record.get("kind") == "sidecar":
                continue
            result.append((key_text, record))
        return result

    @staticmethod
    def _record_media_name(record_key: str, record: Dict[str, Any], media_prefix: str) -> str:
        """取记录对应的云端文件名，供刮削文件归属判断使用。"""
        name = str(record.get("name") or "").strip()
        if name:
            return name
        cloud_path = str(record.get("cloud_path") or "").strip()
        if cloud_path:
            return PurePosixPath(cloud_path).name
        rel_text = str(record_key)[len(media_prefix):]
        return PurePosixPath(rel_text).name if rel_text else ""

    @classmethod
    def _target_from_record(
        cls,
        record_key: str,
        record: Dict[str, Any],
        media_prefix: str,
        resolved: Path,
    ) -> Dict[str, Any]:
        return {
            "record_key": record_key,
            "path": str(resolved),
            "cloud_path": str(record.get("cloud_path") or "").strip(),
            "file_id": str(record.get("file_id") or record.get("fileid") or "").strip(),
            "parent_id": str(record.get("parent_id") or "").strip(),
            "name": cls._record_media_name(record_key, record, media_prefix),
        }

    @staticmethod
    def _has_any_strm(target_dir: Path) -> bool:
        """输出目录下还有没有 STRM。命中即返回，不会把整棵树走完。"""
        try:
            return next(target_dir.rglob("*.strm"), None) is not None
        except OSError:
            return False

    @staticmethod
    def _path_in_scope(resolved: Path, scope: list[Path]) -> bool:
        """路径是否落在本次上报的范围内：文件精确匹配，目录按前缀匹配。"""
        for item in scope:
            if resolved == item:
                return True
            try:
                resolved.relative_to(item)
            except ValueError:
                continue
            return True
        return False

    def decide(
        self,
        mapping: Dict[str, Any],
        records: Dict[str, Any],
        only_paths: Optional[Iterable[str | Path]] = None,
        *,
        bypass_confirm: bool = False,
    ) -> SweepDecision:
        """判定这一轮该删什么。**不发任何 115 请求。**

        闸门顺序是硬约束，见模块 docstring。``only_paths`` 只收窄删除范围，
        熔断始终按全部缺失记录计算 —— 掉盘时即使监听只报了一个文件也要整轮跳过。
        """
        config = self._store.get_config()
        if not config.get("strm_delete_cloud_on_missing"):
            return SweepDecision(ACTION_SKIPPED, "未开启反向删除")

        _mapping_id, media_prefix, sidecar_prefix = self.mapping_prefixes(mapping)
        target_value = str(mapping.get("target_dir") or "").strip()
        if not target_value:
            raise ValueError("STRM 输出目录不能为空")
        target_dir = Path(target_value).expanduser()

        media_records = self._media_records(records, media_prefix, sidecar_prefix)
        total = len(media_records)
        if not total:
            return SweepDecision(ACTION_SKIPPED, "本映射还没有 STRM 记录")

        # 闸门 1：目录必须**本来就存在**。这里刻意不 mkdir —— 正向同步会建目录，
        # 媒体库没挂上时那个空目录会让所有记录看起来都「已被删除」。
        try:
            existed = target_dir.is_dir()
        except OSError:
            existed = False
        if not existed:
            return SweepDecision(
                ACTION_SKIPPED,
                f"STRM 输出目录不存在，判定媒体库未挂载，跳过本轮（{total} 条记录）：{target_dir}",
                total_records=total,
            )
        target_dir = target_dir.resolve()

        # 闸门 2：目录存在但一个 STRM 都没有。挂载点被空目录顶替时 is_dir() 仍为真，
        # 光靠闸门 1 拦不住。真要清空云端，请在 115 侧直接删。
        if not self._has_any_strm(target_dir):
            return SweepDecision(
                ACTION_SKIPPED,
                f"STRM 输出目录里一个 .strm 都没有，判定媒体库异常，跳过本轮（{total} 条记录）：{target_dir}",
                total_records=total,
            )

        # 闸门 3：纯本地 stat 得出缺失集合
        missing: list[Dict[str, Any]] = []
        for record_key, record in media_records:
            record_path = str(record.get("path") or "").strip()
            if not record_path:
                continue
            try:
                resolved = Path(record_path).expanduser().resolve()
                resolved.relative_to(target_dir)
            except (OSError, RuntimeError, ValueError):
                logger.warning(f"{LOG_TAG}记录路径无效，保留记录：{record_path}")
                continue
            if resolved.exists():
                continue
            missing.append(
                self._target_from_record(record_key, record, media_prefix, resolved)
            )
        missing_total = len(missing)
        if not missing_total:
            return SweepDecision(ACTION_SKIPPED, "", total_records=total)

        # 闸门 4：缺失比例熔断
        if (
            total >= REVERSE_DELETE_GUARD_MIN_RECORDS
            and missing_total >= total * REVERSE_DELETE_GUARD_MAX_RATIO
        ):
            return SweepDecision(
                ACTION_SKIPPED,
                f"{total} 条记录里有 {missing_total} 条本地 STRM 缺失，比例过高，"
                "疑似媒体库掉盘或输出目录变更，跳过本轮；确实要清空云端请在 115 侧直接删除",
                total_records=total,
                missing_total=missing_total,
            )

        # 闸门 5：按上报范围收窄
        if only_paths is not None:
            scope: list[Path] = []
            for value in only_paths:
                try:
                    scope.append(Path(str(value)).expanduser().resolve())
                except (OSError, RuntimeError, ValueError):
                    continue
            missing = [
                target for target in missing
                if self._path_in_scope(Path(target["path"]), scope)
            ]
            if not missing:
                return SweepDecision(
                    ACTION_SKIPPED, "", total_records=total, missing_total=missing_total
                )

        # 确认执行的那一轮只认传进来的路径：批次早在 confirm 时取走了，不必再看队列
        if bypass_confirm:
            return SweepDecision(
                ACTION_DELETE,
                "",
                targets=tuple(missing),
                total_records=total,
                missing_total=missing_total,
            )

        # 闸门 6：已经挂在待确认队列上的，本轮一律不碰 —— 它们只能经人工确认删除。
        # 不做这一步的话，阈值只看「本轮范围内有几个」，队列里的文件被单独上报一次就
        # 会绕过确认被直接删掉。
        covered = self.pending_paths(mapping)
        queued = [target for target in missing if str(target.get("path")) in covered]
        fresh = [target for target in missing if str(target.get("path")) not in covered]
        if not fresh:
            return SweepDecision(
                ACTION_SKIPPED,
                f"{len(queued)} 个待删媒体已在待确认队列里，等人工处理",
                total_records=total,
                missing_total=missing_total,
                queued_total=len(queued),
            )

        # 闸门 7：分级确认。判定用「当前待删总量」而不是本轮新增量 —— 队列里已经积了
        # 一堆没处理，新冒出来的那几个也该继续走审查，而不是因为「这次只有 3 个」就直接删。
        threshold = normalize_confirm_threshold(config.get("strm_delete_confirm_threshold"))
        if threshold and len(missing) > threshold:
            detail = f"（其中 {len(queued)} 个已在队列里）" if queued else ""
            return SweepDecision(
                ACTION_PENDING,
                f"待删媒体 {len(missing)} 个{detail}，超过确认阈值 {threshold}，"
                f"新增 {len(fresh)} 个已转入待确认队列",
                targets=tuple(fresh),
                total_records=total,
                missing_total=missing_total,
                queued_total=len(queued),
            )
        return SweepDecision(
            ACTION_DELETE,
            "",
            targets=tuple(fresh),
            total_records=total,
            missing_total=missing_total,
            queued_total=len(queued),
        )

    # ---- 执行阶段：这里才碰 115 ----

    def _list_cloud_dir(self, dir_id: str, counts: Dict[str, int]) -> Optional[list[Dict[str, Any]]]:
        """列出 115 目录内容；失败返回 ``None``，调用方必须按「无法确认」保守处理。"""
        try:
            children = self._client.get_dir_list(dir_id)
        except (U115AccessLimitError, U115AuthError):
            raise
        except Exception as err:  # noqa: BLE001
            counts["errors"] = counts.get("errors", 0) + 1
            logger.error(
                f"{LOG_TAG}读取 115 目录内容失败，保留目录及其刮削文件："
                f"目录ID：{dir_id}，原因：{safe_error_text(err)}"
            )
            return None
        return [item for item in (children or []) if isinstance(item, dict)]

    def _delete_cloud(
        self,
        file_ids: list[str],
        description: str,
        counts: Dict[str, int],
        *,
        attempts: int = 1,
        delay: float = CLOUD_DIR_DELETE_DELAY,
    ) -> bool:
        """删除一批 115 条目。访问上限/授权失效直接上抛，交由上层中止整轮任务。

        ``attempts`` 大于 1 时带退避重试 —— 目录删除要用，因为 115 的目录删除是异步的，
        刚删掉子目录时删父目录会被挡下来。
        """
        if not file_ids:
            return True
        try:
            retry_call(
                lambda: self._client.delete_file(file_ids),
                attempts=attempts,
                delay=delay,
                abort_on=(U115AccessLimitError, U115AuthError),
                sleeper=self._sleeper,
            )
        except (U115AccessLimitError, U115AuthError):
            raise
        except Exception as err:  # noqa: BLE001
            text = safe_error_text(err)
            if any(marker in text for marker in ALREADY_MISSING_MARKERS):
                # 目标本来就没了（上一轮删过、或用户自己在 115 侧删了），等同删除成功
                logger.debug(f"{LOG_TAG}115 {description} 本来就不存在，视为已删除")
                return True
            counts["errors"] = counts.get("errors", 0) + 1
            logger.error(
                f"{LOG_TAG}删除 115 {description} 失败，保留记录待下次重试："
                f"ID：{','.join(file_ids)}，原因：{text}"
            )
            return False
        return True

    def _lookup_cloud_item(self, cloud_path: str) -> Optional[Dict[str, Any]]:
        """按云端路径反查条目信息。取不到返回 ``None``，绝不猜。"""
        if not cloud_path:
            return None
        get_item = getattr(self._client, "get_item", None)
        if not callable(get_item):
            return None
        try:
            item = get_item(cloud_path)
        except (U115AccessLimitError, U115AuthError):
            raise
        except Exception as err:  # noqa: BLE001
            logger.warning(
                f"{LOG_TAG}按云端路径反查失败，保留记录：{cloud_path}，"
                f"原因：{safe_error_text(err)}"
            )
            return None
        return item if isinstance(item, dict) else None

    def _ensure_parent_id(self, target: Dict[str, Any]) -> None:
        """补齐 target 的 ``parent_id``。

        v1.2.7 及更早版本把父目录 ID 当成文件 ID 写进了记录（``_item_id`` 先取 ``cid``
        的 bug），所以 ``file_id == parent_id`` 一律判定为脏数据丢弃。父目录 ID 本身
        是可信的 —— 它由扫描时的 ``_current_cid`` 直接写入，没有经过那个 bug。
        """
        if target.get("file_id") and target["file_id"] == target.get("parent_id"):
            target["file_id"] = ""
            target["dirty_identity"] = True
        if target.get("parent_id"):
            return
        item = self._lookup_cloud_item(target.get("cloud_path") or "")
        if not item:
            return
        parent_id = str(item.get("parent_id") or "").strip()
        if parent_id:
            target["parent_id"] = parent_id
        own_id = str(item.get("fileid") or item.get("file_id") or "").strip()
        if own_id and own_id not in ("0", parent_id):
            target["file_id"] = own_id

    @staticmethod
    def _listing_file_ids(listing: list[Dict[str, Any]]) -> Dict[str, str]:
        """云端目录列表 -> ``{小写文件名: 自身 ID}``，只收文件。"""
        result: Dict[str, str] = {}
        for item in listing:
            if cloud_item_is_dir(item):
                continue
            name = cloud_item_name(item)
            item_id = cloud_item_id(item)
            if name and item_id:
                result[name.lower()] = item_id
        return result

    def _unlink_local_output(self, record: Dict[str, Any], target_dir: Path) -> bool:
        """删掉记录留下的本地输出（严格限定在 target_dir 内）。

        云端副本都没了，本地那份刮削文件不会再被同步维护，留着只会让媒体服务器显示
        一个点不开的条目。正向同步清理失效输出时也是这个语义。
        """
        record_path = str(record.get("path") or "").strip()
        if not record_path:
            return False
        try:
            resolved = Path(record_path).expanduser().resolve()
            resolved.relative_to(target_dir)
        except (OSError, RuntimeError, ValueError):
            return False
        if not resolved.exists():
            return False
        try:
            resolved.unlink()
        except OSError as err:
            logger.warning(
                f"{LOG_TAG}清理本地残留刮削文件失败：{resolved}，原因：{safe_error_text(err)}"
            )
            return False
        logger.info(f"{LOG_TAG}清理本地残留刮削文件：{resolved}")
        return True

    def _drop_records_for_cloud_ids(
        self,
        records: Dict[str, Any],
        media_prefix: str,
        cloud_ids: set[str],
        target_dir: Path,
    ) -> int:
        """云端条目已删除，丢弃对应记录并清掉本地残留。"""
        if not cloud_ids:
            return 0
        dropped = 0
        for key, record in list(records.items()):
            key_text = str(key)
            if not isinstance(record, dict) or not key_text.startswith(media_prefix):
                continue
            file_id = str(record.get("file_id") or record.get("fileid") or "").strip()
            if not file_id or file_id not in cloud_ids:
                continue
            self._unlink_local_output(record, target_dir)
            records.pop(key_text, None)
            dropped += 1
        return dropped

    def _drop_records_under_cloud_dir(
        self,
        records: Dict[str, Any],
        media_prefix: str,
        dir_id: str,
        dir_cloud_path: str,
        target_dir: Path,
    ) -> int:
        """整个云端目录被删除后，丢弃该目录（含子目录）下的全部记录。"""
        prefix = f"{normalize_cloud_path(dir_cloud_path).rstrip('/')}/" if dir_cloud_path else ""
        dropped = 0
        for key, record in list(records.items()):
            key_text = str(key)
            if not isinstance(record, dict) or not key_text.startswith(media_prefix):
                continue
            cloud_path = (
                normalize_cloud_path(str(record.get("cloud_path") or ""))
                if record.get("cloud_path")
                else ""
            )
            under_dir = bool(prefix and cloud_path and cloud_path.startswith(prefix))
            same_parent = bool(dir_id) and str(record.get("parent_id") or "").strip() == dir_id
            if not under_dir and not same_parent:
                continue
            self._unlink_local_output(record, target_dir)
            records.pop(key_text, None)
            dropped += 1
        return dropped

    def _remember_deleted(self, record: Dict[str, Any]) -> None:
        """把刚删掉的 pickcode 与文件 ID 记进短期黑名单。

        pickcode 供正向同步跳过重建；文件 ID 供生活监控识别「这是我们自己删的」——
        115 会为每一次删除回一条 type 22 生活事件，而记录早就被这一轮 pop 掉了，
        不认它就会刷一屏「无法定位删除事件对应 STRM」。
        """
        if self._recent_deletes is None:
            return
        pickcode = str(record.get("pickcode") or "").strip().lower()
        if pickcode:
            self._recent_deletes.set(pickcode, True, RECENT_DELETE_TTL)
        self.remember_deleted_id(str(record.get("file_id") or record.get("fileid") or ""))

    def remember_deleted_id(self, file_id: str) -> None:
        """记下一个刚被本插件删掉的 115 条目 ID（文件或目录）。"""
        if self._recent_deletes is None:
            return
        value = str(file_id or "").strip()
        if value:
            self._recent_deletes.set(f"id:{value}", True, RECENT_DELETE_TTL)

    @staticmethod
    def _bump(counts: Dict[str, int], key: str, delta: int = 1) -> None:
        counts[key] = int(counts.get(key) or 0) + delta

    def execute(
        self,
        mapping: Dict[str, Any],
        records: Dict[str, Any],
        targets: Iterable[Dict[str, Any]],
        counts: Dict[str, int],
    ) -> None:
        """按云端父目录成组删除 —— 每个目录只列一次，删除批量提交。"""
        targets = list(targets)
        _mapping_id, media_prefix, _sidecar_prefix = self.mapping_prefixes(mapping)
        source_cid = str(mapping.get("source_cid") or "").strip()
        protected_dir_ids = {"", "0", source_cid}
        target_dir = Path(str(mapping.get("target_dir") or "")).expanduser().resolve()

        # 只有缺 parent_id 的旧记录才会在这里打接口
        for target in targets:
            self._ensure_parent_id(target)

        groups: Dict[str, list[Dict[str, Any]]] = {}
        for target in targets:
            groups.setdefault(str(target.get("parent_id") or ""), []).append(target)

        for parent_id, group in groups.items():
            self._sweep_group(
                records=records,
                media_prefix=media_prefix,
                parent_id=parent_id,
                group=group,
                protected_dir_ids=protected_dir_ids,
                target_dir=target_dir,
                counts=counts,
            )

    def _sweep_group(
        self,
        *,
        records: Dict[str, Any],
        media_prefix: str,
        parent_id: str,
        group: list[Dict[str, Any]],
        protected_dir_ids: set[str],
        target_dir: Path,
        counts: Dict[str, int],
    ) -> None:
        # 目录列表是文件 ID 的**权威来源**：即便记录里的 file_id 是旧版本写坏的，
        # 按文件名从列表里取到的 ID 也一定是文件自己的。
        listing = self._list_cloud_dir(parent_id, counts) if parent_id else None
        name_to_id = self._listing_file_ids(listing) if listing is not None else {}

        pending: Dict[str, Dict[str, Any]] = {}
        for target in group:
            name = str(target.get("name") or "")
            if listing is not None:
                file_id = name_to_id.get(name.lower(), "")
                if not file_id:
                    # 云端本来就没有它了：上一轮删过、或用户直接在 115 侧删了
                    if records.pop(target["record_key"], None) is not None:
                        self._bump(counts, "records_dropped")
                    self._bump(counts, "already_gone")
                    logger.info(
                        f"{LOG_TAG}115 上已无此文件，只清理记录："
                        f"{target.get('cloud_path') or target.get('path')}"
                    )
                    continue
            else:
                # 目录列不出来时只能退回记录里的 ID，脏数据已在 _ensure_parent_id 清空
                file_id = str(target.get("file_id") or "")
            if not file_id:
                self._bump(counts, "unidentified")
                logger.debug(
                    f"{LOG_TAG}缺少可信的 115 文件 ID，本轮不删："
                    f"{target.get('cloud_path') or target.get('path')}"
                )
                continue
            pending[file_id] = target

        deleted_ids: set[str] = set()
        deleted_names: set[str] = set()
        if pending and self._delete_cloud(
            list(pending), f"媒体文件（{len(pending)} 个）", counts
        ):
            for file_id, target in pending.items():
                record = records.pop(target["record_key"], None)
                if isinstance(record, dict):
                    self._remember_deleted(record)
                    self._bump(counts, "records_dropped")
                deleted_ids.add(file_id)
                if target.get("name"):
                    deleted_names.add(str(target["name"]))
                self._bump(counts, "cloud_deleted")
                logger.info(
                    f"{LOG_TAG}本地 STRM 已删除，移除 115 云端文件："
                    f"{target.get('cloud_path') or target.get('path')}"
                )

        if listing is None or not deleted_ids:
            return

        scrape_ids = self._delete_group_scrapes(
            listing=listing,
            deleted_names=deleted_names,
            records=records,
            media_prefix=media_prefix,
            target_dir=target_dir,
            counts=counts,
        )
        self._cleanup_emptied_dir(
            listing=listing,
            consumed_ids=deleted_ids | scrape_ids,
            dir_id=parent_id,
            group=group,
            protected_dir_ids=protected_dir_ids,
            records=records,
            media_prefix=media_prefix,
            target_dir=target_dir,
            counts=counts,
        )

    def _delete_group_scrapes(
        self,
        *,
        listing: list[Dict[str, Any]],
        deleted_names: set[str],
        records: Dict[str, Any],
        media_prefix: str,
        target_dir: Path,
        counts: Dict[str, int],
    ) -> set[str]:
        """删除属于已删媒体的云端刮削文件与字幕。

        按「最具体归属」把目录里的刮削文件分给各自的媒体，兄弟媒体的 nfo / 海报 /
        字幕不会被牵连。归属不明的一律不动。
        """
        config = self._store.get_config()
        extra = parse_extensions(
            config.get("upload_sidecar_extensions", ""), DEFAULT_SIDECAR_EXTENSIONS
        )
        media_names = {
            name
            for item in listing
            if not cloud_item_is_dir(item)
            and (name := cloud_item_name(item))
            and PurePosixPath(name).suffix.lower() in MEDIA_EXTENSIONS
        }
        media_names |= deleted_names
        wanted = {name.lower() for name in deleted_names if name}

        pending: Dict[str, str] = {}
        for item in listing:
            if cloud_item_is_dir(item):
                continue
            name = cloud_item_name(item)
            if not name or not is_scrape_artifact(name, extra):
                continue
            owner = associated_media_name(name, media_names)
            if not owner or owner.lower() not in wanted:
                continue
            item_id = cloud_item_id(item)
            if item_id:
                pending[item_id] = name

        if not pending:
            return set()
        if not self._delete_cloud(
            list(pending), f"刮削/字幕文件（{len(pending)} 个）", counts
        ):
            return set()
        for item_id, name in pending.items():
            self._bump(counts, "scrapes_deleted")
            self.remember_deleted_id(item_id)
            logger.info(f"{LOG_TAG}移除 115 云端刮削/字幕文件：{name}")
        deleted_ids = set(pending)
        dropped = self._drop_records_for_cloud_ids(
            records, media_prefix, deleted_ids, target_dir
        )
        if dropped:
            self._bump(counts, "records_dropped", dropped)
        return deleted_ids

    def _cleanup_emptied_dir(
        self,
        *,
        listing: list[Dict[str, Any]],
        consumed_ids: set[str],
        dir_id: str,
        group: list[Dict[str, Any]],
        protected_dir_ids: set[str],
        records: Dict[str, Any],
        media_prefix: str,
        target_dir: Path,
        counts: Dict[str, int],
    ) -> None:
        """目录被清空后删掉它，再向上级联清理跟着变空的祖先目录。

        判定用的是「列表里除了本轮删掉的条目之外一个都不剩」，而不是「没有媒体文件」——
        目录里可能还有插件不认识的东西，那种情况下宁可留着目录。
        """
        remaining = [
            item for item in listing if cloud_item_id(item) not in consumed_ids
        ]
        if remaining:
            return
        dir_cloud_path = ""
        for target in group:
            cloud_path = str(target.get("cloud_path") or "").strip()
            if cloud_path:
                dir_cloud_path = str(PurePosixPath(normalize_cloud_path(cloud_path)).parent)
                break
        if not dir_cloud_path:
            # 判断不了它在云端的层级，也就判断不了它是不是一级目录，宁可留着
            logger.debug(f"{LOG_TAG}目录云端路径未知，不删除：{dir_id}")
            return
        if is_protected_cloud_dir(dir_id, dir_cloud_path, protected_dir_ids):
            logger.debug(f"{LOG_TAG}目录受保护，不删除：{dir_cloud_path}")
            return
        # 必须在删除之前把父级取到手：目录一旦删掉，115 就再也查不到它的父级了，
        # 向上级联也就无从下手（这一步漏掉的话空目录清理等于形同虚设）。
        parent_id, parent_path = self._parent_of(dir_id, dir_cloud_path)
        if not self._delete_cloud(
            [dir_id], f"空目录：{dir_cloud_path}", counts,
            attempts=CLOUD_DIR_DELETE_ATTEMPTS,
        ):
            return
        self._bump(counts, "cloud_dirs_deleted")
        self.remember_deleted_id(dir_id)
        logger.info(f"{LOG_TAG}目录已空，删除 115 云端目录：{dir_cloud_path}")
        dropped = self._drop_records_under_cloud_dir(
            records, media_prefix, dir_id, dir_cloud_path, target_dir
        )
        if dropped:
            self._bump(counts, "records_dropped", dropped)
        self._cascade_empty_ancestors(
            parent_id=parent_id,
            parent_path=parent_path,
            # 把本轮删掉的东西带上去：115 的目录删除是异步的，紧接着列父目录时
            # 刚删掉的子目录往往还在列表里，不排掉就会误判成「父目录非空」。
            deleted_ids=set(consumed_ids) | {dir_id},
            protected_dir_ids=protected_dir_ids,
            counts=counts,
        )

    def _parent_of(self, dir_id: str, dir_cloud_path: str = "") -> tuple[str, str]:
        """取目录的父级 ``(id, cloud_path)``。**必须在删除该目录之前调用。**"""
        get_item_by_id = getattr(self._client, "get_item_by_id", None)
        if not callable(get_item_by_id):
            return "", ""
        try:
            info = get_item_by_id(dir_id) or {}
        except (U115AccessLimitError, U115AuthError):
            raise
        except Exception as err:  # noqa: BLE001
            logger.warning(
                f"{LOG_TAG}读取 115 目录父级失败，停止向上清理空目录："
                f"目录ID：{dir_id}，原因：{safe_error_text(err)}"
            )
            return "", ""
        parent_id = str(info.get("parent_id") or "").strip()
        own_path = str(info.get("path") or "").strip() or dir_cloud_path
        parent_path = (
            str(PurePosixPath(normalize_cloud_path(own_path)).parent) if own_path else ""
        )
        return parent_id, parent_path

    def _cascade_empty_ancestors(
        self,
        *,
        parent_id: str,
        parent_path: str,
        deleted_ids: set[str],
        protected_dir_ids: set[str],
        counts: Dict[str, int],
    ) -> None:
        """自下而上删除跟着变空的祖先目录，最多 CLOUD_DIR_CASCADE_MAX_DEPTH 层。

        「空」的判定要减掉 ``deleted_ids`` —— 115 的目录删除是异步的，刚删掉的子目录
        还会在父目录列表里挂一会儿，只看列表长度会把每一级都判成非空，级联等于白做。
        """
        seen: set[str] = set()
        for _ in range(CLOUD_DIR_CASCADE_MAX_DEPTH):
            if not parent_id or parent_id in seen:
                return
            if not parent_path or is_protected_cloud_dir(
                parent_id, parent_path, protected_dir_ids
            ):
                return
            children = self._list_cloud_dir(parent_id, counts)
            if children is None:
                return
            if [item for item in children if cloud_item_id(item) not in deleted_ids]:
                return
            # 同理：删之前先把上一级取到手
            grand_id, grand_path = self._parent_of(parent_id, parent_path)
            if not self._delete_cloud(
                [parent_id], f"空目录：{parent_path}", counts,
                attempts=CLOUD_DIR_DELETE_ATTEMPTS,
            ):
                return
            self._bump(counts, "cloud_dirs_deleted")
            self.remember_deleted_id(parent_id)
            logger.info(f"{LOG_TAG}上级目录也已空，删除：{parent_path}")
            seen.add(parent_id)
            deleted_ids.add(parent_id)
            parent_id, parent_path = grand_id, grand_path

    # ---- 入口 ----

    @staticmethod
    def _records_signature(records: Dict[str, Any]) -> Dict[str, str]:
        """记录指纹：key 集合 + file_id。用来判断这一轮到底改没改，没改就不落盘。"""
        return {
            str(key): str(record.get("file_id") or "")
            for key, record in records.items()
            if isinstance(record, dict)
        }

    @staticmethod
    def mapping_label(mapping: Dict[str, Any]) -> str:
        return str(mapping.get("source_path") or mapping.get("source_cid") or "-")

    def _mapping_batches(
        self,
        mapping: Dict[str, Any],
        batches: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> list[Dict[str, Any]]:
        """本映射的待确认批次，按首次发现时间从旧到新。"""
        mapping_id, _media_prefix, _sidecar_prefix = self.mapping_prefixes(mapping)
        source = batches if batches is not None else self._store.get_strm_delete_pending()
        mine = [
            batch
            for batch in source.values()
            if isinstance(batch, dict) and str(batch.get("mapping_id")) == mapping_id
        ]
        mine.sort(key=lambda batch: str(batch.get("created_at") or ""))
        return mine

    def pending_paths(self, mapping: Dict[str, Any]) -> set[str]:
        """本映射所有待确认批次覆盖的本地路径。这些路径只能经人工确认删除。"""
        covered: set[str] = set()
        for batch in self._mapping_batches(mapping):
            for item in batch.get("items") or []:
                if isinstance(item, dict) and item.get("path"):
                    covered.add(str(item["path"]))
        return covered

    def _enqueue_pending(self, mapping: Dict[str, Any], decision: SweepDecision) -> str:
        """把本轮**新增**的待删清单单独存成一张批次，返回批次 ID。

        每次超阈值的新发现都是独立一张，方便逐批审查、逐批决定留删；已经挂在别的批次上的
        路径不会再进来（:meth:`decide` 已经把它们剔掉了），所以同一个文件不会同时出现在
        两张卡片上。批次攒到 :data:`STRM_DELETE_PENDING_MAX_BATCHES` 还没人处理，新增的
        就并进最旧的那一张 —— 宁可让最旧那张变长，也不丢东西、不让队列无上限增长。
        """
        mapping_id, _media_prefix, _sidecar_prefix = self.mapping_prefixes(mapping)
        batches = self._store.get_strm_delete_pending()
        mine = self._mapping_batches(mapping, batches)
        now = datetime.now().isoformat(timespec="seconds")
        incoming = list(decision.targets)

        if len(mine) >= STRM_DELETE_PENDING_MAX_BATCHES:
            oldest = mine[0]
            batch_id = str(oldest.get("id") or "") or token_hex(8)
            known = {
                str(item.get("path"))
                for item in (oldest.get("items") or [])
                if isinstance(item, dict)
            }
            merged = list(oldest.get("items") or []) + [
                item for item in incoming if str(item.get("path")) not in known
            ]
            created_at = str(oldest.get("created_at") or now)
            logger.warning(
                f"{LOG_TAG}待确认批次已达上限 {STRM_DELETE_PENDING_MAX_BATCHES} 张，"
                f"本轮新增 {len(incoming)} 个并入最旧的批次 {batch_id}"
            )
        else:
            batch_id = token_hex(8)
            merged = incoming
            created_at = now

        items = merged[:STRM_DELETE_PENDING_MAX_ITEMS]
        batches[batch_id] = {
            "id": batch_id,
            "mapping_id": mapping_id,
            "mapping": self.mapping_label(mapping),
            "created_at": created_at,
            "updated_at": now,
            "reason": decision.reason,
            "count": len(merged),
            "items_truncated": len(merged) > len(items),
            "items": items,
        }
        self._store.save_strm_delete_pending(batches)
        return batch_id

    def _prune_pending(
        self,
        mapping: Dict[str, Any],
        records: Dict[str, Any],
    ) -> int:
        """剔掉待确认批次里已经不成立的条目，剔空的批次整张删掉。

        「不成立」有两种：本地 STRM 又被放回来了（用户改主意），或者对应记录已经不在了
        （云端文件早就没了、或者被别的流程清理过）。只在全量轮次做 —— 范围收窄的轮次看不到
        全局，没资格判定别的批次里的条目是死是活。
        """
        batches = self._store.get_strm_delete_pending()
        mine = self._mapping_batches(mapping, batches)
        if not mine:
            return 0
        dropped = 0
        for batch in mine:
            kept = []
            for item in batch.get("items") or []:
                if not isinstance(item, dict):
                    continue
                record_key = str(item.get("record_key") or "")
                path = str(item.get("path") or "")
                if record_key and record_key not in records:
                    dropped += 1
                    continue
                try:
                    if path and Path(path).exists():
                        dropped += 1
                        continue
                except OSError:
                    pass
                kept.append(item)
            batch_id = str(batch.get("id") or "")
            if not kept:
                batches.pop(batch_id, None)
                logger.info(f"{LOG_TAG}待确认批次 {batch_id} 的条目已全部失效，撤销该批次")
                continue
            if len(kept) != len(batch.get("items") or []):
                batch["items"] = kept
                batch["count"] = len(kept)
                batch["items_truncated"] = False
                batch["updated_at"] = datetime.now().isoformat(timespec="seconds")
                batches[batch_id] = batch
        if dropped:
            logger.info(f"{LOG_TAG}待确认队列里 {dropped} 个条目已不成立（本地已恢复或记录已清），已剔除")
            self._store.save_strm_delete_pending(batches)
        return dropped

    def sweep(
        self,
        mapping: Dict[str, Any],
        only_paths: Optional[Iterable[str | Path]] = None,
        *,
        bypass_confirm: bool = False,
    ) -> Dict[str, Any]:
        """一次映射的反向删除巡检，返回可直接写进执行记录的条目。

        与正向同步的关键区别是**不枚举 115 目录树**：巡检与实时监听都要高频触发，
        全量扫描既慢又容易撞 115 的访问上限，所以只对「记录里有、本地已经没有」的
        少数条目动手。
        """
        started = monotonic()
        counts: Dict[str, int] = {
            "cloud_deleted": 0,
            "scrapes_deleted": 0,
            "cloud_dirs_deleted": 0,
            "already_gone": 0,
            "unidentified": 0,
            "records_dropped": 0,
            "errors": 0,
        }
        label = self.mapping_label(mapping)
        records = self._store.get_strm_records()
        before = self._records_signature(records)
        if only_paths is None and not bypass_confirm:
            # 只有全量轮次看得到全局，才有资格判定别的批次里的条目是死是活
            self._prune_pending(mapping, records)
        decision = self.decide(mapping, records, only_paths, bypass_confirm=bypass_confirm)

        pending_count = 0
        if decision.action == ACTION_PENDING:
            batch_id = self._enqueue_pending(mapping, decision)
            pending_count = len(decision.targets)
            logger.warning(f"{LOG_TAG}{label}：{decision.reason}（批次 {batch_id}）")
        elif decision.action == ACTION_SKIPPED:
            if decision.queued_total:
                # 全都在等确认，不是异常
                logger.info(f"{LOG_TAG}{label}：{decision.reason}")
            elif decision.reason:
                logger.error(f"{LOG_TAG}{label}：{decision.reason}")
        else:
            logger.info(f"{LOG_TAG}{label}：{len(decision.targets)} 个本地 STRM 已删除，开始清理云端")
            try:
                self.execute(mapping, records, decision.targets, counts)
            finally:
                # 云端已经删掉的东西必须落盘，哪怕是被访问上限打断的 ——
                # 记录留着只会让下一轮对着已经不存在的文件再列一遍目录。
                if self._records_signature(records) != before:
                    self._store.save_strm_records(records)
                    before = self._records_signature(records)

        if self._records_signature(records) != before:
            self._store.save_strm_records(records)
        if counts["unidentified"]:
            logger.warning(
                f"{LOG_TAG}{counts['unidentified']} 条记录的本地 STRM 已不存在，但拿不到可信的"
                "115 文件 ID，本轮没有删除对应云端文件；这类记录来自旧版本，"
                "执行一次全量 STRM 同步补齐记录后即可删除"
            )
        return {
            "kind": "strm_sweep",
            "time": datetime.now().isoformat(timespec="seconds"),
            "mapping": label,
            "action": decision.action,
            "reason": decision.reason,
            "pending": pending_count,
            "queued": decision.queued_total,
            **counts,
            "duration_ms": int((monotonic() - started) * 1000),
        }
