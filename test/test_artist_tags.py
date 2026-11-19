"""艺术家数组与 artist_mode 的传递"""

from vncmd import downloader
from vncmd.net.api import _normalize_song


def test_规范化保留艺术家数组():
    song = {"id": 1, "name": "T", "ar": [{"name": "A"}, {"name": "B"}], "al": {}}

    got = _normalize_song(dict(song))

    assert got["artist"] == "A, B"
    assert got["artists"] == ["A", "B"]


def test_补详情复制艺术家数组(monkeypatch):
    track = {"id": 1, "title": "T", "artist": "A, B"}
    monkeypatch.setattr(
        downloader,
        "get_song_details_many",
        lambda ids: {1: {"id": 1, "artists": ["A", "B"]}},
    )

    downloader._complete_track_details([track])

    assert track["artists"] == ["A", "B"]


def test_补详情的空艺术家列表不覆盖(monkeypatch):
    track = {"id": 1, "title": "T", "artist": "A, B", "artists": ["A", "B"]}
    monkeypatch.setattr(
        downloader,
        "get_song_details_many",
        lambda ids: {1: {"id": 1, "artists": []}},
    )

    downloader._complete_track_details([track])

    assert track["artists"] == ["A", "B"]


def test_multi模式才交给embed(monkeypatch):
    monkeypatch.setattr(downloader, "get_artist_mode", lambda: "multi")
    assert downloader._artists_for_embed(["A", "B"]) == ["A", "B"]

    monkeypatch.setattr(downloader, "get_artist_mode", lambda: "single")
    assert downloader._artists_for_embed(["A", "B"]) is None
