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

    @pytest.mark.parametrize(
        ("key", "行", "取到"),
        [
            ("embed_compress", "embed_compress = true", True),
            ("save_compress", "save_compress = false", False),
        ],
    )
    def test键整个缺失不报错且取到默认值(self, 配置文件, key, 行, 取到):
        """缺键不再报错 —— 配置可以只写想改的键

        原来这里是拦下的：那时 getter 直接下标取，缺一个键就是 KeyError，
        校验放行等于把崩溃推迟到下载那一刻。现在 getter 按表取，缺了有默认值
        """
        CONFIG_FILE.write_text(CONFIG_TOML.replace(f"{行}\n", ""), encoding="utf-8")
        validate_config(quiet=True)
        取值 = (
            get_embed_cover_compress()
            if key == "embed_compress"
            else get_save_cover_compress()
        )
        assert 取值 is 取到, f"{key} 缺了却取到 {取值!r}"


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

    def test没写不报错且取到默认值(self, 配置文件):
        """content 缺了按 alc 走，也就是全部都要 —— 与不写等价"""
        self._写("")
        CONFIG_FILE.write_text(
            CONFIG_TOML.replace('content = "alc"\n', ""), encoding="utf-8"
        )
        validate_config(quiet=True)
        assert get_download_content() == "alc"

    def test漏了引号写成了数字(self, 配置文件):
        """content = 12 会被 tomllib 读成整数，
        下面 set() 它会抛 TypeError，用户看到的是一整段调用栈"""
        self._写("12")
        with pytest.raises(SystemExit):
            validate_config(quiet=True)


class Test歌词模式的取值:
    """embed_mode 与 save_mode 的第三档不同：drop 是不要译文，split 是分两个文件。

    以前两个键都是 "2"，字面完全一样而意思两样，只能靠文档解释。
    换成不同的词之后，看值就知道是哪一档
    """

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
        """split 只属于存文件，旧数字一律不认，没实现的 only 也不认"""
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
    """filename_artist 的三个值。

    这个键以前叫 filename_format，但分隔符、大小写、扩展名它一个都管不了，
    三个值全由「艺术家在哪」这一个维度决定，名字比内容宽
    """

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
    """几处校验漏掉的写法，每一条都在真跑时炸给用户一整段调用栈

    这些不是假想的边界：缺键、写成整数、忘了引号，都是手改配置时
    最常见的几种错，而校验放行的后果是崩溃推迟到下载那一刻
    """

    @pytest.fixture
    def 配置文件(self):
        原样 = CONFIG_FILE.read_text(encoding="utf-8")
        yield
        CONFIG_FILE.write_text(原样, encoding="utf-8")

    def _写(self, 文本: str) -> None:
        CONFIG_FILE.write_text(文本, encoding="utf-8")

    def test_concurrency缺键不报错且取到默认值(self, 配置文件):
        """原来这里是拦下的：getter 直接下标取，缺了就是 KeyError，
        校验放行等于把崩溃推迟到下载那一刻。现在按表取，缺了是 4
        """
        self._写(CONFIG_TOML.replace("concurrency = 4\n", ""))
        validate_config(quiet=True)
        assert get_concurrency() == 4

    def test_concurrency写成布尔要报错(self, 配置文件):
        """布尔是 int 的子类，不单独拦一路过关；
        min(True, 曲数) 得 1，静默降成单线程还不给任何提示
        """
        self._写(CONFIG_TOML.replace("concurrency = 4", "concurrency = true"))
        with pytest.raises(SystemExit):
            validate_config(quiet=True)

    def test_concurrency越界要报错(self, 配置文件):
        for 值 in ("0", "17", "-1"):
            self._写(CONFIG_TOML.replace("concurrency = 4", f"concurrency = {值}"))
            with pytest.raises(SystemExit):
                validate_config(quiet=True)

    def test_cache的enabled写成字符串要报错(self, 配置文件):
        """最阴的一条：'false' 是非空字符串、真值为真，
        用户以为关了缓存而缓存照开，界面上完全看不出来
        """
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
                "[download] 必须是一段配置，实际是 int",
            ),
            (lambda c: c.__setitem__("cache", 5), "[cache] 必须是一段配置，实际是 int"),
            (
                lambda c: c.__setitem__("display", 5),
                "[display] 必须是一段配置，实际是 int",
            ),
            (
                lambda c: c["download"].update(audio=5),
                "[download.audio] 必须是一段配置，实际是 int",
            ),
            (
                lambda c: c["download"].update(lyric=5),
                "[download.lyric] 必须是一段配置，实际是 int",
            ),
            (
                lambda c: c["download"].update(cover=5),
                "[download.cover] 必须是一段配置，实际是 int",
            ),
        ],
    )
    def test段被写成标量要报错(self, monkeypatch, tmp_path, 改法, 该报的那句, capsys):
        """段写成数字时，下面各处取键会抛 TypeError，
        用户看到的是调用栈而不是哪一段写错了

        这里只换那一段、其余段原样留着。原来是整文件覆盖成一行，
        那样其他段整个消失，段检查按顺序撞上第一个坏的就退出 ——
        五个参数里只有 download 那一个真的走到了自己声称的分支，
        剩下三个子段的检查是死代码，删掉照样全绿

        所以要断言报出来的是哪一句，只 raises(SystemExit) 分不出是哪道拦的
        """
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
        """整段没写与写坏了是两回事

        段检查原来写成 cfg.get(name) 没给默认值，段不写拿到 None，
        isinstance(None, dict) 为假，于是报「必须是一段配置，实际是 NoneType」——
        比缺一个键还严，而第 4 步承诺的就是「配置可以只写想改的键」。
        而 NoneType 是 TOML 里写不出来的东西，看到那句话的人只会去查段里写了什么，
        看不出真正的原因是这一段整个没写
        """
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

        # 缺的那些键要取到表里的默认值，而不是 None
        assert config_mod.is_artist_color() is True
        assert config_mod.get_cache_ttl() == 3

    def test_段是标量时不说成键缺失(self, 配置文件, capsys):
        """报错要指明是段写错了，而不是列一堆「xx 缺失」让人以为是键少了"""
        self._写("download = 5\n")
        with pytest.raises(SystemExit):
            validate_config(quiet=True)
        出错 = capsys.readouterr().err
        assert "必须是一段配置" in 出错
        # 逐项的话一条都不该有：段写坏了，表里那几项取不到值，
        # 那些串一冒出来就说明段检查没排在逐项校验前面
        assert "必须为" not in 出错
        assert "不为" not in 出错
        assert "只能包含" not in 出错


class Test报错带实际值:
    """报错里要写用户实际填了什么

    只说「必须为 128、192、320」的话，写了 320 的人会以为键名也错了。

    断言要写全「实际是」那几个字 —— 只查 320 会被允许值列表里的 320 骗过，
    那种断言加不加实际值都在，等于没测
    """

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
        """enabled 写成带引号的 false 时，报错里要原样写出来，
        用户才看得出自己多打了引号 —— 而那串字符串是真值，缓存会照开"""
        出错 = self._报错("enabled = true", 'enabled = "false"', capsys)
        assert "实际是 'false'" in 出错


class TestCheckConfig收一份现成的配置:
    """校验与读文件分开，为 --config 那条链路留入口

    --config 要在「读文件」与「校验」之间插一步替换，
    所以校验得能直接收一份已经在内存里的 dict。
    """

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
        """不必再自己设 _cfg —— 传进去的那份就是之后 getter 读的那份"""
        import tomllib

        from vncmd.core import config as config_mod
        from vncmd.core.defaults import CONFIG_TOML

        cfg = tomllib.loads(CONFIG_TOML)
        cfg["download"]["concurrency"] = 7
        monkeypatch.setattr(config_mod, "_die", lambda lines: pytest.fail(str(lines)))
        config_mod.check_config(cfg)
        assert config_mod.get_concurrency() == 7

    def test_不读文件(self, monkeypatch):
        """这个入口只管校验，不许偷偷去读磁盘上的那一份

        真去读了的话，测试里传进来的配置就成了摆设
        """
        import tomllib

        from vncmd.core import config as config_mod
        from vncmd.core.defaults import CONFIG_TOML

        monkeypatch.setattr(
            config_mod, "load_config", lambda: pytest.fail("不该读文件")
        )
        monkeypatch.setattr(config_mod, "_die", lambda lines: pytest.fail(str(lines)))
        config_mod.check_config(tomllib.loads(CONFIG_TOML))

    def test_顶层拼错的键在这个入口也报(self, monkeypatch):
        """两个入口走的是同一套检查，不该有哪个漏掉一层"""
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
    """把 --config 的覆盖叠到配置上

    它在校验之前跑，所以写坏的值也能被盖掉 —— 那正是「临时覆盖」的意思
    """

    def test_按点号路径放进去(self):
        from vncmd.core.config import apply_overrides

        cfg = {"download": {"audio": {"quality": "max"}}}
        出 = apply_overrides(cfg, {"download.audio.quality": "128"})
        assert 出["download"]["audio"]["quality"] == "128"

    def test_不改调用方那一份(self):
        """--config 是临时覆盖，把原配置改花了会让「原本是什么」查不清"""
        from vncmd.core.config import apply_overrides

        cfg = {"download": {"audio": {"quality": "max"}}}
        apply_overrides(cfg, {"download.audio.quality": "128"})
        assert cfg["download"]["audio"]["quality"] == "max"

    def test_中间层不存在时建出来(self):
        from vncmd.core.config import apply_overrides

        出 = apply_overrides({}, {"download.audio.quality": "128"})
        assert 出 == {"download": {"audio": {"quality": "128"}}}

    def test_中间层写坏了也能盖(self):
        """cache 写成标量时，往里放一个键把那一层重建出来

        写坏的那一段照样会被校验报出来 —— 这里建新的只是为了让覆盖能落下去
        """
        from vncmd.core.config import apply_overrides

        出 = apply_overrides({"cache": 5}, {"cache.ttl": 7})
        assert 出["cache"] == {"ttl": 7}

    def test_空覆盖原样返回(self):
        from vncmd.core.config import apply_overrides

        cfg = {"a": 1}
        assert apply_overrides(cfg, {}) is cfg


class TestOverrides在校验之前:
    """覆盖要能盖掉一处写坏的值

    顺序是「读 → 覆盖 → 校验」，所以校验看到的是盖过之后的配置。
    反过来先校验的话，配置文件里某个值写坏了就再也救不回来，
    而临时覆盖恰恰应该能救这种情况
    """

    def test_盖掉一处写坏的值(self, monkeypatch, tmp_path):
        import tomllib

        from vncmd.core import config as config_mod
        from vncmd.core.defaults import CONFIG_TOML

        cfg = tomllib.loads(CONFIG_TOML)
        cfg["download"]["audio"]["quality"] = "999"  # 写坏了

        monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "config.toml")
        monkeypatch.setattr(config_mod, "load_config", lambda: cfg)
        monkeypatch.setattr(config_mod, "_die", lambda lines: pytest.fail(str(lines)))
        config_mod.validate_config(
            quiet=True, overrides={"download.audio.quality": "320"}
        )
        assert config_mod.get_quality() == 320000

    def test_不盖的话照样报错(self, monkeypatch, tmp_path):
        """对照：上面那条不是靠「校验变松了」过的"""
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
    """--config 的解析与那两条约束

    解析放在 CLI 那层（`_config_overrides`），因为它在读配置之前跑
    """

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
            ("download.concurrency=abc", "要整数"),
            ("download.check=yes", "只能是 true 或 false"),
            ("download.audio.qualty=max", "没有"),
            ("download.concurrency", "不是 key=value"),
            ("=5", "key 是空的"),
        ],
    )
    def test_写错了就退出(self, 参数, 该说的, capsys):
        from vncmd.cli import _config_overrides

        with pytest.raises(SystemExit) as e:
            _config_overrides([参数])
        assert e.value.code == 2
        # 退出码之外还得有话说，否则脚本只知道「参数不对」不知道哪不对
        assert 该说的 in capsys.readouterr().err, 参数

    def test_没有参数时是空映射(self):
        from vncmd.cli import _config_overrides

        assert _config_overrides([]) == {}

    def test_init拒绝config(self, monkeypatch, capsys):
        """--init 只写默认模板，覆盖没有意义；给一起多半是误会了它的用途

        这一条走真的 main()，因为拒绝发生在 parse_args 之后、
        validate_config 之前 —— 只测解析函数看不到这个约束
        """
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
    """每个短选项都要与它的长选项落到同一个 field

    这一组是照着改完之后的清单写的，防的是「加了 -x 但 dest 与长选项
    不是同一个」这种低级错 —— 那样两个选项各写各的，谁也不知道
    """

    @pytest.mark.parametrize(
        ("argv", "属性", "期望"),
        [
            (["--init"], "init", True),
            (["-i"], "init", True),
            (["search", "x", "--count", "5"], "count", 5),
            (["search", "x", "-c", "5"], "count", 5),
            (["search", "x", "--offset", "2"], "offset", 2),
            (["search", "x", "-o", "2"], "offset", 2),
            # album/playlist 共用 _add_list_args，tracker 自己加了一份 ——
            # 只测 search 的话，那两处的短选项掉了都发现不了
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
        """version 是 argparse 原生的 action，解析时就退出，不能按普通参数取"""
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
        """单字母短选项原生的连写，-dx 就是 -d -x"""
        from vncmd.cli import build_parser

        args = build_parser().parse_args(["tracker", "n", "-dx"])
        assert args.download is True
        assert args.diff is True


class Testtranslate要配合lyric:
    """--translate 只是 --lyric 的修饰

    早先它是静默的：整段嵌在 `if args.lyrics` 里面，不给 --lyric 就什么都不做，
    用户以为翻译会出来。现在单独给直接报错退 2。
    """

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
