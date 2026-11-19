"""艺术家数组与 artist_mode 的传递"""

from vncmd import downloader
from vncmd.core.artists import join_artists
from vncmd.net.api import _normalize_song


def test_公共拼接规则():
    assert join_artists(["A", "B"]) == "A, B"
    assert join_artists([]) == ""
    assert join_artists(None) == ""
    assert join_artists("A, B") == "A, B"


def test_规范化保留艺术家数组():
    song = {"id": 1, "name": "T", "ar": [{"name": "A"}, {"name": "B"}], "al": {}}

    got = _normalize_song(dict(song))

    assert "artist" not in got
    assert got["artists"] == ["A", "B"]


def test_补详情复制艺术家数组(monkeypatch):
    track = {"id": 1, "title": "T"}
    monkeypatch.setattr(
        downloader,
        "get_song_details_many",
        lambda ids, **_kwargs: {1: {"id": 1, "artists": ["A", "B"]}},
    )

    downloader._complete_track_details([track])

    assert track["artists"] == ["A", "B"]


def test_补详情强制绕过缓存(monkeypatch):
    seen = {}

    def fake(ids, **kwargs):
        seen.update(kwargs)
        return {}

    monkeypatch.setattr(downloader, "get_song_details_many", fake)

    downloader._complete_track_details(
        [
            {
                "id": 1,
                "title": "T",
                "album": "A",
                "cover": "c",
                "track_no": 1,
                "cd_no": 1,
            }
        ]
    )

    assert seen["use_cache"] is False


def test_补详情的空艺术家列表不覆盖(monkeypatch):
    track = {"id": 1, "title": "T", "artists": ["A", "B"]}
    monkeypatch.setattr(
        downloader,
        "get_song_details_many",
        lambda ids, **_kwargs: {1: {"id": 1, "artists": []}},
    )

    downloader._complete_track_details([track])

    assert track["artists"] == ["A", "B"]
