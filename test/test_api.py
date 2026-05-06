import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""API module tests."""
from test._runner import check, section, summary, reset, PLAYLIST_ID, SONG_ID, ALBUM_ID

reset()

section("API — Search")
from function.api import search

result = search("Beyond", limit=5)
check("search returns dict with songs", "songs" in result and "total" in result)
check("search has results", len(result["songs"]) > 0)
for k in ("id", "title", "artist", "album", "cover", "duration"):
    check(f"song has {k}", k in result["songs"][0])

section("API — Song details")
from function.api import get_song_details

song = get_song_details(SONG_ID)
check(f"song id={SONG_ID} found", song["id"] == SONG_ID)
for k in ("title", "artist", "album", "publish_time"):
    check(f"song has {k}", bool(song[k]))
check("song has cover URL", song["cover"].startswith("http"))
check("song has duration", ":" in song["duration"])
print(f"    → {song['title']} - {song['artist']} [{song['album']}]")

song2 = get_song_details(SONG_ID)
check("cached song identical", song == song2)

section("API — Playlist")
from function.api import get_playlist_details

pl = get_playlist_details(PLAYLIST_ID)
check(f"playlist id={PLAYLIST_ID} found", pl["id"] == PLAYLIST_ID)
check("playlist has name", bool(pl["name"]))
check("playlist has tracks", len(pl["tracks"]) > 0)
check("track has id", "id" in pl["tracks"][0])
print(f"    → {pl['name']} by {pl['creator']} ({pl['track_count']} tracks)")

section("API — Album")
from function.api import get_album_details

al = get_album_details(ALBUM_ID)
check(f"album id={ALBUM_ID} found", al["id"] == ALBUM_ID)
check("album has name", bool(al["name"]))
check("album has artist", bool(al["artist"]))
check("album has tracks", len(al["tracks"]) > 0)
print(f"    → {al['name']} by {al['artist']} ({al['track_count']} tracks)")

section("API — Lyrics")
from function.api import get_lyrics

lyrics = get_lyrics(SONG_ID)
check("lyrics has lrc", "lrc" in lyrics)
check("lyrics has tlyric", "tlyric" in lyrics)
check("lrc has text", len(lyrics["lrc"].get("lyric", "")) > 0)
lyrics2 = get_lyrics(SONG_ID)
check("cached lyrics has lrc", "lrc" in lyrics2)
check("cached lyrics has lyric text", len(lyrics2["lrc"].get("lyric", "")) > 0)

section("API — Song URL")
from function.api import get_song_url

url = get_song_url(SONG_ID)
if url:
    check("song URL available (cookie OK)", url.startswith("http"))
else:
    check("song URL unavailable (no cookie/VIP) — acceptable", True)
url320 = get_song_url(SONG_ID, quality=320000)
check("URL with quality param", isinstance(url320, str) or url320 is None)

failed = summary()
if __name__ == "__main__":
    raise SystemExit(failed)
