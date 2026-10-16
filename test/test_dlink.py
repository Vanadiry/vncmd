"""--dlink 的下载信息面板

取代了原先的 --url。那个只多输出一个链接，而且折行之后没法复制，
查询串又是两百多字符的鉴权 token，把面板撑成四行没人读。
"""

import pytest

from function.output import FEE_LABEL, FEE_NEED, display_download_detail

READY = {
    "url": "http://m804.music.126.net/20261016193257/abc/jdymusic/obj/x/1.flac?vuutv=tok&authSecret=s",
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


def show(capsys, info, song_id=2742965504):
    display_download_detail(song_id, info)
    return capsys.readouterr().out


class TestAvailable:
    def test_面板标题带ID(self, capsys):
        assert "下载信息 - 2742965504" in show(capsys, READY)

    def test_关键字段都在(self, capsys):
        out = show(capsys, READY)
        for label in (
            "URL",
            "类型",
            "音质",
            "比特率",
            "采样率",
            "时长",
            "大小",
            "MD5",
            "有效期",
            "费用",
        ):
            assert label in out, f"缺 {label}"

    def test_字段值正确(self, capsys):
        out = show(capsys, READY)
        assert "flac" in out
        assert "1848126 bps" in out
        assert "48000 Hz" in out
        assert "2:34" in out, "154835 毫秒应显示为 2:34"
        assert "0e2403ed33777cce040157439a4a0da5" in out
        assert "1200 秒" in out

    def test_大小带上易读单位(self, capsys):
        assert "34.1 MB" in show(capsys, READY)

    def test_音质用中文(self, capsys):
        """level 是英文字段名，直接嵌进提示里中英文硬拼"""
        out = show(capsys, READY)
        assert "无损音质" in out
        assert "lossless" not in out

    def test_费用标明是否已购(self, capsys):
        out = show(capsys, READY)
        assert "单曲购买" in out
        assert "已购买" in out

    def test_鉴权参数不展开(self, capsys):
        """token 两百多字符，展开就把面板撑满，没人读它"""
        out = show(capsys, READY)
        assert "authSecret=s" not in out
        assert "鉴权参数" in out

    def test_可用标为是(self, capsys):
        assert "可用" in show(capsys, READY)


class TestDenied:
    def test_取不到链接时照样输出(self, capsys):
        out = show(capsys, DENIED)
        assert "下载信息 - 2742965504" in out
        assert "URL" in out

    def test_给出原因(self, capsys):
        """fee=1 本身就说明了原因，不必再查账号信息"""
        assert "需要会员权限或单独购买该曲目" in show(capsys, DENIED)

    def test_空字段不留空行(self, capsys):
        out = show(capsys, DENIED)
        assert "MD5" not in out
        assert "大小" not in out
        assert "采样率" not in out

    def test_标明未购买(self, capsys):
        assert "未购买" in show(capsys, DENIED)

    def test_免费曲目的失败不乱归因(self, capsys):
        """fee=8 本该能下，下不了多半是别的原因，不能说成要买"""
        out = show(capsys, {"fee": 8, "payed": 0})
        assert "原因" not in out

    def test_未知fee不给原因(self, capsys):
        assert "原因" not in show(capsys, {"fee": 99})


class TestFeeTables:
    def test_四种fee都有中文名(self):
        assert set(FEE_LABEL) == {0, 1, 4, 8}

    def test_需要购买的两档才有原因(self):
        assert set(FEE_NEED) == {1, 4}

    def test_免费档不在原因表里(self):
        assert 8 not in FEE_NEED


class TestByteFormat:
    def test_不足一兆只报字节(self):
        from function.output import _fmt_bytes

        assert _fmt_bytes(500) == "500 字节"

    def test_零字节返回空(self, capsys):
        """空值会被过滤掉，不能留下「0 字节」这种误导性的显示"""
        from function.output import _fmt_bytes

        assert _fmt_bytes(0) == ""

    def test_超过一兆带小数(self):
        from function.output import _fmt_bytes

        assert "34.1 MB" in _fmt_bytes(35772329)


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
        got = api.fetch_player_url(2742965504)
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
