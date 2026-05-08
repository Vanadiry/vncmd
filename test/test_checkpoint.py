import os
import pytest
from function.checkpoint import (
    load_checkpoint,
    save_checkpoint,
    create_checkpoint,
    mark_downloaded,
    sync_checkpoint_tracks,
)


@pytest.fixture(autouse=True)
def _isolate_checkpoint_dir(monkeypatch, temp_dir):
    checkpoint_dir = os.path.join(temp_dir, "download")
    monkeypatch.setattr(
        "function.checkpoint._get_checkpoint_dir", lambda: checkpoint_dir
    )
    os.makedirs(checkpoint_dir, exist_ok=True)
    return checkpoint_dir


class TestLoadSave:
    def test_load_nonexistent(self):
        assert load_checkpoint("playlist", "123") is None

    def test_save_and_load(self, _isolate_checkpoint_dir):
        data = {"type": "album", "id": "456", "download_dir": "/tmp/x", "tracks": {}}
        save_checkpoint("album", "456", data)
        loaded = load_checkpoint("album", "456")
        assert loaded == data

    def test_load_other_type_not_found(self, _isolate_checkpoint_dir):
        save_checkpoint("playlist", "1", {"tracks": {}})
        assert load_checkpoint("album", "1") is None


class TestCreateCheckpoint:
    def test_creates_and_returns(self, _isolate_checkpoint_dir):
        cp = create_checkpoint("playlist", "789", "/tmp/dl", [10, 20])
        assert cp["type"] == "playlist"
        assert cp["id"] == "789"
        assert cp["download_dir"] == "/tmp/dl"
        assert cp["tracks"] == {"10": False, "20": False}

    def test_persisted_to_disk(self, _isolate_checkpoint_dir):
        create_checkpoint("album", "999", "/tmp/a", [1])
        loaded = load_checkpoint("album", "999")
        assert loaded is not None
        assert loaded["tracks"] == {"1": False}


class TestMarkDownloaded:
    def test_marks_true(self, _isolate_checkpoint_dir):
        create_checkpoint("playlist", "p1", "/tmp/x", [1, 2, 3])
        mark_downloaded("playlist", "p1", 2)
        cp = load_checkpoint("playlist", "p1")
        assert cp["tracks"]["1"] is False
        assert cp["tracks"]["2"] is True
        assert cp["tracks"]["3"] is False

    def test_noop_on_missing_checkpoint(self, _isolate_checkpoint_dir):
        mark_downloaded("playlist", "nonexistent", 1)


class TestSyncCheckpointTracks:
    def test_no_checkpoint_returns_all_pending(self, _isolate_checkpoint_dir):
        pending, has_changes = sync_checkpoint_tracks(
            "playlist", "new", {"1": "A", "2": "B"}
        )
        assert pending == ["1", "2"]
        assert not has_changes

    def test_resume_all_done(self, _isolate_checkpoint_dir):
        create_checkpoint("playlist", "p2", "/tmp/x", [1, 2])
        mark_downloaded("playlist", "p2", 1)
        mark_downloaded("playlist", "p2", 2)
        pending, has_changes = sync_checkpoint_tracks(
            "playlist", "p2", {"1": "A", "2": "B"}
        )
        assert pending == []
        assert not has_changes

    def test_resume_partial(self, _isolate_checkpoint_dir):
        create_checkpoint("playlist", "p3", "/tmp/x", [1, 2, 3])
        mark_downloaded("playlist", "p3", 1)
        pending, has_changes = sync_checkpoint_tracks(
            "playlist", "p3", {"1": "A", "2": "B", "3": "C"}
        )
        assert set(pending) == {"2", "3"}
        assert not has_changes

    def test_new_tracks_added(self, _isolate_checkpoint_dir):
        create_checkpoint("playlist", "p4", "/tmp/x", [1])
        pending, has_changes = sync_checkpoint_tracks(
            "playlist", "p4", {"1": "A", "2": "B"}
        )
        assert set(pending) == {"1", "2"}
        assert has_changes
        cp = load_checkpoint("playlist", "p4")
        assert set(cp["tracks"].keys()) == {"1", "2"}

    def test_removed_tracks_deleted(self, _isolate_checkpoint_dir):
        create_checkpoint("playlist", "p5", "/tmp/x", [1, 2])
        pending, has_changes = sync_checkpoint_tracks(
            "playlist", "p5", {"1": "A"}
        )
        assert pending == ["1"]
        assert has_changes
        cp = load_checkpoint("playlist", "p5")
        assert set(cp["tracks"].keys()) == {"1"}

    def test_tracker_silent_on_changes(self, _isolate_checkpoint_dir):
        create_checkpoint("tracker", "t1", "/tmp/x", [1])
        pending, has_changes = sync_checkpoint_tracks(
            "tracker", "t1", {"1": "A", "3": "C"}
        )
        assert set(pending) == {"1", "3"}
        assert has_changes

    def test_tracker_silent_no_changes(self, _isolate_checkpoint_dir):
        create_checkpoint("tracker", "t2", "/tmp/x", [1, 2])
        mark_downloaded("tracker", "t2", 1)
        mark_downloaded("tracker", "t2", 2)
        pending, has_changes = sync_checkpoint_tracks(
            "tracker", "t2", {"1": "A", "2": "B"}
        )
        assert pending == []
        assert not has_changes


def teardown_module():
    import function.checkpoint as cp
    cp._CHECKPOINT_DIR = None
