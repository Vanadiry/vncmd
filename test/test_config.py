from pathlib import Path
from function.config import (
    validate_config,
    load_config,
    get_download_dir,
    get_quality,
    get_filename_format,
    get_download_content,
    get_embed_lyrics_mode,
    get_save_lyrics_mode,
    get_embed_cover_quality,
    get_save_cover_quality,
    get_cookie,
    is_cache_enabled,
    get_cache_dir,
    CONFIG_FILE,
    QUALITY_MAP,
)


class TestConfigFile:
    def test_exists(self):
        assert CONFIG_FILE.exists()

    def test_validate_passes(self):
        validate_config()  # would sys.exit if broken

    def test_load_returns_dict(self):
        assert isinstance(load_config(), dict)

    def test_download_section_present(self):
        assert "download" in load_config()

    def test_cache_section_present(self):
        assert "cache" in load_config()


class TestGetters:
    def test_download_dir(self):
        assert isinstance(get_download_dir(), str)

    def test_download_dir_exists(self):
        assert Path(get_download_dir()).is_dir()

    def test_quality(self):
        q = get_quality()
        assert isinstance(q, int)
        assert q in QUALITY_MAP.values()

    def test_filename_format(self):
        fmt = get_filename_format()
        assert fmt in ("10", "01", "1")

    def test_download_content(self):
        content = get_download_content()
        assert all(c in "012" for c in content)

    def test_embed_lyrics_mode(self):
        assert get_embed_lyrics_mode() in ("0", "1", "2")

    def test_save_lyrics_mode(self):
        assert get_save_lyrics_mode() in ("0", "1", "2")

    def test_embed_cover_quality(self):
        assert get_embed_cover_quality() in ("0", "1")

    def test_save_cover_quality(self):
        assert get_save_cover_quality() in ("0", "1")

    def test_cache_enabled(self):
        assert isinstance(is_cache_enabled(), bool)

    def test_cache_dir_exists(self):
        assert Path(get_cache_dir()).is_dir()

    def test_cookie(self):
        cookie = get_cookie()
        assert isinstance(cookie, str)
