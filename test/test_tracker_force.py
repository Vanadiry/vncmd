"""`--fetch` 的两个修饰

`--fetch-auto` 退休成 `--fetch --auto-accept`，另加 `--force`。
两者都是 `--fetch` 的修饰，不是独立动作 —— 与 `--diff` 是 `-d` 的修饰同一个模式。
"""

import argparse

import pytest

from vncmd import tracker


def ns(**kw):
    base = {
        "name": "like",
        "fetch": False,
        "download": False,
        "diff": False,
        "json": False,
        "auto_accept": False,
        "force": False,
        "count": None,
        "offset": 0,
    }
    base.update(kw)
    return argparse.Namespace(**base)


SETTINGS = {"description": "d", "sources": [{"type": "playlist", "ids": [1]}]}


def songs(n=5):
    return [{"id": i, "title": f"T{i}", "artist": "A"} for i in range(1, n + 1)]


@pytest.fixture
def ready(monkeypatch, tmp_path):
    """一个已存在的 tracker，fetch 回来的结果固定"""
    (tmp_path / "like").mkdir()
    monkeypatch.setattr(tracker, "_tracker_path", lambda name: tmp_path / name)
    monkeypatch.setattr(tracker, "load_settings", lambda name: SETTINGS)
    monkeypatch.setattr(
        tracker, "fetch_all_songs", lambda s: ({s["id"]: s for s in songs()}, [])
    )
    monkeypatch.setattr(tracker, "load_songs_db", lambda name: songs(3))
    return tmp_path


class Test修饰必须配fetch:
    @pytest.mark.parametrize(
        ("flag", "shown"),
        [("auto_accept", "--auto-accept"), ("force", "--force")],
    )
    def test_单独给报错(self, ready, capsys, flag, shown):
        with pytest.raises(SystemExit) as exc:
            tracker.cmd_tracker(ns(**{flag: True}))
        assert exc.value.code == 2
        assert shown in capsys.readouterr().err

    def test_提示要说清是修饰(self, ready, capsys):
        """只说「需要配合 --fetch」不说为什么，用户会以为那是个 bug"""
        with pytest.raises(SystemExit):
            tracker.cmd_tracker(ns(force=True))
        err = capsys.readouterr().err
        assert "修饰" in err, err

    def test_检查在联网之前(self, ready, monkeypatch):
        monkeypatch.setattr(
            tracker, "fetch_all_songs", lambda s: pytest.fail("不该联网")
        )
        with pytest.raises(SystemExit):
            tracker.cmd_tracker(ns(auto_accept=True))
        # 能走到 SystemExit 就说明没联网

    def test_配了fetch就不报(self, ready, monkeypatch):
        ran = []
        monkeypatch.setattr(
            tracker, "save_songs_db", lambda n, s: ran.append(("db", len(s)))
        )
        monkeypatch.setattr(tracker, "save_diff", lambda n, c: ran.append(("diff",)))
        tracker.cmd_tracker(ns(fetch=True, force=True))
        assert ("db", 5) in ran


class Test互斥:
    def test_parser层就拦下(self):
        from vncmd.cli import build_parser

        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args(
                ["tracker", "like", "-f", "--force", "--auto-accept"]
            )
        assert exc.value.code == 2

    def test_fetch_auto已经不存在(self):
        """退休了就不该再接受这个拼法，否则用户以为还有效"""
        from vncmd.cli import build_parser

        with pytest.raises(SystemExit):
            build_parser().parse_args(["tracker", "like", "--fetch-auto"])


class TestForce:
    def test_无条件覆盖(self, ready, monkeypatch):
        got = {}
        monkeypatch.setattr(tracker, "save_songs_db", lambda n, s: got.update(n=s))
        tracker.cmd_tracker(ns(fetch=True, force=True))
        assert [s["id"] for s in got["n"]] == [1, 2, 3, 4, 5]

    def test_无变更也覆盖(self, ready, monkeypatch):
        """无变更不动是那两个 resolve 的行为，--force 恰恰要写库"""
        monkeypatch.setattr(tracker, "load_songs_db", lambda name: songs())
        called = []
        monkeypatch.setattr(tracker, "save_songs_db", lambda n, s: called.append(1))
        tracker.cmd_tracker(ns(fetch=True, force=True))
        assert called, "无变更时也该覆盖"

    def test_无变更时diff不写(self, ready, monkeypatch):
        monkeypatch.setattr(tracker, "load_songs_db", lambda name: songs())
        written = []
        monkeypatch.setattr(tracker, "save_diff", lambda n, c: written.append(1))
        tracker.cmd_tracker(ns(fetch=True, force=True))
        assert not written, "没变更时 diff 该保持原样"

    def test_无变更时说清diff没更新(self, ready, monkeypatch, capsys):
        """「覆盖了但 diff 没变」用户看不到，不说就以为 diff 已是新的"""
        monkeypatch.setattr(tracker, "load_songs_db", lambda name: songs())
        monkeypatch.setattr(tracker, "save_songs_db", lambda n, s: None)
        tracker.cmd_tracker(ns(fetch=True, force=True))
        err = capsys.readouterr().err
        assert "diff" in err and "保持" in err, err

    def test_有变更时diff照写(self, ready, monkeypatch):
        written = []
        monkeypatch.setattr(tracker, "save_songs_db", lambda n, s: None)
        monkeypatch.setattr(tracker, "save_diff", lambda n, c: written.append(1))
        tracker.cmd_tracker(ns(fetch=True, force=True))
        assert written, "有变更时 diff 该更新"

    def test_覆盖了要报首数(self, ready, monkeypatch, capsys):
        monkeypatch.setattr(tracker, "save_songs_db", lambda n, s: None)
        tracker.cmd_tracker(ns(fetch=True, force=True))
        assert "5 首" in capsys.readouterr().err

    def test_不弹交互(self, ready, monkeypatch):
        monkeypatch.setattr(
            tracker, "resolve_conflicts", lambda *a: pytest.fail("不该弹交互")
        )
        monkeypatch.setattr(tracker, "save_songs_db", lambda n, s: None)
        tracker.cmd_tracker(ns(fetch=True, force=True))

    def test_照常算diff而不是绕过(self, ready, monkeypatch):
        """绕过 diff 就没法知道该不该更新 diff.json 了"""
        seen = []
        monkeypatch.setattr(
            tracker,
            "compare_songs",
            lambda f, c: (
                seen.append((f, c)) or {"added": [], "removed": [], "changed": []}
            ),
        )
        monkeypatch.setattr(tracker, "save_songs_db", lambda n, s: None)
        tracker.cmd_tracker(ns(fetch=True, force=True))
        assert seen, "应该先算 diff"


class TestAutoAccept:
    def test_走auto_resolve(self, ready, monkeypatch):
        ran = []
        monkeypatch.setattr(
            tracker, "auto_resolve", lambda c, cached, fresh: ran.append(1) or songs()
        )
        monkeypatch.setattr(tracker, "save_songs_db", lambda n, s: None)
        monkeypatch.setattr(tracker, "save_diff", lambda n, c: None)
        tracker.cmd_tracker(ns(fetch=True, auto_accept=True))
        assert ran

    def test_不弹交互(self, ready, monkeypatch):
        monkeypatch.setattr(
            tracker, "resolve_conflicts", lambda *a: pytest.fail("不该弹交互")
        )
        monkeypatch.setattr(tracker, "auto_resolve", lambda c, cached, fresh: songs())
        monkeypatch.setattr(tracker, "save_songs_db", lambda n, s: None)
        monkeypatch.setattr(tracker, "save_diff", lambda n, c: None)
        tracker.cmd_tracker(ns(fetch=True, auto_accept=True))

    def test_无变更时不写(self, ready, monkeypatch):
        monkeypatch.setattr(tracker, "load_songs_db", lambda name: songs())
        called = []
        monkeypatch.setattr(tracker, "save_songs_db", lambda n, s: called.append(1))
        tracker.cmd_tracker(ns(fetch=True, auto_accept=True))
        assert not called, "无变更时 auto_accept 不该动库"

    def test_不给修饰时走交互(self, ready, monkeypatch):
        ran = []
        monkeypatch.setattr(
            tracker,
            "resolve_conflicts",
            lambda c, cached, fresh: ran.append(1) or songs(),
        )
        monkeypatch.setattr(tracker, "save_songs_db", lambda n, s: None)
        monkeypatch.setattr(tracker, "save_diff", lambda n, c: None)
        tracker.cmd_tracker(ns(fetch=True))
        assert ran


class TestHelp:
    def test_force写明只回退一步(self, capsys):
        """`.bak` 连续两次 force 会被顶掉，这句话得在 help 里说"""

        out = _out_of(["tracker", "like", "--help"])
        assert "备份" in out and "顶掉" in out, out

    def test_auto_accept与force都在(self, capsys):

        out = _out_of(["tracker", "like", "--help"])
        assert "--auto-accept" in out and "--force" in out

    def test_都不在互斥组里(self):
        """它们是 --fetch 的修饰，与 --fetch 同给才合法，所以不该进顶层组"""
        from vncmd.cli import build_parser

        args = build_parser().parse_args(["tracker", "like", "-f", "--force"])
        assert args.fetch and args.force


def _out_of(argv):
    import io
    import re
    from contextlib import redirect_stdout

    from vncmd.cli import build_parser

    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            build_parser().parse_args(argv)
    except SystemExit:
        pass
    return re.sub(r"\x1b\[[0-9;]*m", "", buf.getvalue())
