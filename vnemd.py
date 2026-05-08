import argparse
import sys

from function.api import (
    search,
    get_song_details,
    get_playlist_details,
    get_album_details,
    get_lyrics,
    get_song_url,
)
from function.downloader import download_song, download_song_batch, make_session_dir
from function.output import (
    display_search_results,
    display_album,
    display_song_detail,
    display_playlist,
    display_lyrics,
    success,
    error,
    info,
    warning,
    console,
)
from function.config import (
    validate_config,
    get_quality,
    get_download_dir,
    get_download_content,
    QUALITY_MAP,
)
from function.tracker import cmd_tracker


def _resolve_quality(args):
    if args.quality:
        return QUALITY_MAP[args.quality]
    return get_quality()


def _resolve_output_dir(args):
    if args.output:
        return args.output
    return get_download_dir()


def _download_tracks(tracks, quality, output_dir, dry_run=False):
    """Shared download for playlists and albums."""
    download_song_batch(tracks, quality, output_dir, dry_run=dry_run)


def cmd_search(args):
    info(f'Searching "{args.query}"...')
    try:
        result = search(args.query, limit=args.limit, offset=args.offset)
    except Exception as e:
        error(f"Search failed: {e}")
        sys.exit(1)

    if not result["songs"]:
        warning("No results found.")
        return

    display_search_results(args.query, result["songs"], result["total"])


def cmd_song(args):
    """Preview or download a single song."""
    try:
        song = get_song_details(args.id)
    except Exception as e:
        error(f"Failed to get song details: {e}")
        sys.exit(1)

    display_song_detail(song)

    if args.lyrics:
        lyrics_data = get_lyrics(args.id)
        lyric = lyrics_data.get("lrc", {}).get("lyric", "")
        if args.tlyric:
            tlyric = lyrics_data.get("tlyric", {}).get("lyric", "")
            if tlyric:
                lyric = lyric + "\n\n--- 翻译 ---\n" + tlyric
        display_lyrics(lyric)

    if args.url and not args.download:
        quality = _resolve_quality(args)
        url = get_song_url(args.id, quality=quality)
        if url:
            success(f"Stream URL available: {url[:80]}...")
        else:
            warning("Stream URL unavailable — may be VIP-only or require cookie")

    if not args.download:
        return

    if args.dry_run:
        quality = _resolve_quality(args)
        want_song = "0" in get_download_content()
        console.print(f"[bold cyan]Dry run[/] — {song['title']} - {song['artist']}")
        if not want_song:
            console.print("  [dim]Would download (audio disabled in config)[/]")
        else:
            song_url = get_song_url(args.id, quality=quality)
            if song_url:
                console.print("  [green]✓[/] URL available — would download")
            else:
                console.print("  [red]✗[/] URL unavailable (VIP or region) — would skip")
        return

    want_song = "0" in get_download_content()
    quality = _resolve_quality(args)
    song_url = None
    if want_song:
        info(f"Getting stream URL (quality={args.quality or 'config'})...")
        song_url = get_song_url(args.id, quality=quality)
        if not song_url:
            error("No stream URL available. This song may be VIP-only.")
            error("Add a cookie to config/cookie for VIP songs.")
            sys.exit(1)

    output_dir = make_session_dir(_resolve_output_dir(args))
    info(f"Downloading: {song['title']} - {song['artist']}")
    lyrics_api = f"http://music.163.com/api/song/lyric?os=pc&id={args.id}&lv=-1&tv=1"
    ok, msg, path = download_song(
        song_url=song_url,
        song_title=song["title"],
        song_artist=song["artist"],
        song_album=song["album"],
        song_id=str(song["id"]),
        cover_url=song["cover"],
        lyrics_api_url=lyrics_api,
        publish_time=song["publish_time"],
        download_dir=output_dir,
    )
    if ok:
        success(msg)
    else:
        error(msg)


def cmd_album(args):
    """Preview or download an album."""
    try:
        al = get_album_details(args.id)
    except Exception as e:
        error(f"Failed to get album: {e}")
        sys.exit(1)

    display_album(al, max_tracks=args.limit or 10)

    if not args.download:
        return

    quality = _resolve_quality(args)
    output_dir = make_session_dir(_resolve_output_dir(args))
    _download_tracks(al["tracks"], quality, output_dir, dry_run=args.dry_run)


def cmd_playlist(args):
    """Preview or download a playlist."""
    try:
        pl = get_playlist_details(
            args.id, limit=args.limit if args.download else (args.limit or 10)
        )
    except Exception as e:
        error(f"Failed to get playlist: {e}")
        sys.exit(1)

    display_playlist(pl, max_tracks=args.limit or 10)

    if not args.download:
        return

    quality = _resolve_quality(args)
    output_dir = make_session_dir(_resolve_output_dir(args))
    _download_tracks(pl["tracks"], quality, output_dir, dry_run=args.dry_run)


def _add_download_args(parser, batch=False):
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


def _add_quality_arg(parser):
    parser.add_argument(
        "--quality",
        "-q",
        choices=list(QUALITY_MAP),
        default=None,
        help="Audio quality (default: from config)",
    )


def _add_output_arg(parser):
    parser.add_argument(
        "--output", "-o", default=None, help="Output directory (default: from config)"
    )


def main():
    parser = argparse.ArgumentParser(
        prog="vnemd",
        description="Netease Cloud Music CLI — search, preview, and download",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

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

    validate_config()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    dispatch = {
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
