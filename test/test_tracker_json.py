"""tracker 的纯读视图

四个动作（--fetch、--fetch-auto、-d、-d --diff）的结果都是文件而不是数据，
所以 `--json` 只配纯读视图。`--limit` / `--offset` 同样只切 JSON ——
纯读面板暂时没有曲目表，给了不报错也不生效，曲目表做完就自动接上。
"""

import argparse
import json

import pytest

from function import tracker


def db(n=5, updated_at="2026-10-01T00:00:00Z"):
    return {
        "updated_at": updated_at,
        "songs": [{"id": i, "title": f"曲目{i}"} for i in range(1, n + 1)],
    }


SETTINGS = {
    "description": "我的红心歌单",
    "sources": [{"type": "playlist", "ids": [819104208]}],
}


def ns(**kw):
    base = {
        "name": "like",
        "fetch": False,
        "fetch_auto": False,
        "download": False,
        "diff": False,
        "json": False,
        "limit": None,
        "offset": 0,
        "quality": None,
        "output": None,
    }
    base.update(kw)
    return argparse.Namespace(**base)


@pytest.fixture
def ready(monkeypatch, tmp_path):
    """让 cmd_tracker 认得像一个已经存在的 tracker"""
    (tmp_path / "like").mkdir()
    monkeypatch.setattr(tracker, "_tracker_path", lambda name: tmp_path / name)
    monkeypatch.setattr(tracker, "load_settings", lambda name: SETTINGS)
    monkeypatch.setattr(tracker, "load_songs_db_full", lambda name: db())
    return tmp_path


def parsed(capsys):
    got = capsys.readouterr()
    return json.loads(got.out), got.out, got.err


class Test动作与json互斥:
    @pytest.mark.parametrize(
        "action", [{"fetch": True}, {"fetch_auto": True}, {"download": True}]
    )
    def test_动作配json报错(self, ready, capsys, action):
        """动作的结果是文件，给一份没人读的 JSON 不如说清它只管纯读视图"""
        with pytest.raises(SystemExit) as exc:
            tracker.cmd_tracker(ns(json=True, **action))
        assert exc.value.code == 2
        assert "--json" in capsys.readouterr().err

    def test_检查在联网之前(self, ready, monkeypatch, capsys):
        """用户先等一轮拉取才发现参数写错了"""
        monkeypatch.setattr(
            tracker,
            "fetch_all_songs",
            lambda _s: pytest.fail("不该联网"),
        )
        with pytest.raises(SystemExit):
            tracker.cmd_tracker(ns(json=True, fetch=True))
        assert "联网" not in capsys.readouterr().err

    def test_纯读不给动作就正常(self, ready, capsys):
        tracker.cmd_tracker(ns(json=True))
        data, _out, _err = parsed(capsys)
        assert list(data) == ["tracker"]


class TestJSON形状:
    def test_用信封(self, ready, capsys):
        """裸的 {"updated_at", "songs"} 会让人以为这文件是某个命令的输出"""
        tracker.cmd_tracker(ns(json=True))
        data, _out, _err = parsed(capsys)
        assert list(data) == ["tracker"]
        assert set(data["tracker"]) == {"updated_at", "sources", "songs"}

    def test_带updated_at(self, ready, capsys):
        """判断数据有多旧的唯一依据"""
        tracker.cmd_tracker(ns(json=True))
        data, _out, _err = parsed(capsys)
        assert data["tracker"]["updated_at"] == "2026-10-01T00:00:00Z"

    def test_带sources(self, ready, capsys):
        tracker.cmd_tracker(ns(json=True))
        data, _out, _err = parsed(capsys)
        assert data["tracker"]["sources"] == SETTINGS["sources"]

    def test_songs直接取本地文件(self, ready, capsys):
        """不重新组装，面板与 JSON 出自同一份，不会漂"""
        tracker.cmd_tracker(ns(json=True))
        data, _out, _err = parsed(capsys)
        assert data["tracker"]["songs"] == db()["songs"]

    def test_不放diff(self, ready, capsys):
        """那是另一个文件、另一个语义（上次那一次的差异）"""
        tracker.cmd_tracker(ns(json=True))
        data, _out, _err = parsed(capsys)
        assert "diff" not in data["tracker"]


class Test切片:
    def _ids(self, capsys, **kw):
        tracker.cmd_tracker(ns(json=True, **kw))
        data, _out, _err = parsed(capsys)
        return [s["id"] for s in data["tracker"]["songs"]]

    def test_没给就全量(self, ready, capsys):
        assert self._ids(capsys) == [1, 2, 3, 4, 5]

    def test_给了limit就切(self, ready, capsys):
        assert self._ids(capsys, limit=2) == [1, 2]

    def test_只给offset就切到末尾(self, ready, capsys):
        assert self._ids(capsys, offset=3) == [4, 5]

    def test_offset加limit(self, ready, capsys):
        assert self._ids(capsys, offset=1, limit=2) == [2, 3]

    def test_超出范围给空数组(self, ready, capsys):
        """空的 songs 是合法结果，比空 stdout 加退出码 0 更好分"""
        assert self._ids(capsys, offset=99) == []


class Test面板显示更新时间:
    def test_面板带updated_at(self, ready, capsys):
        """三个月没更新的库，面板上与刚建的一样，看不出该不该再 --fetch"""
        tracker.cmd_tracker(ns(json=False))
        out = capsys.readouterr().out
        assert "2026-10-01T00:00:00Z" in out

    def test_没有更新时间就不给那一行(self, ready, monkeypatch, capsys):
        monkeypatch.setattr(
            tracker, "load_songs_db_full", lambda name: db(updated_at="")
        )
        tracker.cmd_tracker(ns(json=False))
        out = capsys.readouterr().out
        assert "更新于" not in out


class Test读整个库:
    def test_连updated_at一起读(self, monkeypatch, tmp_path):
        """load_songs_db 原来只返回 songs，把 updated_at 丢了"""
        path = tmp_path / "songs.json"
        path.write_text(
            json.dumps({"updated_at": "2026-01-01T00:00:00Z", "songs": [{"id": 1}]}),
            encoding="utf-8",
        )
        monkeypatch.setattr(tracker, "_songs_path", lambda name: path)
        got = tracker.load_songs_db_full("x")
        assert got["updated_at"] == "2026-01-01T00:00:00Z"
        assert got["songs"] == [{"id": 1}]

    def test_原函数仍只给songs(self, monkeypatch, tmp_path):
        path = tmp_path / "songs.json"
        path.write_text(
            json.dumps({"updated_at": "2026-01-01T00:00:00Z", "songs": [{"id": 1}]}),
            encoding="utf-8",
        )
        monkeypatch.setattr(tracker, "_songs_path", lambda name: path)
        assert tracker.load_songs_db("x") == [{"id": 1}]

    def test_主文件坏了退回备份(self, monkeypatch, tmp_path):
        """两处读文件的退回路径要一致，不能只有一处认 .bak"""
        path = tmp_path / "songs.json"
        path.write_text("{ 坏掉的", encoding="utf-8")
        (tmp_path / "songs.json.bak").write_text(
            json.dumps({"updated_at": "2026-02-02T00:00:00Z", "songs": [{"id": 9}]}),
            encoding="utf-8",
        )
        monkeypatch.setattr(tracker, "_songs_path", lambda name: path)
        got = tracker.load_songs_db_full("x")
        assert got["updated_at"] == "2026-02-02T00:00:00Z"
        assert got["songs"] == [{"id": 9}]


class Testparser:
    @pytest.mark.parametrize(
        ("argv", "attr", "want"),
        [
            (["--json"], "json", True),
            (["--limit", "2"], "limit", 2),
            (["-n", "2"], "limit", 2),
            (["--offset", "5"], "offset", 5),
        ],
    )
    def test_三个选项都在(self, argv, attr, want):
        from vncmd import build_parser

        assert (
            getattr(build_parser().parse_args(["tracker", "like", *argv]), attr) == want
        )

    def test_limit默认是None(self):
        from vncmd import build_parser

        args = build_parser().parse_args(["tracker", "like"])
        assert args.limit is None, "写成 0 就分不清用户是显式给了 0 还是没给"

    def test_json不与动作同组(self):
        """--json 与 --download 的互斥在 cmd_tracker 里手写，不是互斥组"""
        from vncmd import build_parser

        args = build_parser().parse_args(["tracker", "like", "--json", "-d"])
        assert args.json and args.download, "parser 层不该拦，交给 cmd_tracker 报错"
