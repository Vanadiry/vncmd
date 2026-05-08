import sys

from function.api import (
    search,
    get_song_details,
    get_playlist_details,
    get_album_details,
    get_lyrics,
    get_lyrics_url,
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
    VNCMD_HOME,
    CONFIG_FILE,
    COOKIE_FILE,
)


def _resolve_quality(args: object) -> int:
    if args.quality:
        return QUALITY_MAP[args.quality]
    return get_quality()


def _resolve_output_dir(args: object) -> str:
    if args.output:
        return args.output
    return get_download_dir()


def _download_tracks(
    tracks: list[dict],
    quality: int,
    output_dir: str,
    dry_run: bool = False,
    dl_type: str | None = None,
    dl_id: str | None = None,
) -> None:
    """Shared download for playlists and albums."""
    download_song_batch(
        tracks, quality, output_dir, dry_run=dry_run, dl_type=dl_type, dl_id=dl_id
    )


def cmd_search(args: object) -> None:
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


def cmd_song(args: object) -> None:
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
                console.print(
                    "  [red]✗[/] URL unavailable (VIP or region) — would skip"
                )
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
    lyrics_api = get_lyrics_url(args.id)
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


def cmd_album(args: object) -> None:
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
    _download_tracks(
        al["tracks"],
        quality,
        output_dir,
        dry_run=args.dry_run,
        dl_type="album",
        dl_id=str(args.id),
    )


def cmd_playlist(args: object) -> None:
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
    output_dir = _resolve_output_dir(args)
    _download_tracks(
        pl["tracks"],
        quality,
        output_dir,
        dry_run=args.dry_run,
        dl_type="playlist",
        dl_id=str(args.id),
    )


def cmd_init(args: object) -> None:
    """Initialize ~/.vncmd/ with default config and empty cookie."""
    console.print("[bold]vncmd init[/]\n")

    v = sys.version_info
    console.print(f"  Python {v.major}.{v.minor}.{v.micro}")

    console.print(f"  VNCMD_HOME: {VNCMD_HOME}")
    VNCMD_HOME.mkdir(parents=True, exist_ok=True)

    if CONFIG_FILE.exists():
        console.print("  [dim]config.toml already exists[/]")
    else:
        validate_config()
        console.print("  [green]✓[/] Created config.toml")

    if COOKIE_FILE.exists():
        console.print("  [dim]cookie already exists[/]")
    else:
        COOKIE_FILE.write_text("", encoding="utf-8")
        console.print("  [green]✓[/] Created empty cookie file")
        console.print(
            f"  [dim]Paste your cookie into {COOKIE_FILE} for VIP/high-quality mode.[/]"
        )

    console.print("\n[bold green]Setup complete.[/]")
