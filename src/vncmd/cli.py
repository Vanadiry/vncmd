import argparse
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from vncmd.commands import (
    announce_account,
    cmd_album,
    cmd_cache,
    cmd_check,
    cmd_cookie,
    cmd_init,
    cmd_playlist,
    cmd_search,
    cmd_song,
)
from vncmd.core.config import acquire_lock, validate_config
from vncmd.core.output import err_console
from vncmd.core.output import error as show_error
from vncmd.core.schema import coerce, split_override
from vncmd.net.api import SEARCH_LIMIT_MAX
from vncmd.tracker import cmd_tracker


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
        show_error(self._friendly(message))
        sys.exit(2)

    def _friendly(self, message: str) -> str:
        hint = f"可以用 {self.prog} -h 查看帮助"
        if message.startswith("the following arguments are required: "):
            missing = message.split(": ", 1)[1]
            return f"缺少参数 {missing}。{hint}"
        if message.startswith("unrecognized arguments: "):
            extra = message.split(": ", 1)[1]
            return f"不认识的参数 {extra}。{hint}"
        if "invalid choice: " in message:
            tail = message.split("invalid choice: ", 1)[1]
            # 不列候选命令，只说明错在哪
            value = tail.split("'")[1]
            return f"没有 {value} 这个命令。{hint}"
        if message.startswith("argument ") and ": " in message:
            head, body = message.split(": ", 1)
            head = head[len("argument ") :]
            if body.startswith("invalid int value: "):
                body = "要一个整数，给的是 " + body.split(": ", 1)[1]
            elif body.startswith("not allowed with argument "):
                body = "不能与 " + body[len("not allowed with argument ") :] + " 同时给"
            elif body == "expected one argument":
                body = "需要一个值"
            return f"{head}：{body}。{hint}"
        return f"{message}。{hint}"


def _version_string() -> str:
    """从已安装包元数据读版本，源码直跑时返回 unknown"""
    try:
        return f"vncmd {_pkg_version('vncmd')}"
    except PackageNotFoundError:
        return "vncmd unknown"


def _add_json_arg(parser: object) -> None:
    """给命令加上 --json"""
    parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="以 JSON 输出结果并退出，供脚本读取",
    )


def _add_list_args(parser: object) -> None:
    """给有曲目表的命令加 --count 与 --offset

    count 默认 None，区分用户显式给值与未给
    """
    parser.add_argument(
        "--count",
        "-c",
        type=int,
        default=None,
        metavar="N",
        help="最多处理曲目数（默认：面板 10，JSON 与下载全部）",
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
    # 音质、校验与下载方式都是配置项，用 --config 临时改


def build_parser() -> _ArgumentParser:
    parser = _ArgumentParser(
        prog="vncmd",
        description="网易云音乐 CLI — 搜索、预览与下载",
    )
    # 打印后立即退出，早于锁与配置检查
    # 走 argparse 原生输出，避免颜色与方括号标记
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=_version_string(),
        help="显示版本号并退出",
    )
    sub = parser.add_subparsers(
        dest="command", help="可用命令", parser_class=_ArgumentParser
    )

    # init 为一次性本机初始化，给成顶层开关
    parser.add_argument(
        "--init", "-i", action="store_true", help="初始化 vncmd 并写入默认配置"
    )
    # 临时覆盖配置项，可重复，后者生效
    # 只挂全局，避免每个子命令的 help 重复
    parser.add_argument(
        "--config",
        "-C",
        action="append",
        default=[],
        metavar="key=value",
        help="临时覆盖某一项配置，如 --config download.audio.quality=128（可重复，"
        "后者生效）。能覆盖的键见 doc/config.md。必须写在子命令之前",
    )

    p_cookie = sub.add_parser("cookie", help="设置 Cookie")
    grp_cookie = p_cookie.add_mutually_exclusive_group()
    # 写成 --check 又给值自相矛盾：--check 即不写文件
    grp_cookie.add_argument("value", nargs="?", help="Cookie 值，省略时需配 --check")
    grp_cookie.add_argument(
        "--check", action="store_true", help="不写文件，只检查当前 Cookie 状态"
    )

    # tool 子命令必须给出，否则按用法错误处理
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
    # 服务端 limit 超过 100 返回 400，用自定义 type 报中文错误
    p_search.add_argument(
        "--count",
        "-c",
        type=_search_limit,
        default=None,
        metavar="N",
        help=f"最大结果数，1-{SEARCH_LIMIT_MAX}（默认：10）",
    )
    p_search.add_argument("--offset", "-o", type=int, default=0, help="分页偏移量")
    # search 没有下载动作，不存在互斥问题
    _add_json_arg(p_search)

    p_song = sub.add_parser("song", help="预览或下载单曲")
    p_song.add_argument("id", type=int, help="曲目 ID")
    # 查看数据与下载互斥，同给时由 argparse 报错
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
    _add_dlink_arg(p_al, "取下载链接（需配合 --json）")
    _add_download_args(p_al)

    p_pl = sub.add_parser("playlist", help="预览或下载歌单")
    p_pl.add_argument("id", type=int, help="歌单 ID")
    _add_list_args(p_pl)
    _add_json_arg(p_pl)
    _add_dlink_arg(p_pl, "取下载链接（需配合 --json）")
    _add_download_args(p_pl)

    p_tracker = sub.add_parser("tracker", help="追踪音乐来源变更并批量下载")
    p_tracker.add_argument("name", help="Tracker 名称")
    # 顶层动作互斥，避免 -f -d 同给时只生效一个
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
    # 两个都为 --fetch 的修饰，单独给由 cmd_tracker 报错
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
        help=(
            "配 --fetch 时无条件覆盖 songs.json。"
            "diff.json 有变化才更新，连续两次会顶掉前一个备份"
        ),
    )
    # --diff 为 -d 或 --json 的修饰，单独给由 cmd_tracker 报错
    p_tracker.add_argument(
        "--diff",
        "-x",
        action="store_true",
        help="上次 --fetch 记下的变更，不联网。配 -d 下载新增的，配 --json 输出三类",
    )
    # --json 只配纯读视图
    _add_json_arg(p_tracker)
    p_tracker.add_argument(
        "--count",
        "-c",
        type=int,
        default=None,
        metavar="N",
        help="最多处理曲目数（默认：面板 10，JSON 全部）",
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


# 这些命令不查账号：cookie 自查，tool 不联网
_NO_ACCOUNT_REPORT = {"cookie", "tool"}


def _search_limit(raw: str) -> int:
    """把 --count 限制在服务端接受的范围，报错用中文而非 invalid choice"""
    try:
        value = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"取回条数须为整数，给的是 {raw!r}") from None
    if not 1 <= value <= SEARCH_LIMIT_MAX:
        # 只有超上限时才提示 offset
        hint = "。更多结果用 --offset 分页取得" if value > SEARCH_LIMIT_MAX else ""
        raise argparse.ArgumentTypeError(
            f"取回条数须在 1 至 {SEARCH_LIMIT_MAX} 之间，给的是 {value}{hint}"
        )
    return value


def _reject_json_download(args: argparse.Namespace) -> None:
    """--json 与 --download 互斥

    argparse 无法表达非传递排除，退出码与用法错误一致
    """
    if getattr(args, "json", False) and getattr(args, "download", False):
        show_error("--json 与 --download 互斥：--json 输出结构化数据，--download 落盘")
        sys.exit(2)


def _config_overrides(raw: list[str]) -> dict:
    """把 --config 的 key=value 解析成已转类型的字典

    重复键后者生效
    """
    overrides = {}
    for item in raw:
        try:
            key, raw_value = split_override(item)
            overrides[key] = coerce(key, raw_value)
        except ValueError as e:
            show_error(f"--config {e}")
            sys.exit(2)
    return overrides


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # init 在命令分派前收掉
    if args.init:
        # init 只写默认模板，不接受覆盖
        if args.config:
            show_error("--init 不接受 --config：它只写默认配置，覆盖没有意义")
            sys.exit(2)
        acquire_lock()
        cmd_init(args)
        return

    # 先校验 --config，避免拼错键只打帮助就退 0
    overrides = _config_overrides(args.config)

    # 只看帮助时不碰配置与锁，--help 在 parse_args 内部就已退出
    if args.command is None:
        parser.print_help()
        sys.exit(0)

    _reject_json_download(args)

    acquire_lock()

    validate_config(overrides=overrides)

    # 账号播报放在取链接之前，付费歌拿不到链接会直接退出
    if args.command not in _NO_ACCOUNT_REPORT:
        announce_account()

    dispatch = {
        "cookie": cmd_cookie,
        "search": cmd_search,
        "song": cmd_song,
        "album": cmd_album,
        "playlist": cmd_playlist,
        "tracker": cmd_tracker,
        # tool 为第二层分派，按 args.tool 选处理函数
        "tool": {
            "check": cmd_check,
            "cache": cmd_cache,
        }.get(getattr(args, "tool", None)),
    }

    handler = dispatch.get(args.command)
    if not handler:
        parser.print_help()
        return

    try:
        handler(args)
    except KeyboardInterrupt:
        # 下载循环自己处理并给出明细，这里兜住其余阶段的中断
        err_console.print()
        err_console.print("[yellow]已中断[/]")
        sys.exit(130)
