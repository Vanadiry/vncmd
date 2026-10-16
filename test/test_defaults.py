"""命令行参数的默认值

这些数字同时出现在三处：vncmd.py 的 parser、api.py 的函数签名、doc/*.md。
少改一处就出现「文档说 10、代码给 30」或者反过来，
而这种不一致不会有任何报错，只在用的时候才发现不对。
所以在这里钉住，并让另外两处跟着断言。
"""

from pathlib import Path

import pytest

from vncmd import build_parser

ROOT = Path(__file__).resolve().parent.parent


def _parse(argv):
    return build_parser().parse_args(argv)


class TestSearchLimit:
    def test_不给参数时是十(self):
        assert _parse(["search", "x"]).limit == 10

    def test_短选项照旧(self):
        assert _parse(["search", "x", "-n", "5"]).limit == 5

    def test_长选项照旧(self):
        assert _parse(["search", "x", "--limit", "5"]).limit == 5

    def test_偏移默认零(self):
        assert _parse(["search", "x"]).offset == 0


class TestDefaultsStayInSync:
    """parser、api 签名、文档三处的默认值必须一致"""

    def _doc(self, name):
        return (ROOT / "doc" / name).read_text(encoding="utf-8")

    def test_api签名的默认值与parser一致(self):
        import inspect

        from function.api import search

        sig = inspect.signature(search)
        assert sig.parameters["limit"].default == _parse(["search", "x"]).limit

    def test_文档写的与parser一致(self):
        assert "返回数量，默认 10" in self._doc("search.md")

    def test_help文本与实际默认值一致(self, capsys):
        """help 里写死一个数字，改了默认值忘了改它就会对不上

        顶层 help 不含子命令的参数说明，所以要走 search --help
        """
        import re

        with pytest.raises(SystemExit):
            _parse(["search", "--help"])
        out = capsys.readouterr().out
        hit = re.search(r"最大结果数（默认：(\d+)）", out)
        assert hit, f"help 里找不到默认值的说明：{out}"
        assert int(hit.group(1)) == _parse(["search", "x"]).limit
