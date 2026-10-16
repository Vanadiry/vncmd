import pytest

from function.vocals import COLORS, NAME_TO_COLOR, colorize


def _colors(artist):
    """取出 artist 里所有命中代表色的片段"""
    return [text.strip() for text, color in colorize(artist) if color]


def test_每个色值都对应至少一个名字():
    for color, names in COLORS.items():
        assert names, f"{color} 没有对应名字"


def test_颜色值格式合法():
    for color in COLORS:
        assert len(color) == 7 and color.startswith("#")
        assert all(c in "0123456789abcdefABCDEF" for c in color[1:])


def test_名字不重复():
    names = [n for group in COLORS.values() for n in group]
    assert len(names) == len(set(names))


def test_展开表的色值都在原表里():
    for name, color in NAME_TO_COLOR.items():
        assert name in COLORS[color]


def test_片段拼回原串():
    # 切分只是分段，不能吃掉任何字符
    for artist in (
        "23.exe, 初音ミク, IA",
        "MEIKO，宵崎奏，东云绘名",
        "25時、ナイトコードで。, Azari, 鏡音リン",
        "Eve, 日野森志歩, 初音ミク, 星乃一歌",
    ):
        assert "".join(t for t, _ in colorize(artist)) == artist


def test_单个名字():
    assert _colors("初音ミク") == ["初音ミク"]


def test_逗号分隔():
    assert _colors("23.exe, 初音ミク, IA") == ["初音ミク"]


def test_顿号与全角逗号():
    # 顿号也用来分隔，中文合辑里很常见
    assert _colors("MEIKO，宵崎奏，东云绘名") == ["MEIKO", "宵崎奏", "东云绘名"]


def test_分隔符落在团体名里():
    # 25時、ナイトコードで。 本身带顿号，不能因此把后半截也着色
    assert _colors("25時、ナイトコードで。, Azari, 鏡音リン") == ["鏡音リン"]


def test_同一人多种写法都能命中():
    for name in ("初音ミク", "初音未来"):
        assert _colors(name) == [name]


def test_后缀版本号():
    # 版本号写法很杂，半角全角都有
    for token in ("KAITO V3", "KAITOＶ３", "镜音连V4X", "巡音流歌V4X"):
        assert _colors(token) == [token]


def test_官方后缀():
    assert _colors("洛天依Official") == ["洛天依Official"]


def test_后缀不是版本号时不命中():
    # 墨清弦相关收集站 是网友的合集号，不该按 墨清弦 着色
    assert _colors("墨清弦相关收集站") == []


def test_查不到的名字原样返回():
    assert colorize("椎名もた") == [("椎名もた", None)]


def test_空串():
    assert colorize("") == []


def test_多个已知名字混排():
    artist = "Eve, 日野森志歩, 初音ミク, 星乃一歌, 天馬咲希, 望月穗波"
    assert _colors(artist) == [
        "日野森志歩",
        "初音ミク",
        "星乃一歌",
        "天馬咲希",
        "望月穗波",
    ]


def test_相邻的无色片段会合并():
    # n-buna/ナブNA 被斜杠切成三段，三段都没命中，合并回一段
    segs = colorize("n-buna/ナブナ")
    assert segs == [("n-buna/ナブナ", None)]


def test_分隔符隔开的两段同色不合并():
    # 中间隔着分隔符，拆开渲染才能让分隔符保持原样式
    segs = colorize("A, 初音ミク, 初音未来, B")
    assert "".join(t for t, _ in segs) == "A, 初音ミク, 初音未来, B"
    assert [c for _, c in segs] == [
        None,
        "#39C5BB",
        None,
        "#39C5BB",
        None,
    ]


def test_未命中的片段色值为空():
    for _, color in colorize("Someone, 初音ミク"):
        assert color is None or color == NAME_TO_COLOR["初音ミク"]


def test_斜杠不是分隔符():
    # n-buna/ナブナ 是一个人，不能切开
    assert colorize("n-buna/ナブナ") == [("n-buna/ナブナ", None)]


@pytest.mark.parametrize("name", list(NAME_TO_COLOR))
def test_表里每个名字都能被自己的映射命中(name):
    assert _colors(name) == [name]


class TestKaaiYuki:
    """歌愛ユキ / 歌爱雪

    AHS 的角色，官网只说「红色制服、红色书包」，没有公布形象色，
    色值取那身红的砖红调子。日文原名与中文名都注册，
    接口的艺人字段里「歌愛ユキ」和「歌爱雪」两种写法都出现过。
    """

    def test_四种写法(self):
        for name in ("歌愛ユキ", "歌爱ユキ", "歌愛雪", "歌爱雪"):
            assert _colors(name) == [name], name

    def test_色值(self):
        for name in ("歌愛ユキ", "歌爱ユキ", "歌愛雪", "歌爱雪"):
            assert NAME_TO_COLOR[name] == "#A83E34", name

    def test_四种写法同一个色(self):
        assert (
            len(
                {NAME_TO_COLOR[n] for n in ("歌愛ユキ", "歌爱ユキ", "歌愛雪", "歌爱雪")}
            )
            == 1
        )

    def test_接口里出现过的串(self):
        """这两串是实测抓到的，删了会让真实数据不再着色"""
        assert _colors("稲葉曇, 歌愛ユキ") == ["歌愛ユキ"]
        assert _colors("会飞的四十六条腿青木P, 歌爱雪") == ["歌爱雪"]

    def test_与别人的色不撞(self):
        """撞了的话两个歌手在表里就分不出来了"""
        assert NAME_TO_COLOR["歌愛ユキ"] not in ("#39C5BB", "#C8484E", "#DD4444")

    def test_混排时各自独立(self):
        segs = colorize("いよわ, 初音ミク, 歌愛ユキ")
        assert [c for _, c in segs][-1] == "#A83E34"
        assert "#39C5BB" in [c for _, c in segs]
