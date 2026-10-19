import os
import sys
import tomllib
from pathlib import Path

from filelock import FileLock, Timeout

from vncmd.core.defaults import CONFIG_TOML

# 值域搬进 schema.py 了。这几个名字在 cli、tracker、commands 与测试里被 import，
# 这里再转发一遍，各调用点就能分批跟着搬，不必一次全改
from vncmd.core.schema import CONTENT_LETTERS as CONTENT_LETTERS
from vncmd.core.schema import FILENAME_ARTIST as FILENAME_ARTIST
from vncmd.core.schema import LYRIC_MODES as LYRIC_MODES
from vncmd.core.schema import QUALITY_MAP as QUALITY_MAP
from vncmd.core.schema import section_names as section_names
from vncmd.core.schema import unknown_keys as unknown_keys
from vncmd.core.schema import validate as schema_validate
from vncmd.core.schema import value_of as value_of


def abbrev_home(path) -> str:
    """把用户主目录那段替换成 ~，路径太长时能省下十几个字符

    住在这里而不是 output.py，是因为 config.py 自己也要用（首次运行的提示、
    解析失败），而 output.py 从这一层导入，反过来会成环。
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
        print("已有其他 vncmd 实例在运行。", file=sys.stderr)
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


def validate_config(quiet: bool = False) -> None:
    """Check config file has all required keys.  Auto-creates on first run."""
    if not CONFIG_FILE.exists():
        VNCMD_HOME.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(CONFIG_TOML, encoding="utf-8")
        if not quiet:
            print(
                f"未能找到配置文件，已创建：{abbrev_home(CONFIG_FILE)}", file=sys.stderr
            )
            print("首次运行？请执行 vncmd --init 以获取更多信息", file=sys.stderr)

    try:
        cfg = load_config()
    except Exception as e:
        _die([f"解析 {abbrev_home(CONFIG_FILE)} 失败：{e}"])
        return

    global _cfg
    _cfg = cfg

    errors = []

    # 段本身写错类型时先拦下，它得排在逐项校验之前 ——
    # 段不是表时表里那几项取不到值，只能当作缺键放过，
    # 而真正的问题只是那一段写坏了，不报就等于没看见。
    #
    # 段的名字从 SCHEMA 里推，不手写清单 ——
    # 手写过一次就漏了 display，后来是审查发现的
    for section in section_names():
        # 按点号一层层走进去。TOML 的嵌套表解析出来是
        # cfg["download"]["audio"]，不是 cfg["download.audio"] ——
        # 直接 cfg.get("download.audio") 拿到的是 None，
        # 于是三个子段的检查全成了死代码
        container = cfg
        for part in section.split("."):
            if not isinstance(container, dict):
                break
            container = container.get(part)
        if container is None:
            # 整个段没写，与写坏了是两回事：没写按缺键处理，
            # 由表里那几项各取各自的默认值
            continue
        if not isinstance(container, dict):
            _die([f"[{section}] 必须是一段配置，实际是 {type(container).__name__}"])

    # 十八项的逐项知识都在 schema 的表里。段检查放前面就是为这一步 ——
    # 表按点号路径取值，那几段不是表时它取不到值只能跳过，
    # 跳过与「该段没写」分不清，段检查就是替它分的那道
    errors.extend(schema_validate(cfg))

    # 表里没有的段与键一律报错，点名是哪个 ——
    # 静默放过的话，用户照抄新键名却忘了删旧的，那种配置看不出问题
    errors.extend(f"{item}，表里没有这个键" for item in unknown_keys(cfg))

    if errors:
        _die(errors)


def _die(errors: list[str]) -> None:
    from vncmd.core.output import err_console, error

    err_console.print("[red]配置验证失败：[/]")
    for e in errors:
        error(e)
    sys.exit(1)


def _user_path(value: str) -> Path:
    """展开用户填的路径，相对的挂到 VNCMD_HOME 下

    用 os.path.expanduser 而非 Path.expanduser，用户名不存在时前者原样返回，
    后者抛 RuntimeError，配置里误写一个 ~someone 会变成加载崩溃。
    绝对路径直接返回，不与 VNCMD_HOME 拼接。
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
    """是否做 ffmpeg 全量解码校验

    缺这个键时按开着处理 —— 那是对老配置网的容让：
    老配置里根本没有这一项，补一个等于替所有老用户改了行为
    """
    return value_of(_get_cfg(), "download.check")


def get_downloader() -> str:
    return value_of(_get_cfg(), "download.downloader")


def get_curl_arg() -> str:
    return value_of(_get_cfg(), "download.curl_arg")


def resolve_output_dir(value: str | None) -> str:
    if value:
        # 不展开 ~ 会在当前目录下建出名为 ~ 的目录
        return os.path.expanduser(value)
    return get_download_dir()


def get_quality() -> int:
    return QUALITY_MAP[value_of(_get_cfg(), "download.audio.quality")]


def get_cookie() -> str:
    # 权限不足或文件损坏时返回空串，调用方本来就按无 Cookie 走，
    # 这里抛异常会让每次请求都带不上 Cookie 并中断
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
    """缓存固定在 VNCMD_HOME 下，不再是配置项。

    一首歌的缓存是三个小文件、一个歌一个目录，实测 592 首 2.3 MB，
    上限是曲库有多少首而不是用了多久 —— 这样大的东西没有搬家的理由。
    真要换地方，把这个目录做成软链接就行，比配置键还灵活。
    """
    return str(VNCMD_HOME / "cache")


def is_cache_enabled() -> bool:
    return value_of(_get_cfg(), "cache.enabled")


def is_artist_color() -> bool:
    return value_of(_get_cfg(), "display.artist_color")
