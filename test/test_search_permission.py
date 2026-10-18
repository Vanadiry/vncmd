"""搜索表的权限列

列只在结果里真出现下不了或看不出来的曲目时才占位。搜索表已经挤到标题和艺术家
都在截断，能不占地方就不占。用符号而不是文字，一格宽度摆得下。
"""

from vncmd.api import permission_verdict
from vncmd.output import display_search_results

NO_VIP = {"logged_in": True, "vip": False, "vip_type": 0}
VIP = {"logged_in": True, "vip": True, "vip_type": 11}

# 判定为 True 是下不了，False 是能下，None 是看不出来
BLOCK_ALL = [True, False, None]


def song(sid, fee):
    return {
        "id": sid,
        "title": f"歌{sid}",
        "artist": "甲",
        "album": "乙",
        "duration": "1:00",
        "fee": fee,
    }


def render(capsys, songs, account):
    display_search_results(
        "q", songs, len(songs), [permission_verdict(s, account) for s in songs]
    )
    return capsys.readouterr().out


class TestVerdict:
    def test_无会员的单曲购买下不了(self):
        """实测无会员时 fee=1 的 205 首一首都下不了"""
        assert permission_verdict(song(1, 1), NO_VIP) is True

    def test_无会员的专辑购买下不了(self):
        assert permission_verdict(song(1, 4), NO_VIP) is True

    def test_免费的两档无会员也能下(self):
        assert permission_verdict(song(1, 0), NO_VIP) is False
        assert permission_verdict(song(1, 8), NO_VIP) is False

    def test_有会员一律给能下(self):
        """实测有会员时 fee=1 的 205 首全部能下；
        fee=4 要看专辑买没买过，接口不给，没法证伪就不断言"""
        for fee in (0, 1, 4, 8):
            assert permission_verdict(song(1, fee), VIP) is False, f"fee={fee}"

    def test_查不出账号状态就说看不出来(self):
        """标成能下或下不了都是在编"""
        assert permission_verdict(song(1, 1), None) is None

    def test_缺fee就说看不出来(self):
        """搜索接口哪天不给这个字段时，别把结论钉死"""
        assert permission_verdict({"id": 1, "title": "x"}, NO_VIP) is None

    def test_未登录等同于无会员(self):
        """实测两者在下载上表现一致"""
        anon = {"logged_in": False, "vip": False, "vip_type": 0}
        assert permission_verdict(song(1, 1), anon) is True


class TestColumn:
    def test_有下不了的就出现(self, capsys):
        out = render(capsys, [song(1, 8), song(2, 1)], NO_VIP)
        assert "权限" in out
        assert "✗" in out
        assert "✓" in out

    def test_有看不清楚的也出现(self, capsys):
        """问号同样是用户需要知道的事，不该被当成没有这一列的理由"""
        display_search_results("q", [song(1, 8)], 1, [None])
        out = capsys.readouterr().out
        assert "权限" in out
        assert "?" in out

    def test_全能下就不出现(self, capsys):
        """VIP 用户搜出来的歌往往全能下，这一列是白占地方"""
        out = render(capsys, [song(1, 8), song(2, 1)], VIP)
        assert "权限" not in out
        assert "✓" not in out
        assert "✗" not in out

    def test_不给判定就不出现(self, capsys):
        """歌单与专辑视图没有 fee，硬塞一列全是猜的"""
        display_search_results(
            "q",
            [{"id": 1, "title": "x", "artist": "a", "album": "b", "duration": "1:00"}],
            1,
        )
        assert "权限" not in capsys.readouterr().out

    def test_全问号也出现(self, capsys):
        """查不出账号状态时整列都是问号，仍比让用户猜好"""
        out = render(capsys, [song(1, 1), song(2, 1)], None)
        assert "?" in out
        assert "✗" not in out, "问号不能混进叉号里"

    def test_标记跟着行走(self, capsys):
        """第几行标错就是信息错误，比没有这一列更糟"""
        rows = _rows(render(capsys, [song(1, 1), song(2, 8)], NO_VIP))
        assert len(rows) == 2, f"表格只渲染出 {len(rows)} 行"
        assert rows[0][-2].strip() == "✗"
        assert rows[1][-2].strip() == "✓"

    def test_三态各就各位(self, capsys):
        songs = [
            song(1, 8),
            song(2, 1),
            {"id": 3, "title": "c", "artist": "丙", "album": "c", "duration": "1:00"},
        ]
        rows = _rows(render(capsys, songs, NO_VIP))
        assert [r[-2].strip() for r in rows] == ["✓", "✗", "?"]

    def test_短了不显示也不崩(self, capsys):
        """短了会 IndexError"""
        display_search_results("q", [song(1, 8), song(2, 1)], 2, [True])
        assert "权限" not in capsys.readouterr().out

    def test_长了不显示也不错位(self, capsys):
        """长了会让整列从第一行起就全错"""
        display_search_results("q", [song(1, 8)], 1, [True, True, True])
        assert "权限" not in capsys.readouterr().out

    def test_用文字会把表格撑宽(self, capsys):
        """「无权限」四个字要四格，符号只占一格，标题能多拿三格"""
        display_search_results("q", [song(1, 8), song(2, 1)], 2, [True, False])
        out = capsys.readouterr().out
        assert "可下" not in out
        assert "无权限" not in out


def _rows(out):
    """把表格按列切开，取每行去掉边框后的各格"""
    rows = []
    for line in out.splitlines():
        if "│" not in line:
            continue
        cells = [c for c in line.split("│") if c.strip()]
        if len(cells) >= 4 and cells[0].strip().isdigit():
            rows.append(cells)
    return rows


class TestMarks:
    def test_三态各有符号(self):
        from vncmd.output import _PERM_MARKS

        assert [m for m, _ in (_PERM_MARKS[b] for b in BLOCK_ALL)] == ["✗", "✓", "?"]

    def test_符号都占一格(self):
        """宽符号会把标题再挤掉几格，那这一列就白加了"""
        from rich.cells import cell_len

        from vncmd.output import _PERM_MARKS

        for blocked, (mark, _) in _PERM_MARKS.items():
            assert cell_len(mark) == 1, f"{blocked} 用了 {mark}，占 {cell_len(mark)} 格"

    def test_颜色分得开(self):
        from vncmd.output import _PERM_MARKS

        styles = {style for _, style in _PERM_MARKS.values()}
        assert len(styles) == 3, "三态用同一个颜色就分不出来了"


class TestSearchCarriesFee:
    """search() 必须把 fee 带出来

    少了这一步，判定永远拿到 None，整列一次都不会出现，
    而且不报错、不出声，看着像「这些歌都能下」。
    """

    def _search(self, monkeypatch, raw_songs):
        import vncmd.api as api

        class Resp:
            @staticmethod
            def json():
                return {
                    "code": 200,
                    "result": {"songCount": len(raw_songs), "songs": raw_songs},
                }

        class Session:
            def get(self, *_a, **_k):
                return Resp()

        monkeypatch.setattr(api, "_get_session", lambda: Session())
        return api.search("q")["songs"]

    def _raw(self, fees):
        """按给定的 fee 造接口原始返回，None 表示该字段整个不存在"""
        out = []
        for i, fee in enumerate(fees):
            s = {"id": i, "name": f"歌{i}", "ar": [], "al": {}}
            if fee is not None:
                s["fee"] = fee
            out.append(s)
        return out

    def test_fee原样带出(self, monkeypatch):
        songs = self._search(monkeypatch, self._raw([8, 1, 0, 4]))
        assert [s["fee"] for s in songs] == [8, 1, 0, 4]

    def test_带出的fee能驱动判定(self, monkeypatch):
        """端到端对一遍：接口给了 fee，判定就认得出来"""
        songs = self._search(monkeypatch, self._raw([8, 1]))
        assert [permission_verdict(s, NO_VIP) for s in songs] == [False, True]

    def test_接口不给fee也不炸(self, monkeypatch):
        songs = self._search(monkeypatch, self._raw([None]))
        assert songs[0]["fee"] is None
        assert permission_verdict(songs[0], NO_VIP) is None
