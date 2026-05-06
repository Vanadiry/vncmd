#!/usr/bin/env python3
import argparse
import sys
import time

from function.api import (
    search,
    get_song_details,
    get_playlist_details,
    get_album_details,
    get_lyrics,
    get_song_url,
)
from function.downloader import download_song
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
    get_quality, get_download_dir, get_download_content, QUALITY_MAP,
)


def _resolve_quality(args):
    if args.quality:
        return QUALITY_MAP[args.quality]
    return get_quality()


def _resolve_output_dir(args):
    if args.output:
        return args.output
    return get_download_dir()


def _download_tracks(tracks, quality, output_dir):
    """Shared download loop for playlists and albums."""
    want_song = "0" in get_download_content()
    success_count = 0
    fail_count = 0
    fail_ids = []

    for i, track in enumerate(tracks, 1):
        sid = track["id"]
        title = track["title"]
        artist = track["artist"]

        info(f"[{i}/{len(tracks)}] {title} - {artist}")

        song_url = ""
        if want_song:
            song_url = get_song_url(sid, quality=quality) or ""
            if not song_url:
                warning(f"  Skipping (no URL — VIP or unavailable): {sid}")
                fail_count += 1
                fail_ids.append(sid)
                continue

        lyrics_api = f"http://music.163.com/api/song/lyric?os=pc&id={sid}&lv=-1&tv=1"
        ok, msg, _ = download_song(
            song_url=song_url,
            song_title=title,
            song_artist=artist,
            song_album=track["album"],
            song_id=str(sid),
            cover_url=track["cover"],
            lyrics_api_url=lyrics_api,
            publish_time=track["publish_time"],
            download_dir=output_dir,
        )
        if ok:
            success_count += 1
            console.print(f"  [green]✓[/] Downloaded")
        else:
            fail_count += 1
            fail_ids.append(sid)
            console.print(f"  [red]✗[/] {msg}")

        time.sleep(0.3)

    console.print()
    console.print(f"Done: [green]{success_count} success[/], [red]{fail_count} failed[/]")
    if fail_ids:
        console.print(f"Failed IDs: {', '.join(str(i) for i in fail_ids)}")


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

    output_dir = _resolve_output_dir(args)
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
    output_dir = _resolve_output_dir(args)
    _download_tracks(al["tracks"], quality, output_dir)


def cmd_playlist(args):
    """Preview or download a playlist."""
    try:
        pl = get_playlist_details(args.id, limit=args.limit if args.download else (args.limit or 10))
    except Exception as e:
        error(f"Failed to get playlist: {e}")
        sys.exit(1)

    display_playlist(pl, max_tracks=args.limit or 10)

    if not args.download:
        return

    quality = _resolve_quality(args)
    output_dir = _resolve_output_dir(args)
    _download_tracks(pl["tracks"], quality, output_dir)


def _add_download_args(parser, batch=False):
    """Add download-related args to a parser."""
    parser.add_argument("--download", "-d", action="store_true",
                        help="Download instead of preview only")
    _add_quality_arg(parser)
    _add_output_arg(parser)
    if batch:
        parser.add_argument("--limit", "-n", type=int, default=None,
                            help="Max tracks to download (default: all)")


def _add_quality_arg(parser):
    parser.add_argument("--quality", "-q", choices=list(QUALITY_MAP), default=None,
                        help="Audio quality (default: from config)")


def _add_output_arg(parser):
    parser.add_argument("--output", "-o", default=None,
                        help="Output directory (default: from config)")


def main():
    parser = argparse.ArgumentParser(
        prog="vnemd",
        description="Netease Cloud Music CLI — search, preview, and download",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    p_search = sub.add_parser("search", help="Search songs")
    p_search.add_argument("query", help="Search keyword")
    p_search.add_argument("--limit", "-n", type=int, default=30, help="Max results (default: 30)")
    p_search.add_argument("--offset", type=int, default=0, help="Result offset for pagination")

    p_song = sub.add_parser("song", help="Preview or download a song")
    p_song.add_argument("id", type=int, help="Song ID")
    p_song.add_argument("--lyrics", "-l", action="store_true", help="Show lyrics")
    p_song.add_argument("--tlyric", action="store_true", help="Show translated lyrics")
    p_song.add_argument("--url", "-u", action="store_true", help="Check stream URL availability")
    _add_download_args(p_song)

    p_al = sub.add_parser("album", help="Preview or download an album")
    p_al.add_argument("id", type=int, help="Album ID")
    _add_download_args(p_al, batch=True)

    p_pl = sub.add_parser("playlist", help="Preview or download a playlist")
    p_pl.add_argument("id", type=int, help="Playlist ID")
    _add_download_args(p_pl, batch=True)

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
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
