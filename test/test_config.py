import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Config module tests."""
import os
from test._runner import check, section, summary, reset

reset()
TMP = __import__("test._runner", fromlist=["tmp_dir"]).tmp_dir()

section("Config")

from function.config import (
    validate_config, load_config, get_download_dir, get_quality,
    get_filename_format, get_download_content,
    get_embed_lyrics_mode, get_save_lyrics_mode,
    get_embed_cover_quality, get_save_cover_quality,
    get_cookie, is_cache_enabled, get_cache_dir,
    CONFIG_FILE, QUALITY_MAP,
)

check("config.toml exists", os.path.exists(CONFIG_FILE))
validate_config()  # would sys.exit if broken
check("validate_config() passes", True)

cfg = load_config()
check("load_config returns dict", isinstance(cfg, dict))
check("[download] section present", "download" in cfg)
check("[cache] section present", "cache" in cfg)
check("get_download_dir() returns string", isinstance(get_download_dir(), str))
check("download dir exists", os.path.isdir(get_download_dir()))
q = get_quality()
check("get_quality() returns int", isinstance(q, int))
check("quality in valid range", q in QUALITY_MAP.values())
fmt = get_filename_format()
check(f"filename_format='{fmt}' valid", fmt in ("10", "01", "1"))
content = get_download_content()
check(f"download_content='{content}' valid", all(c in "012" for c in content))
em = get_embed_lyrics_mode()
check(f"embed_lyrics_mode='{em}' valid", em in ("0", "1", "2"))
sm = get_save_lyrics_mode()
check(f"save_lyrics_mode='{sm}' valid", sm in ("0", "1", "2"))
eq = get_embed_cover_quality()
check(f"embed_cover_quality='{eq}' valid", eq in ("0", "1"))
sq = get_save_cover_quality()
check(f"save_cover_quality='{sq}' valid", sq in ("0", "1"))
check("is_cache_enabled() bool", isinstance(is_cache_enabled(), bool))
check("get_cache_dir() exists", os.path.isdir(get_cache_dir()))
cookie = get_cookie()
check(f"get_cookie() {'set' if cookie else 'not set'}", isinstance(cookie, str))

failed = summary()
if __name__ == "__main__":
    raise SystemExit(failed)
