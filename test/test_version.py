"""`--version` 的行为

它唯一的功能价值是「在任何环境下都能问出自己在跑哪个版本」——
CI 会跑 `vncmd --version` 并比对输出，所以它必须在 acquire_lock、
validate_config 与账号播报之前退出，一个字节的诊断都不能混进去。
"""

import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

import pytest

import vncmd.cli as vncmd

EXPECTED = f"vncmd {_pkg_version('vncmd')}"


@pytest.fixture
def called(monkeypatch):
    """记录 main 在版本分支里到底走到了哪一步"""
    hits = []

    def spy(name):
        return lambda *a, **k: hits.append(name)

    for name in ("acquire_lock", "validate_config", "announce_account"):
        monkeypatch.setattr(vncmd, name, spy(name))
    monkeypatch.setattr(sys, "argv", ["vncmd", "--version"])
    return hits


class Test打印:
    def test_长选项(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["vncmd", "--version"])
        with pytest.raises(SystemExit) as exc:
            vncmd.main()
        assert exc.value.code == 0
        assert capsys.readouterr().out == EXPECTED + "\n"

    def test_短选项同结果(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["vncmd", "-V"])
        with pytest.raises(SystemExit):
            vncmd.main()
        assert capsys.readouterr().out == EXPECTED + "\n"

    def test_stderr一个字都不出(self, monkeypatch, capsys):
        """CI 比对的是 stdout，诊断混进去就要先剥，比对本身也就不可靠了"""
        monkeypatch.setattr(sys, "argv", ["vncmd", "--version"])
        with pytest.raises(SystemExit):
            vncmd.main()
        assert capsys.readouterr().err == ""

    def test_没有ANSI(self, monkeypatch, capsys):
        """走 rich 的 print 会带上颜色码，CI 侧还得先剥一层"""
        monkeypatch.setattr(sys, "argv", ["vncmd", "--version"])
        with pytest.raises(SystemExit):
            vncmd.main()
        assert "\x1b" not in capsys.readouterr().out

    def test_版本与包元数据一致(self):
        """不是从 pyproject.toml 读的，也不是写死的常量"""
        assert vncmd._version_string() == EXPECTED


class Test早于一切副作用:
    """这三个都是要在本机落东西或联网的，版本查询不该触发任何一个"""

    def test_没上锁(self, called):
        with pytest.raises(SystemExit):
            vncmd.main()
        assert "acquire_lock" not in called

    def test_没校验配置(self, called):
        with pytest.raises(SystemExit):
            vncmd.main()
        assert "validate_config" not in called

    def test_没播报账号(self, called):
        with pytest.raises(SystemExit):
            vncmd.main()
        assert "announce_account" not in called

    def test_三个都没跑到(self, called):
        with pytest.raises(SystemExit):
            vncmd.main()
        assert called == []


class Test包读不到时:
    def test_兜unknown而不是抛栈(self, monkeypatch):
        """装成非包的形式直接跑源码时会抛 PackageNotFoundError，
        打印 unknown 比抛一整段栈好"""

        def boom(_name):
            raise PackageNotFoundError("vncmd")

        monkeypatch.setattr(vncmd, "_pkg_version", boom)
        assert vncmd._version_string() == "vncmd unknown"


class Test帮助:
    def test_列在顶层帮助里(self, capsys):
        with pytest.raises(SystemExit):
            vncmd.build_parser().parse_args(["--help"])
        out = capsys.readouterr().out
        assert "--version" in out
        assert "-V" in out
