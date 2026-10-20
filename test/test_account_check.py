"""下载前的 Cookie 状态提示"""

import json
import os
import sys
import time

import pytest

from vncmd import downloader
from vncmd.net.api import EXPECTED_LEVEL, LEVEL_LABEL


@pytest.fixture(autouse=True)
def _fresh_flags():
    """降级提示在进程内只说一次，每个用例都要重置"""
    downloader._downgrade_notified = False


@pytest.fixture
def disk(tmp_path, monkeypatch):
    """把账号缓存与 cookie 文件挪进 tmp_path
    不隔离会读到用户真目录里的 account.json
    """
    import vncmd.net.api as api
    from vncmd.net import cache

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
    import vncmd.net.api as api

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
        import vncmd.net.api as api

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
        import vncmd.net.api as api

        _responder(monkeypatch, {"code": 200, "account": {"vipType": 11}})
        api.get_account_info()
        saved = json.loads(disk["path"].read_text(encoding="utf-8"))
        assert saved["vip"] is True
        assert saved["vip_type"] == 11
        assert saved["checked_at"] <= time.time()

    def test_缓存写在缓存根目录(self, disk, monkeypatch):
        """cache --clear 会 rmtree 整个根目录，放对位置才能顺带清掉"""
        import vncmd.net.api as api

        _responder(monkeypatch, {"code": 200, "account": {"vipType": 11}})
        api.get_account_info()
        assert disk["path"].parent == disk["root"]

    def test_超过一天重新查(self, disk, monkeypatch):
        import vncmd.net.api as api

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
        """set_at 记不到手工编辑，会拿着旧账号状态去下音频"""
        import vncmd.net.api as api

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
        import vncmd.net.api as api

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
        """cookie 换了就等于换了个人"""
        import vncmd.net.api as api

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
        import vncmd.net.api as api

        disk["path"].write_text(json.dumps({"checked_at": int(time.time())}), "utf-8")
        count = _responder(monkeypatch, {"code": 200, "account": {"vipType": 11}})
        got = api.get_account_info()
        assert count() == 1
        assert got["vip"] is True

    def test_坏掉的json当没有(self, disk, monkeypatch, capsys):
        import vncmd.net.api as api

        disk["path"].write_text("{ 坏的", encoding="utf-8")
        count = _responder(monkeypatch, {"code": 200, "account": {"vipType": 11}})
        assert api.get_account_info()["vip"] is True
        assert count() == 1
        assert "损坏" in capsys.readouterr().err, "坏文件要出声，别静默重查"


class TestAccountCheckFailed:
    def test_保留上一次的好值(self, disk, monkeypatch):
        """一次网络抖动不该让用户一整天看不到权限状态"""
        import vncmd.net.api as api

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
        """不推进的话下次运行会因过期再失败一次，永远走不到好值"""
        import vncmd.net.api as api

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
        """提示要说明这份数据来自缓存"""
        import vncmd.net.api as api

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
        """没有好值可留时返回失败"""
        import vncmd.net.api as api

        _responder(monkeypatch, boom=True)
        assert api.get_account_info() is None
        assert not disk["path"].exists(), "没有好值可保留就不该写文件"

    def test_刚查成功的不标为缓存(self, disk, monkeypatch):
        import vncmd.net.api as api

        _responder(monkeypatch, {"code": 200, "account": {"vipType": 11}})
        api.get_account_info()
        assert api.account_stamp() == (api.account_stamp()[0], False)


class TestForceCheck:
    def test_强制时缓存再新也查(self, disk, monkeypatch):
        """cookie 刚被改过，缓存里那份属于另一个人"""
        import vncmd.net.api as api

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
        """强制检查要当下的状态，拿一小时前的缓存顶替等于没查"""
        import vncmd.net.api as api

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
        import vncmd.net.api as api

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


class TestAccountNeedsCheck:
    """预告“正在检查”之前要先知道会不会真发请求"""

    def test_没有缓存说要查(self, disk):
        import vncmd.net.api as api

        assert api.account_needs_check() is True

    def test_缓存新鲜说不用查(self, disk):
        import vncmd.net.api as api

        _write_cache(
            disk["path"],
            checked_at=time.time(),
            logged_in=True,
            vip=True,
            vip_type=11,
        )
        assert api.account_needs_check() is False

    def test_缓存过期说要查(self, disk):
        import vncmd.net.api as api

        _write_cache(
            disk["path"],
            checked_at=time.time() - 90000,
            logged_in=True,
            vip=True,
            vip_type=11,
        )
        assert api.account_needs_check() is True

    def test_cookie改过说要查(self, disk):
        import vncmd.net.api as api

        _write_cache(
            disk["path"],
            checked_at=time.time(),
            logged_in=True,
            vip=True,
            vip_type=11,
        )
        os.utime(disk["cookie"], (time.time(), time.time()))
        assert api.account_needs_check() is True

    def test_进程内已有结果说不查(self, disk, monkeypatch):
        import vncmd.net.api as api

        _write_cache(
            disk["path"],
            checked_at=time.time() - 90000,
            logged_in=True,
            vip=True,
            vip_type=11,
        )
        monkeypatch.setattr(
            api, "_account_state", {"logged_in": True, "vip": True, "vip_type": 11}
        )
        assert api.account_needs_check() is False

    def test_与实际请求一致(self, disk, monkeypatch):
        """预告说查却没发请求，或者不预告却发了，都会让人以为出了问题"""
        import vncmd.net.api as api

        count = _responder(monkeypatch, {"code": 200, "account": {"vipType": 11}})
        assert api.account_needs_check() is True
        api.get_account_info()
        assert count() == 1
        assert api.account_needs_check() is False, "查过之后不该再预告"


class Test命令改名后的分派:
    """--init 与 tool check 各走各的路径，都要真的跑到对应的 handler"""

    def _run(self, monkeypatch, argv):
        import vncmd.cli as vncmd

        ran = []
        monkeypatch.setattr(vncmd, "acquire_lock", lambda: None)
        monkeypatch.setattr(
            vncmd, "validate_config", lambda quiet=False, overrides=None: None
        )
        monkeypatch.setattr(vncmd, "announce_account", lambda: None)
        monkeypatch.setattr(vncmd, "cmd_init", lambda _a: ran.append("init"))
        monkeypatch.setattr(vncmd, "cmd_check", lambda _a: ran.append("check"))
        monkeypatch.setattr(vncmd, "cmd_cache", lambda _a: ran.append("cache"))
        monkeypatch.setattr(sys, "argv", ["vncmd", *argv])
        vncmd.main()
        return ran

    def test_init走的是顶层开关(self, monkeypatch):
        """--init 为顶层开关，没有 args.command，靠 args.init 判断"""
        assert self._run(monkeypatch, ["--init"]) == ["init"]

    def test_init不走validate_config(self, monkeypatch):
        """--init 不校验配置，与它作为独立命令时一致"""
        import vncmd.cli as vncmd

        calls = []
        monkeypatch.setattr(vncmd, "acquire_lock", lambda: None)
        monkeypatch.setattr(vncmd, "cmd_init", lambda _a: calls.append("init"))
        monkeypatch.setattr(
            vncmd,
            "validate_config",
            lambda quiet=False, overrides=None: pytest.fail("init 不该校验配置"),
        )
        monkeypatch.setattr(sys, "argv", ["vncmd", "--init"])
        vncmd.main()
        assert calls == ["init"]

    def test_init后面接命令时init优先(self, monkeypatch):
        """同时给 --init 与子命令时走 init"""
        assert self._run(monkeypatch, ["--init", "song", "1"]) == ["init"]

    def test_tool_check真的调到cmd_check(self, monkeypatch):
        """分派表写错时它会落到 print_help 静默退出，没有报错"""
        assert self._run(monkeypatch, ["tool", "check", "/tmp"]) == ["check"]

    def test_tool_cache真的调到cmd_cache(self, monkeypatch):
        assert self._run(monkeypatch, ["tool", "cache", "--stats"]) == ["cache"]

    def test_提示里的命令名要跟着改(self, monkeypatch, capsys, tmp_path):
        """写死旧命令名时用户照着敲会得到不存在的命令"""
        import argparse

        from vncmd import commands as commands_mod

        # 目录必须真存在，否则 cmd_cache 开头就报“缓存目录不存在”，走不到那行提示
        (tmp_path / "cache").mkdir()
        monkeypatch.setattr(
            commands_mod, "get_cache_dir", lambda: str(tmp_path / "cache")
        )
        monkeypatch.setattr(commands_mod, "abbrev_home", lambda p: str(p))
        commands_mod.cmd_cache(argparse.Namespace(stats=True, clear=False))
        assert "vncmd tool cache --clear" in capsys.readouterr().err

    def test_tool不给子命令时报用法错(self, monkeypatch):
        """敲 tool 却回整个应用的帮助，像敲错了命令"""
        import vncmd.cli as vncmd

        monkeypatch.setattr(vncmd, "acquire_lock", lambda: None)
        monkeypatch.setattr(sys, "argv", ["vncmd", "tool"])
        with pytest.raises(SystemExit) as exc:
            vncmd.main()
        assert exc.value.code == 2


class TestAnnounceSkips:
    def test_这几条命令不查(self):
        """cookie 自己要查账号，tool 下的都不联网，init 由 main 里的 args.init 处理
        cache --clear 刚清完缓存又被写回来就白清了，check 纯本地干活
        """
        from vncmd.cli import _NO_ACCOUNT_REPORT

        assert set(_NO_ACCOUNT_REPORT) == {"cookie", "tool"}

    def test_下载与浏览类的命令要查(self):
        from vncmd.cli import _NO_ACCOUNT_REPORT

        for cmd in ("song", "album", "playlist", "search", "tracker"):
            assert cmd not in _NO_ACCOUNT_REPORT, f"{cmd} 漏了"

    def _run_main(self, monkeypatch, argv):
        """跑一次 main，统计账号状态的查询次数"""
        import vncmd.cli as vncmd

        calls = {"n": 0}
        monkeypatch.setattr(vncmd, "acquire_lock", lambda: None)
        monkeypatch.setattr(
            vncmd, "validate_config", lambda quiet=False, overrides=None: None
        )
        monkeypatch.setattr(vncmd, "cmd_init", lambda _a: None)
        monkeypatch.setattr(
            vncmd, "announce_account", lambda: calls.__setitem__("n", calls["n"] + 1)
        )
        for name in ("cmd_check", "cmd_cache", "cmd_song"):
            monkeypatch.setattr(vncmd, name, lambda _a: None)
        monkeypatch.setattr(sys, "argv", ["vncmd", *argv])
        vncmd.main()
        return calls["n"]

    def test_tool_check不联网查(self, monkeypatch, tmp_path):
        """纯本地操作，多一次请求就白等一次网络"""
        assert self._run_main(monkeypatch, ["tool", "check", str(tmp_path)]) == 0

    def test_cache不联网查(self, monkeypatch):
        """--clear 刚清完缓存又被自动写回来就白清了"""
        assert self._run_main(monkeypatch, ["tool", "cache", "--stats"]) == 0

    def test_song要查(self, monkeypatch):
        assert self._run_main(monkeypatch, ["song", "1"]) == 1


def _cap(capsys):
    """账号播报与降级提示走 stderr"""
    return capsys.readouterr().err


class TestExpectedLevel:
    def test_四档都有对应(self):
        assert set(EXPECTED_LEVEL) == {128000, 192000, 320000, 2147483647}

    def test_最高档对应无损(self):
        """只有这一档会因权限不足降级，其余三档有无会员一致"""
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
    """联网查过 Cookie 权限就播报一次"""

    def _say(self, monkeypatch, capsys, state, from_cache=False, needs_check=True):
        from vncmd import commands

        monkeypatch.setattr(commands, "get_account_info", lambda: state)
        monkeypatch.setattr(commands, "account_stamp", lambda: (0, from_cache))
        monkeypatch.setattr(commands, "account_needs_check", lambda: needs_check)
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
        # 未登录与无会员为两回事，不能混
        assert "VIP" not in out

    def test_检查失败也要报(self, monkeypatch, capsys):
        """查不出来不等于查出来没有，这两种提示不能混"""
        out = self._say(monkeypatch, capsys, None)
        assert "检查失败" in out
        assert "不影响" in out

    def test_一切正常时也报一次(self, monkeypatch, capsys):
        """一切正常也要报一次，否则用户看不出权限有没有生效"""
        out = self._say(
            monkeypatch, capsys, {"logged_in": True, "vip": True, "vip_type": 11}
        )
        assert "有 VIP 权限" in out

    def test_标签叫Cookie权限(self, monkeypatch, capsys):
        """“账号状态”会被理解成服务端账号，这里查本地 Cookie 的权限"""
        out = self._say(
            monkeypatch, capsys, {"logged_in": True, "vip": True, "vip_type": 11}
        )
        assert "Cookie 权限" in out
        assert "账号状态" not in out

    def test_请求前先说一声(self, monkeypatch, capsys):
        """不然中间那一下停顿看着像卡住了"""
        out = self._say(
            monkeypatch, capsys, {"logged_in": True, "vip": True, "vip_type": 11}
        )
        assert "正在检查" in out
        assert out.index("正在检查") < out.index("Cookie 权限"), "预告要排在结果前面"

    def test_不联网时不要预告(self, monkeypatch, capsys):
        """说了要查却读缓存，前后对不上"""
        out = self._say(
            monkeypatch,
            capsys,
            {"logged_in": True, "vip": True, "vip_type": 11},
            needs_check=False,
        )
        assert "正在检查" not in out

    def test_用缓存时完全静默(self, monkeypatch, capsys):
        """缓存只表示上次查出的状态，每次复读会淹掉真正要提醒的那一次"""
        out = self._say(
            monkeypatch,
            capsys,
            {"logged_in": True, "vip": True, "vip_type": 11},
            from_cache=True,
            needs_check=False,
        )
        assert out == "", f"命中缓存不该出声：{out}"

    def test_用缓存时有毛病也不出声(self, monkeypatch, capsys):
        """播报跟着联网检查走，缓存里的旧结论不重复提"""
        out = self._say(
            monkeypatch,
            capsys,
            {"logged_in": True, "vip": False, "vip_type": 0},
            from_cache=True,
            needs_check=False,
        )
        assert out == ""

    def test_刚查的不提缓存(self, monkeypatch, capsys):
        out = self._say(
            monkeypatch, capsys, {"logged_in": True, "vip": True, "vip_type": 11}
        )
        assert "缓存" not in out


class TestNotifyDowngrade:
    """降级提示的时机与次数，登录态分岔在 test_stream_split.py"""

    @pytest.fixture(autouse=True)
    def 重置开关(self, monkeypatch):
        """提示整个进程只报一次，每条测试都要重置
        get_cookie 打桩成有登录态，登录态分岔在 test_stream_split.py
        """
        monkeypatch.setattr(downloader, "_downgrade_notified", False)
        monkeypatch.setattr(downloader, "get_cookie", lambda: "NMTID=xxx")

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
        """拿不到实际 level 时不提示"""
        downloader._notify_downgrade("lossless", "")
        downloader._notify_downgrade("", "exhigh")
        assert _cap(capsys) == ""

    def test_只说一次(self, capsys):
        for _ in range(5):
            downloader._notify_downgrade("lossless", "exhigh")
        assert _cap(capsys).count("不支持无损音质") == 1

    def test_未知level用原名兜底(self, capsys):
        """表里没有的 level 名要原样印出，空着只剩“本次已按下载”"""
        downloader._notify_downgrade("weird", "other")
        out = _cap(capsys)
        assert "weird" in out and "other" in out


class TestAccountInfoCache:
    def test_结果在进程内缓存(self, monkeypatch):
        """批量下载只发一次请求"""
        import vncmd.net.api as api

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
        import vncmd.net.api as api

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
        import vncmd.net.api as api

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
        import vncmd.net.api as api

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
        from vncmd.net.api import AudioSource

        src = AudioSource("http://x/a.flac", level="exhigh")
        assert src.level == "exhigh"

    def test_缺省为空串(self):
        from vncmd.net.api import AudioSource

        assert AudioSource("http://x/a.flac").level == ""
