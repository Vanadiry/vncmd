import os
import sys
import tomllib
from pathlib import Path

from function._defaults import CONFIG_TOML

VNCMD_HOME = Path(os.environ.get("VNCMD_HOME", "~/.vSoft/vncmd")).expanduser()
CONFIG_FILE = VNCMD_HOME / "config.toml"
COOKIE_FILE = VNCMD_HOME / "cookie"

QUALITY_MAP = {
    "128": 128000,
    "192": 192000,
    "320": 320000,
    "999": 2147483647,
}

_cfg: dict | None = None


def load_config() -> dict:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return tomllib.loads(f.read())


def _get_cfg() -> dict:
    global _cfg
    if _cfg is None:
        _cfg = load_config()
    return _cfg


def validate_config() -> None:
    """Check config file has all required keys.  Auto-creates on first run."""
    if not CONFIG_FILE.exists():
        VNCMD_HOME.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(CONFIG_TOML, encoding="utf-8")

    try:
        cfg = load_config()
    except Exception as e:
        _die([f"Failed to parse {CONFIG_FILE}: {e}"])
        return

    global _cfg
    _cfg = cfg

    errors = []

    # [download]
    dl = cfg.get("download", {})

    if not dl.get("filename_format"):
        errors.append("[download] filename_format is missing or empty")
    elif dl["filename_format"] not in ("10", "01", "1"):
        errors.append('[download] filename_format must be "10", "01", or "1"')

    if not dl.get("content"):
        errors.append("[download] content is missing or empty")
    else:
        for c in dl["content"]:
            if c not in "012":
                errors.append("[download] content may only contain 0, 1, 2")
                break

    # [download.song]
    ds = dl.get("song", {})
    if not ds.get("quality"):
        errors.append("[download.song] quality is missing or empty")
    elif ds["quality"] not in QUALITY_MAP:
        errors.append(f"[download.song] quality must be one of: {', '.join(QUALITY_MAP)}")

    # [download.lyric]
    dly = dl.get("lyric", {})
    for key in ("embed_mode", "save_mode"):
        if not dly.get(key):
            errors.append(f"[download.lyric] {key} is missing or empty")
        elif dly[key] not in ("0", "1", "2"):
            errors.append(f'[download.lyric] {key} must be "0", "1", or "2"')

    # [download.cover]
    dc = dl.get("cover", {})
    for key in ("embed_quality", "save_quality"):
        if not dc.get(key):
            errors.append(f"[download.cover] {key} is missing or empty")
        elif dc[key] not in ("0", "1"):
            errors.append(f'[download.cover] {key} must be "0" or "1"')

    # [cache]
    cc = cfg.get("cache", {})
    if "enabled" not in cc:
        errors.append("[cache] enabled is missing")
    if not cc.get("dir"):
        errors.append("[cache] dir is missing or empty")

    if errors:
        _die(errors)


def _die(errors: list[str]) -> None:
    from function.output import error, console

    console.print("[red]Config validation failed:[/]")
    for e in errors:
        error(e)
    sys.exit(1)


def get_download_dir() -> str:
    path = _get_cfg()["download"].get("dir", "") or ""
    if path:
        path = os.path.expanduser(path)
        if not os.path.isabs(path):
            path = str(VNCMD_HOME / path)
        return path
    return str(Path.home() / "Downloads" / "vncmd-dl")


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


def get_cache_dir() -> str:
    return str(VNCMD_HOME / _get_cfg()["cache"]["dir"])


def is_cache_enabled() -> bool:
    return _get_cfg()["cache"]["enabled"]


def show_config() -> str:
    lines = [
        f"--- Config TOML ({CONFIG_FILE}) ---",
    ]
    lines.append(CONFIG_FILE.read_text(encoding="utf-8").rstrip())
    lines.append("")
    lines.append("--- Cookie ---")
    cookie = get_cookie()
    if cookie:
        lines.append(f"Set ({len(cookie)} chars)  —  {COOKIE_FILE}")
    else:
        lines.append("Not set")
    return "\n".join(lines)
