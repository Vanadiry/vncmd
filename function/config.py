import os
import sys
import tomllib
from pathlib import Path

from function._defaults import CONFIG_TOML

VNEMD_HOME = Path(os.environ.get("VNEMD_HOME", "~/.vnemd")).expanduser()
CONFIG_FILE = VNEMD_HOME / "config.toml"
COOKIE_FILE = VNEMD_HOME / "cookie"

QUALITY_MAP = {
    "128": 128000,
    "192": 192000,
    "320": 320000,
    "999": 2147483647,
}

_cfg: dict | None = None


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return tomllib.loads(f.read())


def _get_cfg():
    global _cfg
    if _cfg is None:
        _cfg = load_config()
    return _cfg


def validate_config():
    """Check config file has all required keys.  Auto-creates on first run."""
    if not CONFIG_FILE.exists():
        VNEMD_HOME.mkdir(parents=True, exist_ok=True)
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
    if not dl.get("quality"):
        errors.append("[download] quality is missing or empty")
    elif dl["quality"] not in QUALITY_MAP:
        errors.append(f"[download] quality must be one of: {', '.join(QUALITY_MAP)}")

    if not dl.get("filename_format"):
        errors.append("[download] filename_format is missing or empty")
    elif dl["filename_format"] not in ("10", "01", "1"):
        errors.append('[download] filename_format must be "10", "01", or "1"')

    if not dl.get("download_content"):
        errors.append("[download] download_content is missing or empty")
    else:
        for c in dl["download_content"]:
            if c not in "012":
                errors.append("[download] download_content may only contain 0, 1, 2")
                break

    if not dl.get("embed_lyrics_mode"):
        errors.append("[download] embed_lyrics_mode is missing or empty")
    elif dl["embed_lyrics_mode"] not in ("0", "1", "2"):
        errors.append('[download] embed_lyrics_mode must be "0", "1", or "2"')

    if not dl.get("save_lyrics_mode"):
        errors.append("[download] save_lyrics_mode is missing or empty")
    elif dl["save_lyrics_mode"] not in ("0", "1", "2"):
        errors.append('[download] save_lyrics_mode must be "0", "1", or "2"')

    for cover_key in ("embed_cover_quality", "save_cover_quality"):
        if not dl.get(cover_key):
            errors.append(f"[download] {cover_key} is missing or empty")
        elif dl[cover_key] not in ("0", "1"):
            errors.append(f'[download] {cover_key} must be "0" or "1"')

    # [cache]
    cc = cfg.get("cache", {})
    if "enabled" not in cc:
        errors.append("[cache] enabled is missing")
    if not cc.get("dir"):
        errors.append("[cache] dir is missing or empty")

    if errors:
        _die(errors)


def _die(errors):
    from rich.console import Console

    c = Console(stderr=True)
    c.print("[red]Config validation failed:[/]")
    for e in errors:
        c.print(f"  [red]✗[/] {e}")
    sys.exit(1)


def get_download_dir():
    path = _get_cfg()["download"].get("dir", "") or ""
    if path:
        path = os.path.expanduser(path)
        if not os.path.isabs(path):
            path = str(VNEMD_HOME / path)
        return path
    return str(Path.home() / "Downloads")


def get_quality():
    return QUALITY_MAP[_get_cfg()["download"]["quality"]]


def get_cookie():
    if not COOKIE_FILE.exists():
        return ""
    return COOKIE_FILE.read_text(encoding="utf-8").strip()


def get_filename_format():
    return _get_cfg()["download"]["filename_format"]


def get_download_content():
    return _get_cfg()["download"]["download_content"]


def get_embed_lyrics_mode():
    return _get_cfg()["download"]["embed_lyrics_mode"]


def get_save_lyrics_mode():
    return _get_cfg()["download"]["save_lyrics_mode"]


def get_embed_cover_quality():
    return _get_cfg()["download"]["embed_cover_quality"]


def get_save_cover_quality():
    return _get_cfg()["download"]["save_cover_quality"]


def get_cache_dir():
    return str(VNEMD_HOME / _get_cfg()["cache"]["dir"])


def is_cache_enabled():
    return _get_cfg()["cache"]["enabled"]


def show_config():
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
