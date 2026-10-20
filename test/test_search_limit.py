"""search --count 的取值范围"""

import pytest

from vncmd.cli import _search_limit, build_parser
from vncmd.net.api import SEARCH_LIMIT_MAX


def parse(limit):
    return build_parser().parse_args(["search", "初音", "-c", str(limit)])


def _error_line(capsys, limit):
    """只取 argparse 报错里以 ✗ 开头的那一行，整段断言会混进 --offset 的提示"""
    with pytest.raises(SystemExit):
        parse(limit)
    for line in capsys.readouterr().err.splitlines():
        if line.lstrip().startswith("✗"):
            return line
    pytest.fail("没有找到报错行")


class Test合法值:
    @pytest.mark.parametrize("n", [1, 10, 50, 99, 100])
    def test_范围内收下(self, n):
        assert parse(n).count == n

    def test_上限就是实测的那个数(self):
        """100 能过而 101 回 code 400，这个数由接口确定"""
        assert SEARCH_LIMIT_MAX == 100

    def test_不给时是None而不是10(self):
        """None 表示用户没说，默认 10 由 cmd_search 决定
        写成 10 会让 --json 分不清是否显式指定
        """
        assert build_parser().parse_args(["search", "初音"]).count is None


class Test越界:
    @pytest.mark.parametrize("n", [0, -1, 101, 200, 10000])
    def test_越界报错(self, n, capsys):
        """越界只有一个方向，不分成上下限两套文案"""
        with pytest.raises(SystemExit) as exc:
            parse(n)
        assert exc.value.code != 0
        err = capsys.readouterr().err
        assert "1 至 100 之间" in err
        assert str(n) in err, "要把用户给的值原样还给他"

    def test_超限提到还有别的办法(self, capsys):
        """只有超上限时 offset 才有用，“要 0 条”提它就错"""
        assert "--offset" in _error_line(capsys, 101)

    def test_下限不提offset(self, capsys):
        assert "--offset" not in _error_line(capsys, 0)

    def test_不是整数报错(self, capsys):
        with pytest.raises(SystemExit) as exc:
            parse("abc")
        assert exc.value.code != 0
        assert "须为整数" in capsys.readouterr().err


class Test报错文案:
    def test_不刷一百个数字(self, capsys):
        """用 choices=range(1,101) 会把 1 到 100 全列进报错，只会制造噪音"""
        with pytest.raises(SystemExit):
            parse(101)
        err = capsys.readouterr().err
        assert "choose from" not in err
        assert err.count("'") <= 4, f"报错里混进了选项列表：{err}"

    def test_不是argparse那句英文(self, capsys):
        with pytest.raises(SystemExit):
            parse(101)
        assert "invalid choice" not in capsys.readouterr().err


class Test_help:
    def test_上限写在帮助里(self, capsys):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["search", "--help"])
        out = capsys.readouterr().out
        assert "1-100" in out
        assert "N" in out, "metavar=N，值域不该把 1 到 100 铺进用法行"


class Test底层函数:
    def test_接受字符串(self):
        assert _search_limit("50") == 50

    def test_越界抛ArgumentTypeError(self):
        import argparse

        with pytest.raises(argparse.ArgumentTypeError):
            _search_limit("101")

    def test_不合法时不要连带TypeError(self):
        """from None 去掉上下文，traceback 里只剩这一条"""
        import argparse

        try:
            _search_limit("abc")
        except argparse.ArgumentTypeError as e:
            assert e.__cause__ is None, "带了 __cause__ 会把 ValueError 也印出来"
        else:
            pytest.fail("没抛异常")
