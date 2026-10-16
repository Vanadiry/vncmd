"""--dlink 的下载信息面板

取代了原先的 --url。那个只多输出一个链接，而且折行之后没法复制，
查询串又是两百多字符的鉴权 token，把面板撑成四行没人读。
"""

import pytest
from rich.cells import cell_len

from function.output import FEE_NEED, display_download_detail

NAME = "PPPP (feat. Hatsune Miku, Kasane Teto)"
SONG_ID = 2742965504

READY = {
    # 真实链接去掉查询串有 173 字符，一行放不下，正是要截断的那类
    "url": "http://m704.music.126.net/20261016194005/8182db3769589c367b35dd236251e000d"
    "/jdymusic/obj/wo3DlMOGwrbDjj7DisKw/62331298615/1287/5fb4/4c0b"
    "/0e2403ed33777cce040157439a4a0da5.flac?vuutv=igLi0OniWM8O4FynXUkgJHgQH06&authSecret=abc",
    "type": "flac",
    "level": "lossless",
    "br": 1848126,
    "sr": 48000,
    "time": 154835,
    "size": 35772329,
    "md5": "0e2403ed33777cce040157439a4a0da5",
    "expi": 1200,
    "fee": 1,
    "payed": 1,
}

DENIED = {"fee": 1, "payed": 0, "code": -110}

SONG = {
    "id": SONG_ID,
    "title": NAME,
    "artist": "TAK, 初音ミク, 重音テト",
    "album": "PPPP",
    "cover": "https://p1.music.126.net/x.jpg",
    "publish_time": "2025-09-17 00:00:00",
    # api 层给的是排好的字符串，不是毫秒数
    "duration": "2:34",
}


def show(capsys, info, name=NAME, song_id=SONG_ID):
    display_download_detail(song_id, name, info)
    return capsys.readouterr().out


def row_of(out: str, label: str) -> str:
    """取面板里某个键值对的整行，断言值时用得着"""
    rows = [stripped for ln in out.splitlines() if (stripped := ln.strip(" │"))]
    rows = [ln for ln in rows if ln.startswith(label)]
    assert len(rows) == 1, f"没有恰好一行 {label}：{rows}"
    return rows[0]


class TestAvailable:
    def test_面板标题带ID(self, capsys):
        assert f"下载信息 - {SONG_ID}" in show(capsys, READY)

    def test_关键字段都在(self, capsys):
        out = show(capsys, READY)
        for label in (
            "标题",
            "类型",
            "音质",
            "比特率",
            "采样率",
            "时长",
            "大小",
            "MD5",
            "权限",
        ):
            assert label in out, f"缺 {label}"

    def test_字段值正确(self, capsys):
        out = show(capsys, READY)
        assert "flac" in out
        assert "1848 kbps (1848126 bps)" in out
        assert "48000 Hz" in out
        assert "2:34" in out, "154835 毫秒应显示为 2:34"
        assert "0e2403ed33777cce040157439a4a0da5" in out
        assert "20 分钟内有效" in out

    def test_大小带上易读单位(self, capsys):
        assert "34.1 MB (35772329 字节)" in show(capsys, READY)

    def test_音质用中文(self, capsys):
        """level 是英文字段名，直接嵌进提示里中英文硬拼"""
        out = show(capsys, READY)
        assert "无损音质" in out
        assert "lossless" not in out

    def test_允许访问不附原因(self, capsys):
        """下得了的人不关心有没有买过，那行写了也是噪声

        查整行而不是查某几个词：只查「单曲购买」的话，塞个 fee=1 就绕过去了。
        """
        row = row_of(show(capsys, READY), "权限")
        assert row == "权限    允许访问"

    def test_有效期移到标题(self, capsys):
        """1200 秒换算成 20 分钟写在标题，面板里不再单列一行"""
        out = show(capsys, READY)
        assert f"下载信息 - {SONG_ID} - 20 分钟内有效" in out
        assert "有效期" not in out


class TestName:
    def test_标题在面板里(self, capsys):
        """面板外不留别的内容，选哪一块都清楚"""
        out = show(capsys, READY)
        assert "标题" in out
        assert NAME in out


class TestUrl:
    def test_整条链接都在(self, capsys):
        """面板里那行折了字之后既选不中也点不开"""
        assert READY["url"] in show(capsys, READY)

    def test_链接在面板外面(self, capsys):
        out = show(capsys, READY)
        first = out.splitlines()[0]
        assert "http" in first, "链接得单独一行印在面板外，才能整条选中"
        assert "│" not in first, "带边框就不好整段选中"

    def test_链接不出现两次(self, capsys):
        out = show(capsys, READY)
        assert out.count("http") == 1

    def test_取不到链接时什么都不印(self, capsys):
        """没有链接就没有那行，别留个空的 URL 行"""
        out = show(capsys, DENIED)
        assert "http" not in out
        assert "URL" not in out


class TestDenied:
    def test_取不到链接时照样输出(self, capsys):
        out = show(capsys, DENIED)
        assert f"下载信息 - {SONG_ID}" in out
        assert "标题" in out

    def test_权限行附上原因(self, capsys):
        """fee=1 本身就说明了原因，不必再查账号信息"""
        out = show(capsys, DENIED)
        assert "不允许访问" in out
        assert "需要会员权限或单独购买该曲目" in out

    def test_空字段不留空行(self, capsys):
        out = show(capsys, DENIED)
        assert "MD5" not in out
        assert "大小" not in out
        assert "采样率" not in out

    def test_失败时不报购买状态(self, capsys):
        """下不了的时候说「要买」比说「没买」有用，前者才可操作"""
        assert "未购买" not in show(capsys, DENIED)

    def test_失败时也给有效期(self, capsys):
        """取不到链接不代表没有链接，标题仍应带上有效期"""
        assert "20 分钟内有效" in show(capsys, {**DENIED, "expi": 1200})

    def test_免费曲目的失败不乱归因(self, capsys):
        """fee=8 本该能下，下不了多半是别的原因，不能说成要买"""
        out = show(capsys, {"fee": 8, "payed": 0})
        assert "需要会员权限" not in out
        assert "不允许访问" in out

    def test_未知fee给中性说法(self, capsys):
        out = show(capsys, {"fee": 99})
        assert "不允许访问" in out
        assert "需要会员权限" not in out


class TestNeedTable:
    def test_需要购买的两档才有原因(self):
        assert set(FEE_NEED) == {1, 4}

    def test_免费档不在原因表里(self):
        assert 8 not in FEE_NEED


class TestFormatters:
    def test_不足一兆只报字节(self):
        from function.output import _fmt_size

        assert _fmt_size(500) == "500 字节"

    def test_零字节返回空(self):
        """空值会被过滤掉，不能留下「0 字节」这种误导性的显示"""
        from function.output import _fmt_size

        assert _fmt_size(0) == ""

    def test_超过一兆带小数(self):
        from function.output import _fmt_size

        assert "34.1 MB" in _fmt_size(35772329)

    def test_不足一分钟仍报秒(self):
        from function.output import _fmt_validity

        assert _fmt_validity(45) == "45 秒内有效"

    def test_整分钟不带小数(self):
        from function.output import _fmt_validity

        assert _fmt_validity(1200) == "20 分钟内有效"

    def test_零秒返回空(self):
        from function.output import _fmt_validity

        assert _fmt_validity(0) == ""

    def test_比特率带原始值(self):
        from function.output import _fmt_kbps

        assert _fmt_kbps(320000) == "320 kbps (320000 bps)"

    def test_比特率为零返回空(self):
        from function.output import _fmt_kbps

        assert _fmt_kbps(0) == ""


class TestParser:
    def _parse(self, argv):
        from vncmd import build_parser

        return build_parser().parse_args(argv)

    def test_dlink可用(self):
        assert self._parse(["song", "123", "--dlink"]).dlink is True

    def test_短选项仍在(self):
        assert self._parse(["song", "123", "-u"]).dlink is True

    def test_默认关闭(self):
        assert self._parse(["song", "123"]).dlink is False

    def test_旧选项已移除(self):
        """--url 折行后没法复制，换成面板"""
        with pytest.raises(SystemExit):
            self._parse(["song", "123", "--url"])


class TestSongCommand:
    """真跑一遍 cmd_song，看它在 --dlink 下吐出什么

    只测 display 函数不够：详情卡打不打、艺术家给不给，都在命令里决定。
    """

    def _run(self, monkeypatch, capsys, dlink):
        from function import commands
        from vncmd import build_parser

        monkeypatch.setattr(commands, "get_song_details", lambda _id, *_a, **_k: SONG)
        monkeypatch.setattr(commands, "fetch_player_url", lambda _id, **_k: READY)
        monkeypatch.setattr(commands, "get_lyrics", lambda _id, **_k: {})

        argv = ["song", str(SONG_ID)] + (["--dlink"] if dlink else [])
        commands.cmd_song(build_parser().parse_args(argv))
        return capsys.readouterr().out

    def test_dlink下不打详情卡(self, monkeypatch, capsys):
        out = self._run(monkeypatch, capsys, dlink=True)
        assert "曲目详情" not in out
        assert "发行时间" not in out

    def test_dlink下带标题不带给艺术家(self, monkeypatch, capsys):
        """辨认靠标题就够，艺术家一长面板就散了"""
        out = self._run(monkeypatch, capsys, dlink=True)
        assert NAME in out
        assert "重音テト" not in out

    def test_不加dlink时详情卡照旧(self, monkeypatch, capsys):
        """--dlink 只是省掉详情卡，不是把它一并删了"""
        out = self._run(monkeypatch, capsys, dlink=False)
        assert "曲目详情" in out
        assert "发行时间" in out


class TestRawFetch:
    def test_失败响应也带fee(self, monkeypatch):
        """判断为什么下不了不必再发一次请求"""
        from function import api

        class Resp:
            @staticmethod
            def json():
                return {"code": 200, "data": [{"fee": 1, "payed": 0, "code": -110}]}

        class Session:
            def get(self, *_a, **_k):
                return Resp()

        monkeypatch.setattr(api, "_get_session", lambda: Session())
        got = api.fetch_player_url(SONG_ID)
        assert got["fee"] == 1
        assert got["payed"] == 0
        assert "url" not in got

    def test_空响应不炸(self, monkeypatch):
        from function import api

        class Resp:
            @staticmethod
            def json():
                return {"code": 200, "data": []}

        class Session:
            def get(self, *_a, **_k):
                return Resp()

        monkeypatch.setattr(api, "_get_session", lambda: Session())
        assert api.fetch_player_url(1) == {}


def test_链接没有超出终端宽度地被裁掉(capsys):
    """链接单独一行印出来，不该被面板的宽度算进去截断"""
    out = show(capsys, READY)
    first = out.splitlines()[0]
    assert first == READY["url"]
    assert cell_len(first) > 80, "样本 URL 放不进一行才有意义"
