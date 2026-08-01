import argparse
import sys

from function.commands import (
    cmd_search,
    cmd_song,
    cmd_album,
    cmd_playlist,
    cmd_init,
    cmd_cookie,
)
from function.config import validate_config, QUALITY_MAP, acquire_lock
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


def _add_download_args(parser: object, batch: bool = False) -> None:
    """Add download-related args to a parser."""
    parser.add_argument("--download", "-d", action="store_true", help="下载而非仅预览")
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


def main() -> None:
    acquire_lock()
    parser = _ArgumentParser(
        prog="vncmd",
        description="网易云音乐 CLI — 搜索、预览与下载",
    )
    sub = parser.add_subparsers(
        dest="command", help="可用命令", parser_class=_ArgumentParser
    )

    sub.add_parser("init", help="初始化 vncmd 并写入默认配置", parents=[])

    p_cookie = sub.add_parser("cookie", help="设置 Cookie")
    p_cookie.add_argument("value", help="Cookie 值")

    p_search = sub.add_parser("search", help="搜索曲目")
    p_search.add_argument("query", help="搜索关键词")
    p_search.add_argument(
        "--limit", "-n", type=int, default=30, help="最大结果数（默认：30）"
    )
    p_search.add_argument("--offset", type=int, default=0, help="分页偏移量")

    p_song = sub.add_parser("song", help="预览或下载单曲")
    p_song.add_argument("id", type=int, help="曲目 ID")
    p_song.add_argument("--lyrics", "-l", action="store_true", help="显示歌词")
    p_song.add_argument("--tlyric", action="store_true", help="显示翻译歌词")
    p_song.add_argument("--url", "-u", action="store_true", help="检查流 URL 可用性")
    _add_download_args(p_song)

    p_al = sub.add_parser("album", help="预览或下载专辑")
    p_al.add_argument("id", type=int, help="专辑 ID")
    _add_download_args(p_al, batch=True)

    p_pl = sub.add_parser("playlist", help="预览或下载歌单")
    p_pl.add_argument("id", type=int, help="歌单 ID")
    _add_download_args(p_pl, batch=True)

    p_tracker = sub.add_parser("tracker", help="追踪音乐来源变更并批量下载")
    p_tracker.add_argument("name", help="Tracker 名称")
    p_tracker.add_argument(
        "--fetch",
        "-f",
        action="store_true",
        help="拉取并对比，交互式解决冲突",
    )
    p_tracker.add_argument(
        "--fetch-auto",
        action="store_true",
        help="拉取并自动同步，无需交互",
    )
    p_tracker.add_argument(
        "--diff",
        action="store_true",
        help="与 -d 配合时，仅下载上次拉取后新增的曲目",
    )
    p_tracker.add_argument(
        "--download", "-d", action="store_true", help="下载所有已缓存曲目"
    )
    _add_quality_arg(p_tracker)
    _add_output_arg(p_tracker)

    args = parser.parse_args()

    if args.command != "init":
        validate_config()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    dispatch = {
        "init": cmd_init,
        "cookie": cmd_cookie,
        "search": cmd_search,
        "song": cmd_song,
        "album": cmd_album,
        "playlist": cmd_playlist,
        "tracker": cmd_tracker,
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
