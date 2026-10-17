"""tracker 的曲目表与 artist 入库

`songs.json` 里每条原来只有 `{id, title}`。`fetch_all_songs` 的 `raw`
里已经解析过 artist（`removed` 那条一直在用 `rt.get("artist", "")`），
只是没往下带 —— 补一个字段即可，不需要重新拉历史数据。
"""

import argparse
import json

import pytest
from rich.console import Console

from function import tracker


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


def songs(n=200, with_artist=True):
    out = []
    for i in range(1, n + 1):
        s = {"id": i, "title": f"曲目{i}"}
        if with_artist:
            s["artist"] = f"艺术家{i % 3}"
        out.append(s)
    return out


def db(n=200, with_artist=True):
    return {
        "updated_at": "2026-10-01T00:00:00Z",
        "songs": songs(n, with_artist),
    }


def parsed(capsys):
    got = capsys.readouterr()
    return json.loads(got.out), got.out, got.err


@pytest.fixture
def ready(monkeypatch, tmp_path):
    (tmp_path / "like").mkdir()
    monkeypatch.setattr(tracker, "_tracker_path", lambda name: tmp_path / name)
    monkeypatch.setattr(
        tracker,
        "load_settings",
        lambda name: {"description": "我的红心", "sources": []},
    )
    monkeypatch.setattr(tracker, "load_songs_db", lambda name: songs())
    monkeypatch.setattr(tracker, "load_songs_db_full", lambda name: db())
    return tmp_path


class TestArtist入库:
    def test_raw里存了artist(self):
        """fetch_all_songs 的 raw 早就解析过 artist，只是没往下带。

        走 fetch_all_songs 要联网，所以直接测它拼 raw 的那一步。
        """
        raw = {}
        tracker._add_to_raw(raw, {"id": 1, "title": "T", "artist": "A"}, "album", 5)
        assert raw[1]["artist"] == "A"

    def test_entry把artist带进结果(self):
        """raw 存了不算完，entry 那一段也得往下带，否则存不进 songs.json"""
        import inspect

        src = inspect.getsource(tracker.fetch_all_songs)
        assert '"artist": data.get("artist", "")' in src, "entry 少了 artist"

    def test_曲目没有artist时留空(self):
        raw = {}
        tracker._add_to_raw(raw, {"id": 1, "title": "T"}, "song", 5)
        assert raw[1]["artist"] == "", "缺了就留空，不要回退到现查 API"

    def test_同一首来自多个源时artist一致(self):
        raw = {}
        tracker._add_to_raw(raw, {"id": 1, "title": "T", "artist": "A"}, "album", 1)
        tracker._add_to_raw(raw, {"id": 1, "title": "T", "artist": "B"}, "playlist", 2)
        # 第一次解析到的为准，第二次只补 source_ref
        assert raw[1]["artist"] == "A"
        assert len(raw[1]["sources"]) == 2

    def test_老库读出来仍能用(self):
        """老条目是没有 artist 键，不是值为空串，下游一律 .get 而非 ["artist"]"""
        old = db(with_artist=False)["songs"][0]
        assert "artist" not in old
        assert old.get("artist", "") == "", "缺键时给空串，表格那一列才有东西可填"

    def test_保存后artist进json(self, monkeypatch, tmp_path):
        captured = {}
        monkeypatch.setattr(
            tracker, "save_songs_db", lambda n, s: captured.update(songs=s)
        )
        merged = [{"id": 1, "title": "T", "artist": "A"}]
        tracker.save_songs_db("x", merged)
        assert captured["songs"][0]["artist"] == "A"


class Test曲目表:
    @pytest.fixture(autouse=True)
    def wide(self, monkeypatch):
        """宽度固定，否则 rich 把标题折行，断言的字符串就断了"""
        monkeypatch.setattr(tracker, "console", Console(width=200))

    def test_四列(self, ready, capsys):
        tracker.cmd_tracker(ns())
        out = capsys.readouterr().out
        for col in ("#", "ID", "标题", "艺术家"):
            assert col in out, f"少了 {col} 列"

    def test_序号是绝对的(self, ready, capsys):
        tracker.cmd_tracker(ns(offset=100, limit=3))
        out = capsys.readouterr().out
        rows = [
            ln
            for ln in out.splitlines()
            if ln.startswith("│") and ln.split("│")[1].strip().isdigit()
        ]
        assert [ln.split("│")[1].strip() for ln in rows] == ["101", "102", "103"]

    def test_标题带区间(self, ready, capsys):
        tracker.cmd_tracker(ns(offset=5, limit=3))
        assert "6-8/20" in capsys.readouterr().out

    def test_不给offset也给区间(self, ready, capsys):
        tracker.cmd_tracker(ns(limit=10))
        assert "1-10/200" in capsys.readouterr().out

    def test_默认十条(self, ready, capsys):
        tracker.cmd_tracker(ns())
        assert "1-10/200" in capsys.readouterr().out

    def test_超出范围给提示(self, ready, capsys):
        tracker.cmd_tracker(ns(offset=999))
        assert "超出范围（共 200 首）" in capsys.readouterr().out

    def test_没有artist的老条目那一列是空的(self, ready, monkeypatch, capsys):
        monkeypatch.setattr(
            tracker, "load_songs_db", lambda n: songs(with_artist=False)
        )
        tracker.cmd_tracker(ns(limit=2))
        out = capsys.readouterr().out
        assert "曲目1" in out, "老条目照样要能看，不能因为缺 artist 就整表不显示"

    def test_空库不给表(self, ready, monkeypatch, capsys):
        monkeypatch.setattr(tracker, "load_songs_db", lambda n: [])
        tracker.cmd_tracker(ns())
        out = capsys.readouterr().out
        assert "已缓存曲目 -" not in out


class TestLimitOffset现在对面板生效:
    def test_help不再说只作用于json(self):
        """曲目表做完了，那句得删"""

        out = _out_of(["tracker", "like", "--help"])
        assert "只作用于 --json" not in out

    def test_json仍然切片(self, ready, capsys):
        tracker.cmd_tracker(ns(json=True, limit=2, offset=3))
        data, _out, _err = parsed(capsys)
        assert [s["id"] for s in data["tracker"]["songs"]] == [4, 5]


class TestJson带artist:
    def test_json里的song有artist(self, ready, capsys):
        tracker.cmd_tracker(ns(json=True, limit=1))
        data, _out, _err = parsed(capsys)
        assert data["tracker"]["songs"][0]["artist"] == "艺术家1"

    def test_老条目没有artist键也照样输出(self, ready, monkeypatch, capsys):
        """不补键：那会让 songs.json 的形状随是否 fetch 过而变"""
        monkeypatch.setattr(
            tracker, "load_songs_db_full", lambda n: db(with_artist=False)
        )
        tracker.cmd_tracker(ns(json=True, limit=1))
        data, _out, _err = parsed(capsys)
        assert data["tracker"]["songs"][0] == {"id": 1, "title": "曲目1"}


def _out_of(argv):
    import io
    import re
    from contextlib import redirect_stdout

    from vncmd import build_parser

    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            build_parser().parse_args(argv)
    except SystemExit:
        pass
    return re.sub(r"\x1b\[[0-9;]*m", "", buf.getvalue())
