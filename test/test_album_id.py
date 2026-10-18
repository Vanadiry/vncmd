"""曲目详情面板的专辑 ID

接口的 song/detail 里 album.id 是现成的，能直接拿去查专辑详情。
没有专辑条目的曲目接口给的是 id 为 0，那不是真的专辑，显示时要当没有。

顺带钉住一件踩到的事：字段值为 null 时不能把 None 传到面板，
rich 的 Text.append 只收 str 与 Text，收到 None 直接抛 TypeError。
"""

import pytest

from vncmd.api import _normalize_song, _text
from vncmd.output import display_song_detail

# 接口对有专辑的曲目返回的样子
WITH_ALBUM = {
    "id": 2742965504,
    "name": "PPPP (feat. Hatsune Miku, Kasane Teto)",
    "artists": [{"name": "TAK"}],
    "duration": 154835,
    "album": {
        "name": "PPPP",
        "id": 283881237,
        "picUrl": "https://p1.music.126.net/x.jpg",
        "publishTime": 1758076800000,
    },
}

# 接口对没有专辑条目的曲目返回的样子：整块是空壳
WITHOUT_ALBUM = {
    "id": 1301714740,
    "name": None,
    "artists": [{"name": "", "id": 0}],
    "duration": 0,
    "album": {"name": None, "id": 0, "picUrl": None, "publishTime": 0},
}


def _show(capsys, raw):
    display_song_detail(_normalize_song(dict(raw)))
    return capsys.readouterr().out


class TestAlbumId:
    def test_专辑后面带出ID(self, capsys):
        out = _show(capsys, WITH_ALBUM)
        assert "PPPP（283881237）" in out

    def test_ID用括号包住(self, capsys):
        """点号隔开会被当成专辑名的一部分，看不出括号里那个是编号"""
        out = _show(capsys, WITH_ALBUM)
        assert "PPPP · 283881237" not in out
        assert "PPPP283881237" not in out

    def test_没有专辑时不印零(self, capsys):
        """接口给 id 为 0，那不是真的专辑，印个 0 出去会让人以为有个 0 号专辑"""
        out = _show(capsys, WITHOUT_ALBUM)
        assert "（0）" not in out
        assert "专辑" in out

    def test_专辑为空时不留空括号(self, capsys):
        out = _show(capsys, WITHOUT_ALBUM)
        assert "（）" not in out

    def test_旧缓存里的None不会崩(self, capsys):
        """改动之前写进缓存的专辑名是 None，面板收到 None 会抛 TypeError"""
        song = _normalize_song(dict(WITH_ALBUM))
        song["album"] = None
        song["cover"] = None
        display_song_detail(song)
        assert capsys.readouterr().out

    def test_专辑为None且没有ID时不会崩(self, capsys):
        """这一组才会真的炸：album 为 None 且 album_id 为 0，
        值原样进了面板；有 ID 时拼成 f 字符串，反而碰不到"""
        song = _normalize_song(dict(WITH_ALBUM))
        song["album"] = None
        song["album_id"] = 0
        display_song_detail(song)
        assert capsys.readouterr().out


class TestNullFields:
    @pytest.mark.parametrize("field", ["title", "album", "cover", "duration"])
    def test_单个字段为null不崩(self, capsys, field):
        song = _normalize_song(dict(WITH_ALBUM))
        song[field] = None
        display_song_detail(song)
        assert capsys.readouterr().out

    def test_整首都是空壳也不崩(self, capsys):
        """接口对有地区限制的曲目返回 name 为 null、duration 为 0 的空壳"""
        out = _show(capsys, WITHOUT_ALBUM)
        assert "曲目详情 - 1301714740" in out

    def test_归一化后是字符串(self):
        got = _normalize_song(dict(WITHOUT_ALBUM))
        for field in ("title", "album", "cover", "duration"):
            assert isinstance(got[field], str), f"{field} 是 {got[field]!r}"

    def test_正常值不受影响(self):
        got = _normalize_song(dict(WITH_ALBUM))
        assert got["title"] == "PPPP (feat. Hatsune Miku, Kasane Teto)"
        assert got["album"] == "PPPP"
        assert got["album_id"] == 283881237


class TestTextHelper:
    def test_字符串照旧清理(self):
        assert _text("初音ミク") == "初音ミク"

    def test_None变空串(self):
        assert _text(None) == ""

    def test_数字变空串而不是字符串(self):
        """0 是占位不是内容，变出「0」反而会显示一个假的专辑名"""
        assert _text(0) == ""
