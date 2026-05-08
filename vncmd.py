import argparse
import sys

from function.commands import cmd_search, cmd_song, cmd_album, cmd_playlist, cmd_init
from function.config import validate_config, QUALITY_MAP
from function.tracker import cmd_tracker


def _add_quality_arg(parser: object) -> None:
    parser.add_argument(
        "--quality",
        "-q",
        choices=list(QUALITY_MAP),
        default=None,
        help="Audio quality (default: from config)",
    )


def _add_output_arg(parser: object) -> None:
    parser.add_argument(
        "--output", "-o", default=None, help="Output directory (default: from config)"
    )


def _add_download_args(parser: object, batch: bool = False) -> None:
    """Add download-related args to a parser."""
    parser.add_argument(
        "--download", "-d", action="store_true", help="Download instead of preview only"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only valid with -d. Preview what would be downloaded without fetching audio.",
    )
    _add_quality_arg(parser)
    _add_output_arg(parser)
    if batch:
        parser.add_argument(
            "--limit",
            "-n",
            type=int,
            default=None,
            help="Max tracks to download (default: all)",
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="vncmd",
        description="Netease Cloud Music CLI — search, preview, and download",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    sub.add_parser("init", help="Initialize ~/.vncmd/ with default config")

    p_search = sub.add_parser("search", help="Search songs")
    p_search.add_argument("query", help="Search keyword")
    p_search.add_argument(
        "--limit", "-n", type=int, default=30, help="Max results (default: 30)"
    )
    p_search.add_argument(
        "--offset", type=int, default=0, help="Result offset for pagination"
    )

    p_song = sub.add_parser("song", help="Preview or download a song")
    p_song.add_argument("id", type=int, help="Song ID")
    p_song.add_argument("--lyrics", "-l", action="store_true", help="Show lyrics")
    p_song.add_argument("--tlyric", action="store_true", help="Show translated lyrics")
    p_song.add_argument(
        "--url", "-u", action="store_true", help="Check stream URL availability"
    )
    _add_download_args(p_song)

    p_al = sub.add_parser("album", help="Preview or download an album")
    p_al.add_argument("id", type=int, help="Album ID")
    _add_download_args(p_al, batch=True)

    p_pl = sub.add_parser("playlist", help="Preview or download a playlist")
    p_pl.add_argument("id", type=int, help="Playlist ID")
    _add_download_args(p_pl, batch=True)

    p_tracker = sub.add_parser(
        "tracker", help="Track music sources for changes and batch download"
    )
    p_tracker.add_argument("name", help="Tracker name")
    p_tracker.add_argument(
        "--fetch",
        "-f",
        action="store_true",
        help="Fetch and compare, interactive conflict resolution",
    )
    p_tracker.add_argument(
        "--fetch-auto",
        action="store_true",
        help="Fetch and auto-sync without interaction",
    )
    p_tracker.add_argument(
        "--diff",
        action="store_true",
        help="When used with -d, download only tracks added since last fetch",
    )
    p_tracker.add_argument(
        "--download", "-d", action="store_true", help="Download all cached songs"
    )
    p_tracker.add_argument(
        "--dry-run",
        action="store_true",
        help="Only valid with -d. Preview what would be downloaded without fetching audio.",
    )
    _add_quality_arg(p_tracker)
    _add_output_arg(p_tracker)

    args = parser.parse_args()

    if args.command != "init":
        validate_config()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    dispatch = {
        "init": cmd_init,
        "search": cmd_search,
        "song": cmd_song,
        "album": cmd_album,
        "playlist": cmd_playlist,
        "tracker": cmd_tracker,
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
