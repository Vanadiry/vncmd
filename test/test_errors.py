import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Error handling tests."""
from test._runner import check, section, summary, reset, cleanup

reset()
TMP = __import__("test._runner", fromlist=["tmp_dir"]).tmp_dir()

section("Error handling")

from function.api import get_song_details, get_playlist_details
from function.downloader import download_song

try:
    get_song_details(99999999999)
    check("non-existent song raises", False)
except ValueError as e:
    check("non-existent song raises ValueError", "not found" in str(e).lower())

try:
    get_playlist_details(99999999999)
    check("non-existent playlist raises", False)
except ValueError as e:
    check("non-existent playlist raises ValueError", "not found" in str(e).lower())

ok, msg, _ = download_song(
    song_url="http://invalid.example/never.mp3",
    song_title="Test",
    song_artist="Test",
    song_album="Test",
    song_id="0",
    cover_url="",
    lyrics_api_url="",
    publish_time="",
    download_dir=TMP,
)
check("bad URL", not ok, f"msg={msg[:50]}")

# Search for nonsense should still return results (API fuzzy matches)
from function.api import search

try:
    result = search("xyzabc123def456ghi789jkl", limit=5)
    check("nonsense search doesn't crash", "songs" in result)
except Exception as e:
    check("nonsense search doesn't crash", False, str(e))

cleanup(TMP)

failed = summary()
if __name__ == "__main__":
    raise SystemExit(failed)
