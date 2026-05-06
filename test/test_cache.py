import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Cache module tests."""
import os
from test._runner import check, section, summary, reset, cleanup

reset()
section("Cache")

from function.cache import get_song as cache_get_song, put_song as cache_put_song
from function.cache import get_lyrics as cache_get_lyrics, put_lyrics as cache_put_lyrics
from function.config import get_cache_dir

test_song = {"id": 99999999, "title": "Test Song", "artist": "Tester", "album": "Test Album"}
cache_put_song(99999999, test_song)
cached = cache_get_song(99999999)
check("put_song / get_song round-trip", cached == test_song)

test_lyric = {"lrc": {"lyric": "[00:01.00]Hello"}, "tlyric": {"lyric": "[00:01.00]Nihao"}}
cache_put_lyrics(99999999, test_lyric)
cached_l = cache_get_lyrics(99999999)
check("put_lyrics / get_lyrics round-trip", cached_l == test_lyric)

# Cleanup
for d in ("song", "lyrics"):
    for f in os.listdir(os.path.join(get_cache_dir(), d)):
        if f.startswith("99999999"):
            os.remove(os.path.join(get_cache_dir(), d, f))

failed = summary()
if __name__ == "__main__":
    raise SystemExit(failed)
