import pytest
from rich.console import Console

from function import output as output_mod
from function.api import _clean

TRACKS = [
    {
        "id": 1,
        "title": "灰色轨迹",
        "artist": "Beyond",
        "album": "华纳廿三周年纪念精选系列",
        "duration": "5:24",
    },
    {
        "id": 2,
        "title": "海阔天空",
        "artist": "Beyond",
        "album": "Beyond 24K Gold 金碟至尊精选",
        "duration": "3:59",
    },
]


@pytest.fixture
def render(monkeypatch):
    """把 output 模块的 console 换成指定宽度的，控制台输出变成可断言的文本"""

    def _render(width, show_album):
        console = Console(width=width)
        monkeypatch.setattr(output_mod, "console", console)
        with console.capture() as cap:
            output_mod._display_track_table(TRACKS, len(TRACKS), show_album=show_album)
        return cap.get().rstrip("\n").split("\n")

    return _render


def test_专辑视图不显示专辑列(render):
    assert "专辑" not in render(160, show_album=False)[1]


def test_搜索视图有专辑列(render):
    assert "专辑" in render(160, show_album=True)[1]


def test_专辑列不折行(render):
    # no_wrap 之前专辑名会折成两三行，行高不齐
    lines = render(100, show_album=True)
    body = [ln for ln in lines[2:-1] if ln.startswith("│")]
    assert len(body) == len(TRACKS), "专辑名折行导致行数变多"


def test_专辑名过长时省略而不是折行(render):
    lines = render(100, show_album=True)
    assert "…" in lines[3], "专辑名应当被省略号截断"


def test_专辑视图行数与搜索视图一致(render):
    assert len(render(100, show_album=False)) == len(render(100, show_album=True))


@pytest.mark.parametrize("cp", ["", "‌", "‍", "⁠", "﻿"])
def test_零宽字符被清除(cp):
    assert _clean(f"B{cp}eyond") == "Beyond"


def test_非字符串原样返回():
    assert _clean(None) is None
    assert _clean(123) == 123


def test_正常文本不受影响():
    assert _clean("Beyond 24K Gold 金碟至尊精选") == "Beyond 24K Gold 金碟至尊精选"
