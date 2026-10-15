import pytest
from rich import box
from rich.cells import cell_len
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from function.output import _artist_text

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

NARROW_HEADERS = ("#", "ID", "时长")


def _render(width):
    """按 output.py 的列配置渲染，量出每列表头占的格数"""
    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("#", style="dim")
    table.add_column("ID", style="dim")
    table.add_column("标题", style="bright_white", ratio=4, max_width=48)
    table.add_column("艺术家", style="yellow", ratio=3, max_width=36)
    table.add_column("专辑", style="green", ratio=2, max_width=32)
    table.add_column("时长", style="blue", justify="right")
    for i, t in enumerate(TRACKS, 1):
        table.add_row(
            str(i),
            str(t["id"]),
            escape(t["title"]),
            _artist_text(t["artist"], "yellow"),
            escape(t["album"]),
            t["duration"],
        )
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
    table = Table(box=box.ROUNDED, show_header=True, expand=True)
    table.add_column("#", style="dim")
    table.add_column("ID", style="dim")
    table.add_column("标题", ratio=4, max_width=48)
    table.add_row("1", "12345678901", "短标题")
    console = Console(width=200)
    with console.capture() as cap:
        console.print(table)
    assert "12345678901" in cap.get()
