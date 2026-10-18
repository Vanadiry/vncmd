import os
import sys
import tomllib
from pathlib import Path

from filelock import FileLock, Timeout

from vncmd.core.defaults import CONFIG_TOML


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

QUALITY_MAP = {
    "128": 128000,
    "192": 192000,
    "320": 320000,
    "max": 2147483647,
}

# 艺术家在文件名里的位置。以前这个键叫 filename_format，
# 但它管不到分隔符、大小写、扩展名，全部三个值都由这一个维度决定，
# 名字比内容宽
FILENAME_ARTIST = ("front", "back", "drop")

# 下载内容。三个字母任意组合，"alc" 是全要，"cl" 只要歌词和封面。
# 用字母而不是数字：数字串读起来就是个带前导零的数，
# 有人会当成整数写上引号就忘了，而 alc 一眼知道不是数字。
# 三个字母没有天然顺序，所以读的时候按包含判断，顺序无所谓
CONTENT_LETTERS = "alc"

# 译文歌词的处理方式。embed 只有 drop 一档不要译文；
# save 多一档 split 是分两个文件，另有一档 drop 同样不要译文
LYRIC_MODES = {
    "embed_mode": ("line", "block", "drop"),
    "save_mode": ("line", "block", "split", "drop"),
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

    # [download]
    dl = cfg.get("download", {})

    # 留空表示用 ~/Downloads，键本身必须在
    if "dir" not in dl:
        errors.append("[download] dir 缺失")

    if not dl.get("filename_artist"):
        errors.append("[download] filename_artist 缺失或为空")
    elif dl["filename_artist"] not in FILENAME_ARTIST:
        errors.append(f"[download] filename_artist 必须为 {'、'.join(FILENAME_ARTIST)}")

    # 不是字符串要单独拦：content = 12 会被 tomllib 读成整数，
    # 下面 set() 它会抛 TypeError，用户看到的是一整段调用栈而不是配置写错了
    content = dl.get("content")
    if not isinstance(content, str) or not content:
        errors.append("[download] content 缺失或为空，且必须是带引号的字符串")
    elif set(content) - set(CONTENT_LETTERS):
        allowed = "、".join(CONTENT_LETTERS)
        extra = "、".join(sorted(set(content) - set(CONTENT_LETTERS)))
        errors.append(f"[download] content 只能包含 {allowed}，多余的字符：{extra}")
    elif len(set(content)) != len(content):
        dup = "、".join(sorted({c for c in content if content.count(c) > 1}))
        errors.append(f"[download] content 里 {dup} 重复了，每个字母最多一次")

    ccy = dl.get("concurrency", 4)
    if not isinstance(ccy, int) or ccy < 1 or ccy > 16:
        errors.append("[download] concurrency 必须为 1-16 的整数")

    chk = dl.get("check", True)
    if not isinstance(chk, bool):
        errors.append("[download] check 必须为 true 或 false")

    kind = dl.get("downloader", "builtin")
    if kind not in ("builtin", "curl"):
        errors.append('[download] downloader 只能是 "builtin" 或 "curl"')

    if not isinstance(dl.get("curl_arg", ""), str):
        errors.append("[download] curl_arg 必须是字符串")

    # [download.audio]
    ds = dl.get("audio", {})
    if not ds.get("quality"):
        errors.append("[download.audio] quality 缺失或为空")
    elif ds["quality"] not in QUALITY_MAP:
        errors.append(
            f"[download.audio] quality 必须为以下之一：{', '.join(QUALITY_MAP)}"
        )
    if not isinstance(ds.get("parse_credits"), bool):
        errors.append("[download.audio] parse_credits 缺失或不为布尔值")

    # [download.lyric]
    dly = dl.get("lyric", {})
    # line 与 block 两边共有，第三档不同：embed 是不要译文，save 是分两个文件。
    # 用 if key not in dly 判缺失而不是 not dly.get(key) ——
    # 合法值里没有空串，但那种写法对空值才成立，将来加了空值就会重蹈覆辙
    for key, allowed in LYRIC_MODES.items():
        if key not in dly:
            errors.append(f"[download.lyric] {key} 缺失")
        elif dly[key] not in allowed:
            errors.append(f"[download.lyric] {key} 必须为 {'、'.join(allowed)}")
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
    for key in ("embed_compress", "save_compress"):
        if key not in dc:
            errors.append(f"[download.cover] {key} 缺失")
        elif not isinstance(dc[key], bool):
            errors.append(f"[download.cover] {key} 必须为 true 或 false")

    # [cache]
    cc = cfg.get("cache", {})
    if "enabled" not in cc:
        errors.append("[cache] enabled 缺失")
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
