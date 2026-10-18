"""配置键表

这张表现在只装了 6 个枚举型键，剩下的按 TODO2 第 3 步起逐项进表。
每一步都该是零行为变化，靠 `test_config.py` 里那些既有断言确认 ——
所以这里只盯表自己：形状、取值、以及它与手写校验的一致性。
"""

import re
import tomllib
from pathlib import Path

import pytest

from vncmd.core import schema

模板 = Path("src/vncmd/core/defaults.py").read_text(encoding="utf-8")
完整配置 = tomllib.loads(
    re.search(r'CONFIG_TOML = """\\\n(.*?)\n"""', 模板, re.S).group(1)
)

# 表里的六项与它们在配置里的路径
六个 = [
    "download.filename_artist",
    "download.content",
    "download.audio.quality",
    "download.lyric.embed_mode",
    "download.lyric.save_mode",
    "download.downloader",
]

# 搬进表之前的报错原文，逐字抄下来当基准。
# 放在这里而不是塞进 parametrize 的元组里 —— 那几条超出行宽，
# ruff format 会去折元组的摆放，折长了还会把字符串切开，就不是逐字比对了。
# 常量由格式器不管，它只会原样留着
_逐字样本 = [
    "[download] filename_artist 缺失或为空",
    "[download] filename_artist 必须为 front、back、drop",
    "[download] content 缺失或为空，且必须是带引号的字符串",
    "[download] content 只能包含 a、l、c，多余的字符：x",
    "[download] content 里 l 重复了，每个字母最多一次",
    "[download.audio] quality 缺失或为空",
    # 带实际值那条最容易被误抄，它有一半是逗号分隔的值域
    "[download.audio] quality 必须为以下之一：128, 192, 320, max，实际是 '999'",
    "[download.lyric] embed_mode 缺失",
    "[download.lyric] embed_mode 必须为 line、block、drop，实际是 '2'",
    "[download.lyric] save_mode 缺失",
    "[download.lyric] save_mode 必须为 line、block、split、drop，实际是 '2'",
    '[download] downloader 只能是 "builtin" 或 "curl"',
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
                assert s.bad, f"{s.path} 标成 enum 却没给错值时的措辞"

    def test_content不填值域(self):
        """content 的合法值是任意字母组合，填成枚举会让人误以为
        alc 与 ca 是两个不同的枚举项"""
        s = schema.get("download.content")
        assert s.kind == "content"
        assert s.values == (), "content 不该有 values"

    def test缺键措辞不空(self):
        """第 4 步之前缺键要报错，措辞空着就报不出像样的消息"""
        for s in schema.SCHEMA:
            assert s.miss, f"{s.path} 没写缺键时的措辞"

    def test_lookup查得到这六项(self):
        for 路径 in 六个:
            assert schema.get(路径) is not None, 路径

    def test_lookup查不到时是None(self):
        assert schema.get("download.dir") is None
        assert schema.get("不存在的键") is None


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
    表里没有模板中的某个键（键漏了，getter 会按默认值走而用户填的没人管）、
    表里有模板中没有的键（改了代码没改模板，用户看不到这个键）、
    两边默认值不一样（机器读一套、人读另一套）

    前两种现在还不可能发生 —— 表里只有六项，模板里有 18 个。
    所以用「剩余待进表」的白名单记着，不是假装它们已经对上了。
    白名单里的键搬完一项就少一项，空了就可以删掉这个检查
    """

    待进表 = frozenset(
        {
            "cache.enabled",
            "cache.ttl",
            "display.artist_color",
            "download.audio.parse_credits",
            "download.check",
            "download.concurrency",
            "download.cover.embed_compress",
            "download.cover.save_compress",
            "download.curl_arg",
            "download.dir",
            "download.lyric.auto_trim",
            "download.lyric.credit_scan_lines",
        }
    )

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

    @pytest.mark.parametrize("路径", 六个)
    def test默认值对得上(self, 路径):
        assert schema.get(路径).default == self._默认值(路径)

    @pytest.mark.parametrize("路径", 六个)
    def test类型也对得上(self, 路径):
        """模板里是字符串、表里写成整数，校验会一路放行非字符串的那种"""
        assert type(schema.get(路径).default) is type(self._默认值(路径))

    @pytest.mark.parametrize("路径", 六个)
    def test合法值过得了(self, 路径):
        """模板里就是合法值，喂进去不该报错"""
        assert schema.validate(完整配置) == []


class Test枚举校验:
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
    def test合法值放行(self, 路径, 合法, 非法):
        assert schema.validate(改配置(路径, 合法)) == []

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

    @pytest.mark.parametrize("值", ["", 12, None, ["a", "l"], True])
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
                    "download.filename_artist",
                    "download.content",
                    "download.content",
                    "download.content",
                    "download.audio.quality",
                    "download.audio.quality",
                    "download.lyric.embed_mode",
                    "download.lyric.embed_mode",
                    "download.lyric.save_mode",
                    "download.lyric.save_mode",
                    "download.downloader",
                ],
                [
                    ...,
                    "x",
                    ...,
                    "alx",
                    "all",
                    ...,
                    "999",
                    ...,
                    "2",
                    ...,
                    "2",
                    "wget",
                ],
                _逐字样本,
                strict=True,
            )
        ),
    )
    def test逐字不变(self, 路径, 值, 期望):
        assert schema.validate(改配置(路径, 值)) == [期望]
