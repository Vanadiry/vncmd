import pytest
from function.api import get_song_details, get_playlist_details, search
from function.downloader import download_song


@pytest.mark.network
class TestNonexistentResources:
    def test_nonexistent_song_raises_valueerror(self):
        with pytest.raises(ValueError, match="not found"):
            get_song_details(99999999999)

    def test_nonexistent_playlist_raises_valueerror(self):
        with pytest.raises(ValueError, match="not found"):
            get_playlist_details(99999999999)

    def test_bad_url_download_fails(self, temp_dir):
        ok, msg, _ = download_song(
            song_url="http://invalid.example/never.mp3",
            song_title="Test", song_artist="Test", song_album="Test",
            song_id="0", cover_url="", lyrics_api_url="", publish_time="",
            download_dir=temp_dir,
        )
        assert not ok

    def test_nonsense_search_doesnt_crash(self):
        result = search("xyzabc123def456ghi789jkl", limit=5)
        assert "songs" in result
