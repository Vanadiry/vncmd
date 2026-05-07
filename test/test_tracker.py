"""Tracker module tests."""

import os
import sys
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test._runner import check, section, summary, reset, cleanup, SONG_ID

reset()
TMP = __import__("test._runner", fromlist=["tmp_dir"]).tmp_dir()

# -- name validation ----------------------------------------------------

section("Tracker — name validation")

from function.tracker import validate_name


def _try_validate(name, expect_ok):
    try:
        validate_name(name)
        check(f"validate_name({name!r}) passes", expect_ok)
    except SystemExit:
        check(f"validate_name({name!r}) rejects", not expect_ok)


_try_validate("abc", True)
_try_validate("my-tracker", True)
_try_validate("tracker_01", True)
_try_validate("ABC_def-123", True)
_try_validate("bad name", False)
_try_validate("中文", False)
_try_validate("a/b", False)

# -- create / load settings --------------------------------------------

section("Tracker — create & settings")

test_name = "_test_tracker_unit"

# Standalone path helpers for unit test
from function.tracker import (
    create_tracker,
    load_settings,
    load_songs_db,
    save_songs_db,
    compare_songs,
    _tracker_path,
    _settings_path,
    _songs_path,
)

tdir = _tracker_path(test_name)
if os.path.exists(tdir):
    shutil.rmtree(tdir)

create_tracker(test_name)
check("tracker dir exists", os.path.isdir(tdir))
check("settings.toml exists", os.path.isfile(_settings_path(test_name)))
check("songs.json exists", os.path.isfile(_songs_path(test_name)))

settings = load_settings(test_name)
check("settings has description", "description" in settings)
check("settings has sources", isinstance(settings["sources"], list))
check(
    "default sources filtered (empty ids)",
    len(settings["sources"]) == 0,
)

# -- songs DB round-trip ------------------------------------------------

section("Tracker — songs DB round-trip")

songs = [
    {"id": 1, "title": "Song A"},
    {
        "id": 2,
        "title": "Song B",
        "at": [{"type": "song", "id": 2}, {"type": "playlist", "id": 99}],
    },
]
save_songs_db(test_name, songs)
loaded = load_songs_db(test_name)
check("saved 2 songs", len(loaded) == 2)
check("song A id", loaded[0]["id"] == 1)
check("song A title", loaded[0]["title"] == "Song A")
check("song B has at", loaded[1].get("at") is not None)

# -- backup -------------------------------------------------------------

section("Tracker — backup")

bak_path = _songs_path(test_name) + ".bak"
check("bak exists after save", os.path.isfile(bak_path))

save_songs_db(test_name, [{"id": 3, "title": "Song C"}])
check("bak still exists after second save", os.path.isfile(bak_path))

# -- compare songs ------------------------------------------------------

section("Tracker — compare_songs")

fresh = {
    1: {"id": 1, "title": "Song A"},
    3: {"id": 3, "title": "Song C (renamed)"},
    4: {"id": 4, "title": "Song D"},
}
cached = [
    {"id": 1, "title": "Song A"},
    {"id": 2, "title": "Song B"},
    {"id": 3, "title": "Song C"},
]

cmp = compare_songs(fresh, cached)
check("added: song D", len(cmp["added"]) == 1 and cmp["added"][0]["id"] == 4)
check("removed: song B", len(cmp["removed"]) == 1 and cmp["removed"][0]["id"] == 2)
check(
    "changed: song C renamed",
    len(cmp["changed"]) == 1 and cmp["changed"][0][0]["id"] == 3,
)
check("unchanged: song A", len(cmp["changed"]) == 1)  # only song C changed

# empty comparison
empty_cmp = compare_songs({}, [])
check("empty compare", empty_cmp == {"added": [], "removed": [], "changed": []})

# no changes
same_cmp = compare_songs({1: {"id": 1, "title": "A"}}, [{"id": 1, "title": "A"}])
check("no changes", same_cmp == {"added": [], "removed": [], "changed": []})

# -- cleanup unit test tracker ------------------------------------------

shutil.rmtree(tdir, ignore_errors=True)
cleanup(TMP)

# -- network: fetch + auto-resolve + download ---------------------------

section("Tracker — network: fetch & download")

net_name = "_test_tracker_net"
net_dir = _tracker_path(net_name)
if os.path.exists(net_dir):
    shutil.rmtree(net_dir)

create_tracker(net_name)

# Write a settings with a real song ID
import tomllib

sp = _settings_path(net_name)
with open(sp, "rb") as f:
    data = tomllib.load(f)

# Add a song source
data["sources"][0]["ids"] = [SONG_ID]
with open(sp, "w", encoding="utf-8") as f:
    import tomllib

    # Write manually since we just need the updated file
    pass

# Can't easily write TOML without a writer lib, so rebuild the file
with open(sp, "w", encoding="utf-8") as f:
    f.write(f"""[tracker]
description = "Network test"

[[sources]]
type = "song"
ids = [{SONG_ID}]

[[sources]]
type = "playlist"
ids = []

[[sources]]
type = "album"
ids = []
""")

settings = load_settings(net_name)
check(
    "network: settings loaded with song id", settings["sources"][0]["ids"] == [SONG_ID]
)

from function.tracker import fetch_all_songs, auto_resolve

fresh = fetch_all_songs(settings)
check("network: fetched songs", len(fresh) > 0, f"got {len(fresh)}")

cached = load_songs_db(net_name)
check("network: no songs cached yet", len(cached) == 0)

comparison = compare_songs(fresh, cached)
check("network: all songs are added", len(comparison["added"]) > 0)

resolved = auto_resolve(comparison, cached, fresh)
check("network: auto-resolved", resolved is not None and len(resolved) > 0)

save_songs_db(net_name, resolved)
check("network: saved resolved songs", len(load_songs_db(net_name)) > 0)

# Re-fetch — should be up to date
fresh2 = fetch_all_songs(settings)
cached2 = load_songs_db(net_name)
cmp2 = compare_songs(fresh2, cached2)
check(
    "network: re-fetch up to date",
    len(cmp2["added"]) == 0 and len(cmp2["removed"]) == 0 and len(cmp2["changed"]) == 0,
)

# Download one song
section("Tracker — network: download")
from function.tracker import download_tracker
from function.api import get_song_url
from function.config import get_quality

dl_dir = os.path.join(TMP, "tracker_dl")
url = get_song_url(SONG_ID)
if url:
    download_tracker(net_name, get_quality(), dl_dir)
    files = os.listdir(dl_dir) if os.path.isdir(dl_dir) else []
    check("tracker download creates files", len(files) >= 1, f"got {len(files)}")
else:
    check("tracker download skipped (no URL)", True)

# -- cleanup network test -----------------------------------------------

shutil.rmtree(net_dir, ignore_errors=True)
cleanup(TMP)

failed = summary()
if __name__ == "__main__":
    raise SystemExit(failed)
