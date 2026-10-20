import argparse
import re
import time
from pathlib import Path

import pytest

from vncmd import commands as commands_mod
from vncmd.media.checker import (
    check_audio,
    ffprobe_info,
    has_ffmpeg,
    has_ffprobe,
    has_flac,
)


def _gen_valid_flac(path: Path) -> None:
    import subprocess

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            "0.5",
            "-acodec",
            "flac",
            str(path),
        ],
        capture_output=True,
        check=True,
    )


class TestChecker:
    def test_has_ffmpeg(self):
        assert isinstance(has_ffmpeg(), bool)

    def test_has_ffprobe(self):
        assert isinstance(has_ffprobe(), bool)

    def test_has_flac(self):
        assert isinstance(has_flac(), bool)

    @pytest.mark.skipif(not has_ffmpeg(), reason="需要 ffmpeg")
    def test_check_valid_flac(self, temp_dir):
        flac_path = Path(temp_dir) / "valid.flac"
        _gen_valid_flac(flac_path)
        ok, msg = check_audio(str(flac_path))
        assert ok, msg

    @pytest.mark.skipif(not has_ffmpeg(), reason="需要 ffmpeg")
    def test_check_corrupted(self, temp_dir):
        bad_path = Path(temp_dir) / "bad.mp3"
        bad_path.write_bytes(b"this is not audio at all")
        ok, _ = check_audio(str(bad_path))
        assert not ok

    @pytest.mark.skipif(not has_ffprobe(), reason="需要 ffprobe")
    def test_ffprobe_info(self, temp_dir):
        flac_path = Path(temp_dir) / "valid.flac"
        _gen_valid_flac(flac_path)
        info = ffprobe_info(str(flac_path))
        assert info is not None
        assert info["duration"] is not None
        assert info["duration"] > 0


@pytest.fixture
def audio_dir(tmp_path):
    for name in ("a.flac", "b.flac", "c.flac"):
        (tmp_path / name).write_bytes(b"")
    return tmp_path


def _run_check(monkeypatch, capsys, path, check):
    monkeypatch.setattr(commands_mod, "check_audio", check)
    monkeypatch.setattr(commands_mod, "any_check_tool", lambda: True)
    commands_mod.cmd_check(argparse.Namespace(path=str(path)))
    return capsys.readouterr().out


def _names(out):
    lines = [ln for ln in out.splitlines() if "通过" in ln and '"' in ln]
    return [re.search(r'"([^"]+)"', ln).group(1) for ln in lines]


def test_单个文件检查失败不影响其余(monkeypatch, capsys, audio_dir):
    def check(path):
        if path.endswith("b.flac"):
            raise RuntimeError("ffprobe 崩了")
        return True, ""

    out = _run_check(monkeypatch, capsys, audio_dir, check)
    assert "a.flac" in out and "c.flac" in out
    assert "检查失败" in out
    assert "完成：2 通过，1 损坏" in out


def test_异常类型写进结果(monkeypatch, capsys, audio_dir):
    def check(path):
        if path.endswith("b.flac"):
            raise ValueError("boom")
        return True, ""

    out = _run_check(monkeypatch, capsys, audio_dir, check)
    assert "RuntimeError" in out or "ValueError" in out


def test_并发执行但按文件名排序(monkeypatch, capsys, audio_dir):
    delays = {"a.flac": 0.25, "b.flac": 0.05, "c.flac": 0.15}

    def check(path):
        time.sleep(delays[path.rsplit("/", 1)[-1]])
        return True, ""

    out = _run_check(monkeypatch, capsys, audio_dir, check)
    assert _names(out) == ["a.flac", "b.flac", "c.flac"]


def test_checker在模块顶层绑定():
    assert hasattr(commands_mod, "check_audio")
    assert hasattr(commands_mod, "any_check_tool")
