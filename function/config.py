import os
import sys
import tomllib

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.toml")
COOKIE_FILE = os.path.join(CONFIG_DIR, "cookie")

QUALITY_MAP = {
    "128": 128000,
    "192": 192000,
    "320": 320000,
    "999": 2147483647,
}


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return tomllib.loads(f.read())


def validate_config():
    """Check config file has all required keys. Exit with message if not."""
    errors = []

    if not os.path.exists(CONFIG_FILE):
        _die([f"Config file not found: {CONFIG_FILE}"])

    try:
        cfg = load_config()
    except Exception as e:
        _die([f"Failed to parse {CONFIG_FILE}: {e}"])
        return  # unreachable, but satisfies type checker

    # [download]
    dl = cfg.get("download", {})
    if not dl.get("dir"):
        errors.append("[download] dir is missing or empty")
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
                errors.append('[download] download_content may only contain 0, 1, 2')
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
    path = load_config()["download"]["dir"]
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.join(PROJECT_ROOT, path)
    return path


def get_quality():
    q = load_config()["download"]["quality"]
    return QUALITY_MAP[q]


def get_cookie():
    if not os.path.exists(COOKIE_FILE):
        return ""
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


def get_filename_format():
    return load_config()["download"]["filename_format"]


def get_download_content():
    return load_config()["download"]["download_content"]


def get_embed_lyrics_mode():
    return load_config()["download"]["embed_lyrics_mode"]


def get_save_lyrics_mode():
    return load_config()["download"]["save_lyrics_mode"]


def get_embed_cover_quality():
    return load_config()["download"]["embed_cover_quality"]


def get_save_cover_quality():
    return load_config()["download"]["save_cover_quality"]


def get_cache_dir():
    cfg = load_config()
    relative = cfg["cache"]["dir"]
    return os.path.join(PROJECT_ROOT, relative)


def is_cache_enabled():
    return load_config()["cache"]["enabled"]


def show_config():
    lines = [
        "--- Config TOML ---",
    ]
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        lines.append(f.read().rstrip())
    lines.append("")
    lines.append("--- Cookie ---")
    cookie = get_cookie()
    if cookie:
        lines.append(f"Set ({len(cookie)} chars)  —  {COOKIE_FILE}")
    else:
        lines.append("Not set")
    return "\n".join(lines)
