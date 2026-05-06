import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Download orchestration tests."""
import os
from test._runner import check, section, summary, reset, SONG_ID, cleanup

reset()
TMP = __import__("test._runner", fromlist=["tmp_dir"]).tmp_dir()

section("Download — fetch helpers")
from function.download import fetch_lyrics, fetch_cover
from function.api import get_song_details

lyrics_text, translated_text = fetch_lyrics(
    f"http://music.163.com/api/song/lyric?os=pc&id={SONG_ID}&lv=-1&tv=1", "netease"
)
check("fetch_lyrics returns strings", isinstance(lyrics_text, str) and isinstance(translated_text, str))
check("fetch_lyrics has content", len(lyrics_text) > 0)

song = get_song_details(SONG_ID)
cover = fetch_cover(song["cover"])
check("fetch_cover returns bytes", isinstance(cover, bytes))
check("fetch_cover non-empty", len(cover) > 1000)

section("Download — full single song")
from function.downloader import download_song
from function.api import get_song_url

dl_dir = os.path.join(TMP, "dl")
url = get_song_url(SONG_ID)
if url:
    ok, msg, path = download_song(
        song_url=url,
        song_title=song["title"],
        song_artist=song["artist"],
        song_album=song["album"],
        song_id=str(song["id"]),
        cover_url=song["cover"],
        lyrics_api_url=f"http://music.163.com/api/song/lyric?os=pc&id={SONG_ID}&lv=-1&tv=1",
        publish_time=song["publish_time"],
        download_dir=dl_dir,
    )
    check("download_song returns success", ok, msg if not ok else "")
    files = os.listdir(dl_dir) if os.path.isdir(dl_dir) else []
    if files:
        print(f"    Downloaded {len(files)} files: {', '.join(files)}")
    check("download creates files", len(files) >= 1, f"got {len(files)}")
else:
    check("download_song skipped (no URL)", True)

cleanup(TMP)

failed = summary()
if __name__ == "__main__":
    raise SystemExit(failed)
