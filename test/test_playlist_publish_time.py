"""歌单曲目的发行日

歌曲日优先，歌曲日与专辑日都空时再用 v0 批量补专辑日。
批量只查空日期的 id，不碰 get_song_details_many，也不写单曲缓存。
"""

import json
from urllib.parse import unquote

from vncmd.net import api


def track(sid, *, track_time=None, album_time=None, name="歌"):
    t = {
        "id": sid,
        "name": name,
        "ar": [{"name": "人"}],
        "al": {"name": "专", "picUrl": "p", "publishTime": album_time},
        "dt": 1000,
    }
    if track_time is not None:
        t["publishTime"] = track_time
    return t


def playlist(*tracks):
    return {
        "playlist": {
            "id": 1,
            "name": "歌单",
            "creator": {"nickname": "人"},
            "coverImgUrl": "c",
            "trackCount": len(tracks),
            "trackIds": [{"id": t["id"]} for t in tracks],
            "tracks": list(tracks),
        }
    }


class Resp:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class Session:
    def __init__(self, pl, details=None):
        self.pl = pl
        self.details = details or []
        self.batch_ids = []
        self.calls = []

    def get(self, url, **_kwargs):
        self.calls.append(url)
        if "/api/v6/playlist/detail/" in url:
            return Resp(self.pl)
        if "/api/song/detail/" in url:
            ids = json.loads(unquote(url.split("ids=", 1)[1]))
            self.batch_ids.extend(ids)
            return Resp({"songs": [d for d in self.details if d["id"] in ids]})
        raise AssertionError(url)


def fake(monkeypatch, pl, details=None):
    session = Session(pl, details)
    monkeypatch.setattr(api, "_get_session", lambda: session)
    return session


def test_曲目日优先于专辑日(monkeypatch):
    pl = playlist(track(1, track_time=1609459200000, album_time=1314864000000))
    session = fake(monkeypatch, pl)

    got = api.get_playlist_details(1)

    assert got["tracks"][0]["publish_time"] == "2021-01-01 08:00:00"
    assert session.batch_ids == []


def test_曲目日空时用专辑日(monkeypatch):
    pl = playlist(track(1, album_time=1314864000000))
    session = fake(monkeypatch, pl)

    got = api.get_playlist_details(1)

    assert got["tracks"][0]["publish_time"] == "2011-09-01 16:00:00"
    assert session.batch_ids == []


def test_曲目日为0时用专辑日(monkeypatch):
    pl = playlist(track(1, track_time=0, album_time=1314864000000))
    session = fake(monkeypatch, pl)

    got = api.get_playlist_details(1)

    assert got["tracks"][0]["publish_time"] == "2011-09-01 16:00:00"
    assert session.batch_ids == []


def test_al为空时不报错(monkeypatch):
    t = track(1)
    t["al"] = None
    details = [{"id": 1, "album": {"publishTime": 1314864000000}}]
    session = fake(monkeypatch, playlist(t), details)

    got = api.get_playlist_details(1)

    assert got["tracks"][0]["album"] == ""
    assert got["tracks"][0]["publish_time"] == "2011-09-01 16:00:00"
    assert session.batch_ids == [1]


def test_只批量查空日期的曲目(monkeypatch):
    pl = playlist(
        track(1, track_time=1609459200000),
        track(2, album_time=1314864000000),
        track(3),
    )
    details = [
        {
            "id": 3,
            "publishTime": 1609459200000,
            "album": {"publishTime": 1314864000000},
        }
    ]
    session = fake(monkeypatch, pl, details)

    got = api.get_playlist_details(1)

    assert session.batch_ids == [3]
    assert [t["publish_time"] for t in got["tracks"]] == [
        "2021-01-01 08:00:00",
        "2011-09-01 16:00:00",
        "2021-01-01 08:00:00",
    ]


def test_批量用专辑日兜底(monkeypatch):
    details = [{"id": 1, "publishTime": 0, "album": {"publishTime": 1314864000000}}]
    session = fake(monkeypatch, playlist(track(1)), details)

    got = api.get_playlist_details(1)

    assert session.batch_ids == [1]
    assert got["tracks"][0]["publish_time"] == "2011-09-01 16:00:00"


def test_批量按100分批(monkeypatch):
    tracks = [track(i) for i in range(1, 151)]
    details = [
        {"id": i, "album": {"publishTime": 1314864000000}} for i in range(1, 151)
    ]
    session = fake(monkeypatch, playlist(*tracks), details)

    api.get_playlist_details(1)

    assert session.batch_ids == list(range(1, 101)) + list(range(101, 151))
    assert len([c for c in session.calls if "/api/song/detail/" in c]) == 2


def test_批量失败时保留空日期(monkeypatch):
    class BadSession(Session):
        def get(self, url, **kwargs):
            if "/api/song/detail/" in url:
                raise RuntimeError("坏了")
            return super().get(url, **kwargs)

    session = BadSession(playlist(track(1)))
    monkeypatch.setattr(api, "_get_session", lambda: session)

    got = api.get_playlist_details(1)

    assert got["tracks"][0]["publish_time"] == ""
