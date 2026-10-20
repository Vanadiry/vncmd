import copy
import os
import sys
import tomllib
from pathlib import Path

from filelock import FileLock, Timeout

from vncmd.core.defaults import CONFIG_TOML

# 值域在 schema.py，这里转发给旧调用点
from vncmd.core.schema import CONTENT_LETTERS as CONTENT_LETTERS
from vncmd.core.schema import FILENAME_ARTIST as FILENAME_ARTIST
from vncmd.core.schema import LYRIC_MODES as LYRIC_MODES
from vncmd.core.schema import QUALITY_MAP as QUALITY_MAP
from vncmd.core.schema import section_names as section_names
from vncmd.core.schema import unknown_keys as unknown_keys
from vncmd.core.schema import validate as schema_validate
from vncmd.core.schema import value_of as value_of


def abbrev_home(path) -> str:
    """把主目录替换成 ~，缩短过长的路径

    放在 config 里避免 output 反向导入成环
    """
    text = str(path)
    home = str(Path.home())
    if text == home:
        return "~"
    if text.startswith(home + os.sep):
        return "~" + text[len(home) :]
    return text


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
        print("已有其他 vncmd 实例在运行", file=sys.stderr)
        sys.exit(1)


_cfg: dict | None = None


def load_config() -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return tomllib.loads(f.read())


def _get_cfg() -> dict:
    global _cfg
    if _cfg is None:
        _cfg = load_config()
    return _cfg


def validate_config(quiet: bool = False, overrides: dict | None = None) -> None:
    """读配置并校验，首次运行时写出默认模板

    overrides 在校验前叠加，可覆盖写坏的单值，不新增段
    """
    if not CONFIG_FILE.exists():
        VNCMD_HOME.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(CONFIG_TOML, encoding="utf-8")
        if not quiet:
            print(
                f"未能找到配置文件，已创建：{abbrev_home(CONFIG_FILE)}", file=sys.stderr
            )
            print("首次运行，更多信息见 vncmd --init", file=sys.stderr)

    try:
        cfg = load_config()
    except Exception as e:
        _die([f"解析 {abbrev_home(CONFIG_FILE)} 失败：{e}"])
        return

    check_config(apply_overrides(cfg, overrides or {}))


def apply_overrides(cfg: dict, overrides: dict) -> dict:
    """把 --config 的覆盖叠到配置上，返回深拷贝"""
    if not overrides:
        return cfg
    out = copy.deepcopy(cfg)
    for path, value in overrides.items():
        *parents, leaf = path.split(".")
        container = out
        for part in parents:
            child = container.get(part)
            if not isinstance(child, dict):
                # 中间层缺失或写坏时先建新表，校验会另行报出坏段
                child = {}
                container[part] = child
            container = child
        container[leaf] = value
    return out


def check_config(cfg: dict) -> None:
    """校验内存里的配置，有错就退出

    校验通过后这份配置成为进程内唯一来源
    """
    global _cfg
    _cfg = cfg

    errors = []

    # 段类型写错时先拦下，否则逐项校验取不到值
    # 段名从 SCHEMA 推导，避免手写遗漏
    for section in section_names():
        # TOML 嵌套表按点号逐层取
        container = cfg
        for part in section.split("."):
            if not isinstance(container, dict):
                break
            container = container.get(part)
        if container is None:
            # 整段未写按缺键处理，由各项取默认值
            continue
        if not isinstance(container, dict):
            _die(
                [
                    f"[{section}] 配置不合法，应当为配置段，"
                    f"实际是 {type(container).__name__}"
                ]
            )

    # 段检查在前，逐项表才能区分缺键与段写坏
    errors.extend(schema_validate(cfg))

    # 未知段与键一律报错，避免旧键静默失效
    errors.extend(f"未知配置项：{item}" for item in unknown_keys(cfg))

    if errors:
        _die(errors)


def _die(errors: list[str]) -> None:
    from vncmd.core.output import err_console, error

    err_console.print("[red]配置验证失败[/]：")
    for e in errors:
        error(e)
    sys.exit(1)


def _user_path(value: str) -> Path:
    """展开用户路径，相对路径挂到 VNCMD_HOME 下

    用 os.path.expanduser，避免 ~someone 触发 RuntimeError
    """
    path = os.path.expanduser(value)
    return Path(path) if os.path.isabs(path) else VNCMD_HOME / path


def get_download_dir() -> str:
    path = value_of(_get_cfg(), "download.dir") or ""
    if path:
        return str(_user_path(path))
    return str(Path.home() / "Downloads" / "vncmd-dl")


def get_concurrency() -> int:
    return value_of(_get_cfg(), "download.concurrency")


def get_check_enabled() -> bool:
    """是否做 ffmpeg 全量解码校验，缺键时按开启处理"""
    return value_of(_get_cfg(), "download.check")


def get_downloader() -> str:
    return value_of(_get_cfg(), "download.downloader")


def get_curl_arg() -> str:
    return value_of(_get_cfg(), "download.curl_arg")


def get_quality() -> int:
    """配置的音质，转成发给接口的码率"""
    return QUALITY_MAP[value_of(_get_cfg(), "download.audio.quality")]


def get_quality_name() -> str:
    """配置里的音质名，给提示用"""
    return value_of(_get_cfg(), "download.audio.quality")


def get_cookie() -> str:
    # 权限不足或文件损坏时按无 Cookie 处理，不抛异常
    try:
        return COOKIE_FILE.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def get_filename_artist() -> str:
    return value_of(_get_cfg(), "download.filename_artist")


def get_download_content() -> str:
    return value_of(_get_cfg(), "download.content")


def get_embed_lyrics_mode() -> str:
    return value_of(_get_cfg(), "download.lyric.embed_mode")


def get_save_lyrics_mode() -> str:
    return value_of(_get_cfg(), "download.lyric.save_mode")


def get_embed_cover_compress() -> bool:
    return value_of(_get_cfg(), "download.cover.embed_compress")


def get_save_cover_compress() -> bool:
    return value_of(_get_cfg(), "download.cover.save_compress")


def get_parse_credits() -> bool:
    return value_of(_get_cfg(), "download.audio.parse_credits")


def get_auto_trim() -> bool:
    return value_of(_get_cfg(), "download.lyric.auto_trim")


def get_credit_scan_lines() -> int:
    return value_of(_get_cfg(), "download.lyric.credit_scan_lines")


def get_cache_ttl() -> int:
    return value_of(_get_cfg(), "cache.ttl")


def get_cache_dir() -> str:
    """缓存固定于 VNCMD_HOME，不再作为配置项"""
    return str(VNCMD_HOME / "cache")


def is_cache_enabled() -> bool:
    return value_of(_get_cfg(), "cache.enabled")


def is_artist_color() -> bool:
    return value_of(_get_cfg(), "display.artist_color")
