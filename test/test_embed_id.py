"""tool embed-id 的参数校验骨架"""

import argparse
import json
import struct

import pytest

from vncmd import commands
from vncmd.media.metadata import embed, read_track_id, write_track_id

# MPEG1 Layer3 128kbps 44100Hz 一帧为帧头 4 字节加 413 字节数据
_MP3_FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 413


def _make_mp3(path):
    path.write_bytes(_MP3_FRAME * 4)


def _make_flac(path):
    si = struct.pack(
        ">HH3s3sQ16s",
        4096,
        4096,
        b"\x00\x00\x00",
        b"\x00\x00\x00",
        0xAC44020F00000000,
        b"\x00" * 16,
    )
    path.write_bytes(b"fLaC\x80\x00\x00\x22" + si)


def _tagged_flac(path, title, artist):
    _make_flac(path)
    embed(
        str(path),
        "flac",
        cover_data=None,
        cover_mime=None,
        lyric_text=None,
        song_title=title,
        song_artist=artist,
        song_album=None,
        publish_time=None,
    )


def _songs_source(path, *songs):
    path.write_text(json.dumps({"songs": list(songs)}), encoding="utf-8")
    return path


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
    _make_flac(path)
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
        _make_flac(path)
        commands.cmd_embed_id(ns(path, set_id="123"))
        assert "已写入" in capsys.readouterr().err

    def test_给了set就不读from(self, capsys, audio_file):
        commands.cmd_embed_id(
            ns(audio_file, set_id="123", from_file="/tmp/不存在.json")
        )
        assert "已写入" in capsys.readouterr().err


class TestSet写入:
    def test_flac写入(self, capsys, audio_file):
        commands.cmd_embed_id(ns(audio_file, set_id="3424255901"))

        assert read_track_id(str(audio_file)) == ["3424255901"]
        assert "已写入" in capsys.readouterr().err

    def test_mp3写入(self, capsys, tmp_path):
        path = tmp_path / "track.mp3"
        _make_mp3(path)

        commands.cmd_embed_id(ns(path, set_id="121212124"))

        assert read_track_id(str(path)) == ["121212124"]

    def test_已有相同值不重复写(self, capsys, monkeypatch, audio_file):
        write_track_id(str(audio_file), 3424255901)
        calls = []
        monkeypatch.setattr(commands, "write_track_id", lambda *a: calls.append(a))

        commands.cmd_embed_id(ns(audio_file, set_id="3424255901"))

        assert calls == []
        assert "已是最新" in capsys.readouterr().err

    def test_已有不同值直接覆盖(self, capsys, audio_file):
        write_track_id(str(audio_file), 999)

        commands.cmd_embed_id(ns(audio_file, set_id="3424255901"))

        assert read_track_id(str(audio_file)) == ["3424255901"]


class Test自动写入:
    def test_唯一命中写入(self, capsys, monkeypatch, tmp_path):
        path = tmp_path / "a.flac"
        _tagged_flac(path, "T", "A")
        source = _songs_source(
            tmp_path / "songs.json", {"id": 123, "title": "T", "artist": "A"}
        )

        commands.cmd_embed_id(ns(path, from_file=source))

        assert read_track_id(str(path)) == ["123"]
        assert "写入" in capsys.readouterr().err

    def test_已有相同值不写(self, capsys, monkeypatch, tmp_path):
        path = tmp_path / "a.flac"
        _tagged_flac(path, "T", "A")
        write_track_id(str(path), 123)
        source = _songs_source(
            tmp_path / "songs.json", {"id": 123, "title": "T", "artist": "A"}
        )
        called = []
        monkeypatch.setattr(commands, "write_track_id", lambda *a: called.append(a))

        commands.cmd_embed_id(ns(path, from_file=source))

        assert called == []
        assert "已是最新" in capsys.readouterr().err

    def test_已有不同值报冲突(self, capsys, tmp_path):
        path = tmp_path / "a.flac"
        _tagged_flac(path, "T", "A")
        write_track_id(str(path), 999)
        source = _songs_source(
            tmp_path / "songs.json", {"id": 123, "title": "T", "artist": "A"}
        )

        commands.cmd_embed_id(ns(path, from_file=source))

        assert read_track_id(str(path)) == ["999"]
        err = capsys.readouterr().err
        assert "冲突" in err
        assert "匹配到 123" in err
        assert "--set" not in err

    def test_歧义不写(self, capsys, tmp_path):
        path = tmp_path / "a.flac"
        _tagged_flac(path, "T", "A")
        source = _songs_source(
            tmp_path / "songs.json",
            {"id": 1, "title": "T", "artist": "A"},
            {"id": 2, "title": "T", "artist": "A"},
        )

        commands.cmd_embed_id(ns(path, from_file=source))

        assert read_track_id(str(path)) == []
        assert "匹配到多个候选" in capsys.readouterr().err

    def test_按标题兜底写入(self, capsys, tmp_path):
        path = tmp_path / "a.flac"
        _tagged_flac(path, "T", "A")
        source = _songs_source(
            tmp_path / "songs.json", {"id": 123, "title": "T", "artist": "B"}
        )

        commands.cmd_embed_id(ns(path, from_file=source))

        assert read_track_id(str(path)) == ["123"]

    def test_同一id命中多个文件(self, capsys, tmp_path):
        for name in ("a.flac", "b.flac"):
            _tagged_flac(tmp_path / name, "T", "A")
        source = _songs_source(
            tmp_path / "songs.json", {"id": 123, "title": "T", "artist": "A"}
        )

        commands.cmd_embed_id(ns(tmp_path, from_file=source))

        assert read_track_id(str(tmp_path / "a.flac")) == ["123"]
        assert read_track_id(str(tmp_path / "b.flac")) == ["123"]
        assert "有 1 个 track_id 匹配到多个文件" in capsys.readouterr().err

    def test_写失败后继续(self, capsys, monkeypatch, tmp_path):
        for name, title in (("a.flac", "T1"), ("b.flac", "T2")):
            _tagged_flac(tmp_path / name, title, "A")
        source = _songs_source(
            tmp_path / "songs.json",
            {"id": 1, "title": "T1", "artist": "A"},
            {"id": 2, "title": "T2", "artist": "A"},
        )
        original = commands.write_track_id

        def fake(path, song_id):
            if path.endswith("a.flac"):
                raise OSError("boom")
            original(path, song_id)

        monkeypatch.setattr(commands, "write_track_id", fake)

        commands.cmd_embed_id(ns(tmp_path, from_file=source))

        err = capsys.readouterr().err
        assert "未能写入" in err
        assert read_track_id(str(tmp_path / "b.flac")) == ["2"]


class Test收集文件:
    def test_单个文件直接返回(self, audio_file):
        assert commands._collect_audio_files(audio_file, False) == [audio_file]

    def test_默认只扫当前层(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"")
        (tmp_path / "b.flac").write_bytes(b"")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.mp3").write_bytes(b"")

        got = commands._collect_audio_files(tmp_path, False)

        assert [p.name for p in got] == ["a.mp3", "b.flac"]

    def test_递归扫子目录(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.mp3").write_bytes(b"")
        (tmp_path / "a.mp3").write_bytes(b"")

        got = commands._collect_audio_files(tmp_path, True)

        assert [p.name for p in got] == ["a.mp3", "deep.mp3"]

    def test_跳过不支持的格式(self, tmp_path, capsys):
        path = tmp_path / "tracks"
        path.mkdir()
        (path / "a.m4a").write_bytes(b"")
        _make_mp3(path / "b.mp3")
        source = _songs_source(tmp_path / "songs.json")

        commands.cmd_embed_id(ns(path, from_file=source))

        err = capsys.readouterr().err
        assert "跳过 1 个不支持的格式" in err
        assert "未能匹配到" in err

    def test_只有不支持格式(self, tmp_path, capsys):
        path = tmp_path / "tracks"
        path.mkdir()
        (path / "a.m4a").write_bytes(b"")
        source = tmp_path / "songs.json"
        source.write_text(json.dumps({"songs": []}), encoding="utf-8")

        commands.cmd_embed_id(ns(path, from_file=source))

        err = capsys.readouterr().err
        assert "跳过 1 个不支持的格式" in err
        assert "没有可写入" in err

    def test_目录没有音频(self, tmp_path, capsys):
        path = tmp_path / "empty"
        path.mkdir()
        source = tmp_path / "songs.json"
        source.write_text(json.dumps({"songs": []}), encoding="utf-8")

        commands.cmd_embed_id(ns(path, from_file=source))

        assert "未找到音频文件" in capsys.readouterr().err


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

    def test_文件能解析就进入匹配(self, capsys, audio_file, tmp_path):
        source = _songs_source(tmp_path / "songs.json")
        commands.cmd_embed_id(ns(audio_file, from_file=source))
        assert "未能匹配到" in capsys.readouterr().err

    def test_缺少songs列表退一(self, capsys, audio_file, tmp_path):
        source = tmp_path / "songs.json"
        source.write_text("{}", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            commands.cmd_embed_id(ns(audio_file, from_file=source))
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "无法解析" in err
        assert "缺少 songs" in err


class Test没有来源:
    def test_没有tracker时提示未找到(self, capsys, audio_file, no_trackers):
        with pytest.raises(SystemExit) as exc:
            commands.cmd_embed_id(ns(audio_file))
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "未找到 Tracker 曲目库" in err
        assert "--from" not in err

    def test_有tracker时进入匹配(self, capsys, audio_file, no_trackers):
        tracker_dir = no_trackers / "tracker" / "like"
        tracker_dir.mkdir(parents=True)
        (tracker_dir / "songs.json").write_text(
            json.dumps({"songs": []}), encoding="utf-8"
        )
        commands.cmd_embed_id(ns(audio_file))
        assert "未能匹配到" in capsys.readouterr().err

    def test_任意tracker曲目库损坏退一(self, capsys, audio_file, no_trackers):
        tracker_dir = no_trackers / "tracker" / "like"
        tracker_dir.mkdir(parents=True)
        (tracker_dir / "songs.json").write_text("{坏", encoding="utf-8")

        with pytest.raises(SystemExit) as exc:
            commands.cmd_embed_id(ns(audio_file))

        assert exc.value.code == 1
        assert "Tracker 曲目库无法解析" in capsys.readouterr().err
