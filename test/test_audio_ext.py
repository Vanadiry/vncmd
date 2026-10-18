import pytest

from vncmd.media.audio import get_type_from_url


@pytest.mark.parametrize(
    ("url", "expect"),
    [
        ("http://h/1.mp3?param=x", "mp3"),
        ("http://h/1.flac?param=yxz", "flac"),
        ("http://h/1.MP3", "mp3"),
    ],
)
def test_常见格式原样返回(url, expect):
    assert get_type_from_url(url) == expect


@pytest.mark.parametrize(
    ("url", "expect"),
    [
        ("http://h/1.m4a", "m4a"),
        ("http://h/1.aac", "aac"),
        ("http://h/1.alac", "alac"),
        ("http://h/1.opus", "opus"),
        ("http://h/1.wav", "wav"),
        ("http://h/1.ogg", "ogg"),
    ],
)
def test_未知格式保留真实扩展名(url, expect, capsys):
    # 标成 mp3 会产出错扩展名的文件，播放器打不开
    assert get_type_from_url(url) == expect
    assert "未预期的音频格式" in capsys.readouterr().err


@pytest.mark.parametrize(
    "url",
    ["http://h/abc123def", "http://h/1", "http://h/x.verylongextension"],
)
def test_没有可用扩展名时归mp3且不警告(url, capsys):
    out = capsys.readouterr().out
    assert get_type_from_url(url) == "mp3"
    assert "未预期的音频格式" not in capsys.readouterr().err
    assert out == ""


def test_警告每种格式各出一次(capsys):
    for _ in range(3):
        get_type_from_url("http://h/1.m4a")
    assert capsys.readouterr().err.count("未预期的音频格式") == 3


def test_常见格式不产生任何输出(capsys):
    get_type_from_url("http://h/1.flac?param=x")
    assert capsys.readouterr().out == ""


def test_空扩展名不崩():
    assert get_type_from_url("") == "mp3"
