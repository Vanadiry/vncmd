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
    VNCMD_HOME,
    abbrev_home,
    get_cache_dir,
    get_cache_ttl,
    get_download_content,
    get_download_dir,
    get_quality,
    get_quality_name,
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
from vncmd.session import make_session_dir


def _slice(tracks: list[dict], offset: int, limit: int | None) -> list[dict]:
    """按 offset 与 limit 取一段，limit 为 None 时取到末尾"""
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
    """批量下载，专辑与歌单共用"""
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
    info(f"正在搜索“{args.query}”")
    # search 的分页交给服务端，JSON 要全量，单次上限为 100
    limit = args.count or (SEARCH_LIMIT_MAX if args.json else 10)
    try:
        result = search(args.query, limit=limit, offset=args.offset)
    except Exception as e:
        error(f"搜索失败：{e}")
        sys.exit(1)

    # 空结果也输出 JSON，避免脚本分不清没搜到与失败
    # 权限判定随账号变化，不进入稳定输出
    if args.json:
        _dump_json({"search": result})
        return

    if not result["songs"]:
        warning("未找到结果")
        return

    # 账号状态 main 已查过，这里读进程内缓存
    account = get_account_info()
    blocked = [permission_verdict(s, account) for s in result["songs"]]
    display_search_results(
        args.query, result["songs"], result["total"], blocked, offset=args.offset
    )


def _download_entry(info: dict) -> dict:
    """从 player/url 条目里挑出脚本字段

    字段固定，取不到也给键；code 与 payed 用于判断失败原因
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
    """给每条曲目补 download 键，返回拿不到链接的条数"""
    urls = fetch_player_urls([t["id"] for t in tracks], quality)
    missing = 0
    for t in tracks:
        entry = _download_entry(urls.get(t["id"], {}))
        t["download"] = entry
        if not entry["url"]:
            missing += 1
    return missing


def _dump_json(payload: dict) -> None:
    """把结构化结果写到 stdout

    用裸 print，避免 rich 把歌名里的方括号当成样式标记
    """
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_song(args: argparse.Namespace) -> None:
    """预览或下载单曲"""
    # --translate 只修饰 --lyric，参数写错时先报错再联网
    if args.translate and not args.lyric:
        error("--translate 只能与 --lyric 同时使用")
        sys.exit(2)

    try:
        song = get_song_details(args.id)
    except Exception as e:
        error(f"获取曲目详情失败：{e}")
        sys.exit(1)

    # 取详情失败已退出，stdout 保持为空
    if args.json:
        payload = {"song": song}
        # --dlink 与 --json 互补，元数据与下载信息一次拿全
        if args.dlink:
            # 收窄成固定字段，与批量输出同形
            payload["download"] = _download_entry(
                fetch_player_url(args.id, quality=get_quality())
            )
        _dump_json(payload)
        return

    # --dlink 自带标题，不再重复打详情卡
    if not args.dlink:
        display_song_detail(song)

    if args.lyric:
        lyrics_data = get_lyrics(args.id)
        lyric = lyrics_data.get("lrc", {}).get("lyric", "")
        if args.translate:
            tlyric = lyrics_data.get("tlyric", {}).get("lyric", "")
            if tlyric:
                lyric = lyric + "\n\n翻译\n" + tlyric
        display_lyrics(lyric)

    if args.dlink and not args.download:
        # 下载信息面板已带标题，不再打详情卡
        quality = get_quality()
        display_download_detail(
            args.id, song["title"], fetch_player_url(args.id, quality=quality)
        )

    if not args.download:
        return

    want_song = "a" in get_download_content()
    quality = get_quality()
    source = None
    if want_song:
        info(f"正在获取音频流，音质 {get_quality_name()}")
        for attempt in range(1, 4):
            source = get_audio_source(args.id, quality=quality)
            if source:
                break
            if attempt < 3:
                info(f"  重试 {attempt}/3")
        if not source:
            error("无法提取下载链接，该曲目可能受限")
            sys.exit(1)

    output_dir = make_session_dir(get_download_dir())
    info(f"正在下载“{song['title']} - {song['artist']}”")
    info(f"下载到 {abbrev_home(output_dir)}")
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
        run_check=None,
        use_curl=None,
        song_level=source.level if source else "",
        want_br=quality,
    )
    if ok:
        success(msg)
    else:
        error(msg)


def _require_json_for_dlink(args: argparse.Namespace) -> None:
    """album 与 playlist 的 --dlink 只在 --json 下有意义"""
    if args.dlink and not args.json:
        error("--dlink 只能与 --json 同时使用")
        sys.exit(2)


def _json_payload(args: argparse.Namespace, source: dict) -> dict:
    """切出要输出的曲目，并按需补下载链接

    先切再取链接，避免为未选中的曲目发请求
    """
    tracks = source["tracks"]
    if args.count is not None or args.offset:
        tracks = _slice(tracks, args.offset, args.count)

    payload = dict(source)
    payload["tracks"] = tracks

    if args.dlink:
        missing = _attach_downloads(tracks, get_quality())
        if missing:
            # 只给数量，不按 fee 分类，fee=8 的含义没有可靠依据
            warning(f"{missing} 首未能提取下载链接")
    return payload


def cmd_album(args: argparse.Namespace) -> None:
    """预览或下载专辑"""
    _require_json_for_dlink(args)
    try:
        al = get_album_details(args.id)
    except Exception as e:
        error(f"获取专辑失败：{e}")
        sys.exit(1)

    # 面板截断避免刷屏，JSON 给完整曲目表
    if args.json:
        _dump_json({"album": _json_payload(args, al)})
        return

    display_album(al, max_tracks=args.count or 10, offset=args.offset)

    if not args.download:
        return

    quality = get_quality()
    output_dir = get_download_dir()
    _download_tracks(
        al["tracks"],
        quality,
        output_dir,
        dl_type="album",
        dl_id=str(args.id),
        limit=args.count,
        offset=args.offset,
        run_check=None,
        use_curl=None,
    )


def cmd_playlist(args: argparse.Namespace) -> None:
    """预览或下载歌单"""
    _require_json_for_dlink(args)
    try:
        pl = get_playlist_details(args.id)
    except Exception as e:
        error(f"获取歌单失败：{e}")
        sys.exit(1)

    # 面板截断，JSON 给全量
    if args.json:
        _dump_json({"playlist": _json_payload(args, pl)})
        return

    display_playlist(pl, max_tracks=args.count or 10, offset=args.offset)

    removed = pl.get("removed_tracks", [])
    # 明细跟在 warning 标题下，两边都进 stderr
    if removed:
        err_console.print()
        warning(f"此歌单有 {len(removed)} 首已下架曲目：")
        for r in removed:
            err_console.print(
                f"    [dim]{r['id']}[/]  [red]{escape(r['title'])}[/]"
                f"  [dim]{escape(r['artist'])}，{escape(r['album'])}[/]"
            )

    if not args.download:
        return

    quality = get_quality()
    output_dir = get_download_dir()
    _download_tracks(
        pl["tracks"],
        quality,
        output_dir,
        dl_type="playlist",
        dl_id=str(args.id),
        limit=args.count,
        offset=args.offset,
        run_check=None,
        use_curl=None,
    )


def _write_cookie(value: str) -> None:
    COOKIE_FILE.write_text(value, encoding="utf-8")
    # Cookie 为登录凭证，收窄为仅本人可读
    os.chmod(COOKIE_FILE, 0o600)


def announce_account() -> None:
    """联网查过 Cookie 权限才报一次，命中缓存就静默

    必须放在取链接之前，否则付费歌拿不到链接会直接退出
    """
    # 请求前先提示，避免停顿看起来像卡住
    if account_needs_check():
        info("正在检查 Cookie 权限")

    state = get_account_info()
    if account_stamp()[1]:
        return

    if state is None:
        warning("Cookie 检查失败，未能提取账号信息，本次下载不受影响")
    elif not state["logged_in"]:
        warning("未检测到登录状态，Cookie 可能不合法或登录已失效")
    elif not state["vip"]:
        warning("Cookie 所属账号没有 VIP 权限，高音质不可用")
    else:
        success("Cookie 权限：已登录，有 VIP 权限")


def cmd_init(args: argparse.Namespace) -> None:
    """初始化 VNCMD_HOME，写入默认配置与空 Cookie"""
    console.print()

    v = sys.version_info
    console.print(f"  Python {v.major}.{v.minor}.{v.micro}")

    # 路径统一走 abbrev_home，避免展开后过长
    console.print(f"  VNCMD_HOME: {abbrev_home(VNCMD_HOME)}")
    VNCMD_HOME.mkdir(parents=True, exist_ok=True)

    # 上方已给出 VNCMD_HOME，这里只报文件名
    if CONFIG_FILE.exists():
        console.print(f"  [dim]存在 {CONFIG_FILE.name}[/]")
    else:
        validate_config(quiet=True)
        success(f"已创建 {CONFIG_FILE.name}")

    if COOKIE_FILE.exists():
        console.print(f"  [dim]存在 {COOKIE_FILE.name}[/]")
    else:
        _write_cookie("")
        # 同一句里说清文件与用途
        success(
            f"已创建 {COOKIE_FILE.name}，"
            "将登录 Cookie 写入该文件即可下载 VIP 与高音质歌曲"
        )

    # 检查系统依赖
    tools = check_tools()
    found = [name for name in tools if tools[name]]
    missing = [name for name in tools if not tools[name]]
    if found:
        console.print(f"  [dim]存在 {' / '.join(found)}[/]")
    if missing:
        warning(f"未检测到 {' / '.join(missing)}")
        info("这些系统库用于 Check 功能")

    console.print()
    success("初始化完成")
    console.print(
        "  [dim]详细指南：[/]https://github.com/Vanadiry/vncmd/blob/main/doc/guide.md"
    )
    console.print()


def cmd_cookie(args: argparse.Namespace) -> None:
    """设置或检查 Cookie"""
    if not args.check and not args.value:
        # 与其它命令的缺参数提示保持同一形状
        error("缺少参数 Cookie 值 或 --check")
        sys.exit(2)

    if args.value:
        VNCMD_HOME.mkdir(parents=True, exist_ok=True)
        _write_cookie(args.value.strip())
        success("Cookie 已保存")

    info("正在检查账户权限")
    # Cookie 刚改过，强制检查，缓存可能属于另一个账号
    account = get_account_info(force=True)
    if account is None:
        # 退出码 2 表示查不成，与查出无效区分
        error("Cookie 检查失败，未能提取账号信息")
        sys.exit(2)
    if not account["logged_in"]:
        error("Cookie 不合法或登录已失效")
        sys.exit(1)
    if not account["vip"]:
        # 非会员 Cookie 仍可用，只是拿不到高音质
        warning("Cookie 有效，所属账号没有 VIP 权限，高音质不可用")
        return
    success("Cookie 有效")


def cmd_cache(args: argparse.Namespace) -> None:
    """查看或清理本地缓存，两个开关必须给一个"""
    if not args.stats and not args.clear:
        error("缺少参数 --stats 或 --clear")
        sys.exit(2)

    root = Path(get_cache_dir())
    if not root.is_dir():
        info("缓存目录不存在，无需处理")
        return

    songs = sorted((root / "song").glob("*")) if (root / "song").is_dir() else []
    files = [f for f in root.rglob("*") if f.is_file()]
    size = sum(f.stat().st_size for f in files)

    if args.stats:
        ttl = get_cache_ttl()
        console.print(f"缓存目录：{abbrev_home(root)}")
        console.print(f"占用：{size / 1024 / 1024:.1f} MB，共 {len(files)} 个文件")
        console.print(f"曲目：{len(songs)} 首")
        console.print(f"有效期：{'永不过期' if ttl == 0 else f'{ttl} 天'}")

    if args.clear:
        shutil.rmtree(root)
        success(f"已清空缓存，释放 {size / 1024 / 1024:.1f} MB")
    else:
        err_console.print()
        # 命令名必须与 parser 一致
        info("清空缓存：vncmd tool cache --clear")


def cmd_check(args: argparse.Namespace) -> None:
    """检查音频文件完整性"""
    if not any_check_tool():
        error("没有可用的校验工具")
        sys.exit(1)

    note = describe_missing_check_tools()
    if note:
        # 只在任务开始时说一次，缺哪样只跳过那一步
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
        info("未找到支持的音频文件")
        return

    console.print(f"共 [bold]{len(files)}[/] 个文件，开始检查\n")
    ok_count = bad_count = 0
    bad_files = []

    def _show(f: Path) -> str:
        """传目录时只显示相对路径，避免长路径折行
        加引号让 rich 把整段当字符串着色"""
        rel = f.relative_to(path) if path.is_dir() else f.name
        return f'"{escape(str(rel))}"'

    with ThreadPoolExecutor(max_workers=4) as pool:
        # 按提交顺序取结果，保证输出稳定，检查本身仍并发
        futures = [(f, pool.submit(check_audio, str(f))) for f in files]
        for f, future in futures:
            # 单个文件异常不中断整条命令
            exc = future.exception()
            if exc is not None:
                bad_count += 1
                bad_files.append((f, f"{type(exc).__name__}: {exc}"))
                console.print(f"  [red]损坏[/] {_show(f)}  检查失败")
                continue
            ok, msg = future.result()
            if ok:
                ok_count += 1
                console.print(f"  [cyan]通过[/]  {_show(f)}")
            else:
                bad_count += 1
                bad_files.append((f, msg))
                console.print(f"  [red]损坏[/] {_show(f)}  {msg}")

    console.print(f"\n完成：[cyan]{ok_count} 通过[/]，[red]{bad_count} 损坏[/]")
    if bad_files:
        console.print("损坏文件：")
        for f, msg in bad_files:
            console.print(f"  [red]{_show(f)}[/]  {msg}")
