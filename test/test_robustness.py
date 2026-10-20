import subprocess

import pytest
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn

from vncmd import downloader
from vncmd.core import output as output_mod
from vncmd.media import checker

# ---------- #23 子进程超时 ----------


def _timeout_run(*a, **kw):
    raise subprocess.TimeoutExpired(cmd="x", timeout=kw.get("timeout", 1))


def test_ffprobe超时返回空(monkeypatch):
    monkeypatch.setattr(checker.subprocess, "run", _timeout_run)
    assert checker.ffprobe_info("x.mp3") is None


def test_ffprobe超时时按超时值传下去(monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw)
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kw["timeout"])

    monkeypatch.setattr(checker.subprocess, "run", fake_run)
    checker.ffprobe_info("x.mp3")
    assert seen["timeout"] == 10, "ffprobe 的超时值应与文档一致"


def test_ffprobe输出不是合法JSON(monkeypatch):
    class P:
        returncode = 0
        stdout = "not json"
        stderr = ""

    monkeypatch.setattr(checker.subprocess, "run", lambda *a, **k: P())
    assert checker.ffprobe_info("x.mp3") is None


def test_ffprobe输出是JSON数组(monkeypatch):
    class P:
        returncode = 0
        stdout = "[1, 2]"
        stderr = ""

    monkeypatch.setattr(checker.subprocess, "run", lambda *a, **k: P())
    assert checker.ffprobe_info("x.mp3") is None


def test_ffmpeg解码超时不能当成通过(monkeypatch):
    """超时返回空错误列表的话，调用方会当成“解码完整”放行
    于是一首 30 秒都解不完的歌被当完好文件收进库"""
    monkeypatch.setattr(checker.subprocess, "run", _timeout_run)
    errors, actual = checker.ffmpeg_decode("x.mp3")
    assert errors, "超时必须给出原因"
    assert actual is None


def test_超时的文件在check_audio里判失败(monkeypatch):
    monkeypatch.setattr(checker.shutil, "which", lambda n: "/usr/bin/" + n)
    monkeypatch.setattr(checker.subprocess, "run", _timeout_run)
    ok, msg = checker.check_audio("x.flac")
    assert not ok
    assert "超时" in msg


def test_flac超时给可读原因(monkeypatch, tmp_path):
    monkeypatch.setattr(checker.shutil, "which", lambda n: "/usr/bin/flac")
    monkeypatch.setattr(checker.subprocess, "run", _timeout_run)
    assert checker.flac_test("x.flac") == "flac 校验超时"


def test_flac没有安装时返回空(monkeypatch):
    monkeypatch.setattr(checker.shutil, "which", lambda n: None)
    assert checker.flac_test("x.flac") is None


def test_子进程缺失不抛异常(monkeypatch):
    def boom(*a, **kw):
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr(checker.subprocess, "run", boom)
    assert checker.ffprobe_info("x.mp3") is None


# ---------- #24 进度条描述转义 ----------


def _render_desc(monkeypatch, width, text):
    monkeypatch.setattr(output_mod, "console", Console(width=width))
    monkeypatch.setattr(downloader, "console", Console(width=width))
    return downloader._progress_desc(text)


@pytest.mark.parametrize(
    "text",
    ["曲 [bold] 现场", "a[/b]b", "Song [red]x[/red] hi", "[Live] 海阔天空"],
)
def test_含方括号不抛异常(text, monkeypatch):
    # 未转义时 [/b] 会抛 MarkupError，整条进度条渲染中断
    out = _render_desc(monkeypatch, 100, text)
    with Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        console=Console(width=100),
    ) as p:
        p.update(p.add_task(""), description=out)


def test_转义后渲染出的文字没丢(monkeypatch):
    text = "曲 [bold] 现场"
    out = _render_desc(monkeypatch, 200, text)
    console = Console(width=200)
    with (
        console.capture() as cap,
        Progress(TextColumn("{task.description}"), console=console) as p,
    ):
        p.update(p.add_task(""), description=out)
    # 未转义时 [bold] 被当成样式标签，渲染出来的是 曲 现场，bold 两个字消失
    assert "bold" in cap.get()


def test_转义不改变补齐宽度(monkeypatch):
    # 反斜杠不占渲染宽度，补齐量要按转义前的显示宽度算
    from rich.cells import cell_len

    limit = max(Console(width=200).width - 60, 30)
    for text in ("abc", "曲 [bold] 现场", "a[/b]b"):
        out = _render_desc(monkeypatch, 200, text)
        # escape 加的反斜杠在渲染时被 markup 解析器吃掉
        rendered = out.replace("\\[", "[")
        assert cell_len(rendered) == limit


def test_普通文本内容不变(monkeypatch):
    out = _render_desc(monkeypatch, 200, "abc")
    assert out.startswith("abc")
