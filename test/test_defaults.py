"""命令行参数的默认值

这些数字同时出现在三处：vncmd.py 的 parser、api.py 的函数签名、doc/*.md。
少改一处就出现「文档说 10、代码给 30」或者反过来，
而这种不一致不会有任何报错，只在用的时候才发现不对。
所以在这里钉住，并让另外两处跟着断言。
"""

import argparse
import unittest.mock
from pathlib import Path

import pytest

from vncmd import build_parser

ROOT = Path(__file__).resolve().parent.parent


def _parse(argv):
    return build_parser().parse_args(argv)


class TestSearchLimit:
    def test_不给参数时是None(self):
        """None 表示「用户没说」，面板默认的 10 由 cmd_search 决定。

        写成 10 就分不清用户是显式给了 10 还是没给，而 --json 要的是全量。
        """
        assert _parse(["search", "x"]).limit is None

    def test_短选项照旧(self):
        assert _parse(["search", "x", "-n", "5"]).limit == 5

    def test_长选项照旧(self):
        assert _parse(["search", "x", "--limit", "5"]).limit == 5

    def test_偏移默认零(self):
        assert _parse(["search", "x"]).offset == 0


class TestMutuallyExclusive:
    """查看数据与下载是两种动作，同给要报错而不是静默丢弃一个"""

    def _parse(self, argv):
        return build_parser().parse_args(argv)

    def test_song的dlink与d互斥(self):
        """早先这里是 `args.dlink and not args.download`，
        两者同给时 --dlink 被静默丢弃，用户以为两个开关叠加了"""
        with pytest.raises(SystemExit) as exc:
            self._parse(["song", "1", "--dlink", "-d"])
        assert exc.value.code == 2

    def test_短选项同样互斥(self):
        with pytest.raises(SystemExit):
            self._parse(["song", "1", "-u", "-d"])

    def test_长选项同样互斥(self):
        with pytest.raises(SystemExit):
            self._parse(["song", "1", "--dlink", "--download"])

    def test_单独用dlink(self):
        args = self._parse(["song", "1", "--dlink"])
        assert args.dlink is True
        assert args.download is False

    def test_单独用d(self):
        args = self._parse(["song", "1", "-d"])
        assert args.download is True
        assert args.dlink is False

    def test_专辑与歌单不受影响(self):
        """它们没有查看链接的开关，-d 照常用"""
        for cmd in ("album", "playlist"):
            assert self._parse([cmd, "1", "-d"]).download is True

    def test_cookie值与check互斥(self):
        with pytest.raises(SystemExit) as exc:
            self._parse(["cookie", "abc", "--check"])
        assert exc.value.code == 2

    @pytest.mark.parametrize(
        "argv",
        [
            ["-f", "-d"],
            ["-f", "--auto-accept", "-d"],
            ["-f", "--auto-accept", "--force"],
            ["-f", "-d", "--auto-accept", "--force"],
        ],
    )
    def test_tracker的顶层动作与两个修饰互斥(self, argv):
        """命令里是 if / elif / else，同给时前面的分支静默吃掉后面的"""
        with pytest.raises(SystemExit) as exc:
            self._parse(["tracker", "like", *argv])
        assert exc.value.code == 2

    @pytest.mark.parametrize(
        "flag", [["-f"], ["-f", "--auto-accept"], ["-f", "--force"], ["-d"], []]
    )
    def test_tracker单独用各动作都行(self, flag):
        args = self._parse(["tracker", "like", *flag])
        assert not (args.fetch and args.download)
        assert not (args.auto_accept and args.force)


class TestDiffNeedsDownload:
    """--diff 只是 -d 的修饰，不是独立动作"""

    def test_单独给diff报错(self):
        from function.tracker import cmd_tracker

        args = argparse.Namespace(
            name="like",
            diff=True,
            download=False,
            json=False,
            fetch=False,
            auto_accept=False,
            force=False,
        )
        with pytest.raises(SystemExit) as exc:
            cmd_tracker(args)
        assert exc.value.code == 2

    def test_提示要说清要配合d(self, capsys):
        from function.tracker import cmd_tracker

        args = argparse.Namespace(
            name="like",
            diff=True,
            download=False,
            json=False,
            fetch=False,
            auto_accept=False,
            force=False,
        )
        with pytest.raises(SystemExit):
            cmd_tracker(args)
        out = capsys.readouterr().err
        assert "-d" in out, "只说「需要配合」却不说配合什么，等于没说"

    def test_检查在询问创建tracker之前(self, monkeypatch):
        """放到存在性判断之后的话，用户会先被问「是否创建 tracker」，
        才发现自己的参数写错了"""
        from function import tracker

        asked = []

        class FakeConfirm:
            def ask(self):
                asked.append(1)
                return False

        monkeypatch.setattr(
            tracker.questionary, "confirm", lambda *a, **k: FakeConfirm()
        )
        args = argparse.Namespace(
            name="一个不存在的名字",
            diff=True,
            download=False,
            json=False,
            fetch=False,
            auto_accept=False,
            force=False,
        )
        with pytest.raises(SystemExit):
            tracker.cmd_tracker(args)
        assert not asked, "参数写错时不该先去问要不要创建 tracker"

    def test_配了d就不报(self, monkeypatch):
        """配了 -d 时要走下载分支，不该被参数检查拦下"""
        from function import tracker

        called = []
        monkeypatch.setattr(tracker, "load_settings", lambda name: {"sources": [1]})
        monkeypatch.setattr(tracker, "download_diff", lambda *a: called.append(a))
        monkeypatch.setattr(tracker, "_tracker_path", lambda name: Path("/tmp"))
        monkeypatch.setattr(Path, "is_dir", lambda self: True)
        monkeypatch.setattr(tracker, "resolve_output_dir", lambda o=None: "/tmp")
        monkeypatch.setattr(tracker, "QUALITY_MAP", {"320": 320000})
        args = argparse.Namespace(
            name="like",
            diff=True,
            download=True,
            json=False,
            fetch=False,
            auto_accept=False,
            force=False,
            quality=None,
            output=None,
        )
        tracker.cmd_tracker(args)
        assert called, "没有走到下载 diff 的分支"


class TestDefaultsStayInSync:
    """parser 用的默认值、help 里写的、文档里写的，三处必须一致"""

    def _doc(self, name):
        return (ROOT / "doc" / name).read_text(encoding="utf-8")

    def test_cmd_search传给接口的条数永远合法(self):
        """parser 的默认值改成 None 之后，「10」只活在 cmd_search 里了

        早先这里断言的是 api.search 签名的默认值与 parser 一致。
        那个前提是两边共用一个 10，现在没有了 —— api 的 10 是给直接调它的人
        的兜底，生产代码里 cmd_search 每次都显式传值。
        真正要防的是传出去的值越界，那正是服务端会回 code 400 的地方。
        """
        import function.commands as commands
        from function.api import SEARCH_LIMIT_MAX

        for json_flag in (False, True):
            for limit in (None, 1, 50, SEARCH_LIMIT_MAX):
                ns = argparse.Namespace(
                    query="x", limit=limit, offset=0, json=json_flag
                )
                with unittest.mock.patch.object(
                    commands, "search", return_value={"songs": [], "total": 0}
                ) as fake:
                    commands.cmd_search(ns)
                sent = fake.call_args.kwargs["limit"]
                assert 1 <= sent <= SEARCH_LIMIT_MAX, (json_flag, limit, sent)

    def test_文档写的与help一致(self):
        """两边写的那个数都指面板，不是 parser 的 limit。

        早先断言的是文档里那句「返回数量，默认 10」的字面，
        那个短语被挪进表格后就找不到了，而数字一个字没变。
        所以改成读 --limit 那一行的「默认」列：要防的是数字漂移，
        不是文档的措辞与排版。
        """
        import re

        row = next(
            (
                line
                for line in self._doc("search.md").splitlines()
                if line.startswith("| `--limit")
            ),
            None,
        )
        assert row, "文档的 search.md 里没有 --limit 那一行"
        cells = [c.strip() for c in row.split("|")]
        assert len(cells) > 4, f"那一行没有「默认」列：{row}"
        hit = re.search(r"\d+", cells[3])
        assert hit, f"「默认」列里没有数字：{cells[3]}"
        assert int(hit.group()) == 10

    def test_help文本与面板默认值一致(self, capsys):
        """help 里写死一个数字，改了面板默认值忘了改它就会对不上

        断言的对象不再是 parser 的 limit（它是 None，表示「用户没说」），
        而是面板那条分支实际取的数 —— help 描述的是面板。
        """
        import re

        with pytest.raises(SystemExit):
            _parse(["search", "--help"])
        out = capsys.readouterr().out
        hit = re.search(r"最大结果数，\d+-\d+（默认：(\d+)）", out)
        assert hit, f"help 里找不到默认值的说明：{out}"
        assert int(hit.group(1)) == 10
