import pytest
from rich.cells import cell_len

from function.downloader import _progress_desc


def _limit():
    from function.output import console

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
