"""Tracker 数据版本规则"""

import argparse
import json

import pytest

from vncmd import tracker
from vncmd.core import data_version_checker as checker
from vncmd.core import data_version_rules as rules


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


def db(version):
    return {
        "version": version,
        "updated_at": "",
        "songs": [{"id": 1, "title": "T", "artists": ["A"]}],
    }


@pytest.fixture
def ready(monkeypatch, tmp_path):
    (tmp_path / "like").mkdir()
    monkeypatch.setattr(tracker, "_tracker_path", lambda name: tmp_path / name)
    monkeypatch.setattr(
        tracker,
        "load_settings",
        lambda name: {"description": "", "sources": []},
    )
    return tmp_path


class Test规则:
    def test_版本0放行但提示fF(self):
        decision = checker.check(0, "tracker.view", name="like")

        assert decision.allowed is True
        assert "-fF" in decision.message

    def test_版本1静默(self):
        decision = checker.check(1, "tracker.view", name="like")

        assert decision.allowed is True
        assert decision.message is None

    def test_高版本只放行fF(self):
        blocked = checker.check(2, "tracker.view", name="like")
        allowed = checker.check(2, "tracker.fetch_force", name="like")

        assert blocked.allowed is False
        assert "升级 vncmd" in blocked.message
        assert allowed.allowed is True
        assert "-fF" in allowed.message

    @pytest.mark.parametrize("version", ["x", -1, True, 1.5])
    def test_异常版本只放行fF(self, version):
        blocked = checker.check(version, "tracker.view", name="like")
        allowed = checker.check(version, "tracker.fetch_force", name="like")

        assert blocked.allowed is False
        assert allowed.allowed is True

    def test_embed_id只允许v1(self):
        assert checker.check(0, "embed_id.use").allowed is False
        assert checker.check(1, "embed_id.use").allowed is True
        assert checker.check(2, "embed_id.use").allowed is False

    def test_操作覆盖所有分支(self):
        assert tracker._tracker_permission(ns()) == "tracker.view"
        assert tracker._tracker_permission(ns(json=True)) == "tracker.view_json"
        assert tracker._tracker_permission(ns(fetch=True)) == "tracker.fetch"
        assert tracker._tracker_permission(ns(fetch=True, auto_accept=True)) == (
            "tracker.fetch_auto"
        )
        assert (
            tracker._tracker_permission(ns(fetch=True, force=True))
            == "tracker.fetch_force"
        )
        assert tracker._tracker_permission(ns(download=True)) == "tracker.download"
        assert tracker._tracker_permission(ns(download=True, diff=True)) == (
            "tracker.diff_download"
        )
        assert tracker._tracker_permission(ns(json=True, diff=True)) == (
            "tracker.diff_json"
        )

    def test_规则里没有未请求的权限(self):
        requested = {
            "tracker.view",
            "tracker.view_json",
            "tracker.fetch",
            "tracker.fetch_auto",
            "tracker.fetch_force",
            "tracker.download",
            "tracker.diff_download",
            "tracker.diff_json",
            "embed_id.use",
        }
        all_rules = (
            *rules.TRACKER_RULES.values(),
            *rules.EMBED_ID_RULES.values(),
            rules.FUTURE_TRACKER_RULE,
            rules.INVALID_TRACKER_RULE,
            rules.FUTURE_EMBED_RULE,
            rules.INVALID_EMBED_RULE,
        )
        for rule in all_rules:
            assert rule.permissions <= requested

    def test_未知权限命名空间报错(self):
        with pytest.raises(ValueError):
            checker.check(1, "unknown.permission")


class Test版本检查:
    def test_版本0提示但JSON仍合法(self, ready, monkeypatch, capsys):
        monkeypatch.setattr(tracker, "load_songs_db_full", lambda name: db(0))

        tracker.cmd_tracker(ns(json=True, count=1))

        got = capsys.readouterr()
        assert "-fF" in got.err
        assert json.loads(got.out)["tracker"]["songs"][0]["id"] == 1

    def test_版本1静默(self, ready, monkeypatch, capsys):
        monkeypatch.setattr(tracker, "load_songs_db_full", lambda name: db(1))

        tracker.cmd_tracker(ns(json=True, count=1))

        assert capsys.readouterr().err == ""

    def test_高版本阻断普通操作(self, ready, monkeypatch, capsys):
        monkeypatch.setattr(tracker, "load_songs_db_full", lambda name: db(2))

        with pytest.raises(SystemExit) as exc:
            tracker.cmd_tracker(ns(json=True, count=1))

        assert exc.value.code == 1
        assert "升级 vncmd" in capsys.readouterr().err

    def test_缺版本按0处理(self, ready, monkeypatch, capsys):
        monkeypatch.setattr(
            tracker,
            "load_songs_db_full",
            lambda name: {"version": 0, "updated_at": "", "songs": []},
        )
        tracker.cmd_tracker(ns(json=True, count=1))
        assert "-fF" in capsys.readouterr().err


class Test版本写入:
    def test_新建Tracker写1(self, monkeypatch, tmp_path):
        monkeypatch.setattr(tracker, "_tracker_path", lambda name: tmp_path / name)

        tracker.create_tracker("like")

        data = json.loads((tmp_path / "like" / "songs.json").read_text())
        assert data["version"] == 1

    def test_普通保存保持版本(self, ready):
        tracker.save_songs_db("like", [{"id": 1, "title": "T"}], version=0)

        data = json.loads((ready / "like" / "songs.json").read_text())
        assert data["version"] == 0

    def test_fF写当前版本(self, ready):
        tracker._apply_force(
            "like",
            {1: {"id": 1, "title": "T", "artists": ["A"]}},
            {"added": [], "removed": [], "changed": []},
        )

        data = json.loads((ready / "like" / "songs.json").read_text())
        assert data["version"] == rules.CURRENT_TRACKER_VERSION
