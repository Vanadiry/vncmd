from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

console = Console()


def _display_track_table(tracks, total_count):
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("ID", style="dim", width=12)
    table.add_column("Title", style="bright_white", max_width=40)
    table.add_column("Artist", style="yellow", max_width=30)
    table.add_column("Album", style="green", max_width=30)
    table.add_column("Duration", style="blue", width=8, justify="right")

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
        console.print(f"  ... and {remaining} more tracks", style="dim")


def display_search_results(query, songs, total):
    """Display search results as a table."""
    table = Table(
        title=f'Search: "{query}"  —  {total} results',
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("ID", style="dim", width=12)
    table.add_column("Title", style="bright_white", max_width=40)
    table.add_column("Artist", style="yellow", max_width=30)
    table.add_column("Album", style="green", max_width=30)
    table.add_column("Duration", style="blue", width=8, justify="right")

    for i, s in enumerate(songs, 1):
        table.add_row(
            str(i),
            str(s["id"]),
            s["title"],
            s["artist"],
            s["album"],
            s["duration"],
        )

    console.print(table)


def display_song_detail(song):
    """Display a single song's full metadata."""
    lines = [
        ("ID", str(song["id"])),
        ("Title", song["title"]),
        ("Artist", song["artist"]),
        ("Album", song["album"]),
        ("Cover", song["cover"]),
        ("Publish Time", song["publish_time"]),
        ("Duration", song["duration"]),
    ]

    max_key_len = max(len(k) for k, _ in lines)
    text = Text()
    for key, value in lines:
        text.append(f"{key:<{max_key_len}}  ", style="bold cyan")
        text.append(f"{value}\n", style="bright_white")

    panel = Panel(text, title=f"[bold]Song Detail[/]", border_style="cyan", box=box.ROUNDED)
    console.print(panel)


def display_playlist(playlist, max_tracks=100):
    """Display playlist info and its tracks as a table."""
    # Header
    header = Text()
    header.append(f"Playlist: ", style="bold")
    header.append(f"{playlist['name']}\n", style="bold bright_white")
    header.append(f"Creator: ", style="dim")
    header.append(f"{playlist['creator']}", style="yellow")
    header.append(f"  |  Tracks: ", style="dim")
    header.append(f"{playlist['track_count']}", style="green")
    console.print(Panel(header, border_style="cyan", box=box.ROUNDED))

    _display_track_table(playlist["tracks"][:max_tracks], playlist["track_count"])


def display_album(album, max_tracks=100):
    header = Text()
    header.append("Album: ", style="bold")
    header.append(f"{album['name']}\n", style="bold bright_white")
    header.append("Artist: ", style="dim")
    header.append(f"{album['artist']}", style="yellow")
    header.append("  |  Tracks: ", style="dim")
    header.append(f"{album['track_count']}", style="green")
    console.print(Panel(header, border_style="cyan", box=box.ROUNDED))
    _display_track_table(album["tracks"][:max_tracks], album["track_count"])


def display_lyrics(lyrics_text):
    """Display lyrics in a panel."""
    if not lyrics_text:
        console.print("[dim]No lyrics available[/]")
        return
    panel = Panel(
        lyrics_text.strip(),
        title="[bold]Lyrics[/]",
        border_style="cyan",
        box=box.ROUNDED,
    )
    console.print(panel)


def success(msg):
    console.print(f"[green]✓[/] {msg}")


def error(msg):
    console.print(f"[red]✗[/] {msg}")


def info(msg):
    console.print(f"[blue]ℹ[/] {msg}")


def warning(msg):
    console.print(f"[yellow]⚠[/] {msg}")
