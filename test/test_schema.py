"""配置键表

十八项全在表里了 —— 第 1 步搬了六个枚举，第 3 步搬了十二个类型与范围。
`validate_config` 的逐项知识全在这里，那边只剩读文件与段检查。

每一步都是零行为变化，靠 `test_config.py` 里那些既有断言确认 ——
所以这组测试盯的是表自己：形状、取值、报错措辞，以及它与模板的一致性。
"""

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

# 表里的十八项与它们在配置里的路径。
# 前六项是枚举那几个，第 1 步搬的；后十二项是类型与范围，第 3 步搬的。
# 分开列是为了让「枚举那一组」与「非枚举那一组」在测试里能分别取用
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

# 搬进表之前的报错原文，逐字抄下来当基准。
# 放在这里而不是塞进 parametrize 的元组里 —— 那几条超出行宽，
# ruff format 会去折元组的摆放，折长了还会把字符串切开，就不是逐字比对了。
# 常量由格式器不管，它只会原样留着
# 写错值时的报错原文。缺键那几条第 4 步之后不报了，所以不在这里 ——
# 「值错就报」是现在就要守住的，「缺键不报」由另一组测试管
_逐字样本 = [
    "[download] filename_artist 必须为 front、back、drop",
    "[download] content 只能包含 a、l、c，多余的字符：x",
    "[download] content 里 l 重复了，每个字母最多一次",
    # 带实际值那条最容易被误抄，它有一半是逗号分隔的值域
    "[download.audio] quality 必须为以下之一：128, 192, 320, max，实际是 '999'",
    "[download.lyric] embed_mode 必须为 line、block、drop，实际是 '2'",
    "[download.lyric] save_mode 必须为 line、block、split、drop，实际是 '2'",
    '[download] downloader 只能是 "builtin" 或 "curl"',
]


# 第 3 步搬进来的那十二项，值写错时的报错原文。
#
# 措辞单独提成常量：其中几条超出行宽，放进元组里 ruff format 会把字符串
# 切开，切开之后就不是逐字比对了 —— 而逐字正是这里要守的东西
#
# 这十二项的措辞之间本来就有几处不一致，不是笔误：
#   ttl 与 check 不带实际值，而 concurrency 带
#   dir 报类型名（int）而 concurrency 报值（99）
#   parse_credits 与 auto_trim 缺键与写错值是同一句话，
#   而 check 缺键说「缺失或不为布尔值」、写错值说「必须为 true 或 false」
#
# 这些差异以后很可能被人「顺手统一」掉 —— 那是行为变化，
# 用户在界面上看到的就是这一句。逐字钉住
_措辞_download_dir = "[download] dir 必须是字符串，实际是 int"
_措辞_download_concurrency = "[download] concurrency 必须为 1-16 的整数，实际是 99"
_措辞_download_check = "[download] check 必须为 true 或 false"
_措辞_download_curl_arg = "[download] curl_arg 必须是字符串"
_措辞_download_audio_parse_credits = "[download.audio] parse_credits 缺失或不为布尔值"
_措辞_download_lyric_auto_trim = "[download.lyric] auto_trim 缺失或不为布尔值"
_措辞_download_lyric_credit_scan_lines = (
    "[download.lyric] credit_scan_lines 缺失或不为正整数"
)
_措辞_download_cover_embed_compress = (
    "[download.cover] embed_compress 必须为 true 或 false，实际是 'x'"
)
_措辞_download_cover_save_compress = (
    "[download.cover] save_compress 必须为 true 或 false，实际是 'x'"
)
_措辞_cache_enabled = "[cache] enabled 必须为 true 或 false，实际是 'false'"
_措辞_cache_ttl = "[cache] ttl 不为非负整数"
_措辞_display_artist_color = "[display] artist_color 不为布尔值"

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
        """这一栏留空的话那一项就完全不校验

        值写错时校验器返回空串，`validate` 里 `if message:` 判不到，
        于是静默放行 —— 写错值的键看起来像生效了，而它没有。
        content 是唯一例外：它的措辞要看实际值才说得出多余了哪个字母
        """
        for s in schema.SCHEMA:
            if s.kind == "content":
                continue
            assert s.wrong_value, f"{s.path} 没写值错时的提示，那一项写错值也不会报错"

    def test_漏填措辞会被validate当场抓住(self):
        """不只是测试盯着，validate 自己也要挡一道

        表是手写的，漏填一栏不会有任何动静 —— 直到哪天有人加了新键
        却忘了填。那一栏空着的话那一项静默放行，而校验看起来是绿的
        """
        空 = dataclasses.replace(schema.SCHEMA[0], wrong_value="")
        原 = schema.SCHEMA
        schema.SCHEMA = (空, *原[1:])
        try:
            错 = schema.validate(完整配置)
            assert 错, "漏填措辞时 validate 一声不吭"
            assert "没写值错时的提示" in 错[0]
        finally:
            schema.SCHEMA = 原

    def test_content的措辞不算空(self):
        """content 的 wrong_value 是空的，那是设计 ——
        多余了哪些字母、哪个重复了，都得看实际值才说得出

        所以 validate 里那道防线要放过它，放过之后那一项仍然是活的
        """
        项 = schema.get("download.content")
        assert 项.wrong_value == "", "content 不该有固定措辞"
        assert schema.validate(改配置("download.content", "alx")), (
            "content 那一项要真的校验，只是措辞自己算"
        )

    def test_content不填值域(self):
        """content 的合法值是任意字母组合，填成枚举会让人误以为
        alc 与 ca 是两个不同的枚举项"""
        s = schema.get("download.content")
        assert s.kind == "content"
        assert s.values == (), "content 不该有 values"

    def test每一项都有默认值可回落(self):
        """第 4 步之后缺键一律不报错，所以每一项都得有默认值

        getter 缺键时取的是表里的 default，没有就是取到 None ——
        而 None 与 0 在下游不是一回事：concurrency 拿 None 去 min() 会崩，
        ttl 拿 None 去比大小也会崩。这道是「缺键不报错」的前提
        """
        for s in schema.SCHEMA:
            assert s.default is not None, f"{s.path} 缺键不报错却没有默认值可回落"

    def test_lookup查得到全部十八项(self):
        for 路径 in 全部:
            assert schema.get(路径) is not None, 路径

    def test_lookup查不到时是None(self):
        assert schema.get("download.不存在的键") is None


def 模板的全部叶子键() -> list[str]:
    """模板里的每个叶子键，点号路径

    只数叶子：download.audio 是一个段不是一个键，
    它下面的 quality 才是键。段本身不进表 ——
    段不是表时该报的是「[download.audio] 必须是一段配置」，
    那是段级的事，与某个键能填什么无关
    """
    路径 = []
    for 段, 内容 in 完整配置.items():
        for 键, 值 in 内容.items():
            if isinstance(值, dict):
                路径 += [f"{段}.{键}.{子键}" for 子键 in 值]
            else:
                路径.append(f"{段}.{键}")
    return sorted(路径)


class Test与模板一致:
    """表与 defaults.py 的模板是刻意重复的两份，所以它们会漂移。

    这组测试抓三种漂移：
    表里没有模板中的某个键（键漏了，用户填的那个没人管）、
    表里有模板中没有的键（改了代码没改模板，用户看不到这个键）、
    两边默认值或类型不一样（机器读一套、人读另一套）

    `待进表` 是还没搬完的键，它自己也被一条断言盯着 ——
    白名单多写一项会掩盖真的漏键，少写一项会误报。
    十八项全进表之后它就是空的，那条断言仍在：往表里加键而忘了改模板，
    或者模板加了键而忘了改表，都还会被抓住
    """

    # 十八项全部进表之后这个集合空了，但它得留着 ——
    # 删掉它就等于没人再看「表与模板的键集合是否相等」
    待进表 = frozenset()

    def _默认值(self, 路径: str):
        段 = 路径.split(".")
        游 = 完整配置
        for 一段 in 段:
            游 = 游[一段]
        return 游

    def test_template的每个叶子键都在表里或白名单里(self):
        """模板加了键却没进表，那是漏了 —— 白名单以外的全都不该出现在这里"""
        表里 = {s.path for s in schema.SCHEMA}
        漏掉 = [p for p in 模板的全部叶子键() if p not in 表里 and p not in self.待进表]
        assert not 漏掉, (
            f"模板里有、表里没有：{漏掉}。要么把它加进表，要么明确写进待进表白名单"
        )

    def test表里没有模板中不存在的键(self):
        """表里多一个键而模板里没有，用户按注释找不到它

        真要发生的情形是改代码时改了表里的 path，忘了模板那一段
        """
        模板键 = set(模板的全部叶子键())
        多出来 = [s.path for s in schema.SCHEMA if s.path not in 模板键]
        assert not 多出来, f"表里有、模板里没有：{多出来}。模板是用户看的那一份"

    def test_白名单与实际缺口一致(self):
        """白名单是「还没搬的」，不是「允许漏的」

        搬完一项就从白名单里划掉一项，两边自动对上。
        白名单多写一项就会掩盖真的漏键，所以它也得被盯住
        """
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
        """模板里是字符串、表里写成整数，校验会一路放行非字符串的那种"""
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
        """合法值不该报错

        参数里原来还带一个「非法」而这条根本没用它 ——
        带着不用比不带更糟，读的人会以为非法值也在这一条里被测了
        """
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
        """写 quality = 320 与写 "320" 只差一对引号，报错里不写实际值
        就让人以为键名也错了"""
        assert "实际是 320" in schema.validate(改配置("download.audio.quality", 320))[0]
        assert (
            "实际是 '999'"
            in schema.validate(改配置("download.audio.quality", "999"))[0]
        )

    def test不带实际值的那几项保持原样(self):
        """filename_artist 与 downloader 的措辞一直不带实际值，
        改文案就是改行为，那些断言正钉着它"""
        assert (
            "实际是" not in schema.validate(改配置("download.filename_artist", "x"))[0]
        )
        assert "实际是" not in schema.validate(改配置("download.downloader", "wget"))[0]


class Test内容校验:
    """content 的规则不是取值集合，是字母组合"""

    @pytest.mark.parametrize("值", ["a", "l", "c", "al", "cl", "alc", "ca", "lca"])
    def test任意组合都算数(self, 值):
        assert schema.validate(改配置("download.content", 值)) == []

    @pytest.mark.parametrize("值", ["x", "alx", "1", "a l"])
    def test多余字符被拦下(self, 值):
        错 = schema.validate(改配置("download.content", 值))
        assert len(错) == 1 and "多余的字符" in 错[0]

    @pytest.mark.parametrize("值", ["aa", "all", "cc", "llaa"])
    def test重复字母被拦下(self, 值):
        """每字母最多一次，两个 c 与两个 l 说的都是同一件事"""
        错 = schema.validate(改配置("download.content", 值))
        assert len(错) == 1 and "重复了" in 错[0]

    def test空格也算多余字符(self):
        """写成 "alc c" 的人多半以为空格不算内容，恰恰是这一类里最难发现的"""
        错 = schema.validate(改配置("download.content", "alc c"))
        assert len(错) == 1 and "多余的字符" in 错[0]

    def test多余字符与重复同时出现时先报多余(self):
        """两个都错时先说打错字母那个 —— 改对之后重复那个才会露出来，
        一次只让人改一处比较好"""
        错 = schema.validate(改配置("download.content", "aax"))
        assert "多余的字符" in 错[0]

    @pytest.mark.parametrize("值", ["", 12, ["a", "l"], True])
    def test不是字符串的报缺引号(self, 值):
        """漏引号最常见：content = 12 会被 tomllib 读成整数，
        不拦就是 set() 一个整数抛 TypeError"""
        错 = schema.validate(改配置("download.content", 值))
        assert len(错) == 1 and "带引号" in 错[0]


class Test报错措辞不变:
    """与搬进表之前逐字一致。

    这些字符串是既有测试断言着的，改一个字的差别也是行为变化 ——
    用户看报错的地方比看代码的地方多

    下面那几条样本超出行宽，只能让 ruff format 折摆放、不能折字符串本身 ——
    所以它们是模块级的常量，格式器碰不到，字符串始终是一个字不改的整段
    """

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
        """第 3 步搬进来的那十二项，措辞也逐字钉住

        与上面那六项一起，十八项全有了直接样本。之前那十二项只靠
        test_config.py 里的间接断言，而那些断言用的是 `in` ——
        措辞多出几个字照样过
        """
        assert schema.validate(改配置(路径, 值)) == [期望], 路径

    def test_十八项都有逐字样本(self):
        """样本要盖住表里每一项，漏一项那一项就没人盯了

        _逐字样本 是纯字符串，从里面取不出路径，所以靠另一个测试里
        那个列表的路径来数 —— 两个列表合起来要盖满 18 项
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
    """默认值只有表里那一份是真的

    第 4 步之后 getter 一律按 path 取、缺了回落表里的 default，
    自己不再带 fallback。硬编码的 fallback 会有两个来源：
    改一处忘了另一处就变成两个答案，而这种错只在配置真的缺键时才看得见，
    那时用户已经在下载了
    """

    def test_getter里没有硬编码的默认值(self):
        """按 path 取的 getter 一眼能认，硬编码的一眼看不出来

        用源码查而不是逐个 getter 试 —— 逐个试要先把配置改缺，
        而值恰好相同时根本试不出来（改表里的 default 试才试得出来）
        """
        import inspect

        from vncmd.core import config as config_mod

        # 这些是取值型的 getter，一个一个查有没有自己带默认值的写法。
        # 用 .get( 找而不是找字面量 —— 字面量换个写法就漏了，
        # 而 .get(key, 默认值) 那种写法一定是两个来源
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
        """get_cache_ttl 原来写着 get("ttl", DEFAULT_CACHE_TTL)，
        值恰好与表里一样所以看不出问题。把表里的改掉就能露馅"""
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
        """表里的 default 喂给自己的检查器要过得去

        default 是缺键时用户实际会拿到的东西，它自己非法就等于
        「不写这一项反而跑不起来」—— 而第 4 步之后那就是默认行为
        """
        项 = schema.get(路径)
        assert schema.validate_entry(项, 项.default) is None, (
            f"{路径} 的默认值 {项.default!r} 过不了自己的检查"
        )


class Test类型与范围:
    """第 3 步搬进表的那十二项

    每一条都对着一个具体的坏处：静默降级、界面看不出来、
    或者崩给用户一整段调用栈
    """

    def test_整数不接受布尔(self):
        """最容易漏的一条

        Python 里 isinstance(True, int) 为真，所以 concurrency = true
        一路过类型检查，getter 拿到 True，min(True, 曲数) 得 1 ——
        静默降成单线程还不给任何提示。
        写进 kind 的检查器里就是让这道谁都不用记得
        """
        for 路径 in ("download.concurrency", "cache.ttl"):
            错 = schema.validate(改配置(路径, True))
            assert len(错) == 1, f"{路径} 竟然放过了布尔"
        # concurrency 的措辞带实际值，ttl 的不带 —— 那是从前抄来的差别，
        # 这里盯住的是「都报错」而不是「报成什么样」
        assert "实际是 True" in schema.validate(改配置("download.concurrency", True))[0]

    def test_整数不接受字符串(self):
        """写成 "4" 会被 tomllib 读成字符串，没有它就是一个跑不起来的值"""
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
        """1 与 16 都是合法的并发数，0 才是错的 —— 边界要写清是开区间还是闭区间"""
        assert schema.validate(改配置(路径, 值)) == [], 路径

    def test_布尔不接受整数(self):
        """enabled = 0 恰好是假值，取到 0 也对，所以蒙得过去；
        但 check = 0 与 enabled = 0 在别处未必一样，不能靠运气

        路径从表里推，不手写清单 ——
        手写过一次就漏了 parse_credits 与 auto_trim 那两个，
        只取消这两个的 bool 校验全量照样绿
        """
        布尔的 = [s.path for s in schema.SCHEMA if s.kind == "bool"]
        # 数字钉一下是为了「表里加了布尔项时这条会提醒你」，
        # 不是为了规定该有几个 —— 数目不对时下面那句会把名字列出来
        assert len(布尔的) == 7, f"表里的布尔项变了，现在是 {布尔的}"
        for 路径 in 布尔的:
            错 = schema.validate(改配置(路径, 0))
            assert len(错) == 1, f"{路径} 竟然放过了整数"

    def test_布尔不接受带引号的字符串(self):
        """最阴的一条：'false' 是非空字符串、真值为真，
        用户以为关了缓存实际照开，而界面上完全看不出来"""
        错 = schema.validate(改配置("cache.enabled", "false"))
        assert len(错) == 1 and "实际是 'false'" in 错[0]

    def test_字符串只判类型不判非空(self):
        """dir 留空是合法的，意思是「用 ~/Downloads」

        判了非空等于把默认行为判成错 ——
        而模板里它就是空串，写出来就是要能用的
        """
        assert schema.validate(改配置("download.dir", "")) == []

    def test_字符串判类型时报类型名不报值(self):
        """路径类的值打出来是一长串，用户看不出哪里错，
        写 int、list 这种一眼能认的就行"""
        for 值, 名 in [(123, "int"), (["a"], "list")]:
            错 = schema.validate(改配置("download.dir", 值))
            assert 错 == [f"[download] dir 必须是字符串，实际是 {名}"]

    def test_字符串写成null算缺键(self):
        """dir = null 与没写 dir 在用户看来是一回事，都不报

        toml 里的 null 解析出来就是 None，与没写分不开 ——
        所以 _locate 用「取到 None」判缺键是对的，
        而 get_download_dir 那个 `or ""` 也照旧兜住它
        """
        assert schema.validate(改配置("download.dir", None)) == []
        assert schema.value_of(改配置("download.dir", None), "download.dir") == ""

    def test_缺键不报错的那几项确实可省略(self):
        """它们的 getter 本来就取默认值，缺了不该判错"""
        cfg = copy.deepcopy(完整配置)
        del cfg["download"]["curl_arg"]
        del cfg["cache"]["ttl"]
        del cfg["display"]["artist_color"]
        assert schema.validate(cfg) == []

    def test_缺一个键不报错且取到默认值(self):
        """第 4 步之后配置文件可以只写想改的键

        逐项删而不是一次删光：一次删光只能看到「总共报了几条」，
        某一项的回落坏了照样数得出来。逐项删才看得见是哪一项
        """
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
        """整段都空了的情形：表里那一段的项全都取默认值

        这比逐项删更接近真实用法 —— 用户从一个最小配置开始改
        """
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
        """段写坏与键没写是两回事

        download = 5 时表里那几项一个都取不到值，全报「xx 缺失」
        等于把真正的问题盖住 —— 用户会照着补键，补完还是不行。

        这一段由 validate_config 的段检查报，那里能给出
        「[download] 必须是一段配置，实际是 int」那句
        """
        for 段, 坏值 in [("download", 5), ("cache", 5), ("download", ["x"])]:
            cfg = copy.deepcopy(完整配置)
            cfg[段] = 坏值
            assert schema.validate(cfg) == [], f"{段} 写成 {坏值!r} 时表里多报了"
            cfg2 = copy.deepcopy(完整配置)
            cfg2["download"] = copy.deepcopy(完整配置["download"])
            cfg2["download"]["audio"] = 5
            assert schema.validate(cfg2) == [], "子段写成标量时表里多报了"


class Test未知键:
    """表里没有的段与键一律报错

    静默放过的那几年里，改名之后照抄了新键名却忘了删旧的，
    那种配置静默失效 —— 用户以为改了而实际没改，比报一个错难查得多
    """

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
        """键在子表里也要查 —— 漏了子表就等于只查了顶层那一层

        子表用的是真名（audio、lyric、cover），造一个不存在的段名的话
        报出来的会是「这个段不认识」，那与本条要验的不是一回事
        """
        cfg = copy.deepcopy(完整配置)
        cfg[段][子表][键] = 1
        assert schema.unknown_keys(cfg) == [f"[{段}.{子表}.{键}]"]

    def test_顶层与子表的多余键分开列(self):
        """两个都多的时候要报两条 —— 少报一条用户改完还是跑不起来"""
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
        # 只报段名不报里面每一项 —— 整段都要删，点名段名就够了
        assert schema.unknown_keys(cfg) == ["[tracker]"]

    def test_子表本身不算多余的键(self):
        """download.audio 是一个段不是键，
        把它当成键报「不认识」就等于把用户往错的方向引

        只查这几个子表名 —— 直接断言整个配置没有未知项的话，
        那与 test_完整的配置没有未知键 一字不差，白写一条
        """
        报的 = schema.unknown_keys(完整配置)
        for 子表 in ("download.audio", "download.lyric", "download.cover"):
            assert 子表 not in 报的, f"{子表} 被当成多余的键了：{报的}"

    def test_段不是表时不由这里报(self):
        """那是 validate_config 的「必须是一段配置」那一句的事，
        两边都报就是同一条错说两遍"""
        cfg = copy.deepcopy(完整配置)
        cfg["download"] = 5
        assert schema.unknown_keys(cfg) == []

    def test_顶层拼错的键要报(self):
        """顶层写个表里没有的键，名字不认识就该报

        这条曾经是静默的：原来的代码先判「值是不是表」，不是就跳过，
        而那句跳过是为「已知段写成标量」写的。于是顶层拼错的标量
        一起被跳过 —— 配置里写错一个字母，什么都不发生。
        --config 让这个洞变得极易触发：`--config qualty=max` 就是它
        """
        cfg = copy.deepcopy(完整配置)
        cfg["qualty"] = "max"
        assert schema.unknown_keys(cfg) == ["[qualty]"]

    def test_顶层拼错的键与已知段写坏能分辨(self):
        """一个要报、一个不报，判据是名字认不认识而不是值是什么类型"""
        cfg = copy.deepcopy(完整配置)
        cfg["qualty"] = "max"
        cfg["download"] = 5
        assert schema.unknown_keys(cfg) == ["[qualty]"]

    @pytest.mark.parametrize("值", ["max", 5, None, ["a", "b"]])
    def test_顶层拼错的键不论什么类型都报(self, 值):
        """不认识的键不管写成什么形式都是多余的"""
        cfg = copy.deepcopy(完整配置)
        cfg["qualty"] = 值
        assert schema.unknown_keys(cfg) == ["[qualty]"]


class Test未知键的边界:
    """三个边界之前没有任何测试盯着

    实测把对应那行改掉，全量 1403 条照样全绿
    """

    def test_已知段下的未知嵌套段被列出来(self):
        """download 下面多一段不认识的东西，要报出来

        段是表而表里没有它的键，那是「这一整段多余」而不是「键多余」
        """
        cfg = copy.deepcopy(完整配置)
        cfg["download"]["新段"] = {"a": 1}
        assert schema.unknown_keys(cfg) == ["[download.新段]"]

    def test_空的未知段也被列出来(self):
        """多半是加了段忘了填，空着也要报"""
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
        """那种写法 TOML 里不存在，但要是不查就等于留了个后门"""
        cfg = copy.deepcopy(完整配置)
        cfg["download"]["filename_artist"] = {"里面的": 1}
        assert schema.unknown_keys(cfg)


class Testvalue_of的边界:
    """取值那一步对缺键的各种形态都要有交代"""

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
        """不在表里是搬表过程中的状态，不该抛 —— 抛了会打断整批校验

        取到 None 是应有之义，而它与「取到默认值 4」下游用法不同，
        所以别拿它当正常路径用
        """
        assert schema.value_of({"download": {}}, "download.不在表里") is None


class Test命令行的键值解析:
    """--config 传进来的 key=value 要在 CLI 那层就解析干净

    路径与类型都在这层查掉：写错一个键名要立刻有话说，
    流到校验那一步只会报成笼统的「未知键」，而且是在读了配置之后
    """

    def test_按第一个等号切(self):
        """值里还可能有等号，比如 curl_arg 要带的请求头"""
        assert schema.split_override("curl_arg=-H X=1") == ("curl_arg", "-H X=1")

    def test_没有等号算写法错(self):
        with pytest.raises(ValueError, match="不是 key=value"):
            schema.split_override("download.concurrency")

    def test_等号前面空着算写法错(self):
        """--config =5 是漏了键名，不能当成给空键赋值"""
        with pytest.raises(ValueError, match="key 是空的"):
            schema.split_override("=5")

    def test_值可以是空串(self):
        """dir 留空是合法的，意思是「用 ~/Downloads」"""
        assert schema.split_override("download.dir=") == ("download.dir", "")


class Test按类型转换命令行给的值:
    """CLI 传来的永远是字符串，按表里的 kind 转

    不转的话 `--config download.concurrency=4` 会让校验说
    「必须为 1-16 的整数，实际是 '4'」—— 用户明明写的是 4
    """

    @pytest.mark.parametrize(
        ("raw", "期望"),
        [("true", True), ("false", False)],
    )
    def test_布尔认小写(self, raw, 期望):
        assert schema.coerce("download.check", raw) is 期望

    @pytest.mark.parametrize("raw", ["True", "False", "yes", "1", ""])
    def test_布尔不认别的写法(self, raw):
        """与 TOML 一致：True 在那里本来就不是合法值，照抄过去也过不了校验"""
        with pytest.raises(ValueError, match="只能是 true 或 false"):
            schema.coerce("download.check", raw)

    def test_整数要转成整数(self):
        assert schema.coerce("download.concurrency", "4") == 4
        assert isinstance(schema.coerce("download.concurrency", "4"), int)

    @pytest.mark.parametrize("raw", ["abc", "4.5", "", "true"])
    def test_整数转不动就报错(self, raw):
        with pytest.raises(ValueError, match="要整数"):
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
        """quality 的值是 "128"、content 是 "lc"，转成数字反而错"""
        值 = schema.coerce(路径, raw)
        assert 值 == raw and isinstance(值, str)

    def test_不认识的路径立刻报(self):
        """拼错的键名在这里就该有话说，别等校验那一步"""
        with pytest.raises(ValueError, match=r"没有 .* 这一项"):
            schema.coerce("download.audio.qualty", "max")
