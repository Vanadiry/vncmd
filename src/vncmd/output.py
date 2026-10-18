from rich import box
from rich.cells import cell_len
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from vncmd.config import is_artist_color
from vncmd.vocals import colorize

console = Console()

# 诊断走 stderr，stdout 只留给命令的结果。
# 重定向到文件时诊断混在里面等于噪声，而进度条与「正在检查…」这类提示
# 对管道里的消费者本来就没有意义。顺带 `vncmd search xxx > r.txt` 之后
# 不用再 `grep '│'` 去剔边框
err_console = Console(stderr=True)


def _artist_text(artist: str, base_style: str) -> Text:
    """把艺术家串拼成 Text，命中代表色的片段换成自己的颜色

    表里不只 Vocaloid，PIAPRO 系（星乃一歌、宵崎奏、日野森雫等）也在内，
    所以配置项叫 artist_color 而不叫 virtual_singer_color。
    """
    text = Text()
    if is_artist_color():
        for chunk, color in colorize(artist):
            text.append(chunk, style=color or base_style)
    else:
        text.append(artist, style=base_style)
    return text


# 权限三态：下不了、能下、看不出来
# 用符号而不是文字，一格宽度摆得下，标题能多拿三格
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

    拆出来是为了让测试量到真的那份配置。早先测试里抄了一份列定义，
    于是真表格改了样式或换行方式，测试照样全绿。

    offset 是这批之前被跳过的首数，序号列报绝对序号：
    分了页之后相对序号每页都从 1 开始，用户分不清看到的是第 1 首还是第 101 首。
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
    # ratio 不是宽度上限，是空间不够时三列的退让顺序。
    # 4:3:2 意味着专辑最少，但缺了它，遇到超长字段时 rich 按宽度比例收缩，
    # 最长的那列会通吃，标题能被压到三个汉字宽
    # 这里刻意不设 max_width：终端本来就是终极约束，再设一遍是二次约束。
    # 实测 4 组数据 × 45 个宽度，去掉 max_width 输出完全相同，它一直是死配置。
    # 序号、ID、时长不设 ratio，宽度就按内容自然算，不会被摊宽
    table.add_column("#", style="dim")
    table.add_column("ID", style="dim")
    # 三列都要显式给 overflow="fold"：rich 的列表头默认 ellipsis，
    # 遇到比整列还长的词就切一刀加省略号。
    # 「鏡音リン&天馬司&鳳えむ&草薙寧々&神代類」这种 40 格的长串在 40 格的列里
    # 会被切成「鏡音リン&天馬司&鳳えむ&草薙寧々&神代 …」，接口明明返回了完整的
    table.add_column("标题", style="bright_white", ratio=4, overflow="fold")
    table.add_column("艺术家", style="bright_white", ratio=3, overflow="fold")
    if show_album:
        # 标题、艺术家、专辑三列都自由换行，谁长谁折，各折各的。
        # overflow 必须显式给 fold：rich 的列表头默认是 ellipsis，
        # 日文与中文这种没有空格的名字会被一刀切成「エイプ …」
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
        # 专辑视图下每行的专辑名都是同一个，列表里再列一遍没有信息量
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

    blocked 是与 tracks 等长的逐行判定：True 为下不了，False 为能下，
    None 为看不出来。整列都是 False 时不显示，搜索表已经挤到标题和艺术家
    都在截断，能不占地方就不占。

    长度不等长时整列不显示：短了会 IndexError，长了会整列错位，
    而错位的权限标记比没有这一列更糟。

    这里刻意不再报「还有 N 首未显示」：标题里的区间已经说了同一件事，
    两行都报就成了同一屏两个口径 —— 一行按可切片的首数算，一行按接口声明的
    总数算，在有下架曲目的歌单上这两个数不一样，用户会以为哪个是错的。
    """
    console.print(
        _build_track_table(
            tracks, title, show_album=show_album, blocked=blocked, offset=offset
        )
    )


def _range_suffix(offset: int, shown: int, total: int) -> str:
    """标题右侧的分页区间，像翻页条

    分母是传入的 total，由调用方给可切片的首数，不给接口声明的总数：
    那个数里含已下架的，拿它当分母等于承诺一批翻不出来的曲目。
    """
    if shown <= 0:
        # offset 越过了末尾。这与「末尾不足 limit 首」不同，后者是正常显示
        return f"超出范围（共 {total} 首）"
    return f"{offset + 1}-{offset + shown}/{total}"


def display_search_results(
    query: str,
    songs: list[dict],
    total: int,
    blocked: list[bool | None] | None = None,
    offset: int = 0,
) -> None:
    """Display search results as a table."""
    suffix = _range_suffix(offset, len(songs), total)
    _display_track_table(
        songs,
        title=f"搜索：「{escape(query)}」  —  {suffix}",
        blocked=blocked,
        offset=offset,
    )


def _trim_midnight(publish_time: str) -> str:
    """时间部分是零点时只留日期

    抽样六成里九成半的发行时间都是零点，那段后缀是纯噪声。
    只在这里处理，原始字符串不动，它还要被写进音频标签。
    """
    return publish_time[:10] if publish_time.endswith("00:00:00") else publish_time


# fee 本身就能说明取不到 URL 的原因，不必再查账号信息
FEE_NEED = {
    1: "需要会员权限或单独购买该曲目",
    4: "需要购买该专辑",
}


def _fmt_size(n: int) -> str:
    """先给人看的单位，原始值跟在后面备查"""
    if not n:
        return ""
    mb = n / 1024 / 1024
    return f"{mb:.1f} MB ({n} 字节)" if mb >= 0.1 else f"{n} 字节"


def _fmt_kbps(bps: int) -> str:
    if not bps:
        return ""
    return f"{bps // 1000} kbps ({bps} bps)"


def _fmt_validity(expi: int) -> str:
    """有效期超过一分钟的换算成分钟，秒数看着不如分钟直观"""
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
    """把响应组装成面板的键值行与标题

    取不到 URL 时照样组装，那是最需要看的时候：费用类型与是否购买
    都在响应里，不必再发一次请求去问为什么。
    """
    from vncmd.api import LEVEL_LABEL

    url = info.get("url") or ""
    fee = info.get("fee")

    # 标题放在面板里当第一行，面板外不留别的内容，选哪一块都清楚
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

    # 能下就只说能下，说不了才讲为什么，下得了的人不关心有没有买过
    if url:
        lines.append(("权限", "允许访问"))
    else:
        reason = FEE_NEED.get(fee, "当前账号没有相应权限")
        lines.append(("权限", f"不允许访问（{reason}）"))

    # 取不到链接时多数字段是空的，留着只是空行
    lines = [(k, v) for k, v in lines if v]

    title = f"下载信息 - {song_id}"
    validity = _fmt_validity(info.get("expi") or 0)
    if validity:
        title += f" - {validity}"
    return lines, title


def display_download_detail(song_id: int, name: str, info: dict) -> None:
    """Display everything the download endpoint knows about one song.

    链接整条印在面板外面，不截断也不加边框：面板里那行折了字之后既选不中
    也点不开，而整条裸着印出来，双击就能选中，粘贴到浏览器直接能下。
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
    """Display a single song's full metadata."""
    # 专辑名后面带出专辑 ID，方便直接拿去查专辑详情。
    # 没有专辑条目的曲目接口给的是 id 为 0，那不是真的专辑，别印出去。
    # 旧缓存里存过 None，or 兜住，免得 Text.append 收到 None 直接抛
    album = song.get("album") or ""
    album_id = song.get("album_id") or 0
    lines = [
        ("标题", song["title"] or ""),
        ("艺术家", _artist_text(song["artist"] or "", "bright_white")),
        ("专辑", f"{album}（{album_id}）" if album_id > 0 else album),
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

    # ID 挪到表头，面板里再列一遍是重复
    panel = Panel(
        text,
        title=f"[bold]曲目详情 - {song['id']}[/]",
        border_style="cyan",
        box=box.ROUNDED,
    )
    console.print(panel)


def display_playlist(playlist: dict, max_tracks: int = 100, offset: int = 0) -> None:
    """Display playlist info and its tracks as a table."""
    tracks = playlist["tracks"]
    # 分母是可切片的数量，不是 track_count。后者是接口声明的总数，
    # 含已下架的曲目，而那些拿不到条目、永远翻不出来
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
    """Display lyrics in a panel."""
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
