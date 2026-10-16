"""下载前的 Cookie 状态提示

探测过四种 Cookie 在 account/get 与 player/url 上的表现：

| Cookie | account | vipType | 请求无损 |
| --- | --- | --- | --- |
| 有会员 | 有 | 11 | lossless |
| 登录但无会员 | 有 | 0 | exhigh |
| 空/失效 | None | — | exhigh |
| 正常但拿不到账号信息 | — | — | — |

要点：这个接口无论登录与否都返回 code=200，看 code 没有意义；
登录但无会员的账号 account 同样存在，会员与否要看 vipType 非零。
"""

import pytest

from function import downloader
from function.api import EXPECTED_LEVEL, LEVEL_LABEL


@pytest.fixture(autouse=True)
def _fresh_flags():
    """这两个提示都是进程内只说一次，每个用例都要重置"""
    downloader._account_notified = False
    downloader._downgrade_notified = False


def _cap(capsys):
    return capsys.readouterr().out


class TestExpectedLevel:
    def test_四档都有对应(self):
        assert set(EXPECTED_LEVEL) == {128000, 192000, 320000, 2147483647}

    def test_最高档对应无损(self):
        """实测只有这一档会因权限不足降级，其余三档有无会员一致"""
        assert EXPECTED_LEVEL[2147483647] == "lossless"
        assert EXPECTED_LEVEL[320000] == "exhigh"

    def test_未知码不猜(self):
        assert EXPECTED_LEVEL.get(999999, "") == ""


class TestLevelLabel:
    def test_四档都有中文名(self):
        assert set(LEVEL_LABEL) == set(EXPECTED_LEVEL.values())

    def test_中文名带音质二字(self):
        assert LEVEL_LABEL["lossless"] == "无损音质"

    def test_未知level原样返回(self):
        assert LEVEL_LABEL.get("weird", "weird") == "weird"


class TestNotifyAccount:
    def test_无会员的提示(self, monkeypatch, capsys):
        monkeypatch.setattr(
            downloader,
            "get_account_info",
            lambda: {"logged_in": True, "vip": False, "vip_type": 0},
        )
        downloader._notify_account()
        out = _cap(capsys)
        assert "没有 VIP 权限" in out
        assert "仍会" in out, "要说清不会因此中断下载"

    def test_未登录的提示(self, monkeypatch, capsys):
        monkeypatch.setattr(
            downloader,
            "get_account_info",
            lambda: {"logged_in": False, "vip": False, "vip_type": 0},
        )
        downloader._notify_account()
        out = _cap(capsys)
        assert "登录状态" in out
        # 未登录与无会员是两回事，不能混
        assert "VIP" not in out

    def test_检查失败也要报(self, monkeypatch, capsys):
        """查不出来不等于查出来没有，这两种提示不能混"""
        monkeypatch.setattr(downloader, "get_account_info", lambda: None)
        downloader._notify_account()
        out = _cap(capsys)
        assert "检查失败" in out
        assert "不影响" in out

    def test_一切正常时不啰嗦(self, monkeypatch, capsys):
        monkeypatch.setattr(
            downloader,
            "get_account_info",
            lambda: {"logged_in": True, "vip": True, "vip_type": 11},
        )
        downloader._notify_account()
        assert _cap(capsys) == ""

    def test_只说一次(self, monkeypatch, capsys):
        """批量下载不该把同一句话刷满屏"""
        monkeypatch.setattr(
            downloader,
            "get_account_info",
            lambda: {"logged_in": True, "vip": False, "vip_type": 0},
        )
        for _ in range(5):
            downloader._notify_account()
        assert _cap(capsys).count("没有 VIP 权限") == 1


class TestNotifyDowngrade:
    def test_降级时说清前后(self, capsys):
        downloader._notify_downgrade("lossless", "exhigh")
        out = _cap(capsys)
        assert "无损音质" in out
        assert "超高音质" in out

    def test_音质相同不提示(self, capsys):
        downloader._notify_downgrade("lossless", "lossless")
        assert _cap(capsys) == ""

    def test_请求非最高档不提示(self, capsys):
        """128/192/320 三档有无会员结果一致，降级提示只该出现在最高档"""
        downloader._notify_downgrade("exhigh", "exhigh")
        assert _cap(capsys) == ""

    def test_信息不全不提示(self, capsys):
        """拿不到实际 level 时不能瞎说"""
        downloader._notify_downgrade("lossless", "")
        downloader._notify_downgrade("", "exhigh")
        assert _cap(capsys) == ""

    def test_只说一次(self, capsys):
        for _ in range(5):
            downloader._notify_downgrade("lossless", "exhigh")
        assert _cap(capsys).count("不支持无损音质") == 1

    def test_未知level用原名兜底(self, capsys):
        downloader._notify_downgrade("weird", "other")
        out = _cap(capsys)
        assert "weird" in out and "other" in out


class TestAccountInfoCache:
    def test_结果在进程内缓存(self, monkeypatch):
        """批量下载只能发一次请求，这是放在 api 层缓存的原因"""
        import function.api as api

        calls = {"n": 0}

        class Resp:
            @staticmethod
            def json():
                return {"code": 200, "account": {"vipType": 11}}

        class Session:
            def get(self, *_a, **_k):
                calls["n"] += 1
                return Resp()

        monkeypatch.setattr(api, "_account_state", api._ACCOUNT_UNSET)
        monkeypatch.setattr(api, "_get_session", lambda: Session())
        for _ in range(5):
            api.get_account_info()
        assert calls["n"] == 1

    def test_失败也缓存以免刷请求(self, monkeypatch):
        import function.api as api

        calls = {"n": 0}

        class Session:
            def get(self, *_a, **_k):
                calls["n"] += 1
                raise OSError("断网")

        monkeypatch.setattr(api, "_account_state", api._ACCOUNT_UNSET)
        monkeypatch.setattr(api, "_get_session", lambda: Session())
        for _ in range(5):
            assert api.get_account_info() is None
        assert calls["n"] == 1

    def test_查不到与未登录要分得开(self, monkeypatch):
        import function.api as api

        class Resp:
            @staticmethod
            def json():
                return {"code": 200, "account": None}

        class Session:
            def get(self, *_a, **_k):
                return Resp()

        monkeypatch.setattr(api, "_account_state", api._ACCOUNT_UNSET)
        monkeypatch.setattr(api, "_get_session", lambda: Session())
        got = api.get_account_info()
        assert got is not None
        assert got["logged_in"] is False

    def test_不能拿code判登录(self, monkeypatch):
        """这个接口无论登录与否都返回 code=200"""
        import function.api as api

        class Resp:
            @staticmethod
            def json():
                return {"code": 200, "account": {"vipType": 0}}

        class Session:
            def get(self, *_a, **_k):
                return Resp()

        monkeypatch.setattr(api, "_account_state", api._ACCOUNT_UNSET)
        monkeypatch.setattr(api, "_get_session", lambda: Session())
        got = api.get_account_info()
        assert got["logged_in"] is True, "account 存在即已登录"
        assert got["vip"] is False, "登录了不等于有会员"
        assert got["vip_type"] == 0


class TestAudioSourceCarriesLevel:
    def test_带level字段(self):
        from function.api import AudioSource

        src = AudioSource("http://x/a.flac", level="exhigh")
        assert src.level == "exhigh"

    def test_缺省为空串(self):
        from function.api import AudioSource

        assert AudioSource("http://x/a.flac").level == ""
