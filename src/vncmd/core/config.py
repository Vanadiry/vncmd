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
from vncmd.core.schema import validate as schema_validate


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


DEFAULT_CACHE_TTL = 3

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

    # 已进表的那几项交给 schema —— 值域、默认值与报错措辞都在表里。
    # 顺序放在段类型检查之后：段本身不是表时表里那几项取不到值，
    # 会报出一堆「xx 缺失」，而真正的问题只是那一段写错了
    if isinstance(cfg.get("download", {}), dict) and isinstance(
        cfg.get("cache", {}), dict
    ):
        errors.extend(schema_validate(cfg))

    # 段本身写错类型时先拦下。下面全是 dl.get(key)、key not in dl 这类写法，
    # 段不是表的话它们会抛 TypeError 或 AttributeError，用户看到的是一整段调用栈，
    # 而不是「[download] 这一段写错了」
    dl = cfg.get("download", {})
    if not isinstance(dl, dict):
        _die([f"[download] 必须是一段配置，实际是 {type(dl).__name__}"])
        dl = {}

    # 留空表示用 ~/Downloads，键本身必须在
    if "dir" not in dl:
        errors.append("[download] dir 缺失")
    elif not isinstance(dl["dir"], str):
        errors.append(f"[download] dir 必须是字符串，实际是 {type(dl['dir']).__name__}")

    # filename_artist、content、downloader 三项由 schema 的表来查，
    # 报错措辞在表里；其余手写的还在，等第 3 步起逐项挪进去

    # 缺键要报错而不是默认 4 —— getter 是直接下标取的，
    # 校验放行的话，等到真下载时才炸，而那时候用户看不到是哪句配置写错了
    ccy = dl.get("concurrency")
    # isinstance(ccy, bool) 那道不能省：布尔是 int 的子类，
    # concurrency = true 会一路通过 isinstance 检查，min(True, 曲数) 得 1，
    # 静默降成单线程还不给任何提示
    if not isinstance(ccy, int) or isinstance(ccy, bool) or not 1 <= ccy <= 16:
        errors.append(f"[download] concurrency 必须为 1-16 的整数，实际是 {ccy!r}")

    chk = dl.get("check", True)
    if not isinstance(chk, bool):
        errors.append("[download] check 必须为 true 或 false")

    if not isinstance(dl.get("curl_arg", ""), str):
        errors.append("[download] curl_arg 必须是字符串")

    # [download.audio]
    ds = dl.get("audio", {})
    if not isinstance(ds, dict):
        _die([f"[download.audio] 必须是一段配置，实际是 {type(ds).__name__}"])
        ds = {}
    if not isinstance(ds.get("parse_credits"), bool):
        errors.append("[download.audio] parse_credits 缺失或不为布尔值")

    # [download.lyric]
    dly = dl.get("lyric", {})
    if not isinstance(dly, dict):
        _die([f"[download.lyric] 必须是一段配置，实际是 {type(dly).__name__}"])
        dly = {}
    if not isinstance(dly.get("auto_trim"), bool):
        errors.append("[download.lyric] auto_trim 缺失或不为布尔值")
    scan = dly.get("credit_scan_lines")
    if not isinstance(scan, int) or isinstance(scan, bool) or scan < 1:
        errors.append("[download.lyric] credit_scan_lines 缺失或不为正整数")

    # [download.cover]
    # 判缺失用 `key not in dc` 而不是 `not dc.get(key)`。
    # 这两个键的合法值里有 false，「取不到就是空」那种写法会把 false
    # 当成没写，而 false 恰好是「用原图」那一档
    dc = dl.get("cover", {})
    if not isinstance(dc, dict):
        _die([f"[download.cover] 必须是一段配置，实际是 {type(dc).__name__}"])
        dc = {}
    for key in ("embed_compress", "save_compress"):
        if key not in dc:
            errors.append(f"[download.cover] {key} 缺失")
        elif not isinstance(dc[key], bool):
            errors.append(
                f"[download.cover] {key} 必须为 true 或 false，实际是 {dc[key]!r}"
            )

    # [cache]
    cc = cfg.get("cache", {})
    if not isinstance(cc, dict):
        _die([f"[cache] 必须是一段配置，实际是 {type(cc).__name__}"])
        cc = {}
    # enabled 要判类型：写成带引号的 "false" 时字符串非空、是真值，
    # 用户以为关了缓存实际照开，而这种错在界面上完全看不出来
    if "enabled" not in cc:
        errors.append("[cache] enabled 缺失")
    elif not isinstance(cc["enabled"], bool):
        errors.append(f"[cache] enabled 必须为 true 或 false，实际是 {cc['enabled']!r}")
    ttl = cc.get("ttl", DEFAULT_CACHE_TTL)
    if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl < 0:
        errors.append("[cache] ttl 不为非负整数")

    # [display]
    # 整段缺失时按默认值算，升级旧配置不至于报错，类型写错仍要拦下
    artist_color = cfg.get("display", {}).get("artist_color", True)
    if not isinstance(artist_color, bool):
        errors.append("[display] artist_color 不为布尔值")

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
    path = _get_cfg()["download"]["dir"] or ""
    if path:
        return str(_user_path(path))
    return str(Path.home() / "Downloads" / "vncmd-dl")


def get_concurrency() -> int:
    return _get_cfg()["download"]["concurrency"]


def get_check_enabled() -> bool:
    """是否做 ffmpeg 全量解码校验，老配置没写这个键时按开着处理"""
    return _get_cfg().get("download", {}).get("check", True)


def get_downloader() -> str:
    return _get_cfg().get("download", {}).get("downloader", "builtin")


def get_curl_arg() -> str:
    return _get_cfg().get("download", {}).get("curl_arg", "")


def resolve_output_dir(value: str | None) -> str:
    if value:
        # 不展开 ~ 会在当前目录下建出名为 ~ 的目录
        return os.path.expanduser(value)
    return get_download_dir()


def get_quality() -> int:
    return QUALITY_MAP[_get_cfg()["download"]["audio"]["quality"]]


def get_cookie() -> str:
    # 权限不足或文件损坏时返回空串，调用方本来就按无 Cookie 走，
    # 这里抛异常会让每次请求都带不上 Cookie 并中断
    try:
        return COOKIE_FILE.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def get_filename_artist() -> str:
    return _get_cfg()["download"]["filename_artist"]


def get_download_content() -> str:
    return _get_cfg()["download"]["content"]


def get_embed_lyrics_mode() -> str:
    return _get_cfg()["download"]["lyric"]["embed_mode"]


def get_save_lyrics_mode() -> str:
    return _get_cfg()["download"]["lyric"]["save_mode"]


def get_embed_cover_compress() -> bool:
    return _get_cfg()["download"]["cover"]["embed_compress"]


def get_save_cover_compress() -> bool:
    return _get_cfg()["download"]["cover"]["save_compress"]


def get_parse_credits() -> bool:
    return _get_cfg()["download"]["audio"]["parse_credits"]


def get_auto_trim() -> bool:
    return _get_cfg()["download"]["lyric"]["auto_trim"]


def get_credit_scan_lines() -> int:
    return _get_cfg()["download"]["lyric"]["credit_scan_lines"]


def get_cache_ttl() -> int:
    # 旧配置没有这一项时按默认值算，升级不至于报错
    return _get_cfg().get("cache", {}).get("ttl", DEFAULT_CACHE_TTL)


def get_cache_dir() -> str:
    """缓存固定在 VNCMD_HOME 下，不再是配置项。

    一首歌的缓存是三个小文件、一个歌一个目录，实测 592 首 2.3 MB，
    上限是曲库有多少首而不是用了多久 —— 这样大的东西没有搬家的理由。
    真要换地方，把这个目录做成软链接就行，比配置键还灵活。
    """
    return str(VNCMD_HOME / "cache")


def is_cache_enabled() -> bool:
    return _get_cfg()["cache"]["enabled"]


def is_artist_color() -> bool:
    # 配置段缺失时保持默认开启
    return _get_cfg().get("display", {}).get("artist_color", True)
