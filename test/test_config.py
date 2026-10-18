from pathlib import Path

import pytest

from function._defaults import CONFIG_TOML
from function.config import (
    CONFIG_FILE,
    CONTENT_LETTERS,
    QUALITY_MAP,
    get_cache_dir,
    get_cookie,
    get_download_content,
    get_download_dir,
    get_embed_cover_compress,
    get_embed_lyrics_mode,
    get_filename_format,
    get_quality,
    get_save_cover_compress,
    get_save_lyrics_mode,
    is_cache_enabled,
    load_config,
    validate_config,
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

    def test_音质四档的键都是字符串(self):
        """配置里的值全是 TOML 字符串，所以键也必须是字符串。

        写整数会在 QUALITY_MAP 里查不到，配置又会被 not 判断当成缺失，
        报错信息还跟真正的原因对不上"""
        assert list(QUALITY_MAP) == ["128", "192", "320", "max"]
        assert all(isinstance(k, str) for k in QUALITY_MAP)

    def test_max是最高的那一档(self):
        """2147483647 是 2^31-1，一个「不设码率上限」的哨兵值。
        实测发给服务端的 br 与返回的 br 无关，服务端按能给的最高档给"""
        assert QUALITY_MAP["max"] == 2**31 - 1
        assert QUALITY_MAP["max"] == max(QUALITY_MAP.values())

    def test_filename_format(self):
        fmt = get_filename_format()
        assert fmt in ("10", "01", "1")

    def test_download_content(self):
        content = get_download_content()
        assert content == "alc"
        assert len(set(content)) == len(content), "字母不该重复"
        assert set(content) <= set(CONTENT_LETTERS)

    def test_embed_lyrics_mode(self):
        assert get_embed_lyrics_mode() in ("0", "1", "2")

    def test_save_lyrics_mode(self):
        assert get_save_lyrics_mode() in ("0", "1", "2")

    def test_embed_cover_compress(self):
        assert isinstance(get_embed_cover_compress(), bool)

    def test_save_cover_compress(self):
        assert isinstance(get_save_cover_compress(), bool)

    def test_cache_enabled(self):
        assert isinstance(is_cache_enabled(), bool)

    def test_cache_dir_exists(self):
        assert Path(get_cache_dir()).is_dir()

    def test_cookie(self):
        cookie = get_cookie()
        assert isinstance(cookie, str)


class Test封面缩放的布尔校验:
    """embed_compress 与 save_compress 的合法值里有 false。

    校验一开始写的是 `not dc.get(key)`，那种写法把 false 当成没写，
    于是「用原图」那一档根本配不进去 —— 而那恰好是 save_compress 的默认值。
    改成 `key not in dc` 之后两个方向都算数
    """

    @pytest.fixture
    def 配置文件(self):
        原样 = CONFIG_FILE.read_text(encoding="utf-8")
        yield
        CONFIG_FILE.write_text(原样, encoding="utf-8")

    def _写(self, embed: str, save: str) -> None:
        CONFIG_FILE.write_text(
            CONFIG_TOML.replace(
                "embed_compress = true", f"embed_compress = {embed}"
            ).replace("save_compress = false", f"save_compress = {save}"),
            encoding="utf-8",
        )

    @pytest.mark.parametrize(
        ("embed", "save"),
        [
            ("true", "false"),
            ("false", "true"),
            ("false", "false"),
            ("true", "true"),
        ],
    )
    def test两个方向都算数(self, 配置文件, embed, save):
        self._写(embed, save)
        validate_config(quiet=True)

    @pytest.mark.parametrize("bad", ['"1"', '"0"', "1", "0", '"true"'])
    def test非布尔值被拦下(self, 配置文件, bad):
        self._写(bad, "false")
        with pytest.raises(SystemExit):
            validate_config(quiet=True)

    @pytest.mark.parametrize("key", ["embed_compress", "save_compress"])
    def test键整个缺失被拦下(self, 配置文件, key):
        行 = (
            "embed_compress = true"
            if key == "embed_compress"
            else "save_compress = false"
        )
        CONFIG_FILE.write_text(CONFIG_TOML.replace(f"{行}\n", ""), encoding="utf-8")
        with pytest.raises(SystemExit):
            validate_config(quiet=True)


class Test下载内容的字母:
    """content 从 012 换成 alc。

    校验一开始只查「字符在不在 012 里」，重复拦不住 ——
    `content = "00"` 能过校验，含义是「音频」，多半不是用户想写的
    """

    @pytest.fixture
    def 配置文件(self):
        原样 = CONFIG_FILE.read_text(encoding="utf-8")
        yield
        CONFIG_FILE.write_text(原样, encoding="utf-8")

    def _写(self, value: str) -> None:
        CONFIG_FILE.write_text(
            CONFIG_TOML.replace('content = "alc"', f"content = {value}"),
            encoding="utf-8",
        )

    @pytest.mark.parametrize(
        "value",
        ['"alc"', '"cl"', '"al"', '"a"', '"lc"', '"cal"', '"lca"', '"ac"'],
    )
    def test各种组合与顺序都算数(self, 配置文件, value):
        """三个字母没有天然顺序，cal 与 alc 应该是同一个意思"""
        self._写(value)
        validate_config(quiet=True)

    @pytest.mark.parametrize("value", ['"x"', '"alx"', '"0"', '"012"', '"a1"'])
    def test多余字符被拦下(self, 配置文件, value):
        self._写(value)
        with pytest.raises(SystemExit):
            validate_config(quiet=True)

    @pytest.mark.parametrize("value", ['"aa"', '"ll"', '"cc"', '"aalc"'])
    def test重复字母被拦下(self, 配置文件, value):
        self._写(value)
        with pytest.raises(SystemExit):
            validate_config(quiet=True)

    def test没写被拦下(self, 配置文件):
        self._写("")
        CONFIG_FILE.write_text(
            CONFIG_TOML.replace('content = "alc"\n', ""), encoding="utf-8"
        )
        with pytest.raises(SystemExit):
            validate_config(quiet=True)

    def test漏了引号写成了数字(self, 配置文件):
        """content = 12 会被 tomllib 读成整数，
        下面 set() 它会抛 TypeError，用户看到的是一整段调用栈"""
        self._写("12")
        with pytest.raises(SystemExit):
            validate_config(quiet=True)
