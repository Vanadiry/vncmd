"""配置键表与模板的一致性"""

import copy
import dataclasses
import re
import tomllib
from pathlib import Path

import pytest

from vncmd.core import schema

模板 = Path("src/vncmd/core/defaults.py").read_text(encoding="utf-8")
完整配置 = tomllib.loads(
    re.search(r'CONFIG_TOML = """\\\n(.*?)\n"""', 模板, re.S).group(1)
)

# 表里十八项及其在配置里的路径
# 前六项为枚举项，后十二项为类型与范围项，分开列便于两组分别取用
枚举六项 = [
    "download.filename_artist",
    "download.content",
    "download.audio.quality",
    "download.lyric.embed_mode",
    "download.lyric.save_mode",
    "download.downloader",
]

其余十二项 = [
    "download.dir",
    "download.concurrency",
    "download.check",
    "download.curl_arg",
    "download.audio.parse_credits",
    "download.lyric.auto_trim",
    "download.lyric.credit_scan_lines",
    "download.cover.embed_compress",
    "download.cover.save_compress",
    "cache.enabled",
    "cache.ttl",
    "display.artist_color",
]

全部 = 枚举六项 + 其余十二项

# 写错值时的报错原文，逐字比对
# 放在模块级常量里，塞进 parametrize 元组会被 ruff format 折开字符串
# 缺键不报，那几条样本不在此列
_逐字样本 = [
    "[download] filename_artist 不合法，应当为 front、back、drop",
    "[download] content 不合法，只能包含 a、l、c，多余字符：x",
    "[download] content 不合法，l 重复，每个字母最多一次",
    # 带实际值那条最容易被误抄，它有一半为逗号分隔的值域
    "[download.audio] quality 不合法，可选 128, 192, 320, max，实际是 '999'",
    "[download.lyric] embed_mode 不合法，应当为 line、block、drop，实际是 '2'",
    "[download.lyric] save_mode 不合法，应当为 line、block、split、drop，实际是 '2'",
    '[download] downloader 不合法，应当为 "builtin" 或 "curl"',
]


# 其余十二项值写错时的报错原文
# 措辞之间的几处不一致为既有行为
# ttl 与 check 不带实际值，dir 报类型名
# parse_credits 与 auto_trim 的缺键与写错值同一句话，统一措辞就是行为变化
_措辞_download_dir = "[download] dir 不合法，应当为字符串，实际是 int"
_措辞_download_concurrency = (
    "[download] concurrency 不合法，应当为 1 至 16 的整数，实际是 99"
)
_措辞_download_check = "[download] check 不合法，应当为 true 或 false"
_措辞_download_curl_arg = "[download] curl_arg 不合法，应当为字符串"
_措辞_download_audio_parse_credits = (
    "[download.audio] parse_credits 不合法，应当为 true 或 false"
)
_措辞_download_lyric_auto_trim = (
    "[download.lyric] auto_trim 不合法，应当为 true 或 false"
)
_措辞_download_lyric_credit_scan_lines = (
    "[download.lyric] credit_scan_lines 不合法，应当为正整数"
)
_措辞_download_cover_embed_compress = (
    "[download.cover] embed_compress 不合法，应当为 true 或 false，实际是 'x'"
)
_措辞_download_cover_save_compress = (
    "[download.cover] save_compress 不合法，应当为 true 或 false，实际是 'x'"
)
_措辞_cache_enabled = "[cache] enabled 不合法，应当为 true 或 false，实际是 'false'"
_措辞_cache_ttl = "[cache] ttl 不合法，应当为非负整数"
_措辞_display_artist_color = "[display] artist_color 不合法，应当为 true 或 false"

_类型样本 = [
    ("download.dir", 123, _措辞_download_dir),
    ("download.concurrency", 99, _措辞_download_concurrency),
    ("download.check", 1, _措辞_download_check),
    ("download.curl_arg", 123, _措辞_download_curl_arg),
    ("download.audio.parse_credits", 1, _措辞_download_audio_parse_credits),
    ("download.lyric.auto_trim", 1, _措辞_download_lyric_auto_trim),
    ("download.lyric.credit_scan_lines", 0, _措辞_download_lyric_credit_scan_lines),
    ("download.cover.embed_compress", "x", _措辞_download_cover_embed_compress),
    ("download.cover.save_compress", "x", _措辞_download_cover_save_compress),
    ("cache.enabled", "false", _措辞_cache_enabled),
    ("cache.ttl", -1, _措辞_cache_ttl),
    ("display.artist_color", 1, _措辞_display_artist_color),
]


def 改配置(路径: str, 值):
    """按点号路径改一份配置，缺的那几层自动建出来"""
    import copy

    cfg = copy.deepcopy(完整配置)
    段 = 路径.split(".")
    游 = cfg
    for 一段 in 段[:-1]:
        游 = 游.setdefault(一段, {})
    if 值 is ...:
        del 游[段[-1]]
    else:
        游[段[-1]] = 值
    return cfg


class Test表的形状:
    def test_path互不重复(self):
        路径 = [s.path for s in schema.SCHEMA]
        assert len(路径) == len(set(路径)), "同一个键进表两次，改一处漏一处"

    def test每项都有kind(self):
        for s in schema.SCHEMA:
            assert s.kind in ("str", "int", "bool", "enum", "content"), s.path

    def test_enum必须有值域(self):
        """没有值域的 enum 等于不校验，会一路放行"""
        for s in schema.SCHEMA:
            if s.kind == "enum":
                assert s.values, f"{s.path} 标成 enum 却没给值域"

    def test_wrong_value_措辞不空(self):
        """这一栏留空时那一项完全不校验，validate 的 if message 判不到就直接放行
        content 为例外，措辞要看实际值
        """
        for s in schema.SCHEMA:
            if s.kind == "content":
                continue
            assert s.wrong_value, f"{s.path} 没写值错时的提示，那一项写错值也不会报错"

    def test_漏填措辞会被validate当场抓住(self):
        """表为手写，漏填一栏不会有动静，validate 自己也要挡一道"""
        空 = dataclasses.replace(schema.SCHEMA[0], wrong_value="")
        原 = schema.SCHEMA
        schema.SCHEMA = (空, *原[1:])
        try:
            错 = schema.validate(完整配置)
            assert 错, "漏填措辞时 validate 一声不吭"
            assert "配置表缺少错误提示" in 错[0]
        finally:
            schema.SCHEMA = 原

    def test_content的措辞不算空(self):
        """content 的 wrong_value 为空，那是有意为之
        多余了哪些字母要看实际值才说得出
        """
        项 = schema.get("download.content")
        assert 项.wrong_value == "", "content 不该有固定措辞"
        assert schema.validate(改配置("download.content", "alx")), (
            "content 那一项要真的校验，只是措辞自己算"
        )

    def test_content不填值域(self):
        """content 的合法值为任意字母组合，填成枚举会让人误以为 alc 与 ca 不同"""
        s = schema.get("download.content")
        assert s.kind == "content"
        assert s.values == (), "content 不该有 values"

    def test每一项都有默认值可回落(self):
        """缺键一律不报错，每一项都得有默认值
        None 与 0 在下游不同，concurrency 拿 None 去 min() 会崩
        """
        for s in schema.SCHEMA:
            assert s.default is not None, f"{s.path} 缺键不报错却没有默认值可回落"

    def test_lookup查得到全部十八项(self):
        for 路径 in 全部:
            assert schema.get(路径) is not None, 路径

    def test_lookup查不到时是None(self):
        assert schema.get("download.不存在的键") is None


def 模板的全部叶子键() -> list[str]:
    """模板里每个叶子键的点号路径，段本身不进表"""
    路径 = []
    for 段, 内容 in 完整配置.items():
        for 键, 值 in 内容.items():
            if isinstance(值, dict):
                路径 += [f"{段}.{键}.{子键}" for 子键 in 值]
            else:
                路径.append(f"{段}.{键}")
    return sorted(路径)


class Test与模板一致:
    """表与 defaults.py 的模板为刻意重复的两份
    这组测试抓漏键、多键、默认值或类型不一致
    """

    # 待进表已空但必须保留，删掉就没人再比对表与模板的键集合
    待进表 = frozenset()

    def _默认值(self, 路径: str):
        段 = 路径.split(".")
        游 = 完整配置
        for 一段 in 段:
            游 = 游[一段]
        return 游

    def test_template的每个叶子键都在表里或白名单里(self):
        """模板加了键却没进表即为漏，白名单以外的不该出现"""
        表里 = {s.path for s in schema.SCHEMA}
        漏掉 = [p for p in 模板的全部叶子键() if p not in 表里 and p not in self.待进表]
        assert not 漏掉, (
            f"模板里有、表里没有：{漏掉}。要么把它加进表，要么明确写进待进表白名单"
        )

    def test表里没有模板中不存在的键(self):
        """表里有而模板里没有，用户按注释找不到这个键"""
        模板键 = set(模板的全部叶子键())
        多出来 = [s.path for s in schema.SCHEMA if s.path not in 模板键]
        assert not 多出来, f"表里有、模板里没有：{多出来}。模板是用户看的那一份"

    def test_白名单与实际缺口一致(self):
        """白名单为还没进表的项，多写会掩盖漏键，少写会误报"""
        表里 = {s.path for s in schema.SCHEMA}
        实际待搬 = [p for p in 模板的全部叶子键() if p not in 表里]
        assert sorted(self.待进表) == sorted(实际待搬), (
            f"实际待搬 {sorted(实际待搬)}，白名单写的是 {sorted(self.待进表)}。"
            f"多写会掩盖漏键，少写会误报"
        )

    @pytest.mark.parametrize("路径", 全部)
    def test默认值对得上(self, 路径):
        assert schema.get(路径).default == self._默认值(路径)

    @pytest.mark.parametrize("路径", 全部)
    def test类型也对得上(self, 路径):
        """模板里为字符串而表里写成整数时，校验会放行非字符串的那种"""
        assert type(schema.get(路径).default) is type(self._默认值(路径))

    @pytest.mark.parametrize("路径", 全部)
    def test合法值过得了(self, 路径):
        """模板里就是合法值，喂进去不该报错"""
        assert schema.validate(完整配置) == []


class Test枚举校验:
    @pytest.mark.parametrize(
        ("路径", "合法"),
        [
            ("download.filename_artist", "back"),
            ("download.audio.quality", "max"),
            ("download.lyric.embed_mode", "line"),
            ("download.lyric.save_mode", "split"),
            ("download.downloader", "curl"),
        ],
    )
    def test合法值放行(self, 路径, 合法):
        """合法值不该报错"""
        assert schema.validate(改配置(路径, 合法)) == [], 路径

    @pytest.mark.parametrize(
        ("路径", "合法", "非法"),
        [
            ("download.filename_artist", "back", "x"),
            ("download.audio.quality", "max", "999"),
            ("download.lyric.embed_mode", "line", "2"),
            ("download.lyric.save_mode", "split", "2"),
            ("download.downloader", "curl", "wget"),
        ],
    )
    def test非法值报错且点名这一项(self, 路径, 合法, 非法):
        错 = schema.validate(改配置(路径, 非法))
        assert len(错) == 1
        assert 路径.split(".")[-1] in 错[0]

    def test带实际值的那几项写出用户填了什么(self):
        """写 quality = 320 与写 “320” 只差一对引号，报错不写实际值会让人以为键名也错"""
        assert "实际是 320" in schema.validate(改配置("download.audio.quality", 320))[0]
        assert (
            "实际是 '999'"
            in schema.validate(改配置("download.audio.quality", "999"))[0]
        )

    def test不带实际值的那几项保持原样(self):
        """filename_artist 与 downloader 的措辞不带实际值，改文案就是改行为"""
        assert (
            "实际是" not in schema.validate(改配置("download.filename_artist", "x"))[0]
        )
        assert "实际是" not in schema.validate(改配置("download.downloader", "wget"))[0]


class Test内容校验:
    """content 的规则为字母组合"""

    @pytest.mark.parametrize("值", ["a", "l", "c", "al", "cl", "alc", "ca", "lca"])
    def test任意组合都算数(self, 值):
        assert schema.validate(改配置("download.content", 值)) == []

    @pytest.mark.parametrize("值", ["x", "alx", "1", "a l"])
    def test多余字符被拦下(self, 值):
        错 = schema.validate(改配置("download.content", 值))
        assert len(错) == 1 and "多余字符" in 错[0]

    @pytest.mark.parametrize("值", ["aa", "all", "cc", "llaa"])
    def test重复字母被拦下(self, 值):
        """每字母最多一次，两个 c 与两个 l 为同一件事"""
        错 = schema.validate(改配置("download.content", 值))
        assert len(错) == 1 and "重复" in 错[0]

    def test空格也算多余字符(self):
        """写成 “alc c” 的人多半以为空格不算内容"""
        错 = schema.validate(改配置("download.content", "alc c"))
        assert len(错) == 1 and "多余字符" in 错[0]

    def test多余字符与重复同时出现时先报多余(self):
        """两个都错时先说打错字母那个，一次只让人改一处"""
        错 = schema.validate(改配置("download.content", "aax"))
        assert "多余字符" in 错[0]

    @pytest.mark.parametrize("值", ["", 12, ["a", "l"], True])
    def test不是字符串的报缺引号(self, 值):
        """漏引号最常见，content = 12 会被 tomllib 读成整数
        set() 一个整数会抛 TypeError
        """
        错 = schema.validate(改配置("download.content", 值))
        assert len(错) == 1 and "带引号" in 错[0]


class Test报错措辞不变:
    """这些字符串为用户看得到的报错，改一个字也为行为变化，逐字钉住"""

    @pytest.mark.parametrize(
        ("路径", "值", "期望"),
        list(
            zip(
                [
                    "download.filename_artist",
                    "download.content",
                    "download.content",
                    "download.audio.quality",
                    "download.lyric.embed_mode",
                    "download.lyric.save_mode",
                    "download.downloader",
                ],
                ["x", "alx", "all", "999", "2", "2", "wget"],
                _逐字样本,
                strict=True,
            )
        ),
    )
    def test逐字不变(self, 路径, 值, 期望):
        assert schema.validate(改配置(路径, 值)) == [期望]

    @pytest.mark.parametrize(
        ("路径", "值", "期望"),
        _类型样本,
    )
    def test类型项的措辞逐字不变(self, 路径, 值, 期望):
        """其余十二项的措辞也逐字钉住"""
        assert schema.validate(改配置(路径, 值)) == [期望], 路径

    def test_十八项都有逐字样本(self):
        """样本要盖住表里每一项；_逐字样本 为纯字符串
        路径要从另一个列表取，合起来盖满 18 项
        """
        有样本的 = {路径 for 路径, _, _ in _类型样本} | {
            "download.filename_artist",
            "download.content",
            "download.audio.quality",
            "download.lyric.embed_mode",
            "download.lyric.save_mode",
            "download.downloader",
        }
        表里 = {s.path for s in schema.SCHEMA}
        assert 有样本的 == 表里, (
            f"没有样本的：{sorted(表里 - 有样本的)}；"
            f"样本里多出来的：{sorted(有样本的 - 表里)}"
        )
        assert len(_类型样本) == 12 and len(_逐字样本) == 7, (
            f"样本条数变了：类型 {len(_类型样本)} 条、枚举 {len(_逐字样本)} 条"
        )


class Test表与getter不各说各话:
    """默认值只有表里那一份为真，硬编码的 fallback 会变成两个来源"""

    def test_getter里没有硬编码的默认值(self):
        """逐个 getter 试在值恰好相同时试不出来，所以查源码"""
        import inspect

        from vncmd.core import config as config_mod

        # 只查取值型 getter，找 .get( 而不找字面量，字面量换个写法就漏
        # .get(key, 默认值) 那种写法一定为两个来源
        for 名 in dir(config_mod):
            if not 名.startswith(("get_", "is_")):
                continue
            函数 = getattr(config_mod, 名)
            if not callable(函数):
                continue
            段源码 = inspect.getsource(函数)
            assert ".get(" not in 段源码, (
                f"{名} 里还有 .get(key, 默认值) 那种写法，"
                f"缺键取的是硬编码的默认值而不是表里的 default"
            )

    def test_取ttl时用的是表里的默认值(self, monkeypatch):
        """把表里的默认值改掉，就能看出 getter 有没有自己的默认值"""
        from vncmd.core import config as config_mod

        改过 = schema.Setting("cache.ttl", "int", minimum=0, default=99)
        monkeypatch.setitem(schema._BY_PATH, "cache.ttl", 改过)
        monkeypatch.setattr(config_mod, "_cfg", {"cache": {"enabled": True}})
        assert config_mod.get_cache_ttl() == 99, "getter 还在用自己的默认值"

    def test_模板与表里的默认值都对得上(self):
        assert 完整配置["cache"]["ttl"] == schema.DEFAULT_CACHE_TTL

    @pytest.mark.parametrize(
        "路径",
        [
            "download.dir",
            "download.concurrency",
            "download.check",
            "download.curl_arg",
            "download.audio.parse_credits",
            "download.lyric.auto_trim",
            "download.lyric.credit_scan_lines",
            "download.cover.embed_compress",
            "download.cover.save_compress",
            "cache.enabled",
            "cache.ttl",
            "display.artist_color",
        ],
    )
    def test_每项的默认值都是可用值(self, 路径):
        """default 为缺键时用户实际拿到的东西，它自己非法就等于不写这一项反而跑不起来"""
        项 = schema.get(路径)
        assert schema.validate_entry(项, 项.default) is None, (
            f"{路径} 的默认值 {项.default!r} 过不了自己的检查"
        )


class Test类型与范围:
    """其余十二项，每一条都对着一个坏处：静默降级、界面看不出来或崩出调用栈"""

    def test_整数不接受布尔(self):
        """isinstance(True, int) 为真，concurrency = true 会静默降成单线程"""
        for 路径 in ("download.concurrency", "cache.ttl"):
            错 = schema.validate(改配置(路径, True))
            assert len(错) == 1, f"{路径} 竟然放过了布尔"
        # concurrency 的措辞带实际值，ttl 的不带，这里只盯都报错
        assert "实际是 True" in schema.validate(改配置("download.concurrency", True))[0]

    def test_整数不接受字符串(self):
        """写成 “4” 会被 tomllib 读成字符串"""
        for 路径 in ("download.concurrency", "cache.ttl"):
            assert len(schema.validate(改配置(路径, "4"))) == 1, 路径
        assert "实际是 '4'" in schema.validate(改配置("download.concurrency", "4"))[0]

    @pytest.mark.parametrize(
        ("路径", "值"),
        [
            ("download.concurrency", 0),
            ("download.concurrency", 17),
            ("download.concurrency", -1),
            ("download.lyric.credit_scan_lines", 0),
            ("download.lyric.credit_scan_lines", -5),
            ("cache.ttl", -1),
        ],
    )
    def test_越界被拦下(self, 路径, 值):
        assert len(schema.validate(改配置(路径, 值))) == 1, 路径

    @pytest.mark.parametrize(
        ("路径", "值"),
        [
            ("download.concurrency", 1),
            ("download.concurrency", 16),
            ("download.lyric.credit_scan_lines", 1),
            ("cache.ttl", 0),
        ],
    )
    def test_边界值算数(self, 路径, 值):
        """1 与 16 都为合法并发数，0 才错，边界要写清开区间还是闭区间"""
        assert schema.validate(改配置(路径, 值)) == [], 路径

    def test_布尔不接受整数(self):
        """enabled = 0 恰好为假值所以蒙得过去，路径从表里推才不会漏项"""
        布尔的 = [s.path for s in schema.SCHEMA if s.kind == "bool"]
        # 钉住数目，表里加布尔项时这条会提醒，报错里会列出名字
        assert len(布尔的) == 7, f"表里的布尔项变了，现在是 {布尔的}"
        for 路径 in 布尔的:
            错 = schema.validate(改配置(路径, 0))
            assert len(错) == 1, f"{路径} 竟然放过了整数"

    def test_布尔不接受带引号的字符串(self):
        """加引号的 “false” 为非空字符串，真值为真，用户以为关了缓存实际照开"""
        错 = schema.validate(改配置("cache.enabled", "false"))
        assert len(错) == 1 and "实际是 'false'" in 错[0]

    def test_字符串只判类型不判非空(self):
        """dir 留空合法，意思为用 ~/Downloads，判非空等于把默认行为判成错"""
        assert schema.validate(改配置("download.dir", "")) == []

    def test_字符串判类型时报类型名不报值(self):
        """路径值打出来为一长串，写 int、list 这种类型名一眼能认"""
        for 值, 名 in [(123, "int"), (["a"], "list")]:
            错 = schema.validate(改配置("download.dir", 值))
            assert 错 == [f"[download] dir 不合法，应当为字符串，实际是 {名}"]

    def test_字符串写成null算缺键(self):
        """toml 的 null 解析为 None，与没写分不开，取到 None 即判缺键"""
        assert schema.validate(改配置("download.dir", None)) == []
        assert schema.value_of(改配置("download.dir", None), "download.dir") == ""

    def test_缺键不报错的那几项确实可省略(self):
        """它们的 getter 取默认值，缺了不该判错"""
        cfg = copy.deepcopy(完整配置)
        del cfg["download"]["curl_arg"]
        del cfg["cache"]["ttl"]
        del cfg["display"]["artist_color"]
        assert schema.validate(cfg) == []

    def test_缺一个键不报错且取到默认值(self):
        """配置文件可以只写想改的键，逐项删才看得见哪一项的回落坏了"""
        for 路径 in 全部:
            cfg = copy.deepcopy(完整配置)
            段 = 路径.split(".")
            游 = cfg
            for 一段 in 段[:-1]:
                游 = 游[一段]
            del 游[段[-1]]
            assert schema.validate(cfg) == [], f"{路径} 缺了却报错"
            assert schema.value_of(cfg, 路径) == schema.get(路径).default, 路径

    def test_只留一个键也不报错(self):
        """整段都空时那一段的项全取默认值，这比逐项删更接近真实用法"""
        for 段 in (
            "download",
            "download.audio",
            "download.lyric",
            "download.cover",
            "cache",
        ):
            cfg = copy.deepcopy(完整配置)
            路径 = 段.split(".")
            游 = cfg
            for 一段 in 路径:
                游 = 游[一段]
            for 键 in list(游):
                del 游[键]
            assert schema.validate(cfg) == [], f"{段} 整段空了却报错"

    def test_段本身不是表时不报键的错(self):
        """段写坏时全报缺失会盖住真正的问题，段检查由 validate_config 负责"""
        for 段, 坏值 in [("download", 5), ("cache", 5), ("download", ["x"])]:
            cfg = copy.deepcopy(完整配置)
            cfg[段] = 坏值
            assert schema.validate(cfg) == [], f"{段} 写成 {坏值!r} 时表里多报了"
            cfg2 = copy.deepcopy(完整配置)
            cfg2["download"] = copy.deepcopy(完整配置["download"])
            cfg2["download"]["audio"] = 5
            assert schema.validate(cfg2) == [], "子段写成标量时表里多报了"


class Test未知键:
    """表里没有的段与键一律报错，静默失效会让用户以为改了而实际没改"""

    def test_完整的配置没有未知键(self):
        assert schema.unknown_keys(完整配置) == []

    def test_多余的键被列出来(self):
        cfg = copy.deepcopy(完整配置)
        cfg["download"]["新加的键"] = 1
        assert schema.unknown_keys(cfg) == ["[download.新加的键]"]

    @pytest.mark.parametrize(
        ("段", "子表", "键"),
        [
            ("download", "audio", "parse_credits_旧名"),
            ("download", "lyric", "auto_trim_旧名"),
            ("download", "cover", "embed_compress_旧名"),
        ],
    )
    def test_子表里的键也查(self, 段, 子表, 键):
        """子表也要查；用真名 audio、lyric、cover，造不存在的段名会报成段不认识"""
        cfg = copy.deepcopy(完整配置)
        cfg[段][子表][键] = 1
        assert schema.unknown_keys(cfg) == [f"[{段}.{子表}.{键}]"]

    def test_顶层与子表的多余键分开列(self):
        """两个都多时要报两条，少报一条用户改完还是跑不起来"""
        cfg = copy.deepcopy(完整配置)
        cfg["download"]["多余的顶层"] = 1
        cfg["download"]["audio"]["多余的歌"] = 2
        assert schema.unknown_keys(cfg) == [
            "[download.audio.多余的歌]",
            "[download.多余的顶层]",
        ], "顶层与子表的多余项都要报出来，少报一个用户改完还是跑不起来"

    def test_多余的整段被列出来(self):
        cfg = copy.deepcopy(完整配置)
        cfg["tracker"] = {"description": "x"}
        # 只报段名不报里面每一项，整段都要删，点名段名就够了
        assert schema.unknown_keys(cfg) == ["[tracker]"]

    def test_子表本身不算多余的键(self):
        """download.audio 为段而非键，当成键报会把用户往错的方向引"""
        报的 = schema.unknown_keys(完整配置)
        for 子表 in ("download.audio", "download.lyric", "download.cover"):
            assert 子表 not in 报的, f"{子表} 被当成多余的键了：{报的}"

    def test_段不是表时不由这里报(self):
        """那是 validate_config 的段检查，两边都报就是同一条错说两遍"""
        cfg = copy.deepcopy(完整配置)
        cfg["download"] = 5
        assert schema.unknown_keys(cfg) == []

    def test_顶层拼错的键要报(self):
        """顶层拼错的标量键要报
        按值类型跳过会让拼错一个字母什么都不发生，--config qualty=max 就会踩到
        """
        cfg = copy.deepcopy(完整配置)
        cfg["qualty"] = "max"
        assert schema.unknown_keys(cfg) == ["[qualty]"]

    def test_顶层拼错的键与已知段写坏能分辨(self):
        """一个要报、一个不报，判据为名字认不认识，不看值类型"""
        cfg = copy.deepcopy(完整配置)
        cfg["qualty"] = "max"
        cfg["download"] = 5
        assert schema.unknown_keys(cfg) == ["[qualty]"]

    @pytest.mark.parametrize("值", ["max", 5, None, ["a", "b"]])
    def test_顶层拼错的键不论什么类型都报(self, 值):
        """不认识的键不管写成什么形式都为多余"""
        cfg = copy.deepcopy(完整配置)
        cfg["qualty"] = 值
        assert schema.unknown_keys(cfg) == ["[qualty]"]


class Test未知键的边界:
    """三个边界：未知嵌套段、空未知段、叶子键的值为表"""

    def test_已知段下的未知嵌套段被列出来(self):
        """段为表而表里没有它的键，那是整段多余而非键多余"""
        cfg = copy.deepcopy(完整配置)
        cfg["download"]["新段"] = {"a": 1}
        assert schema.unknown_keys(cfg) == ["[download.新段]"]

    def test_空的未知段也被列出来(self):
        """多半为加了段却忘了填，空着也要报"""
        cfg = copy.deepcopy(完整配置)
        cfg["空白段"] = {}
        assert schema.unknown_keys(cfg) == ["[空白段]"]

    def test_已知段里既有子表又有多余的键(self):
        """两种都要报，少报一个用户改完还是跑不起来"""
        cfg = copy.deepcopy(完整配置)
        cfg["download"]["多余的顶层"] = 1
        cfg["download"]["又一段"] = {"x": 1}
        assert sorted(schema.unknown_keys(cfg)) == [
            "[download.又一段]",
            "[download.多余的顶层]",
        ]

    def test_已知叶子键的值是表时也往下查(self):
        """这种写法在 TOML 里不存在，不查就等于留了个后门"""
        cfg = copy.deepcopy(完整配置)
        cfg["download"]["filename_artist"] = {"里面的": 1}
        assert schema.unknown_keys(cfg)


class Testvalue_of的边界:
    """取值对缺键的各种形态都要回落到默认值"""

    @pytest.mark.parametrize(
        ("cfg", "说明"),
        [
            ({}, "整段都没有"),
            ({"download": {}}, "段在但里面的键没有"),
            ({"download": {"concurrency": None}}, "键的值是 null"),
        ],
    )
    def test_各种缺法都回落到默认值(self, cfg, 说明):
        assert schema.value_of(cfg, "download.concurrency") == 4, 说明

    def test_键不在表里就原样返回(self):
        """键不在表里时返回 None，不该抛，抛了会打断整批校验"""
        assert schema.value_of({"download": {}}, "download.不在表里") is None


class Test命令行的键值解析:
    """--config 的 key=value 在 CLI 层解析干净，写错键名要立刻有话说"""

    def test_按第一个等号切(self):
        """值里还可能有等号，比如 curl_arg 要带的请求头"""
        assert schema.split_override("curl_arg=-H X=1") == ("curl_arg", "-H X=1")

    def test_没有等号算写法错(self):
        with pytest.raises(ValueError, match="不合法，应当为 key=value"):
            schema.split_override("download.concurrency")

    def test_等号前面空着算写法错(self):
        """--config =5 为漏了键名，不能当成给空键赋值"""
        with pytest.raises(ValueError, match="key 为空"):
            schema.split_override("=5")

    def test_值可以是空串(self):
        """dir 留空合法，意思为用 ~/Downloads"""
        assert schema.split_override("download.dir=") == ("download.dir", "")


class Test按类型转换命令行给的值:
    """CLI 传来的永远为字符串，按表里的 kind 转；不转的话用户写 4 会被报成 “4”"""

    @pytest.mark.parametrize(
        ("raw", "期望"),
        [("true", True), ("false", False)],
    )
    def test_布尔认小写(self, raw, 期望):
        assert schema.coerce("download.check", raw) is 期望

    @pytest.mark.parametrize("raw", ["True", "False", "yes", "1", ""])
    def test_布尔不认别的写法(self, raw):
        """与 TOML 一致，True 在 TOML 里也不合法"""
        with pytest.raises(ValueError, match="不合法，应当为 true 或 false"):
            schema.coerce("download.check", raw)

    def test_整数要转成整数(self):
        assert schema.coerce("download.concurrency", "4") == 4
        assert isinstance(schema.coerce("download.concurrency", "4"), int)

    @pytest.mark.parametrize("raw", ["abc", "4.5", "", "true"])
    def test_整数转不动就报错(self, raw):
        with pytest.raises(ValueError, match="应当为整数"):
            schema.coerce("download.concurrency", raw)

    @pytest.mark.parametrize(
        ("路径", "raw"),
        [
            ("download.audio.quality", "128"),
            ("download.content", "lc"),
            ("download.dir", "/tmp/x"),
            ("download.filename_artist", "front"),
        ],
    )
    def test_字符串原样留着(self, 路径, raw):
        """quality 的值为 “128”、content 的值为 “lc”，转成数字反而错"""
        值 = schema.coerce(路径, raw)
        assert 值 == raw and isinstance(值, str)

    def test_不认识的路径立刻报(self):
        """拼错的键名在这里就该有话说，别等校验那一步"""
        with pytest.raises(ValueError, match=r"配置项 .* 不存在"):
            schema.coerce("download.audio.qualty", "max")
