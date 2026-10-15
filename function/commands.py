import argparse
import os
import shutil
import sys

from rich.markup import escape

from function.api import (
    get_album_details,
    get_lyrics,
    get_lyrics_url,
    get_playlist_details,
    get_song_details,
    get_song_url,
    search,
)
from function.config import (
    CONFIG_FILE,
    COOKIE_FILE,
    QUALITY_MAP,
    VNCMD_HOME,
    get_download_content,
    get_quality,
    resolve_output_dir,
    validate_config,
)
from function.downloader import download_song, download_song_batch, make_session_dir
from function.output import (
    abbrev_home,
    console,
    display_album,
    display_lyrics,
    display_playlist,
    display_search_results,
    display_song_detail,
    error,
    info,
    success,
    warning,
)


def _resolve_quality(args: argparse.Namespace) -> int:
    if args.quality:
        return QUALITY_MAP[args.quality]
    return get_quality()


def _download_tracks(
    tracks: list[dict],
    quality: int,
    output_dir: str,
    dl_type: str | None = None,
    dl_id: str | None = None,
    limit: int | None = None,
) -> None:
    """Shared download for playlists and albums."""
    download_song_batch(
        tracks, quality, output_dir, dl_type=dl_type, dl_id=dl_id, limit=limit
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

    output_dir = make_session_dir(resolve_output_dir(args.output))
    info(f"正在下载「{song['title']} - {song['artist']}」")
    info(f'下载到 "{abbrev_home(output_dir)}"')
    lyrics_api = get_lyrics_url(args.id)
    ok, msg, _ = download_song(
        song_url=song_url or "",
        song_title=song["title"],
        song_artist=song["artist"],
        song_album=song["album"],
        song_id=song["id"],
        cover_url=song["cover"],
        lyrics_api_url=lyrics_api,
        publish_time=song["publish_time"],
        download_dir=output_dir,
        track_no=song.get("track_no"),
        cd_no=song.get("cd_no"),
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
    output_dir = resolve_output_dir(args.output)
    _download_tracks(
        al["tracks"],
        quality,
        output_dir,
        dl_type="album",
        dl_id=str(args.id),
        limit=args.limit,
    )


def cmd_playlist(args: argparse.Namespace) -> None:
    """Preview or download a playlist."""
    try:
        pl = get_playlist_details(args.id)
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
    output_dir = resolve_output_dir(args.output)
    _download_tracks(
        pl["tracks"],
        quality,
        output_dir,
        dl_type="playlist",
        dl_id=str(args.id),
        limit=args.limit,
    )


def _write_cookie(value: str) -> None:
    COOKIE_FILE.write_text(value, encoding="utf-8")
    # Cookie 是完整的登录凭证，umask 022 下默认是同机可读。
    # Windows 只认只读位，那里的 chmod 等于确保可写，无害
    os.chmod(COOKIE_FILE, 0o600)


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
        validate_config(quiet=True)
        success("已创建 config.toml")

    if COOKIE_FILE.exists():
        console.print("  [dim]存在 cookie[/]")
    else:
        _write_cookie("")
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


def cmd_cookie(args: argparse.Namespace) -> None:
    """Set the Cookie."""
    VNCMD_HOME.mkdir(parents=True, exist_ok=True)
    _write_cookie(args.value.strip())
    success("Cookie 已保存")

    from function.api import get_song_url

    info("正在检查 Cookie 权限，请稍候...")
    for _ in range(2):
        if get_song_url(2056952623):
            success("Cookie 有效")
            return
    warning("Cookie 可能无 VIP 权限")


def cmd_check(args: argparse.Namespace) -> None:
    """Check audio file integrity."""
    import concurrent.futures
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path

    from function.checker import check_audio, has_ffmpeg

    if not has_ffmpeg():
        error("需要 ffmpeg 和 ffprobe，请先安装。")
        sys.exit(1)

    path = Path(os.path.expanduser(args.path))
    if not path.exists():
        error(f"路径不存在：{args.path}")
        sys.exit(1)

    SUPPORTED = {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".opus", ".wma", ".ape"}
    files = []
    if path.is_file():
        if path.suffix.lower() in SUPPORTED:
            files.append(path)
    else:
        for f in path.rglob("*"):
            if f.is_file() and f.suffix.lower() in SUPPORTED:
                files.append(f)
    files.sort()

    if not files:
        info("未找到支持的音频文件。")
        return

    console.print(f"共 [bold]{len(files)}[/] 个文件，开始检查\n")
    ok_count = bad_count = 0
    bad_files = []

    def _show(f: Path) -> str:
        """传目录时只显示相对路径，绝对路径折行会把文件名断在中间。
        加引号是为了让 rich 把它当字符串整体着色，否则目录与文件名会被涂成两种颜色"""
        rel = f.relative_to(path) if path.is_dir() else f.name
        return f'"{escape(str(rel))}"'

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(check_audio, str(f)): f for f in files}
        for future in concurrent.futures.as_completed(futures):
            f = futures[future]
            ok, msg = future.result()
            if ok:
                ok_count += 1
                console.print(f"  [cyan]OK[/]  {_show(f)}")
            else:
                bad_count += 1
                bad_files.append((f, msg))
                console.print(f"  [red]BAD[/] {_show(f)}  {msg}")

    console.print(f"\n完成：[cyan]{ok_count} 通过[/]，[red]{bad_count} 损坏[/]")
    if bad_files:
        console.print("损坏文件：")
        for f, msg in bad_files:
            console.print(f"  [red]{_show(f)}[/]  {msg}")
