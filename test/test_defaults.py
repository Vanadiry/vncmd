"""命令行默认值与文档、函数签名保持一致"""

import argparse
import unittest.mock
from pathlib import Path

import pytest

from vncmd.cli import build_parser

ROOT = Path(__file__).resolve().parent.parent


def _parse(argv):
    return build_parser().parse_args(argv)


class TestSearchLimit:
    def test_不给参数时是None(self):
        """None 表示“用户没说”，默认 10 由 cmd_search 决定
        写成 10 就分不清用户是否显式给了，而 --json 要全量"""
        assert _parse(["search", "x"]).count is None

    def test_短选项照旧(self):
        assert _parse(["search", "x", "-c", "5"]).count == 5

    def test_长选项照旧(self):
        assert _parse(["search", "x", "--count", "5"]).count == 5

    def test_偏移默认零(self):
        assert _parse(["search", "x"]).offset == 0


class TestMutuallyExclusive:
    """查看数据与下载为两种动作，同给要报错，不能静默丢弃一个"""

    def _parse(self, argv):
        return build_parser().parse_args(argv)

    def test_song的dlink与d互斥(self):
        """两者同给时 --dlink 会被静默丢弃，用户以为两个开关叠加了"""
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
        """命令里为 if / elif / else，同给时前面的分支静默吃掉后面的"""
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
    """--diff 为 -d 的修饰，不能单独使用"""

    def test_单独给diff报错(self):
        from vncmd.tracker import cmd_tracker

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
        from vncmd.tracker import cmd_tracker

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
        """参数检查要在询问创建 tracker 之前，否则用户先被问一句才发现写错"""
        from vncmd import tracker

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
        """配了 -d 时走下载分支，不能被参数检查拦下"""
        from vncmd import tracker

        called = []
        monkeypatch.setattr(tracker, "load_settings", lambda name: {"sources": [1]})
        monkeypatch.setattr(tracker, "download_diff", lambda *a: called.append(a))
        monkeypatch.setattr(tracker, "_tracker_path", lambda name: Path("/tmp"))
        monkeypatch.setattr(Path, "is_dir", lambda self: True)
        monkeypatch.setattr(tracker, "get_download_dir", lambda: "/tmp")
        monkeypatch.setattr(tracker, "get_quality", lambda: 320000)
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
        """parser 默认为 None，“10”只在 cmd_search 里出现
        须防传给接口的值越界，服务端会回 code 400"""
        import vncmd.commands as commands
        from vncmd.net.api import SEARCH_LIMIT_MAX

        for json_flag in (False, True):
            for limit in (None, 1, 50, SEARCH_LIMIT_MAX):
                ns = argparse.Namespace(
                    query="x", count=limit, offset=0, json=json_flag
                )
                with unittest.mock.patch.object(
                    commands, "search", return_value={"songs": [], "total": 0}
                ) as fake:
                    commands.cmd_search(ns)
                sent = fake.call_args.kwargs["limit"]
                assert 1 <= sent <= SEARCH_LIMIT_MAX, (json_flag, limit, sent)

    def test_文档写的与help一致(self):
        """两边写的数都指面板，读 --count 那一行的“默认”列，须防数字漂移"""
        import re

        row = next(
            (
                line
                for line in self._doc("search.md").splitlines()
                if line.startswith("| `--count")
            ),
            None,
        )
        assert row, "文档的 search.md 里没有 --count 那一行"
        cells = [c.strip() for c in row.split("|")]
        assert len(cells) > 4, f"那一行没有「默认」列：{row}"
        hit = re.search(r"\d+", cells[3])
        assert hit, f"「默认」列里没有数字：{cells[3]}"
        assert int(hit.group()) == 10

    def test_help文本与面板默认值一致(self, capsys):
        """help 写死数字，断言面板分支实际取的数，避免改默认值时对不上"""
        import re

        with pytest.raises(SystemExit):
            _parse(["search", "--help"])
        out = capsys.readouterr().out
        hit = re.search(r"最大结果数，\d+-\d+（默认：(\d+)）", out)
        assert hit, f"help 里找不到默认值的说明：{out}"
        assert int(hit.group(1)) == 10
