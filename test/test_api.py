import pytest
from function.api import (
    search,
    get_song_details,
    get_playlist_details,
    get_album_details,
    get_lyrics,
    get_song_url,
)
from test.conftest import SONG_ID, PLAYLIST_ID, ALBUM_ID


@pytest.mark.network
class TestSearch:
    @classmethod
    def setup_class(cls):
        cls.result = search("Beyond", limit=5)

    def test_returns_dict(self):
        assert "songs" in self.result
        assert "total" in self.result

    def test_has_results(self):
        assert len(self.result["songs"]) > 0

    def test_song_has_id(self):
        assert "id" in self.result["songs"][0]

    def test_song_has_title(self):
        assert "title" in self.result["songs"][0]

    def test_song_has_artist(self):
        assert "artist" in self.result["songs"][0]

    def test_song_has_album(self):
        assert "album" in self.result["songs"][0]

    def test_song_has_cover(self):
        assert "cover" in self.result["songs"][0]

    def test_song_has_duration(self):
        assert "duration" in self.result["songs"][0]


@pytest.mark.network
class TestSongDetails:
    @classmethod
    def setup_class(cls):
        cls.song = get_song_details(SONG_ID)

    def test_id_matches(self):
        assert self.song["id"] == SONG_ID

    def test_has_title(self):
        assert bool(self.song["title"])

    def test_has_artist(self):
        assert bool(self.song["artist"])

    def test_has_album(self):
        assert bool(self.song["album"])

    def test_has_publish_time(self):
        assert bool(self.song["publish_time"])

    def test_cover_url(self):
        assert self.song["cover"].startswith("http")

    def test_has_duration(self):
        assert ":" in self.song["duration"]

    def test_cached_identical(self):
        song2 = get_song_details(SONG_ID)
        assert self.song == song2


@pytest.mark.network
class TestPlaylist:
    @classmethod
    def setup_class(cls):
        cls.pl = get_playlist_details(PLAYLIST_ID)

    def test_id_matches(self):
        assert self.pl["id"] == PLAYLIST_ID

    def test_has_name(self):
        assert bool(self.pl["name"])

    def test_has_tracks(self):
        assert len(self.pl["tracks"]) > 0

    def test_track_has_id(self):
        assert "id" in self.pl["tracks"][0]


@pytest.mark.network
class TestAlbum:
    @classmethod
    def setup_class(cls):
        cls.al = get_album_details(ALBUM_ID)

    def test_id_matches(self):
        assert self.al["id"] == ALBUM_ID

    def test_has_name(self):
        assert bool(self.al["name"])

    def test_has_artist(self):
        assert bool(self.al["artist"])

    def test_has_tracks(self):
        assert len(self.al["tracks"]) > 0


@pytest.mark.network
class TestLyrics:
    @classmethod
    def setup_class(cls):
        cls.lyrics = get_lyrics(SONG_ID)

    def test_has_lrc(self):
        assert "lrc" in self.lyrics

    def test_has_tlyric(self):
        assert "tlyric" in self.lyrics

    def test_lrc_has_text(self):
        assert len(self.lyrics["lrc"].get("lyric", "")) > 0

    def test_cached_lyrics_has_lrc(self):
        cached = get_lyrics(SONG_ID)
        assert "lrc" in cached

    def test_cached_lyrics_has_text(self):
        cached = get_lyrics(SONG_ID)
        assert len(cached["lrc"].get("lyric", "")) > 0


@pytest.mark.network
class TestSongUrl:
    def test_url_available(self):
        url = get_song_url(SONG_ID)
        if url:
            assert url.startswith("http")
        else:
            pytest.skip("No stream URL (VIP or rate-limited)")

    def test_with_quality(self):
        url = get_song_url(SONG_ID, quality=320000)
        assert isinstance(url, (str, type(None)))
