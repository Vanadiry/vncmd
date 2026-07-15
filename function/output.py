from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

console = Console()


def _display_track_table(
    tracks: list[dict], total_count: int, title: str | None = None
) -> None:
    table = Table(
        title=title,
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("ID", style="dim", width=12)
    table.add_column("标题", style="bright_white", max_width=40)
    table.add_column("艺术家", style="yellow", max_width=30)
    table.add_column("专辑", style="green", max_width=30)
    table.add_column("时长", style="blue", width=8, justify="right")

    for i, t in enumerate(tracks, 1):
        table.add_row(
            str(i),
            str(t["id"]),
            t["title"],
            t["artist"],
            t["album"],
            t["duration"],
        )

    console.print(table)

    remaining = total_count - len(tracks)
    if remaining > 0:
        console.print(f"  ... 还有 {remaining} 首曲目", style="dim")


def display_search_results(query: str, songs: list[dict], total: int) -> None:
    """Display search results as a table."""
    _display_track_table(songs, total, title=f"搜索：「{query}」  —  共 {total} 首")


def display_song_detail(song: dict) -> None:
    """Display a single song's full metadata."""
    lines = [
        ("ID", str(song["id"])),
        ("标题", song["title"]),
        ("艺术家", song["artist"]),
        ("专辑", song["album"]),
        ("封面", song["cover"]),
        ("发行时间", song["publish_time"]),
        ("时长", song["duration"]),
    ]

    max_key_len = max(len(k) for k, _ in lines)
    text = Text()
    for key, value in lines:
        text.append(f"{key:<{max_key_len}}  ", style="bold cyan")
        text.append(f"{value}\n", style="bright_white")

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
        lyrics_text.strip(),
        title="[bold]歌词[/]",
        border_style="cyan",
        box=box.ROUNDED,
    )
    console.print(panel)


ICON_OK = "[green]✓[/]"
ICON_FAIL = "[red]✗[/]"
ICON_INFO = "[blue]ℹ[/]"
ICON_WARN = "[yellow]⚠[/]"


def success(msg: str) -> None:
    console.print(f"{ICON_OK} {msg}")


def error(msg: str) -> None:
    console.print(f"{ICON_FAIL} {msg}")


def info(msg: str) -> None:
    console.print(f"{ICON_INFO} {msg}")


def warning(msg: str) -> None:
    console.print(f"{ICON_WARN} {msg}")
