import io
import re

import pytest
from rich.cells import cell_len
from rich.console import Console

from vncmd import output
from vncmd.output import _build_track_table

TRACKS = [
    {
        "id": 26096281,
        "title": "鏡音レンの暴走",
        "artist": "cosMo@暴走P, 鏡音レン",
        "album": "鏡音レンの暴走",
        "duration": "4:50",
    },
    {
        "id": 1294899572,
        "title": "劣等上等",
        "artist": "鏡音リン, 鏡音レン, Giga",
        "album": "「マジカルミライ2018」OFFICIAL ALBUM",
        "duration": "3:56",
    },
    {
        "id": 548648148,
        "title": "病名は愛だった",
        "artist": "Neru, 鏡音レン, 鏡音リン, z'5",
        "album": "CYNICISM",
        "duration": "3:51",
    },
]


def _render(width):
    """用 output.py 的真列配置渲染，量出每列表头占的格数"""
    table = _build_track_table(TRACKS)
    console = Console(width=width)
    with console.capture() as cap:
        console.print(table)
    lines = cap.get().rstrip("\n").split("\n")
    # 表头格宽减掉左右各 1 格 padding
    return [cell_len(p) - 2 for p in lines[1].split("│")[1:-1]]


@pytest.mark.parametrize("width", [80, 100, 120, 160, 200])
def test_窄列不随终端变宽(width):
    # 没设 ratio 的列不参与富余宽度分配，列宽只由内容决定
    cols = _render(width)
    got = dict(zip(["#", "ID", "标题", "艺术家", "专辑", "时长"], cols, strict=True))
    want_index = len(str(len(TRACKS)))
    want_id = max(cell_len(str(t["id"])) for t in TRACKS)
    want_duration = max(cell_len(t["duration"]) for t in TRACKS)
    assert got["#"] == want_index, f"序号列宽 {got['#']}，应为 {want_index}"
    assert got["ID"] == want_id, f"ID 列宽 {got['ID']}，应为 {want_id}"
    assert got["时长"] == want_duration, f"时长列宽 {got['时长']}，应为 {want_duration}"


@pytest.mark.parametrize("width", [80, 100, 120, 160, 200])
def test_序号列不按固定值留位(width):
    # 旧实现写死 width=4，序号只有一位时也占 4 格
    assert _render(width)[0] == 1


def test_富余宽度全给文本列():
    # 三列带 ratio，终端越宽越大
    small = _render(120)
    large = _render(200)
    for idx, name in ((2, "标题"), (3, "艺术家"), (4, "专辑")):
        assert large[idx] > small[idx], f"{name} 列没有随终端变宽"


def test_不超出终端宽度():
    table_width = sum(_render(160))
    # 表头两端的竖线各占 1 格
    assert table_width + 7 <= 160


def test_ID超长时不裁掉():
    # 固定 width 会把超长 ID 裁成省略号，ID 裁掉就无法复制
    long_id = [
        {
            "id": 33975028291234,
            "title": "短标题",
            "artist": "甲",
            "album": "乙",
            "duration": "1:00",
        }
    ]
    console = Console(width=200)
    with console.capture() as cap:
        console.print(_build_track_table(long_id))
    assert "33975028291234" in cap.get()


def _ansi(tracks, width=140, **kwargs):
    """渲染成带颜色转义序列的文本，样式才量得到"""
    buf = io.StringIO()
    output.console = Console(
        file=buf, force_terminal=True, width=width, color_system="truecolor"
    )
    output._display_track_table(tracks, **kwargs)
    output.console = Console()
    return buf.getvalue()


def _plain(text):
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


MIXED_ARTIST = [
    {
        "id": 1,
        "title": "歌名",
        "artist": "某乐队, 初音ミク, 歌愛ユキ",
        "album": "某专辑",
        "duration": "1:00",
    }
]

LONG_ALBUM = [
    {
        "id": 3397502829,
        "title": "強風オールバック(Game Size.)",
        "artist": "モンスターピース, Leo/need, 初音ミク, 巡音ルカ, 星乃一歌",
        "album": "エイプリルフール 〜sing, updates, and flowers〜",
        "duration": "2:16",
    }
]


class TestColumnStyle:
    """艺术家与专辑两列改成白字，虚拟歌手的代表色仍然保留"""

    def test_不再用黄字标艺术家(self):
        assert "\x1b[33m" not in _ansi(MIXED_ARTIST)

    def test_不再用绿字标专辑(self):
        assert "\x1b[32m" not in _ansi(MIXED_ARTIST)

    def test_白字还在(self):
        assert "\x1b[97m" in _ansi(MIXED_ARTIST)

    def test_虚拟歌手的代表色保留(self):
        """白字是默认值，不代表把代表色一起抹掉"""
        text = _ansi(MIXED_ARTIST)
        # 初音ミク #39C5BB
        assert "38;2;57;197;187" in text
        # 歌愛ユキ #A83E34
        assert "38;2;168;62;52" in text

    def test_关掉着色后全是白字(self, monkeypatch):
        """配置项关掉时两列都退回白字，不该再有别的颜色"""
        monkeypatch.setattr(output, "is_artist_color", lambda: False)
        text = _ansi(MIXED_ARTIST)
        assert "\x1b[97m" in text
        assert "38;2;57;197;187" not in text


def _rows_of(out):
    """把渲染结果按行切开

    一行表格可能占多个渲染行，序号格非空即新行。
    """
    sep = next(i for i, ln in enumerate(out.splitlines()) if ln.startswith("├"))
    rows: list[list[list[str]]] = []
    for line in out.splitlines()[sep + 1 :]:
        if not line.startswith("│"):
            break
        cells = [c.strip() for c in line.split("│")[1:-1]]
        if cells[0]:
            rows.append([])
        rows[-1].append(cells)
    return rows


def _col_lines(rows, index, col):
    """第 index 行里第 col 列占了几格

    只数渲染出来的内容，所以下面几行富余高度不算。
    """
    return sum(1 for cells in rows[index] if cells[col])


# 序号、ID、标题、艺术家之后就是专辑，有无权限列都不影响这个位置
_TITLE_COL, _ARTIST_COL, _ALBUM_COL = 2, 3, 4


class TestAlbumWraps:
    """专辑与标题、艺术家一样自由换行

    早先试过把专辑的行数限制在前两列的行高之内，又试过在单行时按内容
    给专辑更多宽度，两套加起来近两百行，全删了：要先量列宽、再算预算、
    裁完再量一轮，而列宽分配本身又受内容长度影响，边界多到每加一条规则
    就得重扫一遍宽度才敢确定没写错。现在谁长谁折，各折各的。
    """

    def test_专辑列不设no_wrap(self):
        cols = {c.header: c for c in _build_track_table(LONG_ALBUM).columns}
        assert cols["专辑"].no_wrap is False, "设了 no_wrap 就会截断成省略号"

    def test_列的overflow给的是fold(self):
        """rich 的列表头默认 ellipsis，日文与中文这种没有空格的名字
        会被一刀切成「エイプ …」"""
        cols = {c.header: c for c in _build_track_table(LONG_ALBUM).columns}
        assert cols["专辑"].overflow == "fold"

    def test_三列都不设max_width(self):
        """终端本来就是终极约束，再设一遍上限是二次约束

        这三个 max_width 一直是死配置：4 组数据 × 45 个宽度对比，
        去掉它们输出完全相同。
        """
        cols = _build_track_table(LONG_ALBUM).columns
        for col in cols:
            assert col.max_width is None, f"{col.header} 列设了 max_width"

    def test_三列都不设overflow上限之外的裁剪(self):
        """rich 的列表头默认 ellipsis，长词会被切一刀加省略号

        「鏡音リン&天馬司&鳳えむ&草薙寧々&神代類」这种 40 格的长串在 40 格的列里
        会被切成「…神代 …」，接口明明返回了完整的。
        """
        cols = {c.header: c for c in _build_track_table(LONG_ALBUM).columns}
        for name in ("标题", "艺术家", "专辑"):
            assert cols[name].overflow == "fold", f"{name} 列会被省略号截断"

    def test_长串折行而不是被切掉(self):
        """拿接口真实出现过的标题：38 字里有 20 字连在一起没有断点"""
        tracks = [
            {
                "id": 2132951282,
                "title": "強風オールバック "
                "(feat. 鏡音リン&天馬司&鳳えむ&草薙寧々&神代類)",
                "artist": "ワンダーランズ×ショウタイム, 鏡音リン, ゆこぴ",
                "album": "ワンダーランズ×ショウタイム SEKAI ALBUM vol.3",
                "duration": "2:13",
            }
        ]
        for width in (70, 90, 110, 140, 200):
            rows = _rows_of(_plain(_ansi(tracks, width=width)))
            for key, col in (
                ("title", _TITLE_COL),
                ("artist", _ARTIST_COL),
                ("album", _ALBUM_COL),
            ):
                want = tracks[0][key].replace(" ", "")
                got = "".join(c[col] for c in rows[0]).replace(" ", "")
                assert got == want, f"宽 {width} 的 {key} 列丢了字：{got!r}"

    def test_专辑名长时会折行(self):
        rows = _rows_of(_plain(_ansi(LONG_ALBUM, width=80)))
        assert _col_lines(rows, 0, _ALBUM_COL) > 1, "专辑该折行"

    def test_专辑可以把行撑高(self):
        """不再按前两列的行高设上限"""
        tracks = [
            {
                "id": 1,
                "title": "短",
                "artist": "甲",
                "album": "很长的专辑名字" * 6,
                "duration": "1:00",
            }
        ]
        rows = _rows_of(_plain(_ansi(tracks, width=80)))
        assert _col_lines(rows, 0, _ALBUM_COL) > 1

    def test_放得下时不截断(self):
        tracks = [
            {
                "id": 1,
                "title": "短",
                "artist": "甲",
                "album": "短专辑",
                "duration": "1:00",
            }
        ]
        assert "短专辑" in _plain(_ansi(tracks, width=140))

    def test_三列都能折(self):
        """标题、艺术家、专辑都不设 no_wrap，谁长谁折"""
        tracks = [
            {
                "id": 1,
                "title": "A Title With Spaces That Goes On",
                "artist": "An Artist Name With Spaces Too",
                "album": "Album Name That Is Also Long",
                "duration": "1:00",
            }
        ]
        cols = {c.header: c for c in _build_track_table(tracks).columns}
        for name in ("标题", "艺术家", "专辑"):
            assert cols[name].no_wrap is False, f"{name} 列被设了 no_wrap"

        rows = _rows_of(_plain(_ansi(tracks, width=80)))
        for name, col in (
            ("标题", _TITLE_COL),
            ("艺术家", _ARTIST_COL),
            ("专辑", _ALBUM_COL),
        ):
            assert _col_lines(rows, 0, col) > 1, f"{name} 列该折行"

    def test_各宽度都折得出来(self):
        """列宽按 ratio 分配，分配结果又受内容长度影响，
        同一份数据在不同宽度下布局完全不同，得多扫几个宽度"""
        tracks = [
            {
                "id": 1,
                "title": "A Title With Spaces That Goes On",
                "artist": "An Artist Name With Spaces Too",
                "album": "Album Name That Is Also Long",
                "duration": "1:00",
            }
        ]
        for width in range(60, 201, 10):
            out = _plain(_ansi(tracks, width=width))
            assert cell_len(out.splitlines()[0]) <= width, f"宽 {width} 溢出了"
