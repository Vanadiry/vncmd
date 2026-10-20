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
from vncmd.parser import _search_limit as _search_limit
from vncmd.parser import build_parser as _build_parser
from vncmd.tracker import cmd_tracker


def _version_string() -> str:
    """从已安装包元数据读版本，源码直跑时返回 unknown"""
    try:
        return f"vncmd {_pkg_version('vncmd')}"
    except PackageNotFoundError:
        return "vncmd 版本未知"


def build_parser():
    """按当前安装版本构建参数解析器"""
    return _build_parser(_version_string())


# 这些命令不查账号：cookie 自查，tool 不联网
_NO_ACCOUNT_REPORT = {"cookie", "tool"}


def _reject_json_download(args: argparse.Namespace) -> None:
    """--json 与 --download 互斥

    argparse 无法表达非传递排除，退出码与用法错误一致
    """
    if getattr(args, "json", False) and getattr(args, "download", False):
        show_error("--json 与 --download 不能同时使用")
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
            show_error("--init 不接受 --config，它只写默认配置")
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
