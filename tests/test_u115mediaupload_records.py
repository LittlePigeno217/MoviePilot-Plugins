from plugins.u115mediaupload.records import IncrementalRecordStore, TaskHistory


def test_record_store_detects_changed_file(tmp_path):
    media = tmp_path / "Film.mkv"
    media.write_bytes(b"one")

    store = IncrementalRecordStore()
    assert store.has_changed(media)

    store.mark_uploaded(media, "/Cloud/Film.mkv")
    assert not store.has_changed(media)

    media.write_bytes(b"two")
    assert store.has_changed(media)


def test_record_store_serializes_records(tmp_path):
    media = tmp_path / "Film.mkv"
    media.write_bytes(b"media")

    store = IncrementalRecordStore()
    store.mark_uploaded(media, "/Cloud/Film.mkv", uploaded_at="2026-07-10 10:00:00")

    payload = store.to_dict()
    restored = IncrementalRecordStore(payload)

    assert restored.to_dict()[str(media)]["target"] == "/Cloud/Film.mkv"
    assert restored.to_dict()[str(media)]["uploaded_at"] == "2026-07-10 10:00:00"


def test_task_history_keeps_latest_items_first():
    history = TaskHistory(limit=2)
    history.add({"id": "1", "status": "completed"})
    history.add({"id": "2", "status": "failed"})
    history.add({"id": "3", "status": "completed"})

    assert [item["id"] for item in history.items] == ["3", "2"]
