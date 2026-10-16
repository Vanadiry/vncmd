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

import json
import os
import time

import pytest

from function import downloader
from function.api import EXPECTED_LEVEL, LEVEL_LABEL


@pytest.fixture(autouse=True)
def _fresh_flags():
    """降级提示是进程内只说一次，每个用例都要重置"""
    downloader._downgrade_notified = False


@pytest.fixture
def disk(tmp_path, monkeypatch):
    """把磁盘那份账号缓存与 cookie 文件挪进 tmp_path

    不隔离的话，测试会读到用户真目录里的 account.json，
    请求次数与状态断言全都不可靠。
    """
    import function.api as api
    from function import cache

    root = tmp_path / "cache"
    root.mkdir()
    cookie = tmp_path / "cookie"
    cookie.write_text("K", encoding="utf-8")
    monkeypatch.setattr(cache, "get_cache_dir", lambda: str(root))
    monkeypatch.setattr(cache, "COOKIE_FILE", cookie)
    monkeypatch.setattr(cache, "is_cache_enabled", lambda: True)
    monkeypatch.setattr(api, "_account_state", api._ACCOUNT_UNSET)
    return {"root": root, "cookie": cookie, "path": root / "account.json"}


def _responder(monkeypatch, payload=None, boom=False):
    """装一个计数的假会话，返回调用次数的取值器"""
    import function.api as api

    calls = {"n": 0}

    class Resp:
        @staticmethod
        def json():
            return payload if payload is not None else {"code": 200, "account": None}

    class Session:
        def get(self, *_a, **_k):
            calls["n"] += 1
            if boom:
                raise OSError("断网")
            return Resp()

    monkeypatch.setattr(api, "_get_session", lambda: Session())
    return lambda: calls["n"]


def _write_cache(path, *, checked_at, **state):
    path.write_text(
        json.dumps({"checked_at": checked_at, **state}, ensure_ascii=False),
        encoding="utf-8",
    )


class TestAccountOnDisk:
    def test_命中缓存不发请求(self, disk, monkeypatch):
        import function.api as api

        _write_cache(
            disk["path"],
            checked_at=time.time(),
            logged_in=True,
            vip=True,
            vip_type=11,
        )
        count = _responder(monkeypatch, {"code": 200, "account": {"vipType": 0}})
        assert api.get_account_info() == {
            "logged_in": True,
            "vip": True,
            "vip_type": 11,
        }
        assert count() == 0, "一天内不该重复问"

    def test_查完写进缓存(self, disk, monkeypatch):
        import function.api as api

        _responder(monkeypatch, {"code": 200, "account": {"vipType": 11}})
        api.get_account_info()
        saved = json.loads(disk["path"].read_text(encoding="utf-8"))
        assert saved["vip"] is True
        assert saved["vip_type"] == 11
        assert saved["checked_at"] <= time.time()

    def test_缓存写在缓存根目录(self, disk, monkeypatch):
        """cache --clear 是 rmtree 整个根目录，放对位置才顺带清掉"""
        import function.api as api

        _responder(monkeypatch, {"code": 200, "account": {"vipType": 11}})
        api.get_account_info()
        assert disk["path"].parent == disk["root"]

    def test_超过一天重新查(self, disk, monkeypatch):
        import function.api as api

        _write_cache(
            disk["path"],
            checked_at=time.time() - 90000,
            logged_in=True,
            vip=True,
            vip_type=11,
        )
        count = _responder(monkeypatch, {"code": 200, "account": {"vipType": 0}})
        api.get_account_info()
        assert count() == 1

    def test_cookie改过就重新查(self, disk, monkeypatch):
        """记 set_at 覆盖不到手工编辑这条途径，会拿着旧账号状态去下音频"""
        import function.api as api

        _write_cache(
            disk["path"],
            checked_at=time.time(),
            logged_in=True,
            vip=True,
            vip_type=11,
        )
        os.utime(disk["cookie"], (time.time(), time.time()))
        count = _responder(monkeypatch, {"code": 200, "account": {"vipType": 0}})
        got = api.get_account_info()
        assert count() == 1, "cookie 换了人就该重查"
        assert got["vip"] is False

    def test_cookie没动过就不查(self, disk, monkeypatch):
        import function.api as api

        _write_cache(
            disk["path"],
            checked_at=time.time(),
            logged_in=True,
            vip=True,
            vip_type=11,
        )
        count = _responder(monkeypatch, {"code": 200, "account": {"vipType": 0}})
        api.get_account_info()
        assert count() == 0

    def test_cookie文件不见了重新查(self, disk, monkeypatch):
        """换了一份 cookie 等于换了个人"""
        import function.api as api

        _write_cache(
            disk["path"],
            checked_at=time.time(),
            logged_in=True,
            vip=True,
            vip_type=11,
        )
        disk["cookie"].unlink()
        count = _responder(monkeypatch, {"code": 200, "account": {"vipType": 0}})
        api.get_account_info()
        assert count() == 1

    def test_残缺的缓存当没有(self, disk, monkeypatch):
        """手工编辑过或写坏了的半份数据，重新查比拿它拼状态安全"""
        import function.api as api

        disk["path"].write_text(json.dumps({"checked_at": int(time.time())}), "utf-8")
        count = _responder(monkeypatch, {"code": 200, "account": {"vipType": 11}})
        got = api.get_account_info()
        assert count() == 1
        assert got["vip"] is True

    def test_坏掉的json当没有(self, disk, monkeypatch, capsys):
        import function.api as api

        disk["path"].write_text("{ 坏的", encoding="utf-8")
        count = _responder(monkeypatch, {"code": 200, "account": {"vipType": 11}})
        assert api.get_account_info()["vip"] is True
        assert count() == 1
        assert "损坏" in capsys.readouterr().out, "坏文件要出声，别静默重查"


class TestAccountCheckFailed:
    def test_保留上一次的好值(self, disk, monkeypatch):
        """一次网络抖动不该让用户一整天看不到权限状态"""
        import function.api as api

        _write_cache(
            disk["path"],
            checked_at=time.time() - 90000,
            logged_in=True,
            vip=True,
            vip_type=11,
        )
        _responder(monkeypatch, boom=True)
        got = api.get_account_info()
        assert got == {"logged_in": True, "vip": True, "vip_type": 11}

    def test_失败也把时间戳推进(self, disk, monkeypatch):
        """否则下次运行还会因为「过期」再失败一次，永远走不到好值"""
        import function.api as api

        before = time.time() - 90000
        _write_cache(
            disk["path"],
            checked_at=before,
            logged_in=True,
            vip=True,
            vip_type=11,
        )
        _responder(monkeypatch, boom=True)
        api.get_account_info()
        saved = json.loads(disk["path"].read_text(encoding="utf-8"))
        assert saved["checked_at"] > before
        assert saved["vip"] is True

    def test_失败时标为来自缓存(self, disk, monkeypatch):
        """提示要能说出这份数据不是刚查的"""
        import function.api as api

        _write_cache(
            disk["path"],
            checked_at=time.time() - 90000,
            logged_in=True,
            vip=True,
            vip_type=11,
        )
        _responder(monkeypatch, boom=True)
        api.get_account_info()
        assert api.account_stamp()[1] is True

    def test_没有旧值就返回失败(self, disk, monkeypatch):
        """没有好值可留，就老实说查不成"""
        import function.api as api

        _responder(monkeypatch, boom=True)
        assert api.get_account_info() is None
        assert not disk["path"].exists(), "没有好值可保留就不该写文件"

    def test_刚查成功的不标为缓存(self, disk, monkeypatch):
        import function.api as api

        _responder(monkeypatch, {"code": 200, "account": {"vipType": 11}})
        api.get_account_info()
        assert api.account_stamp() == (api.account_stamp()[0], False)


class TestForceCheck:
    def test_强制时缓存再新也查(self, disk, monkeypatch):
        """cookie 刚被改过，缓存里那份描述的是另一个人"""
        import function.api as api

        _write_cache(
            disk["path"],
            checked_at=time.time(),
            logged_in=True,
            vip=True,
            vip_type=11,
        )
        count = _responder(monkeypatch, {"code": 200, "account": {"vipType": 0}})
        got = api.get_account_info(force=True)
        assert count() == 1
        assert got["vip"] is False

    def test_强制查失败不拿旧值顶替(self, disk, monkeypatch):
        """强制检查要的是当下的真相，拿一小时前的状态顶替等于没查"""
        import function.api as api

        _write_cache(
            disk["path"],
            checked_at=time.time(),
            logged_in=True,
            vip=True,
            vip_type=11,
        )
        _responder(monkeypatch, boom=True)
        assert api.get_account_info(force=True) is None

    def test_强制查完更新缓存(self, disk, monkeypatch):
        import function.api as api

        _write_cache(
            disk["path"],
            checked_at=1,
            logged_in=True,
            vip=True,
            vip_type=11,
        )
        _responder(monkeypatch, {"code": 200, "account": {"vipType": 0}})
        api.get_account_info(force=True)
        saved = json.loads(disk["path"].read_text(encoding="utf-8"))
        assert saved["vip"] is False
        assert saved["checked_at"] > 1


class TestAnnounceSkips:
    def test_这几条命令不播报(self):
        """cache --clear 刚清完缓存又被自动写回来就白清了"""
        from vncmd import _NO_ACCOUNT_REPORT

        assert set(_NO_ACCOUNT_REPORT) == {"init", "cookie", "cache"}

    def test_下载类的命令要播报(self):
        from vncmd import _NO_ACCOUNT_REPORT

        for cmd in ("song", "album", "playlist", "search", "tracker", "check"):
            assert cmd not in _NO_ACCOUNT_REPORT, f"{cmd} 漏了"


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


class TestAnnounceAccount:
    """每次运行报一次账号状态

    原先这条提示挂在下载路径上，只在下载时才出现，
    现在挪到 main 里统一播报，所以搜索、看详情这些也都会报。
    """

    def _say(self, monkeypatch, capsys, state, from_cache=False, checked_at=0):
        from function import commands

        monkeypatch.setattr(commands, "get_account_info", lambda: state)
        monkeypatch.setattr(commands, "account_stamp", lambda: (checked_at, from_cache))
        commands.announce_account()
        return _cap(capsys)

    def test_无会员的提示(self, monkeypatch, capsys):
        out = self._say(
            monkeypatch, capsys, {"logged_in": True, "vip": False, "vip_type": 0}
        )
        assert "没有 VIP 权限" in out

    def test_未登录的提示(self, monkeypatch, capsys):
        out = self._say(
            monkeypatch, capsys, {"logged_in": False, "vip": False, "vip_type": 0}
        )
        assert "登录状态" in out
        # 未登录与无会员是两回事，不能混
        assert "VIP" not in out

    def test_检查失败也要报(self, monkeypatch, capsys):
        """查不出来不等于查出来没有，这两种提示不能混"""
        out = self._say(monkeypatch, capsys, None)
        assert "检查失败" in out
        assert "不影响" in out

    def test_一切正常时也报一次(self, monkeypatch, capsys):
        """原先只在有毛病时出声，一切正常是静默的，
        用户就看不出权限到底有没有在生效"""
        out = self._say(
            monkeypatch, capsys, {"logged_in": True, "vip": True, "vip_type": 11}
        )
        assert "有 VIP 权限" in out

    def test_用缓存时说清有多旧(self, monkeypatch, capsys):
        """不说明的话，「没重新联网」看着像查不动"""
        import time

        out = self._say(
            monkeypatch,
            capsys,
            {"logged_in": True, "vip": True, "vip_type": 11},
            from_cache=True,
            checked_at=time.time() - 3 * 3600,
        )
        assert "缓存" in out
        assert "3 小时前" in out

    def test_刚查的不提缓存(self, monkeypatch, capsys):
        out = self._say(
            monkeypatch, capsys, {"logged_in": True, "vip": True, "vip_type": 11}
        )
        assert "缓存" not in out


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

    def test_失败也缓存以免刷请求(self, monkeypatch, disk):
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
