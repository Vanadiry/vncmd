from rich import box
from rich.cells import cell_len
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from function.config import is_virtual_singer_color
from function.vocals import colorize

console = Console()


def _artist_text(artist: str, base_style: str) -> Text:
    """把艺术家串拼成 Text，命中代表色的片段换成自己的颜色"""
    text = Text()
    if is_virtual_singer_color():
        for chunk, color in colorize(artist):
            text.append(chunk, style=color or base_style)
    else:
        text.append(artist, style=base_style)
    return text


def _display_track_table(
    tracks: list[dict], total_count: int, title: str | None = None
) -> None:
    table = Table(
        title=title,
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    # ratio 只给标题、艺术家、专辑这三列，rich 据此判断哪些列参与富余宽度分配。
    # 序号、ID、时长不设 ratio，宽度就按内容自然算，不会被摊宽
    table.add_column("#", style="dim")
    table.add_column("ID", style="dim")
    table.add_column("标题", style="bright_white", ratio=4, max_width=48)
    table.add_column("艺术家", style="yellow", ratio=3, max_width=36)
    table.add_column("专辑", style="green", ratio=2, max_width=32)
    table.add_column("时长", style="blue", justify="right")

    for i, t in enumerate(tracks, 1):
        table.add_row(
            str(i),
            str(t["id"]),
            escape(t["title"]),
            _artist_text(t["artist"], "yellow"),
            escape(t["album"]),
            t["duration"],
        )

    console.print(table)

    remaining = total_count - len(tracks)
    if remaining > 0:
        console.print(f"  ... 还有 {remaining} 首曲目", style="dim")


def display_search_results(query: str, songs: list[dict], total: int) -> None:
    """Display search results as a table."""
    _display_track_table(
        songs, total, title=f"搜索：「{escape(query)}」  —  共 {total} 首"
    )


def display_song_detail(song: dict) -> None:
    """Display a single song's full metadata."""
    lines = [
        ("ID", str(song["id"])),
        ("标题", song["title"]),
        ("艺术家", _artist_text(song["artist"], "bright_white")),
        ("专辑", song["album"]),
        ("封面", song["cover"]),
        ("发行时间", song["publish_time"]),
        ("时长", song["duration"]),
    ]

    # 键多为中文，len 按字符数算会短一格，补齐要用 cell_len
    max_key_len = max(cell_len(k) for k, _ in lines)
    text = Text()
    for i, (key, value) in enumerate(lines):
        pad = " " * (max_key_len - cell_len(key))
        text.append(f"{key}{pad}  ", style="bold cyan")
        if isinstance(value, Text):
            text.append(value)
        else:
            text.append(value, style="bright_white")
        # 末行不留换行，否则面板底部会多一行空行
        if i < len(lines) - 1:
            text.append("\n")

    panel = Panel(text, title="[bold]曲目详情[/]", border_style="cyan", box=box.ROUNDED)
    console.print(panel)


def display_playlist(playlist: dict, max_tracks: int = 100) -> None:
    """Display playlist info and its tracks as a table."""
    header = Text()
    header.append("歌单：", style="bold")
    header.append(f"{playlist['name']}\n", style="bold bright_white")
    header.append("创建者：", style="dim")
    header.append(f"{playlist['creator']}", style="yellow")
    header.append("  |  曲目数：", style="dim")
    header.append(f"{playlist['track_count']}", style="green")
    console.print(Panel(header, border_style="cyan", box=box.ROUNDED))

    _display_track_table(playlist["tracks"][:max_tracks], playlist["track_count"])


def display_album(album: dict, max_tracks: int = 100) -> None:
    header = Text()
    header.append("专辑：", style="bold")
    header.append(f"{album['name']}\n", style="bold bright_white")
    header.append("艺术家：", style="dim")
    header.append(f"{album['artist']}", style="yellow")
    header.append("  |  曲目数：", style="dim")
    header.append(f"{album['track_count']}", style="green")
    console.print(Panel(header, border_style="cyan", box=box.ROUNDED))
    _display_track_table(album["tracks"][:max_tracks], album["track_count"])


def display_lyrics(lyrics_text: str) -> None:
    """Display lyrics in a panel."""
    if not lyrics_text:
        console.print("[dim]无歌词[/]")
        return
    panel = Panel(
        Text(lyrics_text.strip()),
        title="[bold]歌词[/]",
        border_style="cyan",
        box=box.ROUNDED,
    )
    console.print(panel)


ICON_OK = "[green]✓[/]"
ICON_FAIL = "[red]✗[/]"
ICON_INFO = "[blue]ℹ[/]"
ICON_WARN = "[yellow]⚠[/]"


def _print_status(icon, msg):
    for line in msg.splitlines():
        console.print(f"{icon} {escape(line)}")


def success(msg: str) -> None:
    _print_status(ICON_OK, msg)


def error(msg: str) -> None:
    _print_status(ICON_FAIL, msg)


def info(msg: str) -> None:
    _print_status(ICON_INFO, msg)


def warning(msg: str) -> None:
    _print_status(ICON_WARN, msg)
