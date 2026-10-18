import pytest

from function import audio as audio_mod
from function import commands as commands_mod
from function import config as config_mod


@pytest.fixture
def fmt(monkeypatch):
    def _set(value):
        monkeypatch.setattr(
            config_mod, "_cfg", {"download": {"filename_artist": value}}
        )

    return _set


def test_艺术家为空不留尾随空格(fmt):
    fmt("back")
    assert audio_mod.build_filename("Song", "")[0] == "Song"


def test_标题含空格也没问题(fmt):
    fmt("back")
    assert (
        audio_mod.build_filename("-let's go to the sea", "")[0]
        == "-let's go to the sea"
    )


def test_艺术家为空且位置在前(fmt):
    fmt("front")
    assert audio_mod.build_filename("Song", "")[0] == "Song"


def test_两段齐全时保持原样(fmt):
    fmt("back")
    assert audio_mod.build_filename("正常歌", "Someone")[0] == "正常歌 - Someone"
    fmt("front")
    assert audio_mod.build_filename("正常歌", "Someone")[0] == "Someone - 正常歌"


def test_丢弃艺术家不受影响(fmt):
    fmt("drop")
    assert audio_mod.build_filename("Song", "Someone")[0] == "Song"


def test_文件名首尾无空白(fmt):
    fmt("back")
    name = audio_mod.build_filename("Song", "")[0]
    assert name == name.strip()


def test_check按文件名排序输出(tmp_path, monkeypatch, capsys):
    # 检查仍是并发的，但输出顺序要和 files.sort() 一致
    import argparse
    import time

    for name in ("c.flac", "a.flac", "b.flac", "d.flac"):
        (tmp_path / name).write_bytes(b"")

    delays = {"a.flac": 0.30, "b.flac": 0.20, "c.flac": 0.05, "d.flac": 0.25}

    def fake_check(path):
        time.sleep(delays[path.rsplit("/", 1)[-1]])
        return True, ""

    # check_audio 与 any_check_tool 已在 commands 模块顶层绑定，要打在 commands 上
    monkeypatch.setattr(commands_mod, "check_audio", fake_check)
    monkeypatch.setattr(commands_mod, "any_check_tool", lambda: True)
    args = argparse.Namespace(path=str(tmp_path))
    commands_mod.cmd_check(args)

    import re

    lines = [ln for ln in capsys.readouterr().out.splitlines() if "OK" in ln]
    assert len(lines) == 4
    assert [re.search(r'"([^"]+)"', ln).group(1) for ln in lines] == [
        "a.flac",
        "b.flac",
        "c.flac",
        "d.flac",
    ]
