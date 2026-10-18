import argparse
import json
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rich.markup import escape

from vncmd.core.config import (
    CONFIG_FILE,
    COOKIE_FILE,
    QUALITY_MAP,
    VNCMD_HOME,
    abbrev_home,
    get_cache_dir,
    get_cache_ttl,
    get_download_content,
    get_quality,
    resolve_output_dir,
    validate_config,
)
from vncmd.core.output import (
    console,
    display_album,
    display_download_detail,
    display_lyrics,
    display_playlist,
    display_search_results,
    display_song_detail,
    err_console,
    error,
    info,
    success,
    warning,
)
from vncmd.downloader import (
    download_song,
    download_song_batch,
    make_session_dir,
)
from vncmd.media.checker import (
    any_check_tool,
    check_audio,
    check_tools,
    describe_missing_check_tools,
)
from vncmd.net.api import (
    SEARCH_LIMIT_MAX,
    account_needs_check,
    account_stamp,
    fetch_player_url,
    fetch_player_urls,
    get_account_info,
    get_album_details,
    get_audio_source,
    get_lyrics,
    get_lyrics_url,
    get_playlist_details,
    get_song_details,
    permission_verdict,
    search,
)


def _resolve_quality(args: argparse.Namespace) -> int:
    if args.quality:
        return QUALITY_MAP[args.quality]
    return get_quality()


def _slice(tracks: list[dict], offset: int, limit: int | None) -> list[dict]:
    """按 offset 与 limit 取一段，limit 为 None 时取到末尾

    album 与 playlist 的分页是纯本地切片：曲目表一次就全给下来了，
    offset 只是在这份列表上换个起点，不发请求。
    """
    end = offset + limit if limit else None
    return tracks[offset:end]


def _download_tracks(
    tracks: list[dict],
    quality: int,
    output_dir: str,
    dl_type: str | None = None,
    dl_id: str | None = None,
    limit: int | None = None,
    offset: int = 0,
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
        offset=offset,
        run_check=run_check,
        use_curl=use_curl,
    )


def cmd_search(args: argparse.Namespace) -> None:
    info(f"正在搜索「{args.query}」...")
    # search 的 offset 与 limit 都是服务端的，直接交给接口即可，
    # 本地再切一刀会把 offset 数两遍。JSON 要全量而服务端单次最多 100 条，
    # 所以「全量」在这里就是那个上限，与 album 的全量语义一致
    limit = args.limit or (SEARCH_LIMIT_MAX if args.json else 10)
    try:
        result = search(args.query, limit=limit, offset=args.offset)
    except Exception as e:
        error(f"搜索失败：{e}")
        sys.exit(1)

    # JSON 模式下一条都没有也是合法结果，输出 {"total": 0, "songs": []}。
    # 空 stdout 加退出码 0 会让脚本分不清「没搜到」与「跑挂了」。
    # 权限判定也不进去：它跟着账号变，同一条命令对不同用户给不同结果，
    # 进了稳定输出就没法缓存也没法 diff。要判的脚本自己调 permission_verdict
    if args.json:
        _dump_json({"search": result})
        return

    if not result["songs"]:
        warning("未找到结果。")
        return

    # 账号状态 main 里已经查过，这里读的是进程内缓存，不发请求
    account = get_account_info()
    blocked = [permission_verdict(s, account) for s in result["songs"]]
    display_search_results(
        args.query, result["songs"], result["total"], blocked, offset=args.offset
    )


def _download_entry(info: dict) -> dict:
    """从 player/url 的原始条目里挑出脚本要用的字段

    原始响应有三十多个字段，一半是 null，其中 freeTrialPrivilege 之类与取
    链接无关。批量时每条都带全套，一个 529 首的歌单能撑出十几万字。

    形状固定，取不到时也照样给全，只是值为空 —— 键一直在，脚本就能用
    .download.url 判断，而不用先问键在不在。

    ``code`` 与 ``payed`` 是判断「为什么拿不到」那两个字段。早先以为失败条目
    只剩 fee 一个有值的，实测（2026-10-17，id 477933827）不是那样：
    ``code=404``、``payed=0`` 都在。它们是接口自己给的结论，不是我们猜的 ——
    与「没依据就不下结论」那条不冲突，恰恰是因为有依据才给。
    """
    return {
        "url": info.get("url") or "",
        "level": info.get("level"),
        "br": info.get("br") or 0,
        "size": info.get("size") or 0,
        "md5": info.get("md5") or "",
        "fee": info.get("fee"),
        "payed": info.get("payed", 0),
        "code": info.get("code", 0),
        "expi": info.get("expi") or 0,
    }


def _attach_downloads(tracks: list[dict], quality: int) -> int:
    """给每条曲目补上 download 键，返回拿不到链接的条数

    原地改 tracks：曲目条目已经在那份列表里，复制一份会让 JSON 多一层壳。
    """
    urls = fetch_player_urls([t["id"] for t in tracks], quality)
    missing = 0
    for t in tracks:
        entry = _download_entry(urls.get(t["id"], {}))
        t["download"] = entry
        if not entry["url"]:
            missing += 1
    return missing


def _dump_json(payload: dict) -> None:
    """把结构化结果写到 stdout 并结束这条命令

    用裸 print 而不是 console.print：rich 会把方括号当样式标记解析，
    而「[Live] 这类标注」这种歌名在本项目里是常事，走 rich 会被吃掉一段
    或者整个抛错。脚本读的东西不经任何渲染层。

    ensure_ascii=False 让中文原样输出，缩进两格让 `> file` 之后还能 diff。
    """
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_song(args: argparse.Namespace) -> None:
    """Preview or download a single song."""
    try:
        song = get_song_details(args.id)
    except Exception as e:
        error(f"获取曲目详情失败：{e}")
        sys.exit(1)

    # 取不到详情时上面已经 error 加 exit 了，stdout 到这里一定是空的，
    # 所以失败时管道里拿到空输出、退出码非零，不需要再输出 {"error": ...}
    if args.json:
        payload = {"song": song}
        # --dlink 与 --json 互补而非冲突：元数据与下载信息一次拿全，
        # 后面 --link 要的就是这个组合
        if args.dlink:
            # 收窄成那七个字段，与 album、playlist 的批量同形
            payload["download"] = _download_entry(
                fetch_player_url(args.id, quality=_resolve_quality(args))
            )
        _dump_json(payload)
        return

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

    want_song = "a" in get_download_content()
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


def _require_json_for_dlink(args: argparse.Namespace) -> None:
    """album 与 playlist 的 --dlink 只在 --json 下有意义

    单曲的 --dlink 打面板，而一批曲目的链接是数据 —— 专辑打 500 个面板没人读。
    放在联网之前查，与 tracker 的 --diff 不配 -d 同样处理：
    让用户在拿到几百首曲目之后才发现参数写错了。
    """
    if args.dlink and not args.json:
        error("--dlink 需要配合 --json 使用：批量链接是数据，面板读不完")
        sys.exit(2)


def _json_payload(args: argparse.Namespace, source: dict) -> dict:
    """按 4.1 那条规则切出要输出的曲目，并按需补上下载链接

    顺序是「先切再取链接」：反过来会为没要的那几百首发一次请求，
    而 stderr 报的还是「529 首中 1 首拿不到」，那个 1 大概率不在用户要的
    那几条里，比例也被无关的条目稀释了。
    """
    tracks = source["tracks"]
    if args.limit is not None or args.offset:
        tracks = _slice(tracks, args.offset, args.limit)

    payload = dict(source)
    payload["tracks"] = tracks

    if args.dlink:
        missing = _attach_downloads(tracks, _resolve_quality(args))
        if missing:
            # 只给数量。不按 fee 分类：FEE_NEED 只映射了 1 与 4，
            # 而实测里 fee=8 出现在三分之一的曲目上，没有任何依据说明它是什么。
            # 分类出来大概率是错的解释，比不给更糟
            warning(f"{missing} 首拿不到链接")
    return payload


def cmd_album(args: argparse.Namespace) -> None:
    """Preview or download an album."""
    _require_json_for_dlink(args)
    try:
        al = get_album_details(args.id)
    except Exception as e:
        error(f"获取专辑失败：{e}")
        sys.exit(1)

    # 面板只显示一段，JSON 给的是完整曲目表：
    # 表格给人看要截断免得刷屏，脚本要数据就得齐
    if args.json:
        _dump_json({"album": _json_payload(args, al)})
        return

    display_album(al, max_tracks=args.limit or 10, offset=args.offset)

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
        offset=args.offset,
        run_check=args.check,
        use_curl=args.curl,
    )


def cmd_playlist(args: argparse.Namespace) -> None:
    """Preview or download a playlist."""
    _require_json_for_dlink(args)
    try:
        pl = get_playlist_details(args.id)
    except Exception as e:
        error(f"获取歌单失败：{e}")
        sys.exit(1)

    # 同 album：面板截断，JSON 给全量
    if args.json:
        _dump_json({"playlist": _json_payload(args, pl)})
        return

    display_playlist(pl, max_tracks=args.limit or 10, offset=args.offset)

    removed = pl.get("removed_tracks", [])
    # 明细跟在 warning 的标题下面，两边都进 stderr
    if removed:
        err_console.print()
        warning(f"此歌单中有 {len(removed)} 首已下架曲目：")
        for r in removed:
            err_console.print(
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
        offset=args.offset,
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

    # 路径一律走 abbrev_home，主目录那段替成 ~：
    # 设置、tracker 面板、cache 都用同一个写法，
    # 而 VNCMD_HOME 是环境变量换出来的，展开写会是一长串
    console.print(f"  VNCMD_HOME: {abbrev_home(VNCMD_HOME)}")
    VNCMD_HOME.mkdir(parents=True, exist_ok=True)

    # 这几行一律只报文件名，不带路径：上面已经给过 VNCMD_HOME 了，
    # 同一屏里把同一段路径写两遍是重复
    if CONFIG_FILE.exists():
        console.print(f"  [dim]存在 {CONFIG_FILE.name}[/]")
    else:
        validate_config(quiet=True)
        success(f"已创建 {CONFIG_FILE.name}")

    if COOKIE_FILE.exists():
        console.print(f"  [dim]存在 {COOKIE_FILE.name}[/]")
    else:
        _write_cookie("")
        # 同一句话里说清位置与用途，不再单起一行重复路径
        success(
            f"已创建 {COOKIE_FILE.name}，"
            "粘贴登录 Cookie 到该文件即可下载 VIP 与高音质歌曲"
        )

    # Check system dependencies
    tools = check_tools()
    found = [name for name in tools if tools[name]]
    missing = [name for name in tools if not tools[name]]
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
    """Set or check the Cookie.

    值与 --check 同给由 argparse 的互斥组拦住，这里不再重复校验。
    """
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
        err_console.print()
        # 命令名跟 parser 一起改的，写错会让用户照着敲出一个不存在的命令
        info('"用 vncmd tool cache --clear 清空缓存"')


def cmd_check(args: argparse.Namespace) -> None:
    """Check audio file integrity."""
    if not any_check_tool():
        error("没有可用的校验工具，请至少安装 ffmpeg 或 flac 后重试。")
        sys.exit(1)

    note = describe_missing_check_tools()
    if note:
        # 只说一次，不影响检查本身 —— 缺哪样就只跳过那一步
        warning(note)

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
