from dataclasses import dataclass, asdict


@dataclass
class Mapping:
    """一组「115 源目录 → 本地输出目录」映射。"""
    id: str
    enabled: bool
    source_cid: str
    source_path: str
    target_dir: str

    def to_dict(self):
        return asdict(self)


@dataclass
class SyncRecord:
    """单个已生成 .strm 的记录，用于增量比对。"""
    file_key: str
    pickcode: str
    sha1: str
    strm_path: str

    def to_dict(self):
        return asdict(self)


@dataclass
class HistoryEntry:
    """一次映射同步的结果统计。"""
    time: str
    mapping_id: str
    added: int
    updated: int
    skipped: int
    errors: int
    duration_ms: int
    message: str = ""

    def to_dict(self):
        return asdict(self)
