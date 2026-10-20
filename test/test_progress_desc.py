import pytest
from rich.cells import cell_len
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn

from vncmd import downloader
from vncmd.core import output as output_mod
from vncmd.downloader import _progress_desc


def _limit():
    from vncmd.core.output import console

    return max(console.width - 60, 30)


def test_补齐到固定显示宽度():
    text = "灰色轨迹 - Beyond"
    assert cell_len(_progress_desc(text)) == _limit()


def test_短文本也要补齐():
    assert cell_len(_progress_desc("abc")) == _limit()


@pytest.mark.parametrize(
    "text",
    [
        "splattered_brain - C418",
        "sht - C418",
        "灰色轨迹 - Beyond",
        "ローリンガール - wowaka",
        "灰色轨迹 - Beyond - 花里みのり - 小豆沢こはね",
    ],
)
def test_中英日混排宽度都一致(text):
    # len 统计字符，cell_len 统计显示格，CJK 与假名都是双格
    assert cell_len(_progress_desc(text)) == _limit()


def test_超长文本被裁剪且仍满宽():
    out = _progress_desc("あ" * 200)
    assert cell_len(out) == _limit()
    assert out.rstrip().endswith("…")


def test_裁剪不切在半个宽字符中间():
    # 逐个加宽字符，输出宽度不能出现奇数或负数补齐
    for n in range(1, 40):
        assert cell_len(_progress_desc("あ" * n)) == _limit()


def test_短于终端不裁剪():
    out = _progress_desc("abc")
    assert "…" not in out


def test_空串():
    assert _progress_desc("") == " " * _limit()


def _render_desc(monkeypatch, width, text):
    monkeypatch.setattr(output_mod, "console", Console(width=width))
    monkeypatch.setattr(downloader, "console", Console(width=width))
    return downloader._progress_desc(text)


@pytest.mark.parametrize(
    "text",
    ["曲 [bold] 现场", "a[/b]b", "Song [red]x[/red] hi", "[Live] 海阔天空"],
)
def test_含方括号不抛异常(text, monkeypatch):
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
    assert "bold" in cap.get()


def test_转义不改变补齐宽度(monkeypatch):
    limit = max(Console(width=200).width - 60, 30)
    for text in ("abc", "曲 [bold] 现场", "a[/b]b"):
        out = _render_desc(monkeypatch, 200, text)
        rendered = out.replace("\\[", "[")
        assert cell_len(rendered) == limit


def test_普通文本内容不变(monkeypatch):
    out = _render_desc(monkeypatch, 200, "abc")
    assert out.startswith("abc")
