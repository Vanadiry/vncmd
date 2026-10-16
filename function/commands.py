import argparse
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rich.markup import escape

from function.api import (
    account_needs_check,
    account_stamp,
    fetch_player_url,
    get_account_info,
    get_album_details,
    get_audio_source,
    get_lyrics,
    get_lyrics_url,
    get_playlist_details,
    get_song_details,
    search,
)
from function.checker import check_audio, has_ffmpeg
from function.config import (
    CONFIG_FILE,
    COOKIE_FILE,
    QUALITY_MAP,
    VNCMD_HOME,
    get_cache_dir,
    get_cache_ttl,
    get_download_content,
    get_quality,
    resolve_output_dir,
    validate_config,
)
from function.downloader import (
    download_song,
    download_song_batch,
    make_session_dir,
)
from function.output import (
    abbrev_home,
    console,
    display_album,
    display_download_detail,
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
    run_check: bool | None = None,
    use_curl: bool | None = None,
) -> None:
    """Shared download for playlists and albums."""
    download_song_batch(
        tracks,
        quality,
        output_dir,
        dl_type=dl_type,
        dl_id=dl_id,
        limit=limit,
        run_check=run_check,
        use_curl=use_curl,
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

    # --dlink 自己会给一个辨认用的标题，不必再打完整详情卡
    if not args.dlink:
        display_song_detail(song)

    if args.lyrics:
        lyrics_data = get_lyrics(args.id)
        lyric = lyrics_data.get("lrc", {}).get("lyric", "")
        if args.tlyric:
            tlyric = lyrics_data.get("tlyric", {}).get("lyric", "")
            if tlyric:
                lyric = lyric + "\n\n--- 翻译 ---\n" + tlyric
        display_lyrics(lyric)

    if args.dlink and not args.download:
        # 完整详情卡对看下载信息没有帮助，面板里已经带了标题用于辨认
        quality = _resolve_quality(args)
        display_download_detail(
            args.id, song["title"], fetch_player_url(args.id, quality=quality)
        )

    if not args.download:
        return

    want_song = "0" in get_download_content()
    quality = _resolve_quality(args)
    source = None
    if want_song:
        info(f"正在获取流 URL（音质={args.quality or '配置'}）...")
        for attempt in range(1, 4):
            source = get_audio_source(args.id, quality=quality)
            if source:
                break
            if attempt < 3:
                info(f"  重试 {attempt}/3 …")
        if not source:
            error("无法获取下载链接，若其他曲目能够正常下载，则可能是这个曲目有问题。")
            sys.exit(1)

    output_dir = make_session_dir(resolve_output_dir(args.output))
    info(f"正在下载「{song['title']} - {song['artist']}」")
    info(f'下载到 "{abbrev_home(output_dir)}"')
    lyrics_api = get_lyrics_url(args.id)
    ok, msg, _ = download_song(
        song_url=source.url if source else "",
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
        song_size=source.size if source else 0,
        song_md5=source.md5 if source else "",
        run_check=args.check,
        use_curl=args.curl,
        song_level=source.level if source else "",
        want_br=quality,
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
        run_check=args.check,
        use_curl=args.curl,
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
        run_check=args.check,
        use_curl=args.curl,
    )


def _write_cookie(value: str) -> None:
    COOKIE_FILE.write_text(value, encoding="utf-8")
    # Cookie 是完整的登录凭证，umask 022 下默认是同机可读。
    # Windows 只认只读位，那里的 chmod 等于确保可写，无害
    os.chmod(COOKIE_FILE, 0o600)


def announce_account() -> None:
    """联网查过 Cookie 权限才报一次，命中缓存就静默

    必须放在取链接之前：付费歌拿不到链接时会直接退出，
    等到落盘那一步就永远等不到这条提示了。

    报的是「刚查出来是这样」，不是「此刻是这样」。缓存里那份一天至多刷新一次，
    每次运行都复读一遍只会变成噪声，用户真正要提醒的那一次反而被淹掉。
    """
    # 请求之前先说一声，不然中间那一下停顿看着像卡住了
    if account_needs_check():
        info("正在检查 Cookie 权限，请稍候...")

    state = get_account_info()
    if account_stamp()[1]:
        return

    if state is None:
        warning("Cookie 检查失败：无法获取账号信息，不影响本次下载")
    elif not state["logged_in"]:
        warning("未检测到登录状态，可能是 Cookie 有问题或登录已失效，可尝试重新获取")
    elif not state["vip"]:
        warning("Cookie 所属账号没有 VIP 权限，高音质将不可用")
    else:
        success("Cookie 权限：已登录，有 VIP 权限")


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
    """Set or check the Cookie."""
    if args.check and args.value:
        error("--check 不写文件，与 Cookie 值不能一起给")
        sys.exit(2)
    if not args.check and not args.value:
        error("请给出 Cookie 值，或用 --check 只检查当前状态")
        sys.exit(2)

    if args.value:
        VNCMD_HOME.mkdir(parents=True, exist_ok=True)
        _write_cookie(args.value.strip())
        success("Cookie 已保存")

    info("正在检查账户权限，请稍候...")
    # 强制检查：cookie 刚被改过，缓存里那份描述的是另一个人
    account = get_account_info(force=True)
    if account is None:
        # 断网、DNS 失败、CDN 返回 HTML 都会走到这里，
        # 退出码 2 让脚本能分辨「查不成」与「查出无效」
        error("Cookie 检查失败：无法获取账号信息")
        sys.exit(2)
    if not account["logged_in"]:
        error("Cookie 无效或登录已失效，请检查，或重新获取")
        sys.exit(1)
    if not account["vip"]:
        # 非会员的 Cookie 是能用的，只是拿不到高音质，
        # 判成失败会让脚本以为 Cookie 没设成功
        warning("Cookie 有效，但所属账号没有 VIP 权限，高音质将不可用")
        return
    success("Cookie 有效")


def cmd_cache(args: argparse.Namespace) -> None:
    """查看或清理本地缓存。"""
    root = Path(get_cache_dir())
    if not root.is_dir():
        info('"缓存目录不存在，无需处理"')
        return

    songs = sorted((root / "song").glob("*")) if (root / "song").is_dir() else []
    files = [f for f in root.rglob("*") if f.is_file()]
    size = sum(f.stat().st_size for f in files)

    if args.stats or not args.clear:
        ttl = get_cache_ttl()
        console.print(f'缓存目录："{abbrev_home(root)}"')
        console.print(f"占用：{size / 1024 / 1024:.1f} MB，共 {len(files)} 个文件")
        console.print(f"曲目：{len(songs)} 首")
        console.print(f"有效期：{'永不过期' if ttl == 0 else f'{ttl} 天'}")

    if args.clear:
        shutil.rmtree(root)
        success(f'"已清空缓存，释放 {size / 1024 / 1024:.1f} MB"')
    else:
        console.print()
        info('"用 vncmd cache --clear 清空缓存"')


def cmd_check(args: argparse.Namespace) -> None:
    """Check audio file integrity."""
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
        # 按提交顺序取结果而不是 as_completed，否则输出顺序随线程完成顺序变，
        # 同一个目录两次运行长得不一样。检查本身仍是并发的
        futures = [(f, pool.submit(check_audio, str(f))) for f in files]
        for f, future in futures:
            # 一个文件抛异常不能让整条命令中断，已经检查过的结果不能白跑
            exc = future.exception()
            if exc is not None:
                bad_count += 1
                bad_files.append((f, f"{type(exc).__name__}: {exc}"))
                console.print(f"  [red]BAD[/] {_show(f)}  检查失败")
                continue
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
