import argparse
import shutil
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
from rich.markup import escape
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


def _resolve_quality(args: argparse.Namespace) -> int:
    if args.quality:
        return QUALITY_MAP[args.quality]
    return get_quality()


def _resolve_output_dir(args: argparse.Namespace) -> str:
    if args.output:
        return args.output
    return get_download_dir()


def _download_tracks(
    tracks: list[dict],
    quality: int,
    output_dir: str,
    dl_type: str | None = None,
    dl_id: str | None = None,
) -> None:
    """Shared download for playlists and albums."""
    download_song_batch(
        tracks, quality, output_dir, dl_type=dl_type, dl_id=dl_id
    )


def cmd_search(args: argparse.Namespace) -> None:
    info(f"正在搜索「{args.query}」...")
    try:
        result = search(args.query, limit=args.limit, offset=args.offset)
    except Exception as e:
        error(f"搜索失败：{e}")
        sys.exit(1)

    if not result["songs"]:
        warning("未找到结果。")
        return

    display_search_results(args.query, result["songs"], result["total"])


def cmd_song(args: argparse.Namespace) -> None:
    """Preview or download a single song."""
    try:
        song = get_song_details(args.id)
    except Exception as e:
        error(f"获取曲目详情失败：{e}")
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
            url_display = url if len(url) <= 80 else f"{url[:77]}..."
            success(f"流 URL 可用：{url_display}")
        else:
            warning("流 URL 不可用")

    if not args.download:
        return

    want_song = "0" in get_download_content()
    quality = _resolve_quality(args)
    song_url = None
    if want_song:
        info(f"正在获取流 URL（音质={args.quality or '配置'}）...")
        for attempt in range(1, 4):
            song_url = get_song_url(args.id, quality=quality)
            if song_url:
                break
            if attempt < 3:
                info(f"  重试 {attempt}/3 …")
        if not song_url:
            error("无法获取下载链接，若其他曲目能够正常下载，则可能是这个曲目有问题。")
            sys.exit(1)

    output_dir = make_session_dir(_resolve_output_dir(args))
    info(f"正在下载「{song['title']} - {song['artist']}」")
    lyrics_api = get_lyrics_url(args.id)
    ok, msg, path = download_song(
        song_url=song_url or "",
        song_title=song["title"],
        song_artist=song["artist"],
        song_album=song["album"],
        song_id=song["id"],
        cover_url=song["cover"],
        lyrics_api_url=lyrics_api,
        publish_time=song["publish_time"],
        download_dir=output_dir,
    )
    if ok:
        success(msg)
    else:
        error(msg)


def cmd_album(args: argparse.Namespace) -> None:
    """Preview or download an album."""
    try:
        al = get_album_details(args.id)
    except Exception as e:
        error(f"获取专辑失败：{e}")
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
        dl_type="album",
        dl_id=str(args.id),
    )


def cmd_playlist(args: argparse.Namespace) -> None:
    """Preview or download a playlist."""
    try:
        pl = get_playlist_details(
            args.id, limit=args.limit if args.download else (args.limit or 10)
        )
    except Exception as e:
        error(f"获取歌单失败：{e}")
        sys.exit(1)

    display_playlist(pl, max_tracks=args.limit or 10)

    removed = pl.get("removed_tracks", [])
    if removed:
        console.print()
        warning(f"此歌单中有 {len(removed)} 首已下架曲目：")
        for r in removed:
            console.print(
                f"    [dim]{r['id']}[/]  [red]{escape(r['title'])}[/]"
                f"  [dim]— {escape(r['artist'])}  ·  {escape(r['album'])}[/]"
            )

    if not args.download:
        return

    quality = _resolve_quality(args)
    output_dir = _resolve_output_dir(args)
    _download_tracks(
        pl["tracks"],
        quality,
        output_dir,
        dl_type="playlist",
        dl_id=str(args.id),
    )


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize ~/.vSoft/vncmd/ with default config and empty cookie."""
    console.print()

    v = sys.version_info
    console.print(f"  Python {v.major}.{v.minor}.{v.micro}")

    console.print(f"  VNCMD_HOME: {VNCMD_HOME}")
    VNCMD_HOME.mkdir(parents=True, exist_ok=True)

    if CONFIG_FILE.exists():
        console.print("  [dim]存在 config.toml[/]")
    else:
        validate_config()
        success("已创建 config.toml")

    if COOKIE_FILE.exists():
        console.print("  [dim]存在 cookie[/]")
    else:
        COOKIE_FILE.write_text("", encoding="utf-8")
        success("已创建空 cookie 文件")
        console.print(f"  [dim]将 Cookie 粘贴到 {COOKIE_FILE} 以使用 VIP/高音质模式[/]")

    # Check system dependencies
    missing = []
    found = []
    for dep, name in [("ffmpeg", "ffmpeg"), ("flac", "flac")]:
        if shutil.which(dep):
            found.append(name)
        else:
            missing.append(name)
    if found:
        console.print(f"  [dim]存在 {' / '.join(found)}[/]")
    if missing:
        warning(f"未检测到 {' / '.join(missing)}")
        info("若安装了这些系统库，就可以使用 Check 功能，详细请阅读文档")

    console.print()
    success("初始化完成。")
    console.print(
        "  [dim]建议阅读详细指南：[/]"
        "https://github.com/Vanadiry/vncmd/blob/main/doc/guide.md"
    )
    console.print()
