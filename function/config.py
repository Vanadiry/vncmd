import os
import sys
import tomllib
from pathlib import Path

from filelock import FileLock, Timeout

from function._defaults import CONFIG_TOML

VNCMD_HOME = Path(os.environ.get("VNCMD_HOME", "~/.vSoft/vncmd")).expanduser()
CONFIG_FILE = VNCMD_HOME / "config.toml"
COOKIE_FILE = VNCMD_HOME / "cookie"
LOCK_FILE = VNCMD_HOME / ".lock"

_locker = None


def acquire_lock() -> None:
    global _locker
    VNCMD_HOME.mkdir(parents=True, exist_ok=True)
    _locker = FileLock(str(LOCK_FILE))
    try:
        _locker.acquire(timeout=0)
    except Timeout:
        print("已有其他 vncmd 实例在运行。", file=sys.stderr)
        sys.exit(1)


DEFAULT_CACHE_TTL = 3

QUALITY_MAP = {
    "128": 128000,
    "192": 192000,
    "320": 320000,
    "999": 2147483647,
}

_cfg: dict | None = None


def load_config() -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return tomllib.loads(f.read())


def _get_cfg() -> dict:
    global _cfg
    if _cfg is None:
        _cfg = load_config()
    return _cfg


def validate_config(quiet: bool = False) -> None:
    """Check config file has all required keys.  Auto-creates on first run."""
    if not CONFIG_FILE.exists():
        VNCMD_HOME.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(CONFIG_TOML, encoding="utf-8")
        if not quiet:
            print(f"未能找到配置文件，已创建：{CONFIG_FILE}", file=sys.stderr)
            print("首次运行？请执行 vncmd init 以获取更多信息", file=sys.stderr)

    try:
        cfg = load_config()
    except Exception as e:
        _die([f"解析 {CONFIG_FILE} 失败：{e}"])
        return

    global _cfg
    _cfg = cfg

    errors = []

    # [download]
    dl = cfg.get("download", {})

    # 留空表示用 ~/Downloads，键本身必须在
    if "dir" not in dl:
        errors.append("[download] dir 缺失")

    if not dl.get("filename_format"):
        errors.append("[download] filename_format 缺失或为空")
    elif dl["filename_format"] not in ("10", "01", "1"):
        errors.append('[download] filename_format 必须为 "10"、"01" 或 "1"')

    if not dl.get("content"):
        errors.append("[download] content 缺失或为空")
    else:
        for c in dl["content"]:
            if c not in "012":
                errors.append("[download] content 只能包含 0、1、2")
                break

    ccy = dl.get("concurrency", 4)
    if not isinstance(ccy, int) or ccy < 1 or ccy > 16:
        errors.append("[download] concurrency 必须为 1-16 的整数")

    # [download.song]
    ds = dl.get("song", {})
    if not ds.get("quality"):
        errors.append("[download.song] quality 缺失或为空")
    elif ds["quality"] not in QUALITY_MAP:
        errors.append(
            f"[download.song] quality 必须为以下之一：{', '.join(QUALITY_MAP)}"
        )
    if not isinstance(ds.get("parse_credits"), bool):
        errors.append("[download.song] parse_credits 缺失或不为布尔值")

    # [download.lyric]
    dly = dl.get("lyric", {})
    for key in ("embed_mode", "save_mode"):
        if not dly.get(key):
            errors.append(f"[download.lyric] {key} 缺失或为空")
        elif dly[key] not in ("0", "1", "2"):
            errors.append(f'[download.lyric] {key} 必须为 "0"、"1" 或 "2"')
    if not isinstance(dly.get("auto_trim"), bool):
        errors.append("[download.lyric] auto_trim 缺失或不为布尔值")
    scan = dly.get("credit_scan_lines")
    if not isinstance(scan, int) or isinstance(scan, bool) or scan < 1:
        errors.append("[download.lyric] credit_scan_lines 缺失或不为正整数")
    prefixes = dly.get("credit_prefixes")
    if not isinstance(prefixes, list) or not all(isinstance(p, str) for p in prefixes):
        errors.append("[download.lyric] credit_prefixes 缺失或不为字符串列表")

    # [download.cover]
    dc = dl.get("cover", {})
    for key in ("embed_quality", "save_quality"):
        if not dc.get(key):
            errors.append(f"[download.cover] {key} 缺失或为空")
        elif dc[key] not in ("0", "1"):
            errors.append(f'[download.cover] {key} 必须为 "0" 或 "1"')

    # [cache]
    cc = cfg.get("cache", {})
    if "enabled" not in cc:
        errors.append("[cache] enabled 缺失")
    if not cc.get("dir"):
        errors.append("[cache] dir 缺失或为空")
    ttl = cc.get("ttl", DEFAULT_CACHE_TTL)
    if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl < 0:
        errors.append("[cache] ttl 不为非负整数")

    # [display]
    # 整段缺失时按默认值算，升级旧配置不至于报错，类型写错仍要拦下
    vsc = cfg.get("display", {}).get("virtual_singer_color", True)
    if not isinstance(vsc, bool):
        errors.append("[display] virtual_singer_color 不为布尔值")

    if errors:
        _die(errors)


def _die(errors: list[str]) -> None:
    from function.output import console, error

    console.print("[red]配置验证失败：[/]")
    for e in errors:
        error(e)
    sys.exit(1)


def get_download_dir() -> str:
    path = _get_cfg()["download"]["dir"] or ""
    if path:
        path = os.path.expanduser(path)
        if not os.path.isabs(path):
            path = str(VNCMD_HOME / path)
        return path
    return str(Path.home() / "Downloads" / "vncmd-dl")


def get_concurrency() -> int:
    return _get_cfg()["download"]["concurrency"]


def resolve_output_dir(value: str | None) -> str:
    if value:
        # 不展开 ~ 会在当前目录下建出名为 ~ 的目录
        return os.path.expanduser(value)
    return get_download_dir()


def get_quality() -> int:
    return QUALITY_MAP[_get_cfg()["download"]["song"]["quality"]]


def get_cookie() -> str:
    if not COOKIE_FILE.exists():
        return ""
    return COOKIE_FILE.read_text(encoding="utf-8").strip()


def get_filename_format() -> str:
    return _get_cfg()["download"]["filename_format"]


def get_download_content() -> str:
    return _get_cfg()["download"]["content"]


def get_embed_lyrics_mode() -> str:
    return _get_cfg()["download"]["lyric"]["embed_mode"]


def get_save_lyrics_mode() -> str:
    return _get_cfg()["download"]["lyric"]["save_mode"]


def get_embed_cover_quality() -> str:
    return _get_cfg()["download"]["cover"]["embed_quality"]


def get_save_cover_quality() -> str:
    return _get_cfg()["download"]["cover"]["save_quality"]


def get_parse_credits() -> bool:
    return _get_cfg()["download"]["song"]["parse_credits"]


def get_auto_trim() -> bool:
    return _get_cfg()["download"]["lyric"]["auto_trim"]


def get_credit_scan_lines() -> int:
    return _get_cfg()["download"]["lyric"]["credit_scan_lines"]


def get_credit_prefixes() -> list[str]:
    return _get_cfg()["download"]["lyric"]["credit_prefixes"]


def get_cache_ttl() -> int:
    # 旧配置没有这一项时按默认值算，升级不至于报错
    return _get_cfg().get("cache", {}).get("ttl", DEFAULT_CACHE_TTL)


def get_cache_dir() -> str:
    # 不展开 ~ 会在 VNCMD_HOME 下建出名为 ~ 的目录
    return str(VNCMD_HOME / os.path.expanduser(_get_cfg()["cache"]["dir"]))


def is_cache_enabled() -> bool:
    return _get_cfg()["cache"]["enabled"]


def is_virtual_singer_color() -> bool:
    # 配置段缺失时保持默认开启
    return _get_cfg().get("display", {}).get("virtual_singer_color", True)


def show_config() -> str:
    lines = [
        f"--- Config TOML ({CONFIG_FILE}) ---",
    ]
    lines.append(CONFIG_FILE.read_text(encoding="utf-8").rstrip())
    lines.append("")
    lines.append("--- Cookie ---")
    cookie = get_cookie()
    if cookie:
        lines.append(f"已设置（{len(cookie)} 字符） —  {COOKIE_FILE}")
    else:
        lines.append("未设置")
    return "\n".join(lines)
