import argparse
import re
import stat
import time

import pytest

from vncmd import commands as commands_mod
from vncmd import config as config_mod


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
    lines = [ln for ln in out.splitlines() if "OK" in ln]
    return [re.search(r'"([^"]+)"', ln).group(1) for ln in lines]


def test_单个文件检查失败不影响其余(monkeypatch, capsys, audio_dir):
    # 抛异常会让整条命令中断，已检查过的结果全丢
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
    # 函数内 import 会让 monkeypatch 打不中，也与项目其它模块风格不一致
    assert hasattr(commands_mod, "check_audio")
    assert hasattr(commands_mod, "any_check_tool")


def test_get_cookie文件不存在返回空串(monkeypatch, tmp_path):
    monkeypatch.setattr(config_mod, "COOKIE_FILE", tmp_path / "none")
    assert config_mod.get_cookie() == ""


def test_get_cookie读不了不抛异常(monkeypatch, tmp_path):
    # 权限不足时抛异常会让每次请求都中断，而调用方本来按无 Cookie 走
    cookie = tmp_path / "cookie"
    cookie.write_text("a=b", encoding="utf-8")
    cookie.chmod(0)
    monkeypatch.setattr(config_mod, "COOKIE_FILE", cookie)
    try:
        assert config_mod.get_cookie() == ""
    finally:
        cookie.chmod(stat.S_IRUSR | stat.S_IWUSR)


def test_get_cookie编码错误不抛异常(monkeypatch, tmp_path):
    cookie = tmp_path / "cookie"
    cookie.write_bytes(b"\xff\xfe\x00bad")
    monkeypatch.setattr(config_mod, "COOKIE_FILE", cookie)
    assert config_mod.get_cookie() == ""


def test_get_cookie正常读取(monkeypatch, tmp_path):
    cookie = tmp_path / "cookie"
    cookie.write_text("  MUSIC_U=\u4f60\u597d  \n", encoding="utf-8")
    monkeypatch.setattr(config_mod, "COOKIE_FILE", cookie)
    assert config_mod.get_cookie() == "MUSIC_U=\u4f60\u597d"
