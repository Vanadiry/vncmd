import argparse
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from function.api import SEARCH_LIMIT_MAX
from function.commands import (
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
from function.config import QUALITY_MAP, acquire_lock, validate_config
from function.output import err_console, error
from function.tracker import cmd_tracker


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


def _version_string() -> str:
    """版本从已安装的包元数据读，不从 pyproject.toml 读

    前者是「我现在实际在跑哪个版本」，后者是「源码树声称是哪个」。
    开发时用可编辑安装，两者可能漂移，那时打印后者等于报了个不实的版本。

    装成非包的形式直接跑源码时会抛 PackageNotFoundError，
    打印一个 unknown 比抛栈好。
    """
    try:
        return f"vncmd {_pkg_version('vncmd')}"
    except PackageNotFoundError:
        return "vncmd unknown"


def _add_quality_arg(parser: object) -> None:
    parser.add_argument(
        "--quality",
        "-q",
        choices=list(QUALITY_MAP),
        default=None,
        help="音质（默认：使用配置）",
    )


def _add_output_arg(parser: object) -> None:
    parser.add_argument(
        "--output", "-o", default=None, help="输出目录（默认：使用配置）"
    )


def _add_json_arg(parser: object) -> None:
    """给命令加上 --json

    刻意不进任何互斥组：需要的是「--download 与 --dlink 互斥、与 --json 也互斥，
    而 --dlink 与 --json 不互斥」。argparse 的互斥组是等价关系，
    --download 只能属于一个组，表达不出这种非传递的排除。
    那一条交给 main 里的 _reject_json_download 手写。
    """
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 输出结果并退出，供脚本读取",
    )


def _add_list_args(parser: object) -> None:
    """给有曲目表的命令加 --limit 与 --offset

    --limit 同时管面板条数、JSON 条数与下载条数，所以不放进
    _add_download_args —— 它早就不是只管下载的开关了。
    default 为 None 是为了让「用户显式给了」与「没给」分得开：
    没给时面板取前 10 条，--json 与下载取全量。song 只有一首，不加。
    """
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=None,
        metavar="N",
        help="最多处理曲目数（默认：面板 10，JSON 与下载全部）",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        metavar="N",
        help="起始序号，从 0 计",
    )


def _add_dlink_arg(parser: object, help_text: str) -> None:
    """加 --dlink

    help 分命令给：单曲打面板，一批曲目给 JSON。
    同一个字母在两种形态下不写清楚，从 song 过来的用户会在 album 上撞报错。
    """
    parser.add_argument("--dlink", "-u", action="store_true", help=help_text)


def _add_download_args(parser: object, download_group: object = None) -> None:
    """Add download-related args to a parser.

    download_group 非空时把 --download 放进那个互斥组。
    单曲的 --dlink 是查看数据，与 --download 是两种动作，两者互斥。
    """
    add = download_group.add_argument if download_group else parser.add_argument
    add("--download", "-d", action="store_true", help="下载而非仅预览")
    parser.add_argument(
        "--check",
        action="store_true",
        default=None,
        help="下载时做 ffmpeg 全量解码校验（默认：使用配置）",
    )
    parser.add_argument(
        "--curl",
        action="store_true",
        default=None,
        help="用系统 curl 下载（默认：使用配置）",
    )
    _add_quality_arg(parser)
    _add_output_arg(parser)


def build_parser() -> _ArgumentParser:
    parser = _ArgumentParser(
        prog="vncmd",
        description="网易云音乐 CLI — 搜索、预览与下载",
    )
    # 打印完立刻退出，早于 acquire_lock、validate_config 与账号播报，
    # 所以全新安装、没有配置、没有 Cookie、断网都能正常打印。
    # 走 argparse 原生的 version 动作，它直接写 sys.stdout，
    # 不经过 rich，于是没有 ANSI 也没有把方括号当标记的风险，
    # CI 拿 `vncmd --version` 的输出比对时不用先剥颜色。
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=_version_string(),
        help="显示版本号并退出",
    )
    sub = parser.add_subparsers(
        dest="command", help="可用命令", parser_class=_ArgumentParser
    )

    # init 不是对某个对象的操作，是一次性的本机初始化，
    # 与 --version 同类：跑完就没有后续动作了，所以给成顶层开关
    parser.add_argument(
        "--init", action="store_true", help="初始化 vncmd 并写入默认配置"
    )

    p_cookie = sub.add_parser("cookie", help="设置 Cookie")
    grp_cookie = p_cookie.add_mutually_exclusive_group()
    # 写成 --check 又给值是自相矛盾：--check 的意思就是不写文件
    grp_cookie.add_argument("value", nargs="?", help="Cookie 值，省略时需配 --check")
    grp_cookie.add_argument(
        "--check", action="store_true", help="不写文件，只检查当前 Cookie 状态"
    )

    # tool 下装的是实用工具，与 search/song/album 那种直接取东西的不是一类。
    # 子命令 required：不给时让 argparse 报用法错，而不是打一份顶层帮助 ——
    # 用户敲了 tool 却看到整个应用的帮助，像是敲错了
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
    # choices 而不是 clamp：服务端 limit 超过 100 直接回 code 400，
    # 而那句 {"code": 400} 对用户毫无意义。报错比静默截断诚实。
    # 校验交给一个自定义 type 而不用 choices —— choices 会把 1 到 100
    # 全列进用法那行，报错时更是刷出 100 个数字。
    # 顺带补下限：limit=0 在服务端是合法的但拿不到东西，无意义
    p_search.add_argument(
        "--limit",
        "-n",
        type=_search_limit,
        default=None,
        metavar="N",
        help=f"最大结果数，1-{SEARCH_LIMIT_MAX}（默认：10）",
    )
    p_search.add_argument("--offset", type=int, default=0, help="分页偏移量")
    # search 没有下载动作，不存在互斥问题
    _add_json_arg(p_search)

    p_song = sub.add_parser("song", help="预览或下载单曲")
    p_song.add_argument("id", type=int, help="曲目 ID")
    # 查看数据与下载是两种动作，同给时由 argparse 报错退出。
    # 早先这里是 `args.dlink and not args.download`，两者同给时 --dlink 被
    # 静默丢弃，用户以为两个开关叠加了，实际上什么都没发生
    grp_song = p_song.add_mutually_exclusive_group()
    _add_dlink_arg(grp_song, "显示下载链接与音质、费用等详情")
    _add_json_arg(p_song)
    _add_download_args(p_song, download_group=grp_song)
    p_song.add_argument("--lyrics", "-l", action="store_true", help="显示歌词")
    p_song.add_argument("--tlyric", action="store_true", help="显示翻译歌词")

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
    # 三个顶层动作只能选一个。命令里是 if / elif / else，同给时前面的分支
    # 会静默吃掉后面的：-f --fetch-auto 是 fetch_auto 胜出，-f -d 是拉取胜出，
    # 用户以为两个开关叠加了，实际上只有一个生效
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
    # 两个都是 --fetch 的修饰，不是独立动作，所以不进互斥组：
    # 依赖关系 argparse 表达不了，单独给时由 cmd_tracker 报错
    grp_fetch = p_tracker.add_mutually_exclusive_group()
    grp_fetch.add_argument(
        "--auto-accept",
        action="store_true",
        help="配 --fetch 时自动接受全部变更，无需交互",
    )
    grp_fetch.add_argument(
        "--force",
        action="store_true",
        help=(
            "配 --fetch 时无条件覆盖 songs.json。"
            "diff.json 有变化才更新，连续两次会顶掉前一个备份"
        ),
    )
    # --diff 不是独立动作而是 -d 的修饰，所以不进互斥组：
    # 依赖关系 argparse 表达不了，单独给时由 cmd_tracker 报错
    p_tracker.add_argument(
        "--diff",
        action="store_true",
        help="上次 --fetch 记下的变更，不联网。配 -d 下载新增的，配 --json 输出三类",
    )
    # --json 只配纯读视图：四个动作的结果都是文件，不是数据
    _add_json_arg(p_tracker)
    p_tracker.add_argument(
        "--limit",
        "-n",
        type=int,
        default=None,
        metavar="N",
        help="最多处理曲目数（默认：面板 10，JSON 全部）",
    )
    p_tracker.add_argument(
        "--offset", type=int, default=0, metavar="N", help="起始序号，从 0 计"
    )
    _add_quality_arg(p_tracker)
    _add_output_arg(p_tracker)

    return parser


# 这几条不查账号状态：cookie 自己要查，
# tool 下的都不联网 —— cache --clear 刚清完缓存又被自动写回来就白清了，
# check 纯本地干活，而输出还可能给脚本读。
# --init 在 main 里就收掉了，走不到这一步。
# --help 在 parse_args 内部已退出，也走不到这里
_NO_ACCOUNT_REPORT = {"cookie", "tool"}


def _search_limit(raw: str) -> int:
    """把 --limit 限制在服务端接受的范围，报错用中文而不是 invalid choice"""
    try:
        value = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"取回条数须为整数，给的是 {raw!r}") from None
    if not 1 <= value <= SEARCH_LIMIT_MAX:
        # offset 只在超上限时才是出路，「要 0 条」提它就是错的
        hint = "。更多结果用 --offset 分页取得" if value > SEARCH_LIMIT_MAX else ""
        raise argparse.ArgumentTypeError(
            f"取回条数须在 1 至 {SEARCH_LIMIT_MAX} 之间，给的是 {value}{hint}"
        )
    return value


def _reject_json_download(args: argparse.Namespace) -> None:
    """--json 与 --download 互斥

    argparse 表达不了：需要的是 --download 与 --dlink 互斥、与 --json 也互斥，
    而 --dlink 与 --json 不互斥（两者互补，一起给最有用）。互斥组是等价关系，
    --download 只能进一个组，所以这一条只能手写。退出码取 2，与 argparse
    用法错误保持一致，脚本分「用法错」与「跑失败」时不用多记一种。
    """
    if getattr(args, "json", False) and getattr(args, "download", False):
        error("--json 与 --download 互斥：--json 输出结构化数据，--download 落盘")
        sys.exit(2)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # --init 在这里就收掉：它没有后续动作，不该走到命令分派。
    # 放在 validate_config 之前，与当初它是独立命令时一样 ——
    # 那时候 args.command 就是 "init"，而这里 args.command 是 None
    if args.init:
        acquire_lock()
        cmd_init(args)
        return

    # 只看帮助时不碰配置与锁，--help 在 parse_args 内部就已退出
    if args.command is None:
        parser.print_help()
        sys.exit(0)

    _reject_json_download(args)

    acquire_lock()

    validate_config()

    # 播报账号状态。放这里而不是下载前，是因为它必须在取链接之前，
    # 付费歌拿不到链接会直接退出，等到落盘那一步就永远等不到这条提示了
    if args.command not in _NO_ACCOUNT_REPORT:
        announce_account()

    dispatch = {
        "cookie": cmd_cookie,
        "search": cmd_search,
        "song": cmd_song,
        "album": cmd_album,
        "playlist": cmd_playlist,
        "tracker": cmd_tracker,
        # tool 下装的是第二层分派：顶层命令名都叫 tool，
        # 都读 args.tool 才知道实际要跑哪个
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


if __name__ == "__main__":
    main()
