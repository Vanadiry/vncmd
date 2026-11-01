"""tool embed-id 的参数校验骨架"""

import argparse
import json

import pytest

from vncmd import commands


def ns(path, *, set_id=None, from_file=None, recursive=False):
    return argparse.Namespace(
        path=str(path),
        set_id=set_id,
        from_file=None if from_file is None else str(from_file),
        recursive=recursive,
    )


@pytest.fixture
def audio_file(tmp_path):
    path = tmp_path / "track.flac"
    path.write_bytes(b"")
    return path


@pytest.fixture
def no_trackers(monkeypatch, tmp_path):
    monkeypatch.setattr(commands, "VNCMD_HOME", tmp_path)
    return tmp_path


class TestParser:
    def test_默认值(self):
        from vncmd.cli import build_parser

        args = build_parser().parse_args(["tool", "embed-id", "x"])
        assert args.tool == "embed-id"
        assert args.from_file is None
        assert args.set_id is None
        assert args.recursive is False

    def test_参数都能解析(self):
        from vncmd.cli import build_parser

        args = build_parser().parse_args(
            ["tool", "embed-id", "x", "--from", "songs.json", "-r", "--set", "123"]
        )
        assert args.from_file == "songs.json"
        assert args.set_id == "123"
        assert args.recursive is True


class Test路径:
    def test_路径不存在先报(self, capsys, no_trackers):
        with pytest.raises(SystemExit) as exc:
            commands.cmd_embed_id(ns("/tmp/no-such-path"))
        assert exc.value.code == 1
        assert "路径不存在" in capsys.readouterr().err

    def test_路径不存在时先于set校验(self, capsys, no_trackers):
        with pytest.raises(SystemExit) as exc:
            commands.cmd_embed_id(ns("/tmp/no-such-path", set_id="abc"))
        assert exc.value.code == 1
        assert "路径不存在" in capsys.readouterr().err


class TestSet:
    def test_非数字退二(self, capsys, audio_file):
        with pytest.raises(SystemExit) as exc:
            commands.cmd_embed_id(ns(audio_file, set_id="abc"))
        assert exc.value.code == 2
        assert "纯数字" in capsys.readouterr().err

    def test_全角数字也不接受(self, capsys, audio_file):
        with pytest.raises(SystemExit) as exc:
            commands.cmd_embed_id(ns(audio_file, set_id="１２３"))
        assert exc.value.code == 2

    def test_目录不能用set(self, capsys, tmp_path):
        with pytest.raises(SystemExit) as exc:
            commands.cmd_embed_id(ns(tmp_path, set_id="123"))
        assert exc.value.code == 2
        assert "单个文件" in capsys.readouterr().err

    def test_不支持的格式不能用set(self, capsys, tmp_path):
        path = tmp_path / "track.m4a"
        path.write_bytes(b"")
        with pytest.raises(SystemExit) as exc:
            commands.cmd_embed_id(ns(path, set_id="123"))
        assert exc.value.code == 2
        assert "MP3 与 FLAC" in capsys.readouterr().err

    def test_大写后缀也接受(self, capsys, tmp_path):
        path = tmp_path / "track.FLAC"
        path.write_bytes(b"")
        commands.cmd_embed_id(ns(path, set_id="123"))
        assert "尚未实现" in capsys.readouterr().err

    def test_给了set就不读from(self, capsys, audio_file):
        commands.cmd_embed_id(
            ns(audio_file, set_id="123", from_file="/tmp/不存在.json")
        )
        assert "尚未实现" in capsys.readouterr().err


class TestFrom:
    def test_文件不存在退一(self, capsys, audio_file):
        with pytest.raises(SystemExit) as exc:
            commands.cmd_embed_id(ns(audio_file, from_file="/tmp/不存在.json"))
        assert exc.value.code == 1
        assert "--from 文件不存在" in capsys.readouterr().err

    def test_文件解析失败退一(self, capsys, audio_file, tmp_path):
        source = tmp_path / "bad.json"
        source.write_text("{坏", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            commands.cmd_embed_id(ns(audio_file, from_file=source))
        assert exc.value.code == 1
        assert "无法解析" in capsys.readouterr().err

    def test_文件能解析就进入占位(self, capsys, audio_file, tmp_path):
        source = tmp_path / "songs.json"
        source.write_text(json.dumps({"songs": []}), encoding="utf-8")
        commands.cmd_embed_id(ns(audio_file, from_file=source))
        assert "尚未实现" in capsys.readouterr().err


class Test没有来源:
    def test_没有tracker时提示from(self, capsys, audio_file, no_trackers):
        with pytest.raises(SystemExit) as exc:
            commands.cmd_embed_id(ns(audio_file))
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "未找到 Tracker 曲目库" in err
        assert "--from" in err

    def test_有tracker时进入占位(self, capsys, audio_file, no_trackers):
        tracker_dir = no_trackers / "tracker" / "like"
        tracker_dir.mkdir(parents=True)
        (tracker_dir / "songs.json").write_text(
            json.dumps({"songs": []}), encoding="utf-8"
        )
        commands.cmd_embed_id(ns(audio_file))
        assert "尚未实现" in capsys.readouterr().err
