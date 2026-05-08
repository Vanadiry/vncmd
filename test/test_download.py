import os
import pytest
from function.download import fetch_lyrics, fetch_cover
from function.api import get_song_details, get_song_url
from function.downloader import download_song
from test.conftest import SONG_ID


@pytest.mark.network
class TestFetchHelpers:
    def test_fetch_lyrics_returns_strings(self):
        url = f"http://music.163.com/api/song/lyric?os=pc&id={SONG_ID}&lv=-1&tv=1"
        lrc, tlyric = fetch_lyrics(url, "netease")
        assert isinstance(lrc, str)
        assert isinstance(tlyric, str)

    def test_fetch_lyrics_has_content(self):
        url = f"http://music.163.com/api/song/lyric?os=pc&id={SONG_ID}&lv=-1&tv=1"
        lrc, _ = fetch_lyrics(url, "netease")
        assert len(lrc) > 0

    def test_fetch_cover_non_empty(self):
        song = get_song_details(SONG_ID)
        cover = fetch_cover(song["cover"])
        assert isinstance(cover, bytes)
        assert len(cover) > 1000


@pytest.mark.network
@pytest.mark.slow
class TestFullDownload:
    def test_download_song(self, temp_dir):
        song = get_song_details(SONG_ID)
        dl_dir = os.path.join(temp_dir, "dl")
        url = get_song_url(SONG_ID)
        if not url:
            pytest.skip("No stream URL available (VIP or rate-limited)")
        ok, msg, path = download_song(
            song_url=url,
            song_title=song["title"], song_artist=song["artist"],
            song_album=song["album"], song_id=str(song["id"]),
            cover_url=song["cover"],
            lyrics_api_url=f"http://music.163.com/api/song/lyric?os=pc&id={SONG_ID}&lv=-1&tv=1",
            publish_time=song["publish_time"], download_dir=dl_dir,
        )
        assert ok, msg
        files = os.listdir(dl_dir) if os.path.isdir(dl_dir) else []
        assert len(files) >= 1
