"""命令行参数的默认值

这些数字同时出现在三处：vncmd.py 的 parser、api.py 的函数签名、doc/*.md。
少改一处就出现「文档说 10、代码给 30」或者反过来，
而这种不一致不会有任何报错，只在用的时候才发现不对。
所以在这里钉住，并让另外两处跟着断言。
"""

import argparse
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
            ["-f", "--fetch-auto"],
            ["-f", "-d"],
            ["--fetch-auto", "-d"],
            ["-f", "--fetch-auto", "-d"],
        ],
    )
    def test_tracker的三个顶层动作互斥(self, argv):
        """命令里是 if / elif / else，同给时前面的分支静默吃掉后面的"""
        with pytest.raises(SystemExit) as exc:
            self._parse(["tracker", "like", *argv])
        assert exc.value.code == 2

    @pytest.mark.parametrize("flag", [["-f"], ["--fetch-auto"], ["-d"], []])
    def test_tracker单独用各动作都行(self, flag):
        args = self._parse(["tracker", "like", *flag])
        assert not (args.fetch and args.fetch_auto)


class TestDiffNeedsDownload:
    """--diff 只是 -d 的修饰，不是独立动作"""

    def test_单独给diff报错(self):
        from function.tracker import cmd_tracker

        args = argparse.Namespace(name="like", diff=True, download=False)
        with pytest.raises(SystemExit) as exc:
            cmd_tracker(args)
        assert exc.value.code == 2

    def test_提示要说清要配合d(self, capsys):
        from function.tracker import cmd_tracker

        args = argparse.Namespace(name="like", diff=True, download=False)
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
        args = argparse.Namespace(name="一个不存在的名字", diff=True, download=False)
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
        monkeypatch.setattr(
            tracker, "resolve_output_dir", lambda o=None: "/tmp", raising=False
        )
        monkeypatch.setattr(tracker, "QUALITY_MAP", {"320": 320000}, raising=False)
        args = argparse.Namespace(
            name="like",
            diff=True,
            download=True,
            fetch=False,
            fetch_auto=False,
            quality=None,
            output=None,
        )
        tracker.cmd_tracker(args)
        assert called, "没有走到下载 diff 的分支"


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
