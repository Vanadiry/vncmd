"""--count 与 --offset 的分页规则"""

import argparse
import unittest.mock

import pytest
from rich.console import Console

from vncmd import commands
from vncmd.core import output as output_mod


def tracks(n, start=1):
    return [
        {
            "id": i,
            "title": f"曲目{i}",
            "artist": "A",
            "album": "B",
            "cover": "",
            "publish_time": "",
            "duration": "3:00",
        }
        for i in range(start, start + n)
    ]


def playlist(n, track_count=None):
    return {
        "id": 999,
        "name": "某歌单",
        "creator": "某人",
        "cover": "",
        "track_count": n if track_count is None else track_count,
        "tracks": tracks(n),
        "removed_tracks": [],
    }


@pytest.fixture
def rendered(monkeypatch):
    """渲染 output 的面板并返回纯文本，rich 宽度固定为 160，避免折行影响断言"""

    def _render(fn):
        console = Console(width=160)
        monkeypatch.setattr(output_mod, "console", console)
        with console.capture() as cap:
            fn()
        return cap.get()

    return _render


def indexes(text):
    """取表格 # 列的那些数，不写死列宽，序号列宽随位数变化"""
    out = []
    for line in text.splitlines():
        if not line.startswith("│"):
            continue
        cells = [c.strip() for c in line.strip("│").split("│")]
        if cells and cells[0].isdigit():
            out.append(int(cells[0]))
    return out


class Test序号是绝对的:
    def test_不给offset时从一开始(self, rendered):
        text = rendered(lambda: output_mod.display_playlist(playlist(30), max_tracks=3))
        assert indexes(text) == [1, 2, 3]

    def test_给了offset时接着数(self, rendered):
        """面板只显示 3 首时，相对序号每页都从 1 开始，用户分不清看到第几首"""
        text = rendered(
            lambda: output_mod.display_playlist(playlist(300), max_tracks=3, offset=100)
        )
        assert indexes(text) == [101, 102, 103]

    def test_搜索表也用绝对序号(self, rendered):
        text = rendered(
            lambda: output_mod.display_search_results("q", tracks(3), 300, offset=200)
        )
        assert indexes(text) == [201, 202, 203]

    def test_专辑表也用绝对序号(self, rendered):
        al = {
            "id": 7,
            "name": "叶惠美",
            "artist": "周杰伦",
            "cover": "",
            "track_count": 20,
            "tracks": tracks(20),
        }
        text = rendered(lambda: output_mod.display_album(al, max_tracks=3, offset=8))
        assert indexes(text) == [9, 10, 11]


class Test标题的区间:
    def test_不给offset也给区间(self, rendered):
        text = rendered(
            lambda: output_mod.display_playlist(playlist(298), max_tracks=10)
        )
        assert "1-10/298" in text

    def test_给了offset显示那一段(self, rendered):
        text = rendered(
            lambda: output_mod.display_playlist(
                playlist(298), max_tracks=10, offset=100
            )
        )
        assert "101-110/298" in text

    def test_末尾不足照常显示(self, rendered):
        """293 加 5 在 298 首里为 294-298，不足 5 首不算异常"""
        text = rendered(
            lambda: output_mod.display_playlist(playlist(298), max_tracks=5, offset=293)
        )
        assert "294-298/298" in text
        assert "超出范围" not in text

    def test_翻过头说清楚(self, rendered):
        text = rendered(
            lambda: output_mod.display_playlist(
                playlist(298), max_tracks=10, offset=300
            )
        )
        assert "超出范围（共 298 首）" in text

    def test_分母是可切片的数量而不是接口声明的总数(self, rendered):
        """拿 track_count 当分母等于承诺 100 首而实际只有 20 首，翻到第 21 首为空白"""
        text = rendered(
            lambda: output_mod.display_playlist(
                playlist(20, track_count=100), max_tracks=10
            )
        )
        assert "1-10/20" in text
        assert "/100" not in text

    def test_专辑也带区间(self, rendered):
        al = {
            "id": 7,
            "name": "叶惠美",
            "artist": "周杰伦",
            "cover": "",
            "track_count": 12,
            "tracks": tracks(12),
        }
        text = rendered(lambda: output_mod.display_album(al, max_tracks=4, offset=8))
        assert "9-12/12" in text

    def test_面板上不再有曲目数那一行(self, rendered):
        """区间已经带了总数，两处都写就是同一屏两个数"""
        text = rendered(lambda: output_mod.display_playlist(playlist(30), max_tracks=3))
        assert "曲目数" not in text

    def test_那行未显示的提示整行没了(self, monkeypatch, capsys):
        """那行走 info() 进 stderr，rendered 夹具只换 output.console，用它断言会恒真"""
        monkeypatch.setattr(output_mod, "console", Console(width=160, stderr=True))
        output_mod.display_playlist(playlist(20, track_count=100), max_tracks=10)
        out, err = capsys.readouterr()
        assert "未显示" not in out
        assert "未显示" not in err


class Test切片:
    @pytest.mark.parametrize(
        ("offset", "limit", "want"),
        [
            (0, None, [1, 2, 3, 4, 5]),
            (0, 2, [1, 2]),
            (3, None, [4, 5]),
            (3, 2, [4, 5]),
            (0, 99, [1, 2, 3, 4, 5]),
            (5, 2, []),
            (99, 2, []),
        ],
    )
    def test_slice(self, offset, limit, want):
        got = commands._slice(tracks(5), offset, limit)
        assert [t["id"] for t in got] == want

    def test_limit为0时取到末尾而不是空(self):
        """0 为 falsy，当成没给比当成要 0 条合理"""
        assert len(commands._slice(tracks(5), 1, 0)) == 4


class Test搜索传给接口的条数:
    def _sent(self, **kw):
        base = {"query": "x", "count": None, "offset": 0, "json": False}
        base.update(kw)
        ns = argparse.Namespace(**base)
        with unittest.mock.patch.object(
            commands, "search", return_value={"songs": [], "total": 0}
        ) as fake:
            commands.cmd_search(ns)
        return fake.call_args.kwargs

    def test_面板默认十条(self):
        assert self._sent()["limit"] == 10

    def test_json要全量就是接口上限(self):
        assert self._sent(json=True)["limit"] == 100

    def test_显式给了就用给的(self):
        assert self._sent(count=7, json=True)["limit"] == 7

    def test_offset原样交给接口(self):
        """本地不能再切一刀，那样 offset 会被数两遍"""
        assert self._sent(offset=300)["offset"] == 300


class Test下载也吃切片:
    def test_offset与limit都传下去(self, monkeypatch):
        ns = argparse.Namespace(
            id=1,
            count=5,
            offset=100,
            dlink=False,
            download=True,
            json=False,
            quality=None,
            output=None,
            check=None,
            curl=None,
        )
        monkeypatch.setattr(commands, "get_playlist_details", lambda _i: playlist(30))
        with unittest.mock.patch.object(commands, "download_song_batch") as fake:
            commands.cmd_playlist(ns)
        assert fake.call_args.kwargs["limit"] == 5
        assert fake.call_args.kwargs["offset"] == 100

    def test_切片只动本次下的不动断点(self):
        """断点记全量、只截断本次要下的部分
        改成任务级会让全量下过之后的 -n 1 删掉其余曲目
        """
        from vncmd.session import _select_batch

        dl = tracks(20)
        selected, offset = _select_batch(dl, 3, 5)
        assert [t["id"] for t in selected] == [4, 5, 6, 7, 8]
        assert offset == 3


class Test下载侧的切片:
    @pytest.mark.parametrize(
        ("offset", "limit", "want"),
        [
            (0, None, [1, 2, 3]),
            (0, 2, [1, 2]),
            (2, None, [3]),
            (2, 99, [3]),
            (3, None, []),
        ],
    )
    def test_切片(self, offset, limit, want):
        from vncmd.session import _select_batch

        selected, _ = _select_batch(tracks(3), offset, limit)
        assert [t["id"] for t in selected] == want
