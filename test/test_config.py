from pathlib import Path

import pytest

from vncmd.core.config import (
    CONFIG_FILE,
    CONTENT_LETTERS,
    FILENAME_ARTIST,
    LYRIC_MODES,
    QUALITY_MAP,
    get_cache_dir,
    get_concurrency,
    get_cookie,
    get_download_content,
    get_download_dir,
    get_embed_cover_compress,
    get_embed_lyrics_mode,
    get_filename_artist,
    get_quality,
    get_save_cover_compress,
    get_save_lyrics_mode,
    is_cache_enabled,
    load_config,
    validate_config,
)
from vncmd.core.defaults import CONFIG_TOML


class TestConfigFile:
    def test_exists(self):
        assert CONFIG_FILE.exists()

    def test_validate_passes(self):
        validate_config()  # 配置写坏会 sys.exit

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
        """键必须为字符串，整数在 QUALITY_MAP 里查不到，报错也对不上真正的原因"""
        assert list(QUALITY_MAP) == ["128", "192", "320", "max"]
        assert all(isinstance(k, str) for k in QUALITY_MAP)

    def test_max是最高的那一档(self):
        """2^31-1 为不设码率上限的哨兵值，服务端按能给的最高档返回"""
        assert QUALITY_MAP["max"] == 2**31 - 1
        assert QUALITY_MAP["max"] == max(QUALITY_MAP.values())

    def test_filename_artist(self):
        fmt = get_filename_artist()
        assert fmt in FILENAME_ARTIST

    def test_download_content(self):
        content = get_download_content()
        assert content == "alc"
        assert len(set(content)) == len(content), "字母不该重复"
        assert set(content) <= set(CONTENT_LETTERS)

    def test_embed_lyrics_mode(self):
        assert get_embed_lyrics_mode() in LYRIC_MODES["embed_mode"]

    def test_save_lyrics_mode(self):
        assert get_save_lyrics_mode() in LYRIC_MODES["save_mode"]

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
    """embed_compress 与 save_compress 的 false 也为合法值，判定要按 key 是否存在"""

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

    @pytest.mark.parametrize(
        ("key", "行", "取到"),
        [
            ("embed_compress", "embed_compress = true", True),
            ("save_compress", "save_compress = false", False),
        ],
    )
    def test键整个缺失不报错且取到默认值(self, 配置文件, key, 行, 取到):
        """缺键不报错，getter 按表取默认值，配置可以只写想改的键"""
        CONFIG_FILE.write_text(CONFIG_TOML.replace(f"{行}\n", ""), encoding="utf-8")
        validate_config(quiet=True)
        取值 = (
            get_embed_cover_compress()
            if key == "embed_compress"
            else get_save_cover_compress()
        )
        assert 取值 is 取到, f"{key} 缺了却取到 {取值!r}"


class Test下载内容的字母:
    """只查字符是否在表内拦不住重复，content = "00" 会被当成音频"""

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
        """三个字母没有天然顺序，cal 与 alc 为同一个意思"""
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

    def test没写不报错且取到默认值(self, 配置文件):
        """content 缺了按 alc 处理，与不写等价"""
        self._写("")
        CONFIG_FILE.write_text(
            CONFIG_TOML.replace('content = "alc"\n', ""), encoding="utf-8"
        )
        validate_config(quiet=True)
        assert get_download_content() == "alc"

    def test漏了引号写成了数字(self, 配置文件):
        """content = 12 会被读成整数，set() 抛 TypeError 时用户只看到调用栈"""
        self._写("12")
        with pytest.raises(SystemExit):
            validate_config(quiet=True)


class Test歌词模式的取值:
    """第三档 embed_mode 为 drop 表示不要译文，save_mode 为 split 表示分两个文件"""

    @pytest.fixture
    def 配置文件(self):
        原样 = CONFIG_FILE.read_text(encoding="utf-8")
        yield
        CONFIG_FILE.write_text(原样, encoding="utf-8")

    def _写(self, embed: str, save: str) -> None:
        CONFIG_FILE.write_text(
            CONFIG_TOML.replace('embed_mode = "drop"', f"embed_mode = {embed}").replace(
                'save_mode = "line"', f"save_mode = {save}"
            ),
            encoding="utf-8",
        )

    @pytest.mark.parametrize("value", ['"line"', '"block"', '"drop"'])
    def test_embed三个值都算数(self, 配置文件, value):
        self._写(value, '"line"')
        validate_config(quiet=True)

    @pytest.mark.parametrize("value", ['"line"', '"block"', '"split"'])
    def test_save三个值都算数(self, 配置文件, value):
        self._写('"line"', value)
        validate_config(quiet=True)

    @pytest.mark.parametrize(
        ("embed", "save"),
        [
            ('"split"', '"line"'),
            ('"0"', '"line"'),
            ('"line"', '"2"'),
            ('"line"', '"only"'),
        ],
    )
    def test串了档被拦下(self, 配置文件, embed, save):
        """split 只属于存文件，数字取值与未实现的 only 都不认"""
        self._写(embed, save)
        with pytest.raises(SystemExit):
            validate_config(quiet=True)

    @pytest.mark.parametrize(
        ("key", "行", "取到"),
        [
            ("embed_mode", 'embed_mode = "drop"', "drop"),
            ("save_mode", 'save_mode = "line"', "line"),
        ],
    )
    def test键缺失不报错且取到默认值(self, 配置文件, key, 行, 取到):
        CONFIG_FILE.write_text(CONFIG_TOML.replace(f"{行}\n", ""), encoding="utf-8")
        validate_config(quiet=True)
        取值 = (
            get_embed_lyrics_mode() if key == "embed_mode" else get_save_lyrics_mode()
        )
        assert 取值 == 取到


class Test文件名里的艺术家位置:
    """三个值全由“艺术家在哪”决定，分隔符、大小写与扩展名都不归它管"""

    @pytest.fixture
    def 配置文件(self):
        原样 = CONFIG_FILE.read_text(encoding="utf-8")
        yield
        CONFIG_FILE.write_text(原样, encoding="utf-8")

    def _写(self, value: str) -> None:
        CONFIG_FILE.write_text(
            CONFIG_TOML.replace(
                'filename_artist = "back"', f"filename_artist = {value}"
            ),
            encoding="utf-8",
        )

    @pytest.mark.parametrize("value", ['"front"', '"back"', '"drop"'])
    def test三个值都算数(self, 配置文件, value):
        self._写(value)
        validate_config(quiet=True)

    @pytest.mark.parametrize("value", ['"10"', '"01"', '"1"', '"before"', '"10 "'])
    def test旧数字与别的词被拦下(self, 配置文件, value):
        self._写(value)
        with pytest.raises(SystemExit):
            validate_config(quiet=True)

    def test缺失不报错且取到默认值(self, 配置文件):
        CONFIG_FILE.write_text(
            CONFIG_TOML.replace('filename_artist = "back"\n', ""), encoding="utf-8"
        )
        validate_config(quiet=True)
        assert get_filename_artist() == "back"


class Test没拦住的类型:
    """缺键、写成整数、忘了引号这几类手改配置的错，校验放行会把崩溃推迟到下载那一刻"""

    @pytest.fixture
    def 配置文件(self):
        原样 = CONFIG_FILE.read_text(encoding="utf-8")
        yield
        CONFIG_FILE.write_text(原样, encoding="utf-8")

    def _写(self, 文本: str) -> None:
        CONFIG_FILE.write_text(文本, encoding="utf-8")

    def test_concurrency缺键不报错且取到默认值(self, 配置文件):
        """缺键时 getter 按表取默认值 4，不算错误"""
        self._写(CONFIG_TOML.replace("concurrency = 4\n", ""))
        validate_config(quiet=True)
        assert get_concurrency() == 4

    def test_concurrency写成布尔要报错(self, 配置文件):
        """布尔为 int 的子类，min(True, 曲数) 得 1，会静默降成单线程"""
        self._写(CONFIG_TOML.replace("concurrency = 4", "concurrency = true"))
        with pytest.raises(SystemExit):
            validate_config(quiet=True)

    def test_concurrency越界要报错(self, 配置文件):
        for 值 in ("0", "17", "-1"):
            self._写(CONFIG_TOML.replace("concurrency = 4", f"concurrency = {值}"))
            with pytest.raises(SystemExit):
                validate_config(quiet=True)

    def test_cache的enabled写成字符串要报错(self, 配置文件):
        """“false”为真值，缓存照开而界面上看不出来"""
        self._写(CONFIG_TOML.replace("enabled = true", 'enabled = "false"'))
        with pytest.raises(SystemExit):
            validate_config(quiet=True)

    def test_dir写成整数要报错(self, 配置文件):
        self._写(CONFIG_TOML.replace('dir = ""', "dir = 123"))
        with pytest.raises(SystemExit):
            validate_config(quiet=True)

    @pytest.mark.parametrize(
        ("改法", "该报的那句"),
        [
            (
                lambda c: c.__setitem__("download", 5),
                "[download] 配置不合法，应当为配置段，实际是 int",
            ),
            (
                lambda c: c.__setitem__("cache", 5),
                "[cache] 配置不合法，应当为配置段，实际是 int",
            ),
            (
                lambda c: c.__setitem__("display", 5),
                "[display] 配置不合法，应当为配置段，实际是 int",
            ),
            (
                lambda c: c["download"].update(audio=5),
                "[download.audio] 配置不合法，应当为配置段，实际是 int",
            ),
            (
                lambda c: c["download"].update(lyric=5),
                "[download.lyric] 配置不合法，应当为配置段，实际是 int",
            ),
            (
                lambda c: c["download"].update(cover=5),
                "[download.cover] 配置不合法，应当为配置段，实际是 int",
            ),
        ],
    )
    def test段被写成标量要报错(self, monkeypatch, tmp_path, 改法, 该报的那句, capsys):
        """只换目标段，其余段保持原样，否则段检查会先撞上第一个坏段
        断言具体报错句，只 raises(SystemExit) 分不出哪道检查拦下的"""
        import tomllib

        from vncmd.core import config as config_mod
        from vncmd.core.defaults import CONFIG_TOML

        cfg = tomllib.loads(CONFIG_TOML)
        改法(cfg)
        monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "config.toml")
        monkeypatch.setattr(config_mod, "load_config", lambda: cfg)
        monkeypatch.setattr(config_mod, "_cfg", None)
        with pytest.raises(SystemExit):
            config_mod.validate_config(quiet=True)
        assert 该报的那句 in capsys.readouterr().err

    def test_整个段不写不算错(self, monkeypatch, tmp_path):
        """整段没写与写坏不同，段检查要给空默认值，不能报 NoneType"""
        import tomllib

        from vncmd.core import config as config_mod
        from vncmd.core.defaults import CONFIG_TOML

        cfg = tomllib.loads(CONFIG_TOML)
        cfg.pop("cache")
        cfg.pop("display")
        for 子段 in ("audio", "lyric", "cover"):
            cfg["download"].pop(子段)

        monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "config.toml")
        monkeypatch.setattr(config_mod, "load_config", lambda: cfg)
        monkeypatch.setattr(config_mod, "_cfg", None)
        config_mod.validate_config(quiet=True)  # 不该退出

        # 缺的那些键要取到表里的默认值，不能取到 None
        assert config_mod.is_artist_color() is True
        assert config_mod.get_cache_ttl() == 3

    def test_段是标量时不说成键缺失(self, 配置文件, capsys):
        """报错要指明段写错了，列一堆“xx 缺失”会让人以为键少了"""
        self._写("download = 5\n")
        with pytest.raises(SystemExit):
            validate_config(quiet=True)
        出错 = capsys.readouterr().err
        assert "配置不合法，应当为配置段" in 出错
        # 逐项报错一出现就说明段检查没排在逐项校验前面
        assert "concurrency" not in 出错
        assert "content" not in 出错


class Test报错带实际值:
    """断言要带“实际是”，只查值会被允许值列表里的同一个值骗过"""

    @pytest.fixture
    def 配置文件(self):
        原样 = CONFIG_FILE.read_text(encoding="utf-8")
        yield
        CONFIG_FILE.write_text(原样, encoding="utf-8")

    def _报错(self, 改前, 改后, capsys):
        CONFIG_FILE.write_text(CONFIG_TOML.replace(改前, 改后), encoding="utf-8")
        with pytest.raises(SystemExit):
            validate_config(quiet=True)
        return capsys.readouterr().err

    def test_quality报错带出实际值(self, 配置文件, capsys):
        出错 = self._报错('quality = "max"', "quality = 320", capsys)
        assert "实际是 320" in 出错

    def test_歌词模式报错带出实际值(self, 配置文件, capsys):
        出错 = self._报错('embed_mode = "drop"', 'embed_mode = "inline"', capsys)
        assert "实际是 'inline'" in 出错

    def test_concurrency报错带出实际值(self, 配置文件, capsys):
        出错 = self._报错("concurrency = 4", "concurrency = 99", capsys)
        assert "实际是 99" in 出错

    def test_cache布尔报错带出实际值(self, 配置文件, capsys):
        """报错要原样写出带引号的“false”，用户才看得出自己多打了引号"""
        出错 = self._报错("enabled = true", 'enabled = "false"', capsys)
        assert "实际是 'false'" in 出错


class TestCheckConfig收一份现成的配置:
    """校验与读文件分开，--config 需要在两者之间插入覆盖"""

    def test_合法的dict直接过(self, monkeypatch):
        import tomllib

        from vncmd.core import config as config_mod
        from vncmd.core.defaults import CONFIG_TOML

        cfg = tomllib.loads(CONFIG_TOML)
        monkeypatch.setattr(config_mod, "_die", lambda lines: pytest.fail(str(lines)))
        config_mod.check_config(cfg)

    def test_不合法的dict被拦下(self, monkeypatch):
        import tomllib

        from vncmd.core import config as config_mod
        from vncmd.core.defaults import CONFIG_TOML

        cfg = tomllib.loads(CONFIG_TOML)
        cfg["download"]["audio"]["quality"] = "999"
        caught = []
        monkeypatch.setattr(config_mod, "_die", lambda lines: caught.extend(lines))
        config_mod.check_config(cfg)
        assert any("quality" in ln for ln in caught), caught

    def test_校验通过后成为进程内那一份(self, monkeypatch):
        """传入的那份会成为进程内配置，不必再设 _cfg"""
        import tomllib

        from vncmd.core import config as config_mod
        from vncmd.core.defaults import CONFIG_TOML

        cfg = tomllib.loads(CONFIG_TOML)
        cfg["download"]["concurrency"] = 7
        monkeypatch.setattr(config_mod, "_die", lambda lines: pytest.fail(str(lines)))
        config_mod.check_config(cfg)
        assert config_mod.get_concurrency() == 7

    def test_不读文件(self, monkeypatch):
        """这个入口只校验传入的配置，不读磁盘"""
        import tomllib

        from vncmd.core import config as config_mod
        from vncmd.core.defaults import CONFIG_TOML

        monkeypatch.setattr(
            config_mod, "load_config", lambda: pytest.fail("不该读文件")
        )
        monkeypatch.setattr(config_mod, "_die", lambda lines: pytest.fail(str(lines)))
        config_mod.check_config(tomllib.loads(CONFIG_TOML))

    def test_顶层拼错的键在这个入口也报(self, monkeypatch):
        """两个入口共用同一套检查，不能漏掉某一层"""
        import tomllib

        from vncmd.core import config as config_mod
        from vncmd.core.defaults import CONFIG_TOML

        cfg = tomllib.loads(CONFIG_TOML)
        cfg["qualty"] = "max"
        caught = []
        monkeypatch.setattr(config_mod, "_die", lambda lines: caught.extend(lines))
        config_mod.check_config(cfg)
        assert any("qualty" in ln for ln in caught), caught


class TestApplyOverrides:
    """把 --config 的覆盖叠到配置上，在校验之前跑，写坏的值也能盖掉"""

    def test_按点号路径放进去(self):
        from vncmd.core.config import apply_overrides

        cfg = {"download": {"audio": {"quality": "max"}}}
        出 = apply_overrides(cfg, {"download.audio.quality": "128"})
        assert 出["download"]["audio"]["quality"] == "128"

    def test_不改调用方那一份(self):
        """--config 为临时覆盖，改动调用方那份会让原本的值查不清"""
        from vncmd.core.config import apply_overrides

        cfg = {"download": {"audio": {"quality": "max"}}}
        apply_overrides(cfg, {"download.audio.quality": "128"})
        assert cfg["download"]["audio"]["quality"] == "max"

    def test_中间层不存在时建出来(self):
        from vncmd.core.config import apply_overrides

        出 = apply_overrides({}, {"download.audio.quality": "128"})
        assert 出 == {"download": {"audio": {"quality": "128"}}}

    def test_中间层写坏了也能盖(self):
        """cache 写成标量时重建那一层，写坏的值仍会被校验报出"""
        from vncmd.core.config import apply_overrides

        出 = apply_overrides({"cache": 5}, {"cache.ttl": 7})
        assert 出["cache"] == {"ttl": 7}

    def test_空覆盖原样返回(self):
        from vncmd.core.config import apply_overrides

        cfg = {"a": 1}
        assert apply_overrides(cfg, {}) is cfg


class TestOverrides在校验之前:
    """顺序为读、覆盖、校验，先校验的话写坏的值再也救不回来"""

    def test_盖掉一处写坏的值(self, monkeypatch, tmp_path):
        import tomllib

        from vncmd.core import config as config_mod
        from vncmd.core.defaults import CONFIG_TOML

        cfg = tomllib.loads(CONFIG_TOML)
        cfg["download"]["audio"]["quality"] = "999"  # 写坏的值

        monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "config.toml")
        monkeypatch.setattr(config_mod, "load_config", lambda: cfg)
        monkeypatch.setattr(config_mod, "_die", lambda lines: pytest.fail(str(lines)))
        config_mod.validate_config(
            quiet=True, overrides={"download.audio.quality": "320"}
        )
        assert config_mod.get_quality() == 320000

    def test_不盖的话照样报错(self, monkeypatch, tmp_path):
        """对照：不带覆盖时同一个值照样报错"""
        import tomllib

        from vncmd.core import config as config_mod
        from vncmd.core.defaults import CONFIG_TOML

        cfg = tomllib.loads(CONFIG_TOML)
        cfg["download"]["audio"]["quality"] = "999"
        caught = []
        monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "config.toml")
        monkeypatch.setattr(config_mod, "load_config", lambda: cfg)
        monkeypatch.setattr(config_mod, "_die", lambda lines: caught.extend(lines))
        config_mod.validate_config(quiet=True)
        assert any("quality" in ln for ln in caught), caught


class Test命令行的config参数:
    """--config 的解析与约束，解析放在 CLI 层，在读配置之前跑"""

    def test_解析成点号路径到值的映射(self):
        from vncmd.cli import _config_overrides

        assert _config_overrides(["download.audio.quality=128"]) == {
            "download.audio.quality": "128"
        }

    def test_重复传同一个键后者生效(self):
        from vncmd.cli import _config_overrides

        出 = _config_overrides(
            ["download.audio.quality=128", "download.audio.quality=320"]
        )
        assert 出 == {"download.audio.quality": "320"}

    @pytest.mark.parametrize(
        ("参数", "该说的"),
        [
            ("download.concurrency=abc", "不合法，应当为整数"),
            ("download.check=yes", "不合法，应当为 true 或 false"),
            ("download.audio.qualty=max", "不存在"),
            ("download.concurrency", "不合法，应当为 key=value"),
            ("=5", "key 为空"),
        ],
    )
    def test_写错了就退出(self, 参数, 该说的, capsys):
        from vncmd.cli import _config_overrides

        with pytest.raises(SystemExit) as e:
            _config_overrides([参数])
        assert e.value.code == 2
        # 退出码之外还得有话说，否则脚本只知道“参数不对”不知道哪不对
        assert 该说的 in capsys.readouterr().err, 参数

    def test_没有参数时是空映射(self):
        from vncmd.cli import _config_overrides

        assert _config_overrides([]) == {}

    def test_init拒绝config(self, monkeypatch, capsys):
        """--init 只写默认模板，覆盖没有意义，须走 main() 才能看到这条拒绝"""
        import vncmd.cli as vncmd_mod

        跑过 = {"init": False}
        monkeypatch.setattr(
            vncmd_mod, "cmd_init", lambda _a: 跑过.__setitem__("init", True)
        )
        monkeypatch.setattr(vncmd_mod, "acquire_lock", lambda: None)
        monkeypatch.setattr(
            vncmd_mod,
            "validate_config",
            lambda quiet=False, overrides=None: pytest.fail("不该走到校验"),
        )
        monkeypatch.setattr(
            "sys.argv", ["vncmd", "--init", "--config", "download.concurrency=4"]
        )
        with pytest.raises(SystemExit) as e:
            vncmd_mod.main()
        assert e.value.code == 2
        assert "不接受 --config" in capsys.readouterr().err
        assert not 跑过["init"], "拒绝了就该连 init 都不跑"


class Test短选项:
    """每个短选项都要与长选项落到同一个 field，否则两个选项各写各的"""

    @pytest.mark.parametrize(
        ("argv", "属性", "期望"),
        [
            (["--init"], "init", True),
            (["-i"], "init", True),
            (["search", "x", "--count", "5"], "count", 5),
            (["search", "x", "-c", "5"], "count", 5),
            (["search", "x", "--offset", "2"], "offset", 2),
            (["search", "x", "-o", "2"], "offset", 2),
            # album/playlist 共用 _add_list_args，tracker 另加一份，只测 search 发现不了
            (["album", "1", "-c", "5"], "count", 5),
            (["album", "1", "-o", "2"], "offset", 2),
            (["playlist", "1", "-c", "5"], "count", 5),
            (["playlist", "1", "-o", "2"], "offset", 2),
            (["tracker", "n", "-c", "5"], "count", 5),
            (["tracker", "n", "-o", "2"], "offset", 2),
            (["search", "x", "--json"], "json", True),
            (["search", "x", "-j"], "json", True),
            (["song", "1", "-j"], "json", True),
            (["album", "1", "-j"], "json", True),
            (["playlist", "1", "-j"], "json", True),
            (["tracker", "n", "-j"], "json", True),
            (["song", "1", "--lyric"], "lyric", True),
            (["song", "1", "-l"], "lyric", True),
            (["song", "1", "--translate"], "translate", True),
            (["song", "1", "-t"], "translate", True),
            (["tracker", "n", "--auto-accept"], "auto_accept", True),
            (["tracker", "n", "-A"], "auto_accept", True),
            (["tracker", "n", "--force"], "force", True),
            (["tracker", "n", "-F"], "force", True),
            (["tracker", "n", "--diff"], "diff", True),
            (["tracker", "n", "-x"], "diff", True),
        ],
    )
    def test长短选项同义(self, argv, 属性, 期望):
        from vncmd.cli import build_parser

        args = build_parser().parse_args(argv)
        assert getattr(args, 属性) == 期望

    @pytest.mark.parametrize("旗", ["--version", "-v"])
    def test_version两个写法都退出并打印(self, 旗, capsys):
        """version 为 argparse 原生的 action，解析时退出，不能按普通参数取"""
        from vncmd.cli import build_parser

        with pytest.raises(SystemExit) as e:
            build_parser().parse_args([旗])
        assert e.value.code == 0
        assert capsys.readouterr().out.strip()

    def test_config的短选项(self):
        from vncmd.cli import build_parser

        args = build_parser().parse_args(["-C", "download.check=false", "search", "x"])
        assert args.config == ["download.check=false"]

    def test_进度与下载可以连写(self):
        """单字母短选项可连写，-dx 等价于 -d -x"""
        from vncmd.cli import build_parser

        args = build_parser().parse_args(["tracker", "n", "-dx"])
        assert args.download is True
        assert args.diff is True


class Testtranslate要配合lyric:
    """--translate 为 --lyric 的修饰，单独给要报错退 2"""

    def test_单独给要报错(self, monkeypatch, capsys):
        import argparse

        from vncmd import commands

        monkeypatch.setattr(
            commands,
            "get_song_details",
            lambda _i: pytest.fail("参数写错了不该先联网"),
        )
        with pytest.raises(SystemExit) as e:
            commands.cmd_song(
                argparse.Namespace(
                    id=1,
                    json=False,
                    dlink=False,
                    download=False,
                    lyric=False,
                    translate=True,
                )
            )
        assert e.value.code == 2
        assert "--lyric" in capsys.readouterr().err

    def test_配了lyric就不报错(self, monkeypatch, tmp_path):
        import argparse

        from vncmd import commands

        monkeypatch.setattr(
            commands,
            "get_song_details",
            lambda _i: {
                "id": 1,
                "title": "T",
                "artist": "A",
                "album": "B",
                "cover": "",
                "publish_time": "",
            },
        )
        monkeypatch.setattr(commands, "display_song_detail", lambda *_a, **_k: None)
        monkeypatch.setattr(commands, "display_lyrics", lambda *_a, **_k: None)
        monkeypatch.setattr(
            commands,
            "get_lyrics",
            lambda _i: {"lrc": {"lyric": "原文"}, "tlyric": {"lyric": "译文"}},
        )
        commands.cmd_song(
            argparse.Namespace(
                id=1,
                json=False,
                dlink=False,
                download=False,
                lyric=True,
                translate=True,
            )
        )
