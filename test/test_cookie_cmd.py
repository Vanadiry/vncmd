"""vncmd cookie 的四种结局

原先靠一首固定曲目试探，只能问出「我能不能放这首」，
于是「未登录」和「无会员」被压成同一句话，退出码也都是 1。
改成查account/get 后四种结局分得开，其中无会员不再算失败。
"""

import argparse

import pytest

from function import commands


@pytest.fixture
def run_cookie(tmp_path, monkeypatch):
    """跑一次 cmd_cookie，返回 (输出, 退出码)

    成功分支是正常返回，失败分支才 sys.exit，两种都要接住。
    """
    monkeypatch.setattr(commands, "VNCMD_HOME", tmp_path)
    monkeypatch.setattr(commands, "COOKIE_FILE", tmp_path / "cookie")

    def run(account, value="MYCOOKIE", check=False):
        monkeypatch.setattr(commands, "get_account_info", lambda force=False: account)
        args = argparse.Namespace(value=value, check=check)
        try:
            commands.cmd_cookie(args)
        except SystemExit as exc:
            return exc.code or 0
        return 0

    return run


class TestCookieOutcomes:
    def test_一切正常退出零(self, run_cookie, capsys):
        assert run_cookie({"logged_in": True, "vip": True, "vip_type": 11}) == 0
        assert "Cookie 有效" in capsys.readouterr().out

    def test_无会员仍算成功(self, run_cookie, capsys):
        """无会员的 Cookie 能用，只是拿不到高音质，
        判成失败会让脚本以为没设成功"""
        code = run_cookie({"logged_in": True, "vip": False, "vip_type": 0})
        assert code == 0, "无会员不应判为失败"
        out = capsys.readouterr().out
        assert "有效" in out
        assert "VIP" in out

    def test_未登录退出非零(self, run_cookie, capsys):
        assert run_cookie({"logged_in": False, "vip": False, "vip_type": 0}) == 1
        out = capsys.readouterr().out
        assert "失效" in out or "无效" in out

    def test_检查失败单独一个退出码(self, run_cookie, capsys):
        """「查不成」与「查出无效」要分开，脚本才分辨得出"""
        assert run_cookie(None) == 2
        assert "检查失败" in capsys.readouterr().out

    def test_四种结局的退出码互不相同(self, run_cookie):
        codes = {
            run_cookie({"logged_in": True, "vip": True, "vip_type": 11}),
            run_cookie({"logged_in": True, "vip": False, "vip_type": 0}),
            run_cookie({"logged_in": False, "vip": False, "vip_type": 0}),
            run_cookie(None),
        }
        assert codes == {0, 1, 2}

    def test_未登录与无会员的说法不能混(self, run_cookie, capsys):
        run_cookie({"logged_in": False, "vip": False, "vip_type": 0})
        assert "VIP" not in capsys.readouterr().out


class TestCookieIsWrittenFirst:
    def test_即使检查失败也已写入(self, run_cookie, tmp_path):
        """Cookie 先存后查，查不成不能连累写入"""
        run_cookie(None)
        assert (tmp_path / "cookie").read_text(encoding="utf-8") == "MYCOOKIE"

    def test_首尾空白会被去掉(self, run_cookie, tmp_path):
        run_cookie({"logged_in": True, "vip": True, "vip_type": 11}, value="  K  \n")
        assert (tmp_path / "cookie").read_text(encoding="utf-8") == "K"


def test_探测曲目ID已从代码中移除():
    """探测曲只会问出「能不能放这首」，且曲目下架就误判，不该再用"""
    with open(commands.__file__, encoding="utf-8") as f:
        src = f.read()
    assert "2056952623" not in src


class TestCookieCheckOnly:
    """cookie --check 不碰文件，只查当前状态"""

    def test_不给值也能跑(self, run_cookie, capsys, tmp_path):
        """value 原本是必填，单独用 --check 会报「缺少参数」"""
        code = run_cookie(
            {"logged_in": True, "vip": True, "vip_type": 11}, value=None, check=True
        )
        assert code == 0
        assert not (tmp_path / "cookie").exists(), "--check 不该创建 cookie 文件"

    def test_不覆盖已有cookie(self, run_cookie, capsys, tmp_path):
        (tmp_path / "cookie").write_text("OLD", encoding="utf-8")
        run_cookie(
            {"logged_in": True, "vip": True, "vip_type": 11}, value=None, check=True
        )
        assert (tmp_path / "cookie").read_text(encoding="utf-8") == "OLD"

    def test_查不成仍退出二(self, run_cookie):
        assert run_cookie(None, value=None, check=True) == 2


class TestCookieArgErrors:
    def _run(self, value, check):
        args = argparse.Namespace(value=value, check=check)
        with pytest.raises(SystemExit) as exc:
            commands.cmd_cookie(args)
        return exc.value.code

    def test_两者同给报错(self):
        """--check 的意思就是不写文件，同时给值是自相矛盾"""
        assert self._run("abc", True) == 2

    def test_什么都不给报错(self):
        """value 改成 nargs=? 之后，漏给不再由 argparse 报，
        提示要说清还有 --check 这条路"""
        assert self._run(None, False) == 2


class TestCookieForcesCheck:
    """cookie 这条命令必须绕过磁盘缓存"""

    def _run(self, monkeypatch, tmp_path, account):
        from function import commands

        monkeypatch.setattr(commands, "VNCMD_HOME", tmp_path)
        monkeypatch.setattr(commands, "COOKIE_FILE", tmp_path / "cookie")
        seen = []

        def fake(force=False):
            seen.append(force)
            return account

        monkeypatch.setattr(commands, "get_account_info", fake)
        commands.cmd_cookie(argparse.Namespace(value="K", check=False))
        return seen

    def test_写入后强制查(self, monkeypatch, tmp_path):
        """cookie 文件刚被改过，缓存里那份描述的是另一个人"""
        good = {"logged_in": True, "vip": True, "vip_type": 11}
        assert self._run(monkeypatch, tmp_path, good) == [True]

    def test_只检查时也强制查(self, monkeypatch, tmp_path):
        good = {"logged_in": True, "vip": True, "vip_type": 11}
        from function import commands

        monkeypatch.setattr(commands, "COOKIE_FILE", tmp_path / "cookie")
        seen = []
        monkeypatch.setattr(
            commands,
            "get_account_info",
            lambda force=False: (seen.append(force), good)[1],
        )
        commands.cmd_cookie(argparse.Namespace(value=None, check=True))
        assert seen == [True], "--check 的全部意义就是查当下的状态"
