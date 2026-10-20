from rich import box
from rich.cells import cell_len
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from vncmd.core.config import is_artist_color
from vncmd.core.vocals import colorize

console = Console()

# 诊断走 stderr，stdout 只留给命令结果
err_console = Console(stderr=True)


def _artist_text(artist: str, base_style: str) -> Text:
    """把艺术家串拼成 Text，命中代表色的片段换色"""
    text = Text()
    if is_artist_color():
        for chunk, color in colorize(artist):
            text.append(chunk, style=color or base_style)
    else:
        text.append(artist, style=base_style)
    return text


# 权限三态用符号，省一列宽度
_PERM_MARKS = {
    True: ("✗", "red"),
    False: ("✓", "green"),
    None: ("?", "yellow"),
}


def _build_track_table(
    tracks: list[dict],
    title: str | None = None,
    show_album: bool = True,
    blocked: list[bool | None] | None = None,
    offset: int = 0,
) -> Table:
    """按列配置拼出曲目表，渲染交给调用方

    offset 为这批之前跳过的首数，序号列报绝对序号
    """
    show_perm = (
        blocked is not None
        and len(blocked) == len(tracks)
        and any(b is not False for b in blocked)
    )

    table = Table(
        title=title,
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    # ratio 为空间不足时的退让顺序，4:3:2 避免超长字段通吃
    # 不设 max_width，终端宽度已为约束
    table.add_column("#", style="dim")
    table.add_column("ID", style="dim")
    # 三列都设 overflow=fold，避免长串被省略号截断
    table.add_column("标题", style="bright_white", ratio=4, overflow="fold")
    table.add_column("艺术家", style="bright_white", ratio=3, overflow="fold")
    if show_album:
        # 专辑列同样设 fold，避免无空格的中日文名字被截断
        table.add_column("专辑", style="bright_white", ratio=2, overflow="fold")
    if show_perm:
        table.add_column("权限", justify="center")
    table.add_column("时长", style="blue", justify="right")

    for i, t in enumerate(tracks, offset + 1):
        row = [
            str(i),
            str(t["id"]),
            escape(t["title"]),
            _artist_text(t["artist"], "bright_white"),
        ]
        # 专辑视图下每行专辑名相同，再列一遍没有信息量
        if show_album:
            row.append(escape(t["album"]))
        if show_perm:
            mark, style = _PERM_MARKS[blocked[i - 1]]
            row.append(Text(mark, style=style))
        row.append(t["duration"])
        table.add_row(*row)
    return table


def _display_track_table(
    tracks: list[dict],
    title: str | None = None,
    show_album: bool = True,
    blocked: list[bool | None] | None = None,
    offset: int = 0,
) -> None:
    """显示曲目表

    blocked 与 tracks 等长，True 为不能下载，False 为能，None 为未知
    """
    console.print(
        _build_track_table(
            tracks, title, show_album=show_album, blocked=blocked, offset=offset
        )
    )


def _range_suffix(offset: int, shown: int, total: int) -> str:
    """标题右侧的分页区间，total 为可切片数量"""
    if shown <= 0:
        # offset 越过末尾，与末尾不足 limit 首不同
        return f"超出范围，共 {total} 首"
    return f"{offset + 1}-{offset + shown}/{total}"


def display_search_results(
    query: str,
    songs: list[dict],
    total: int,
    blocked: list[bool | None] | None = None,
    offset: int = 0,
) -> None:
    """以表格显示搜索结果"""
    suffix = _range_suffix(offset, len(songs), total)
    _display_track_table(
        songs,
        title=f"搜索：“{escape(query)}”，{suffix}",
        blocked=blocked,
        offset=offset,
    )


def _trim_midnight(publish_time: str) -> str:
    """时间部分为 00:00:00 时只留日期"""
    return publish_time[:10] if publish_time.endswith("00:00:00") else publish_time


# fee 本身就能说明取不到 URL 的原因，不必再查账号信息
FEE_NEED = {
    1: "需要会员权限或单独购买该曲目",
    4: "需要购买该专辑",
}


def _fmt_size(n: int) -> str:
    """文件大小，附原始字节数"""
    if not n:
        return ""
    mb = n / 1024 / 1024
    return f"{mb:.1f} MB，{n} 字节" if mb >= 0.1 else f"{n} 字节"


def _fmt_kbps(bps: int) -> str:
    if not bps:
        return ""
    return f"{bps // 1000} kbps，{bps} bps"


def _fmt_validity(expi: int) -> str:
    """有效期超过一分钟时换算成分钟"""
    if not expi:
        return ""
    if expi < 60:
        return f"{expi} 秒内有效"
    minutes = expi / 60
    text = f"{int(minutes)}" if minutes == int(minutes) else f"{minutes:.1f}"
    return f"{text} 分钟内有效"


def _download_lines(
    song_id: int, name: str, info: dict
) -> tuple[list[tuple[str, str]], str]:
    """把响应组装成面板键值行与标题"""
    from vncmd.net.api import LEVEL_LABEL

    url = info.get("url") or ""
    fee = info.get("fee")

    # 标题放在面板里当第一行
    lines = [("标题", name)]
    if url:
        lines += [
            ("类型", info.get("type") or ""),
            ("音质", LEVEL_LABEL.get(info.get("level", ""), info.get("level", ""))),
            ("比特率", _fmt_kbps(info.get("br") or 0)),
            ("采样率", f"{info['sr']} Hz" if info.get("sr") else ""),
        ]
    if info.get("time"):
        total = info["time"] // 1000
        lines.append(("时长", f"{total // 60}:{total % 60:02d}"))
    lines += [
        ("大小", _fmt_size(info.get("size") or 0)),
        ("MD5", info.get("md5") or ""),
    ]

    # 能下只说能下，不能下才讲原因
    if url:
        lines.append(("权限", "允许访问"))
    else:
        reason = FEE_NEED.get(fee, "当前账号没有相应权限")
        lines.append(("权限", f"不允许访问，{reason}"))

    # 空字段不印
    lines = [(k, v) for k, v in lines if v]

    title = f"下载信息 - {song_id}"
    validity = _fmt_validity(info.get("expi") or 0)
    if validity:
        title += f" - {validity}"
    return lines, title


def display_download_detail(song_id: int, name: str, info: dict) -> None:
    """显示单曲下载详情

    链接整条印在面板外，便于选中复制
    """
    url = info.get("url") or ""
    if url:
        console.print(url, style="bright_white", soft_wrap=True, crop=False)

    lines, title = _download_lines(song_id, name, info)
    pad_to = max(cell_len(k) for k, _ in lines)

    text = Text()
    for i, (key, value) in enumerate(lines):
        pad = " " * (pad_to - cell_len(key))
        text.append(f"{key}{pad}  ", style="bold cyan")
        text.append(value, style="bright_white")
        if i < len(lines) - 1:
            text.append("\n")

    console.print(
        Panel(text, title=f"[bold]{title}[/]", border_style="cyan", box=box.ROUNDED)
    )


def display_song_detail(song: dict) -> None:
    """显示单曲完整元数据"""
    # 无专辑时 id 为 0，不印；旧缓存可能存过 None
    album = song.get("album") or ""
    album_id = song.get("album_id") or 0
    lines = [
        ("标题", song["title"] or ""),
        ("艺术家", _artist_text(song["artist"] or "", "bright_white")),
        ("专辑", f"{album}，id {album_id}" if album_id > 0 else album),
        ("封面", song["cover"] or ""),
        ("发行时间", _trim_midnight(song["publish_time"] or "")),
        ("时长", song["duration"] or ""),
    ]

    # 键多为中文，len 按字符数算会短一格，补齐要用 cell_len
    max_key_len = max(cell_len(k) for k, _ in lines)
    text = Text()
    for i, (key, value) in enumerate(lines):
        pad = " " * (max_key_len - cell_len(key))
        text.append(f"{key}{pad}  ", style="bold cyan")
        if isinstance(value, Text):
            text.append(value)
        else:
            text.append(value, style="bright_white")
        # 末行不留换行，否则面板底部会多一行空行
        if i < len(lines) - 1:
            text.append("\n")

    # ID 已在表头，面板里不再重复
    panel = Panel(
        text,
        title=f"[bold]曲目详情 - {song['id']}[/]",
        border_style="cyan",
        box=box.ROUNDED,
    )
    console.print(panel)


def display_playlist(playlist: dict, max_tracks: int = 100, offset: int = 0) -> None:
    """显示歌单信息与曲目表"""
    tracks = playlist["tracks"]
    # 分母为可切片数量，不含已下架曲目
    total = len(tracks)
    shown = tracks[offset : offset + max_tracks]

    header = Text()
    header.append("歌单：", style="bold")
    header.append(f"{playlist['name']}\n", style="bold bright_white")
    header.append("创建者：", style="dim")
    header.append(f"{playlist['creator']}", style="yellow")
    console.print(
        Panel(
            header,
            title=f"[bold]歌单详情 - {playlist['id']} - "
            f"{_range_suffix(offset, len(shown), total)}[/]",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )

    _display_track_table(shown, offset=offset)


def display_album(album: dict, max_tracks: int = 100, offset: int = 0) -> None:
    tracks = album["tracks"]
    total = len(tracks)
    shown = tracks[offset : offset + max_tracks]

    header = Text()
    header.append("专辑：", style="bold")
    header.append(f"{album['name']}\n", style="bold bright_white")
    header.append("艺术家：", style="dim")
    header.append(f"{album['artist']}", style="yellow")
    console.print(
        Panel(
            header,
            title=f"[bold]专辑详情 - {album['id']} - "
            f"{_range_suffix(offset, len(shown), total)}[/]",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )
    _display_track_table(shown, show_album=False, offset=offset)


def display_lyrics(lyrics_text: str) -> None:
    """显示歌词面板"""
    if not lyrics_text:
        console.print("[dim]无歌词[/]")
        return
    panel = Panel(
        Text(lyrics_text.strip()),
        title="[bold]歌词[/]",
        border_style="cyan",
        box=box.ROUNDED,
    )
    console.print(panel)


# 绿色留给文件名字符串，图标改青才能区分开
ICON_OK = "[cyan]✓[/]"
ICON_FAIL = "[red]✗[/]"
ICON_INFO = "[blue]ℹ[/]"
ICON_WARN = "[yellow]⚠[/]"


def _print_status(icon, msg):
    for line in msg.splitlines():
        err_console.print(f"{icon} {escape(line)}")


def success(msg: str) -> None:
    _print_status(ICON_OK, msg)


def error(msg: str) -> None:
    _print_status(ICON_FAIL, msg)


def info(msg: str) -> None:
    _print_status(ICON_INFO, msg)


def warning(msg: str) -> None:
    _print_status(ICON_WARN, msg)
