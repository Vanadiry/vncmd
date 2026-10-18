"""填充字符会把表格竖线错开

U+3164 HANGUL FILLER 看着是空白，Unicode 标它为 Wide，终端按宽渲染；
但 rich 的 cell_len 按零宽算。表格按 cell_len 分列宽、终端按真实宽度画边框，
差多少，后面所有行就错开多少。
"""

import pytest
from rich.cells import cell_len

from vncmd.net.api import _clean, _normalize_song

FILLER = "ㅤ"


class TestBlankFiller:
    def test_填充字符被清掉(self):
        assert _clean(FILLER * 2) == ""

    def test_夹在文字中间也清掉(self):
        assert _clean(f"前{FILLER}后") == "前后"

    def test_真零宽字符照旧清(self):
        """原有行为不能因为加了填充字符就退化"""
        assert _clean("Zero\u200bWidth") == "ZeroWidth"
        assert _clean("﻿BOM") == "BOM"

    def test_正常专辑名不受影响(self):
        assert _clean("Unhappy Refrain") == "Unhappy Refrain"

    def test_韩文字母不能误伤(self):
        """U+3161 到 U+3163 是真字母，只清 FILLER 这一个"""
        assert _clean("ㅁㅂㅃ") == "ㅁㅂㅃ"
        assert _clean("안녕하세요") == "안녕하세요"

    def test_盲文空白未被清理(self):
        """U+2800 同类问题但本次不处理，这里钉住现状免得被顺手扩大"""
        assert _clean("⠀") == "⠀"

    def test_非字符串原样返回(self):
        assert _clean(None) is None
        assert _clean(123) == 123

    def test_空串(self):
        assert _clean("") == ""


class TestNormalizationReachesFiller:
    """四条取歌路径都得清，否则有一条漏网就照样错位"""

    @pytest.fixture
    def raw_song(self):
        return {
            "id": 3316857125,
            "name": "我的悲伤是水做的",
            "ar": [{"name": "洛天依"}],
            "al": {"name": FILLER * 2, "picUrl": "http://x/c.jpg"},
        }

    def test_单曲详情路径(self, raw_song):
        out = _normalize_song(dict(raw_song))
        assert out["album"] == ""
        assert out["title"] == "我的悲伤是水做的"

    def test_专辑名里还夹着标题与艺术家时也清(self):
        out = _normalize_song(
            {
                "id": 1,
                "name": f"歌{FILLER}名",
                "ar": [{"name": f"人{FILLER}物"}],
                "al": {"name": FILLER, "picUrl": ""},
            }
        )
        assert out["title"] == "歌名"
        assert out["artist"] == "人物"
        assert out["album"] == ""

    def test_清理后宽度不再错位(self):
        """这才是真正要修的东西：宽度测量与终端渲染要对得上"""
        assert cell_len(_clean(FILLER * 2)) == 0


def test_真实问题曲目的专辑名已可清空():
    """3316857125 的专辑名是两个 HANGUL FILLER，清理后应为空串"""
    assert _clean(FILLER * 2) == ""
