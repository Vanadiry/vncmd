import argparse
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

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


def _add_download_args(
    parser: object, batch: bool = False, download_group: object = None
) -> None:
    """Add download-related args to a parser.

    download_group 非空时把 --download 放进那个互斥组。
    单曲的 --dlink 是查看数据，与 --download 是两种动作，两者互斥；
    专辑与歌单没有查看链接的开关，所以照旧直接加在 parser 上。
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
    if batch:
        parser.add_argument(
            "--limit",
            "-n",
            type=int,
            default=None,
            help="最多下载曲目数（默认：全部）",
        )


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

    sub.add_parser("init", help="初始化 vncmd 并写入默认配置")

    p_cookie = sub.add_parser("cookie", help="设置 Cookie")
    grp_cookie = p_cookie.add_mutually_exclusive_group()
    # 写成 --check 又给值是自相矛盾：--check 的意思就是不写文件
    grp_cookie.add_argument("value", nargs="?", help="Cookie 值，省略时需配 --check")
    grp_cookie.add_argument(
        "--check", action="store_true", help="不写文件，只检查当前 Cookie 状态"
    )

    p_check = sub.add_parser("check", help="检查音频文件完整性")
    p_check.add_argument("path", help="文件或目录路径")

    p_cache = sub.add_parser("cache", help="查看或清理本地缓存")
    p_cache.add_argument("--stats", action="store_true", help="显示占用与条目数")
    p_cache.add_argument("--clear", action="store_true", help="清空缓存目录")

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
        default=10,
        metavar="N",
        help=f"最大结果数，1-{_SEARCH_LIMIT_MAX}（默认：10）",
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
    grp_song.add_argument(
        "--dlink", "-u", action="store_true", help="显示下载链接与音质、费用等详情"
    )
    _add_json_arg(p_song)
    _add_download_args(p_song, download_group=grp_song)
    p_song.add_argument("--lyrics", "-l", action="store_true", help="显示歌词")
    p_song.add_argument("--tlyric", action="store_true", help="显示翻译歌词")

    p_al = sub.add_parser("album", help="预览或下载专辑")
    p_al.add_argument("id", type=int, help="专辑 ID")
    _add_json_arg(p_al)
    _add_download_args(p_al, batch=True)

    p_pl = sub.add_parser("playlist", help="预览或下载歌单")
    p_pl.add_argument("id", type=int, help="歌单 ID")
    _add_json_arg(p_pl)
    _add_download_args(p_pl, batch=True)

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
        "--fetch-auto",
        action="store_true",
        help="拉取并自动同步，无需交互",
    )
    grp_tracker.add_argument(
        "--download", "-d", action="store_true", help="下载所有已缓存曲目"
    )
    # --diff 不是独立动作而是 -d 的修饰，所以不进互斥组：
    # 依赖关系 argparse 表达不了，单独给时由 cmd_tracker 报错
    p_tracker.add_argument(
        "--diff",
        action="store_true",
        help="与 -d 配合时，仅下载上次拉取后新增的曲目",
    )
    _add_quality_arg(p_tracker)
    _add_output_arg(p_tracker)

    return parser


# 这几条不查账号状态：init 还没配置好，cookie 自己要查，
# cache --clear 刚清完缓存又被自动写回来就白清了，
# check 纯本地干活，联网对它没有意义，输出还可能给脚本读。
# --help 在 parse_args 内部已退出，也走不到这里
_NO_ACCOUNT_REPORT = {"init", "cookie", "cache", "check"}

# 搜索接口的单次上限，实测 100 能过而 101 直接回 {'code': 400}
_SEARCH_LIMIT_MAX = 100


def _search_limit(raw: str) -> int:
    """把 --limit 限制在服务端接受的范围，报错用中文而不是 invalid choice"""
    try:
        value = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"取回条数须为整数，给的是 {raw!r}") from None
    if not 1 <= value <= _SEARCH_LIMIT_MAX:
        # offset 只在超上限时才是出路，「要 0 条」提它就是错的
        hint = "。更多结果用 --offset 分页取得" if value > _SEARCH_LIMIT_MAX else ""
        raise argparse.ArgumentTypeError(
            f"取回条数须在 1 至 {_SEARCH_LIMIT_MAX} 之间，给的是 {value}{hint}"
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

    # 只看帮助时不碰配置与锁，--help 在 parse_args 内部就已退出
    if args.command is None:
        parser.print_help()
        sys.exit(0)

    _reject_json_download(args)

    acquire_lock()

    if args.command != "init":
        validate_config()

    # 播报账号状态。放这里而不是下载前，是因为它必须在取链接之前，
    # 付费歌拿不到链接会直接退出，等到落盘那一步就永远等不到这条提示了
    if args.command not in _NO_ACCOUNT_REPORT:
        announce_account()

    dispatch = {
        "init": cmd_init,
        "cookie": cmd_cookie,
        "check": cmd_check,
        "cache": cmd_cache,
        "search": cmd_search,
        "song": cmd_song,
        "album": cmd_album,
        "playlist": cmd_playlist,
        "tracker": cmd_tracker,
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
