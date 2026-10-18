import pytest

from test.conftest import as_tz
from vncmd.net.api import _clean, _normalize_song

BASE = {"id": 1, "name": "歌", "duration": 1000}


def _norm(**over):
    return _normalize_song({**BASE, **over})


@pytest.mark.parametrize(
    "over",
    [
        {"al": None},
        {"ar": None, "al": {"name": "专"}},
        {"ar": None, "al": None},
        {"ar": [], "al": []},
    ],
)
def test_字段为null时不崩(over):
    # .get 的默认值只在键缺失时生效，值为 null 时仍返回 None
    r = _norm(**over)
    assert isinstance(r["artist"], str)
    assert isinstance(r["album"], str)
    assert isinstance(r["cover"], str)


def test_al为null时按无专辑处理():
    r = _norm(ar=[{"name": "人"}], al=None)
    assert r["album"] == ""
    assert r["cover"] == ""
    # 统一成 0：接口对真的没有专辑条目的曲目给的就是 id 为 0，
    # 两种「没有」归成同一个值，显示层只要判一次
    assert r["album_id"] == 0
    assert r["publish_time"] == ""


def test_ar为null时按无艺术家处理():
    r = _norm(ar=None, al={"name": "专"})
    assert r["artist"] == ""
    assert r["album"] == "专"


def test_缺键与值为null结果一致():
    assert _norm(al=None)["album"] == _norm()["album"]
    assert _norm(ar=None)["artist"] == _norm()["artist"]


def test_字段齐全时照常取出():
    # 发行时间是 _normalize_song 内部转的，时区必须罩住整个调用而不是只罩断言
    with as_tz("Asia/Shanghai"):
        r = _norm(
            ar=[{"name": "人"}],
            al={"name": "专", "id": 9, "picUrl": "u", "publishTime": 1314864000000},
        )
        assert r["artist"] == "人"
        assert r["album"] == "专"
        assert r["album_id"] == 9
        assert r["cover"] == "u"
        assert r["publish_time"] == "2011-09-01 16:00:00"


def test_零宽字符被清掉():
    r = _norm(ar=[{"name": "B﻿eyond"}], al={"name": "A﻿lbum"})
    assert r["artist"] == "Beyond"
    assert r["album"] == "Album"


def test_clean只处理字符串():
    assert _clean(None) is None
    assert _clean(123) == 123
    assert _clean("正常") == "正常"
