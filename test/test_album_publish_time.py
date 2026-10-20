"""专辑曲目的发行日优先级"""

from vncmd.net import api


class Resp:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class Session:
    def __init__(self, data):
        self.data = data

    def get(self, url, **_kwargs):
        assert "/api/v1/album/" in url
        return Resp(self.data)


def fake(monkeypatch, data):
    session = Session(data)
    monkeypatch.setattr(api, "_get_session", lambda: session)
    return session


def album(*songs, publish_time=1314864000000):
    return {
        "album": {
            "id": 1,
            "name": "专",
            "picUrl": "c",
            "publishTime": publish_time,
            "size": len(songs),
        },
        "songs": list(songs),
    }


def song(sid=1, publish_time=None):
    s = {
        "id": sid,
        "name": "歌",
        "ar": [{"name": "人"}],
        "dt": 1000,
    }
    if publish_time is not None:
        s["publishTime"] = publish_time
    return s


def test_歌曲日优先于专辑日(monkeypatch):
    fake(monkeypatch, album(song(publish_time=1609459200000)))

    got = api.get_album_details(1)

    assert got["tracks"][0]["publish_time"] == "2021-01-01 08:00:00"


def test_歌曲日空时用专辑日(monkeypatch):
    fake(monkeypatch, album(song()))

    got = api.get_album_details(1)

    assert got["tracks"][0]["publish_time"] == "2011-09-01 16:00:00"


def test_歌曲日为0时用专辑日(monkeypatch):
    fake(monkeypatch, album(song(publish_time=0)))

    got = api.get_album_details(1)

    assert got["tracks"][0]["publish_time"] == "2011-09-01 16:00:00"


def test_两者都为0时留空(monkeypatch):
    fake(monkeypatch, album(song(publish_time=0), publish_time=0))

    got = api.get_album_details(1)

    assert got["tracks"][0]["publish_time"] == ""
