import os
from pathlib import Path

import pytest
from rich.console import Console
from rich.markup import escape
from rich.text import Text

from vncmd.core.config import abbrev_home


def test_家目录缩写为波浪号(monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/Users/tester")))
    assert abbrev_home("/Users/tester/Downloads/x") == "~/Downloads/x"


def test_家目录本身缩写为单独的波浪号(monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/Users/tester")))
    assert abbrev_home("/Users/tester") == "~"


def test_不在家目录下保持原样(monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/Users/tester")))
    assert abbrev_home("/var/folders/abc") == "/var/folders/abc"


def test_只是前缀相同不算家目录(monkeypatch):
    # ~/MusicBackup 那种不能被当成 ~/Music 的一部分缩掉
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/Users/tester")))
    assert abbrev_home("/Users/tester2/x") == "/Users/tester2/x"


def test_路径变短():
    home = str(Path.home())
    long_path = f"{home}/Downloads/vncmd-dl/2026-10-15_23-06-02"
    assert len(abbrev_home(long_path)) < len(long_path)


@pytest.mark.parametrize(
    "name",
    ["曲 [bold] 现场.mp3", "[red]x.mp3", "a]b.mp3", "tail]"],
)
def test_check输出不会被markup注入(name, tmp_path):
    # 文件名含方括号时未转义会被 rich 当成样式标签解析
    # [/b] 这种不配对的标签会让渲染直接抛 MarkupError
    f = tmp_path / name
    f.write_bytes(b"")
    console = Console(width=200)
    rendered = f'"{escape(str(f.relative_to(tmp_path)))}"'
    with console.capture() as cap:
        console.print(f"  [cyan]OK[/]  {rendered}")
    assert name in cap.get().replace("\\", "")


def test_check的相对路径不包含目录前缀(tmp_path):
    sub = tmp_path / "2026-10-15_23-06-02"
    sub.mkdir()
    f = sub / "song.mp3"
    f.write_bytes(b"")
    root = tmp_path
    rel = f.relative_to(root)
    assert str(rel) == "2026-10-15_23-06-02/song.mp3"


def test_quoted文件名整串同色():
    # rich 的 ReprHighlighter 会把不带引号的路径拆成 path 与 filename 两种颜色
    console = Console(width=120, force_terminal=True)
    name = "ローリンガール.mp3"
    with console.capture() as cap:
        console.print(f'[cyan]✓[/] MP3 → "{name}"')
    parsed = Text.from_ansi(cap.get().rstrip("\n"))
    colored = [
        sp.style.color.number for sp in parsed.spans if parsed.plain[sp.start] == '"'
    ]
    assert colored == [2]


def test_不帶引號会被拆成兩種顏色():
    # 反证：去掉引号后目录与文件名颜色不同
    console = Console(width=120, force_terminal=True)
    with console.capture() as cap:
        console.print("[cyan]✓[/] /Users/me/Music/a.mp3")
    parsed = Text.from_ansi(cap.get().rstrip("\n"))
    colors = {sp.style.color.number for sp in parsed.spans}
    assert len(colors) > 2


def test_sep常量存在():
    assert os.sep
