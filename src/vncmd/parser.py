import argparse

from vncmd.net.api import SEARCH_LIMIT_MAX


class _HelpFormatter(argparse.HelpFormatter):
    def _format_usage(self, usage, actions, groups, prefix):
        if prefix is None:
            prefix = "用法："
        return super()._format_usage(usage, actions, groups, prefix)


class _ArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("formatter_class", _HelpFormatter)
        kwargs.setdefault("add_help", False)
        super().__init__(*args, **kwargs)
        self._positionals.title = "位置参数"
        self._optionals.title = "可选参数"
        self.add_argument(
            "-h",
            "--help",
            action="help",
            default=argparse.SUPPRESS,
            help="显示此帮助信息并退出",
        )

    def error(self, message: str) -> None:
        """用法错误的统一出口，转成中文并提示帮助"""
        from vncmd.core.output import error as show_error

        show_error(self._friendly(message))
        raise SystemExit(2)

    def _friendly(self, message: str) -> str:
        hint = f"帮助：{self.prog} -h"
        if message.startswith("the following arguments are required: "):
            missing = message.split(": ", 1)[1]
            return f"缺少参数 {missing}，{hint}"
        if message.startswith("unrecognized arguments: "):
            extra = message.split(": ", 1)[1]
            return f"不认识的参数 {extra}，{hint}"
        if "invalid choice: " in message:
            tail = message.split("invalid choice: ", 1)[1]
            value = tail.split("'")[1]
            return f"没有 {value} 这个命令，{hint}"
        if message.startswith("argument ") and ": " in message:
            head, body = message.split(": ", 1)
            head = head[len("argument ") :]
            if body.startswith("invalid int value: "):
                body = "要一个整数，实际是 " + body.split(": ", 1)[1]
            elif body.startswith("not allowed with argument "):
                body = "不能与 " + body[len("not allowed with argument ") :] + " 同时给"
            elif body == "expected one argument":
                body = "需要一个值"
            return f"{head}：{body}，{hint}"
        return f"{message}，{hint}"


def _search_limit(raw: str) -> int:
    """把 --count 限制在服务端接受的范围"""
    try:
        value = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"搜索条数不合法，应当为整数，实际是 {raw!r}"
        ) from None
    if not 1 <= value <= SEARCH_LIMIT_MAX:
        raise argparse.ArgumentTypeError(
            f"搜索条数不合法，应当为 1 至 {SEARCH_LIMIT_MAX}，实际是 {value}"
        )
    return value


def _add_json_arg(parser: object) -> None:
    """给命令加上 --json"""
    parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="以 JSON 输出结果并退出，供脚本读取",
    )


def _add_list_args(parser: object) -> None:
    """给有曲目表的命令加 --count 与 --offset"""
    parser.add_argument(
        "--count",
        "-c",
        type=int,
        default=None,
        metavar="N",
        help="最多处理曲目数，默认面板 10，JSON 与下载全部",
    )
    parser.add_argument(
        "--offset",
        "-o",
        type=int,
        default=0,
        metavar="N",
        help="起始序号，从 0 计",
    )


def _add_dlink_arg(parser: object, help_text: str) -> None:
    """加 --dlink，help 按命令区分"""
    parser.add_argument("--dlink", "-u", action="store_true", help=help_text)


def _add_download_args(parser: object, download_group: object = None) -> None:
    """加 --download，download_group 非空时放进互斥组"""
    add = download_group.add_argument if download_group else parser.add_argument
    add("--download", "-d", action="store_true", help="下载而非仅预览")


def build_parser(version: str) -> _ArgumentParser:
    parser = _ArgumentParser(
        prog="vncmd",
        description="网易云音乐 CLI，搜索、预览与下载",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=version,
        help="显示版本号并退出",
    )
    sub = parser.add_subparsers(
        dest="command", help="可用命令", parser_class=_ArgumentParser
    )

    parser.add_argument(
        "--init", "-i", action="store_true", help="初始化 vncmd 并写入默认配置"
    )
    parser.add_argument(
        "--config",
        "-C",
        action="append",
        default=[],
        metavar="key=value",
        help="临时覆盖配置项，可重复，后者生效，须放在子命令之前",
    )

    p_cookie = sub.add_parser("cookie", help="设置 Cookie")
    grp_cookie = p_cookie.add_mutually_exclusive_group()
    grp_cookie.add_argument("value", nargs="?", help="Cookie 值，省略时需配 --check")
    grp_cookie.add_argument(
        "--check", action="store_true", help="不写文件，只检查当前 Cookie 状态"
    )

    p_tool = sub.add_parser("tool", help="实用工具")
    tool_sub = p_tool.add_subparsers(
        dest="tool", help="可用工具", required=True, parser_class=_ArgumentParser
    )
    p_tool_check = tool_sub.add_parser("check", help="检查音频文件完整性")
    p_tool_check.add_argument("path", help="文件或目录路径")
    p_tool_cache = tool_sub.add_parser("cache", help="查看或清理本地缓存")
    p_tool_cache.add_argument("--stats", action="store_true", help="显示占用与条目数")
    p_tool_cache.add_argument("--clear", action="store_true", help="清空缓存目录")

    p_search = sub.add_parser("search", help="搜索曲目")
    p_search.add_argument("query", help="搜索关键词")
    p_search.add_argument(
        "--count",
        "-c",
        type=_search_limit,
        default=None,
        metavar="N",
        help=f"最大结果数，1 至 {SEARCH_LIMIT_MAX}，默认 10",
    )
    p_search.add_argument("--offset", "-o", type=int, default=0, help="分页偏移量")
    _add_json_arg(p_search)

    p_song = sub.add_parser("song", help="预览或下载单曲")
    p_song.add_argument("id", type=int, help="曲目 ID")
    grp_song = p_song.add_mutually_exclusive_group()
    _add_dlink_arg(grp_song, "显示下载链接与音质、费用等详情")
    _add_json_arg(p_song)
    _add_download_args(p_song, download_group=grp_song)
    p_song.add_argument("--lyric", "-l", action="store_true", help="显示歌词")
    p_song.add_argument(
        "--translate",
        "-t",
        action="store_true",
        help="配 --lyric 时一并显示翻译歌词",
    )

    p_al = sub.add_parser("album", help="预览或下载专辑")
    p_al.add_argument("id", type=int, help="专辑 ID")
    _add_list_args(p_al)
    _add_json_arg(p_al)
    _add_dlink_arg(p_al, "取下载链接，需配合 --json")
    _add_download_args(p_al)

    p_pl = sub.add_parser("playlist", help="预览或下载歌单")
    p_pl.add_argument("id", type=int, help="歌单 ID")
    _add_list_args(p_pl)
    _add_json_arg(p_pl)
    _add_dlink_arg(p_pl, "取下载链接，需配合 --json")
    _add_download_args(p_pl)

    p_tracker = sub.add_parser("tracker", help="追踪音乐来源变更并批量下载")
    p_tracker.add_argument("name", help="Tracker 名称")
    grp_tracker = p_tracker.add_mutually_exclusive_group()
    grp_tracker.add_argument(
        "--fetch",
        "-f",
        action="store_true",
        help="拉取并对比，交互式解决冲突",
    )
    grp_tracker.add_argument(
        "--download", "-d", action="store_true", help="下载所有已缓存曲目"
    )
    grp_fetch = p_tracker.add_mutually_exclusive_group()
    grp_fetch.add_argument(
        "--auto-accept",
        "-A",
        action="store_true",
        help="配 --fetch 时自动接受全部变更，无需交互",
    )
    grp_fetch.add_argument(
        "--force",
        "-F",
        action="store_true",
        help="配 --fetch 时覆盖 songs.json，diff.json 变化才更新，连续两次会顶掉备份",
    )
    p_tracker.add_argument(
        "--diff",
        "-x",
        action="store_true",
        help="上次 --fetch 的记录，不联网，可配 -d 或 --json",
    )
    _add_json_arg(p_tracker)
    p_tracker.add_argument(
        "--count",
        "-c",
        type=int,
        default=None,
        metavar="N",
        help="最多处理曲目数，默认面板 10，JSON 全部",
    )
    p_tracker.add_argument(
        "--offset",
        "-o",
        type=int,
        default=0,
        metavar="N",
        help="起始序号，从 0 计",
    )

    return parser
