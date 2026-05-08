import shutil
from pathlib import Path
from function.cache import (
    get_song as cache_get_song,
    put_song as cache_put_song,
    get_lyrics as cache_get_lyrics,
    put_lyrics as cache_put_lyrics,
)
from function.config import get_cache_dir


def test_song_round_trip():
    data = {"id": 99999999, "title": "Test Song", "artist": "Tester", "album": "Test Album"}
    cache_put_song(99999999, data)
    cached = cache_get_song(99999999)
    assert cached == data


def test_lyrics_round_trip():
    data = {
        "lrc": {"lyric": "[00:01.00]Hello"},
        "tlyric": {"lyric": "[00:01.00]Nihao"},
    }
    cache_put_lyrics(99999999, data)
    cached = cache_get_lyrics(99999999)
    assert cached == data


def teardown_module():
    d = Path(get_cache_dir()) / "song" / "99999999"
    if d.exists():
        shutil.rmtree(d)
