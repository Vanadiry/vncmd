"""--diff 的 changed 与 JSON 输出"""

import argparse
import json
from pathlib import Path

import pytest

from vncmd import tracker


def ns(**kw):
    base = {
        "name": "like",
        "fetch": False,
        "auto_accept": False,
        "force": False,
        "download": False,
        "diff": False,
        "json": False,
        "count": None,
        "offset": 0,
    }
    base.update(kw)
    return argparse.Namespace(**base)


DIFF = {
    "updated_at": "2026-10-01T00:00:00Z",
    "added": [3],
    "removed": [{"id": 1, "title": "被删了"}],
    "changed": [{"id": 2, "title_old": "旧名", "title_new": "新名"}],
}


SONGS = [
    {"id": 1, "title": "被删了", "artist": "A", "publish_time": ""},
    {"id": 2, "title": "旧名", "artist": "A", "publish_time": ""},
    {
        "id": 3,
        "title": "新来的",
        "artist": "A",
        "publish_time": "2021-01-01 08:00:00",
    },
]


@pytest.fixture
def ready(monkeypatch, tmp_path):
    (tmp_path / "like").mkdir()
    monkeypatch.setattr(tracker, "_tracker_path", lambda name: tmp_path / name)
    monkeypatch.setattr(tracker, "load_diff", lambda name: dict(DIFF))
    (tmp_path / "like" / "songs.json").write_text(
        json.dumps({"updated_at": "", "songs": SONGS}, ensure_ascii=False),
        encoding="utf-8",
    )
    return tmp_path


def parsed(capsys):
    got = capsys.readouterr()
    return json.loads(got.out), got.out, got.err


class Test单独给diff要报错:
    def test_不配d也不配json就退出(self, ready, capsys):
        with pytest.raises(SystemExit) as exc:
            tracker.cmd_tracker(ns(diff=True))
        assert exc.value.code == 2

    def test_提示要说清配什么(self, ready, capsys):
        """只说“需要配合”却不说配合什么，等于没说"""
        with pytest.raises(SystemExit):
            tracker.cmd_tracker(ns(diff=True))
        err = capsys.readouterr().err
        assert "-d" in err and "--json" in err

    def test_检查在询问创建tracker之前(self, monkeypatch):
        asked = []

        class FakeConfirm:
            def ask(self):
                asked.append(1)
                return False

        monkeypatch.setattr(
            tracker.questionary, "confirm", lambda *a, **k: FakeConfirm()
        )
        with pytest.raises(SystemExit):
            tracker.cmd_tracker(ns(name="一个不存在的名字", diff=True))
        assert not asked, "参数写错时不该先去问要不要创建 tracker"

    def test_配了d就不报(self, ready, monkeypatch):
        monkeypatch.setattr(
            tracker, "load_songs_db_full", lambda n: {"updated_at": "", "songs": []}
        )
        ran = []
        monkeypatch.setattr(tracker, "download_diff", lambda *a, **k: ran.append(a))
        monkeypatch.setattr(tracker, "get_quality", lambda: 320000)
        monkeypatch.setattr(tracker, "get_download_dir", lambda: "/tmp")
        tracker.cmd_tracker(ns(diff=True, download=True, quality="320"))
        assert ran, "配了 -d 就该走下载 diff 那条路"


class Testchanged不再被丢:
    def test_正文含removed与changed(self):
        """改标题的曲目也要写进正文，不能整个消失"""
        note = tracker._diff_note(DIFF)
        assert "被删了" in note
        assert "旧名 -> 新名" in note

    def test_撤掉changed那段就会红(self):
        """锚定在 _diff_note 自己的源码上
        正则会匹配到函数外 resolve_conflicts 里的 if changed
        """
        import inspect

        src = inspect.getsource(tracker._diff_note)
        assert "title_old" in src, "_diff_note 里不该再读 changed"
        assert "title_new" in src
        assert 'changed = diff.get("changed", [])' in src

    def test_added不写进这个文件(self):
        """added 的曲目已下载，文件只记变了但不用下载的"""
        note = tracker._diff_note(DIFF)
        assert "新来的" not in note
        assert "3" not in note

    def test_标题写明两类各多少(self):
        note = tracker._diff_note(DIFF)
        assert "已从 Tracker 中移除（1 首）" in note
        assert "标题已变更（1 首）" in note

    def test_只有一类时只给那一类(self):
        note = tracker._diff_note({"removed": DIFF["removed"]})
        assert "被删了" in note
        assert "标题已变更" not in note

    def test_空diff不产内容(self):
        assert tracker._diff_note({"removed": [], "changed": []}).strip() == ""


class Test保存diff:
    def test_added只存id(self, ready):
        comparison = {
            "added": [{"id": 3, "title": "新来的", "artist": "A"}],
            "removed": [{"id": 1, "title": "被删了"}],
            "changed": [({"id": 2, "title": "旧名"}, {"id": 2, "title": "新名"})],
        }
        tracker.save_diff("like", comparison)
        data = json.loads((ready / "like" / "diff.json").read_text(encoding="utf-8"))
        assert data["added"] == [3]
        assert data["removed"] == [{"id": 1, "title": "被删了"}]
        assert data["changed"] == [{"id": 2, "title_old": "旧名", "title_new": "新名"}]


class Test下载diff落盘:
    def _fake_batch(self, monkeypatch, out):
        """假装真的下载过：得把会话目录建出来，代码才会往里写文件"""

        def fake(*_a, **_k):
            session = out / "session"
            session.mkdir(parents=True, exist_ok=True)
            return 1, 0, str(session)

        monkeypatch.setattr(tracker, "download_song_batch", fake)

    def test_added按id回songs_json取整条(self, ready, monkeypatch, tmp_path):
        got = {}

        def fake(songs, *_a, **_k):
            got["songs"] = songs
            session = tmp_path / "out" / "session"
            session.mkdir(parents=True, exist_ok=True)
            return 1, 0, str(session)

        monkeypatch.setattr(tracker, "download_song_batch", fake)
        tracker.download_diff("like", 320, str(tmp_path / "out"))
        assert got["songs"] == [SONGS[2]]

    def test_写changed_txt而不是removed_txt(self, ready, monkeypatch, tmp_path):
        """跑一次 --diff 只该拿一个文件，分成两个要自己记得上次那个还在不在"""
        out = tmp_path / "out"
        self._fake_batch(monkeypatch, out)
        tracker.download_diff("like", 320, str(out))
        assert (out / "session" / "changed.txt").exists()
        assert not (out / "session" / "removed.txt").exists()

    def test_两类都记进同一个文件(self, ready, monkeypatch, tmp_path):
        out = tmp_path / "out"
        self._fake_batch(monkeypatch, out)
        tracker.download_diff("like", 320, str(out))
        text = (out / "session" / "changed.txt").read_text(encoding="utf-8")
        assert "被删了" in text
        assert "旧名 -> 新名" in text

    def test_没有新增时文件落在输出目录(self, ready, monkeypatch, tmp_path):
        monkeypatch.setattr(
            tracker, "load_diff", lambda n: {"changed": DIFF["changed"]}
        )
        out = tmp_path / "out"
        tracker.download_diff("like", 320, str(out))
        assert (out / "changed.txt").exists()

    def test_三类都空时给提示(self, ready, monkeypatch, capsys):
        monkeypatch.setattr(
            tracker, "load_diff", lambda n: {"added": [], "removed": [], "changed": []}
        )
        tracker.download_diff("like", 320, "/tmp/x")
        assert "--fetch" in capsys.readouterr().err

    def test_只有changed时不再说未找到diff(self, ready, monkeypatch, tmp_path, capsys):
        """只看 added 与 removed 时，changed 非空会被当成没有 diff"""
        monkeypatch.setattr(
            tracker, "load_diff", lambda n: {"changed": DIFF["changed"]}
        )
        tracker.download_diff("like", 320, str(tmp_path / "out"))
        assert "未找到 diff" not in capsys.readouterr().err


class TestJsonDiff:
    def test_三类都在(self, ready, capsys):
        tracker.cmd_tracker(ns(diff=True, json=True))
        data, _out, _err = parsed(capsys)
        got = data["tracker"]["diff"]
        assert set(got) >= {"added", "removed", "changed"}
        assert got["added"] == [3]
        assert len(got["removed"]) == 1
        assert len(got["changed"]) == 1

    def test_与下载读的是同一份(self, ready, capsys):
        """--json 只是换成机器可读，不换数据"""
        tracker.cmd_tracker(ns(diff=True, json=True))
        data, _out, _err = parsed(capsys)
        assert data["tracker"]["diff"]["updated_at"] == DIFF["updated_at"]

    def test_不联网(self, ready, monkeypatch, capsys):
        monkeypatch.setattr(
            tracker, "fetch_all_songs", lambda _s: pytest.fail("不该联网")
        )
        tracker.cmd_tracker(ns(diff=True, json=True))
        assert "diff" in parsed(capsys)[0]["tracker"]

    def test_带updated_at(self, ready, capsys):
        """判断这批差异何时算出来，唯一依据为它"""
        tracker.cmd_tracker(ns(diff=True, json=True))
        data, _out, _err = parsed(capsys)
        assert data["tracker"]["diff"]["updated_at"] == "2026-10-01T00:00:00Z"

    def test_不给diff时不给songs(self, ready, monkeypatch, capsys):
        monkeypatch.setattr(
            tracker, "load_songs_db_full", lambda n: {"updated_at": "", "songs": []}
        )
        tracker.cmd_tracker(ns(diff=True, json=True))
        data, _out, _err = parsed(capsys)
        assert "songs" not in data["tracker"], "给 diff 时不该混入当前状态"

    def test_没有diff文件也给合法json(self, ready, monkeypatch, capsys):
        """空 diff 加退出码 0，脚本分不清“没变化”与“跑挂了”"""
        monkeypatch.setattr(tracker, "load_diff", lambda n: {})
        tracker.cmd_tracker(ns(diff=True, json=True))
        data, _out, _err = parsed(capsys)
        assert data["tracker"]["diff"] == {}


class Testparser:
    def test_help写明配什么(self):
        """从 -d 过来的用户会以为 --diff 只能配 -d"""
        from vncmd.cli import build_parser

        with pytest.raises(SystemExit):
            build_parser().parse_args(["tracker", "like", "--help"])
        out = _out_of(["tracker", "like", "--help"])
        assert "--json" in out, "help 要说清还能配 --json"

    def test_diff与json不互斥(self):
        from vncmd.cli import build_parser

        args = build_parser().parse_args(["tracker", "like", "--diff", "--json"])
        assert args.diff and args.json, "两者互补，parser 层不该拦"


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


class Test下载时取配置里的音质与目录:
    """tracker 的下载从配置取音质与目录
    读 args.quality 会 AttributeError，写死则配置永远不生效
    """

    def test_音质来自配置(self, monkeypatch):
        看到 = []
        monkeypatch.setattr(
            tracker, "load_songs_db_full", lambda n: {"updated_at": "", "songs": []}
        )
        monkeypatch.setattr(tracker, "load_settings", lambda n: {"sources": []})
        monkeypatch.setattr(tracker, "_tracker_path", lambda n: Path("/tmp"))
        monkeypatch.setattr(Path, "is_dir", lambda self: True)
        monkeypatch.setattr(tracker, "get_quality", lambda: 192000)
        monkeypatch.setattr(tracker, "get_download_dir", lambda: "/tmp")
        monkeypatch.setattr(tracker, "download_tracker", lambda *a: 看到.append(a))
        tracker.cmd_tracker(ns(download=True))
        assert 看到 and 看到[0][1] == 192000, f"没取配置里的音质：{看到}"

    def test_输出目录来自配置(self, monkeypatch):
        看到 = []
        monkeypatch.setattr(
            tracker, "load_songs_db_full", lambda n: {"updated_at": "", "songs": []}
        )
        monkeypatch.setattr(tracker, "load_settings", lambda n: {"sources": []})
        monkeypatch.setattr(tracker, "_tracker_path", lambda n: Path("/tmp"))
        monkeypatch.setattr(Path, "is_dir", lambda self: True)
        monkeypatch.setattr(tracker, "get_quality", lambda: 320000)
        monkeypatch.setattr(tracker, "get_download_dir", lambda: "/配置里的目录")
        monkeypatch.setattr(tracker, "download_tracker", lambda *a: 看到.append(a))
        tracker.cmd_tracker(ns(download=True))
        assert 看到 and 看到[0][2] == "/配置里的目录", f"没取配置里的目录：{看到}"
