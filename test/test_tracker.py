import shutil
from pathlib import Path
import pytest
from function.tracker import (
    validate_name,
    create_tracker,
    load_settings,
    load_songs_db,
    save_songs_db,
    compare_songs,
    fetch_all_songs,
    auto_resolve,
    download_tracker,
    _tracker_path,
    _settings_path,
    _songs_path,
)
from function.config import get_quality
from test.conftest import SONG_ID


NAME_CRUD = "_test_tracker_crud"
NAME_DB = "_test_tracker_db"
NET_NAME = "_test_tracker_net"


class TestNameValidation:
    def test_valid_simple(self):
        validate_name("abc")

    def test_valid_with_dash(self):
        validate_name("my-tracker")

    def test_valid_with_underscore(self):
        validate_name("tracker_01")

    def test_valid_mixed(self):
        validate_name("ABC_def-123")

    def test_invalid_space(self):
        with pytest.raises(SystemExit):
            validate_name("bad name")

    def test_invalid_chinese(self):
        with pytest.raises(SystemExit):
            validate_name("中文")

    def test_invalid_slash(self):
        with pytest.raises(SystemExit):
            validate_name("a/b")


class TestCreateAndSettings:
    @classmethod
    def setup_class(cls):
        tdir = _tracker_path(NAME_CRUD)
        if tdir.exists():
            shutil.rmtree(tdir)
        create_tracker(NAME_CRUD)

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(_tracker_path(NAME_CRUD), ignore_errors=True)

    def test_tracker_dir_exists(self):
        assert _tracker_path(NAME_CRUD).is_dir()

    def test_settings_file_exists(self):
        assert _settings_path(NAME_CRUD).is_file()

    def test_songs_json_exists(self):
        assert _songs_path(NAME_CRUD).is_file()

    def test_settings_has_description(self):
        settings = load_settings(NAME_CRUD)
        assert "description" in settings

    def test_settings_has_sources(self):
        settings = load_settings(NAME_CRUD)
        assert isinstance(settings["sources"], list)

    def test_default_sources_empty(self):
        settings = load_settings(NAME_CRUD)
        assert len(settings["sources"]) == 0


class TestSongsDb:
    @classmethod
    def setup_class(cls):
        tdir = _tracker_path(NAME_DB)
        if tdir.exists():
            shutil.rmtree(tdir)
        create_tracker(NAME_DB)
        cls._songs = [
            {"id": 1, "title": "Song A"},
            {
                "id": 2,
                "title": "Song B",
                "at": [{"type": "song", "id": 2}, {"type": "playlist", "id": 99}],
            },
        ]
        save_songs_db(NAME_DB, cls._songs)

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(_tracker_path(NAME_DB), ignore_errors=True)

    def test_saved_two_songs(self):
        loaded = load_songs_db(NAME_DB)
        assert len(loaded) == 2

    def test_song_a_id(self):
        loaded = load_songs_db(NAME_DB)
        assert loaded[0]["id"] == 1

    def test_song_a_title(self):
        loaded = load_songs_db(NAME_DB)
        assert loaded[0]["title"] == "Song A"

    def test_song_b_has_at(self):
        loaded = load_songs_db(NAME_DB)
        assert loaded[1].get("at") is not None

    def test_backup_exists(self):
        assert Path(_songs_path(NAME_DB).__str__() + ".bak").exists()

    def test_backup_persists_after_second_save(self):
        save_songs_db(NAME_DB, [{"id": 3, "title": "Song C"}])
        assert Path(_songs_path(NAME_DB).__str__() + ".bak").exists()


class TestCompareSongs:
    def test_added(self):
        fresh = {4: {"id": 4, "title": "Song D"}}
        cmp = compare_songs(fresh, [])
        assert len(cmp["added"]) == 1
        assert cmp["added"][0]["id"] == 4

    def test_removed(self):
        cmp = compare_songs({}, [{"id": 2, "title": "Song B"}])
        assert len(cmp["removed"]) == 1
        assert cmp["removed"][0]["id"] == 2

    def test_changed(self):
        fresh = {3: {"id": 3, "title": "Song C (renamed)"}}
        cached = [{"id": 3, "title": "Song C"}]
        cmp = compare_songs(fresh, cached)
        assert len(cmp["changed"]) == 1
        assert cmp["changed"][0][0]["id"] == 3

    def test_unchanged(self):
        fresh = {
            1: {"id": 1, "title": "Song A"},
            3: {"id": 3, "title": "Song C (renamed)"},
        }
        cached = [{"id": 1, "title": "Song A"}, {"id": 3, "title": "Song C"}]
        cmp = compare_songs(fresh, cached)
        assert len(cmp["changed"]) == 1  # only 3 changed, 1 unchanged

    def test_empty(self):
        assert compare_songs({}, []) == {"added": [], "removed": [], "changed": []}

    def test_no_changes(self):
        fresh = {1: {"id": 1, "title": "A"}}
        cached = [{"id": 1, "title": "A"}]
        assert compare_songs(fresh, cached) == {
            "added": [],
            "removed": [],
            "changed": [],
        }


@pytest.mark.network
class TestTrackerNetwork:
    @classmethod
    def setup_class(cls):
        tdir = _tracker_path(NET_NAME)
        if tdir.exists():
            shutil.rmtree(tdir)
        create_tracker(NET_NAME)
        with open(_settings_path(NET_NAME), "w", encoding="utf-8") as f:
            f.write(f"""[tracker]
description = "Network test"

[sources.song]
ids = [{SONG_ID}]

[sources.playlist]
ids = []

[sources.album]
ids = []
""")

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(_tracker_path(NET_NAME), ignore_errors=True)

    def test_settings_loaded(self):
        settings = load_settings(NET_NAME)
        assert settings["sources"][0]["ids"] == [SONG_ID]

    def test_fetch_songs(self):
        settings = load_settings(NET_NAME)
        fresh, _ = fetch_all_songs(settings)
        assert len(fresh) > 0

    def test_no_songs_cached_yet(self):
        cached = load_songs_db(NET_NAME)
        assert len(cached) == 0

    def test_all_songs_are_added(self):
        settings = load_settings(NET_NAME)
        fresh, _ = fetch_all_songs(settings)
        cached = load_songs_db(NET_NAME)
        cmp = compare_songs(fresh, cached)
        assert len(cmp["added"]) > 0

    def test_auto_resolve_and_re_fetch(self):
        settings = load_settings(NET_NAME)
        fresh, _ = fetch_all_songs(settings)
        cached = load_songs_db(NET_NAME)
        cmp = compare_songs(fresh, cached)
        resolved = auto_resolve(cmp, cached, fresh)
        assert resolved is not None
        assert len(resolved) > 0
        save_songs_db(NET_NAME, resolved)
        # Re-fetch — should be up to date
        fresh2, _ = fetch_all_songs(settings)
        cached2 = load_songs_db(NET_NAME)
        cmp2 = compare_songs(fresh2, cached2)
        assert len(cmp2["added"]) == 0
        assert len(cmp2["removed"]) == 0
        assert len(cmp2["changed"]) == 0

    def test_download(self, temp_dir):
        dl_dir = Path(temp_dir) / "tracker_dl"
        # Ensure songs are in the DB
        settings = load_settings(NET_NAME)
        fresh, _ = fetch_all_songs(settings)
        save_songs_db(NET_NAME, list(fresh.values()))
        download_tracker(NET_NAME, get_quality(), str(dl_dir))
        files = list(dl_dir.iterdir()) if dl_dir.is_dir() else []
        assert len(files) >= 1
