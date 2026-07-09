from pathlib import Path

from plugins.u115mediaupload.records import IncrementalRecordStore
from plugins.u115mediaupload.scanner import MediaScanner


def test_scanner_maps_media_and_sidecars_to_115_paths(tmp_path):
    source = tmp_path / "Movies"
    source.mkdir()
    media = source / "Film.mkv"
    nfo = source / "Film.nfo"
    ignored = source / "Film.txt"
    media.write_bytes(b"media")
    nfo.write_text("nfo", encoding="utf-8")
    ignored.write_text("ignored", encoding="utf-8")

    scanner = MediaScanner(media_extensions=[".mkv"], sidecar_extensions=[".nfo"])
    items, failures = scanner.scan_mappings(
        [{"enabled": True, "source": str(source), "target": "/Cloud/Movies"}],
        include_sidecars=True,
    )

    assert failures == []
    assert [(item.kind, item.target_path) for item in items] == [
        ("media", "/Cloud/Movies/Film.mkv"),
        ("sidecar", "/Cloud/Movies/Film.nfo"),
    ]


def test_scanner_incremental_filters_unchanged_files(tmp_path):
    source = tmp_path / "Movies"
    source.mkdir()
    media = source / "Film.mkv"
    media.write_bytes(b"media")

    scanner = MediaScanner(media_extensions=[".mkv"], sidecar_extensions=[".nfo"])
    records = IncrementalRecordStore()
    records.mark_uploaded(media, "/Cloud/Movies/Film.mkv")

    unchanged, failures = scanner.scan_mappings(
        [{"enabled": True, "source": str(source), "target": "/Cloud/Movies"}],
        include_sidecars=False,
        records=records,
        incremental=True,
    )
    assert failures == []
    assert unchanged == []

    media.write_bytes(b"media changed")
    changed, failures = scanner.scan_mappings(
        [{"enabled": True, "source": str(source), "target": "/Cloud/Movies"}],
        include_sidecars=False,
        records=records,
        incremental=True,
    )
    assert failures == []
    assert [item.path for item in changed] == [media]


def test_scanner_reports_missing_source_without_failing_other_mappings(tmp_path):
    source = tmp_path / "Movies"
    source.mkdir()
    (source / "Film.mkv").write_bytes(b"media")

    scanner = MediaScanner(media_extensions=[".mkv"], sidecar_extensions=[".nfo"])
    items, failures = scanner.scan_mappings(
        [
            {"enabled": True, "source": str(tmp_path / "Missing"), "target": "/Missing"},
            {"enabled": True, "source": str(source), "target": "/Cloud/Movies"},
        ],
        include_sidecars=False,
    )

    assert len(items) == 1
    assert failures[0]["reason"] == "源目录不存在"
