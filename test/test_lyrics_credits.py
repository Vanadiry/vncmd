"""credit 行的识别与裁剪

三个函数里没有测试，所以中文歌词里的全角冒号被漏掉了一直没被发现：
`作曲：XX` 不被当成 credit，裁不掉、作曲人也抽不出来。
"""

import pytest

from function.lyrics import (
    _CREDIT_RE_TEMPLATE,
    extract_credits,
    is_pure_credits,
    trim_lyrics,
)

ROLES = ["作词", "编曲", "制作人", "混音", "母带制作", "作曲"]


def lrc(*lines):
    return "\n".join(lines) + "\n"


# 实测（2026-10-17，用户真实曲库 528 首）被漏掉的那几行
REAL = [
    "[00:08.75]作曲：残月",
    "[00:01.30]编曲：emon(Tes.)",
    "[00:00.94]编曲：カワイヒデヒロ(fox capture plan)",
    "[00:09.14]混音：Kolaa、Hanser",
    "[00:03.578]编曲：ilem",
]


class Test冒号:
    @pytest.mark.parametrize("colon", [":", "："])
    def test_两种冒号都认(self, colon):
        """只认半角会让全角那批全被漏掉 —— 实测 11 行、8 个文件"""
        assert re_match(f"[00:08.75]作曲{colon}残月")

    @pytest.mark.parametrize("colon", [":", "："])
    def test_冒号前后有空格也认(self, colon):
        """实测「作词 : 赵武」这种带空格的写法也在库里"""
        assert re_match(f"[00:01.00] 作词 {colon} 赵武", "作词")

    @pytest.mark.parametrize("line", REAL)
    def test_实测那几行改动后不再被漏(self, line):
        """它们该被 trim_lyrics 认出来裁掉，而不是留在歌词里

        extract_credits 只抽作曲，拿编曲那几行去问作曲当然问不出东西 ——
        那是另一个函数的事，这里测的是「认得出这是 credit 行」。
        """
        role = line.split("]")[1].strip().split("：")[0].split(":")[0].strip()
        out, _ = trim_lyrics(lrc(line, "[00:20.00]歌词"), 10, prefixes=[role])
        assert line.split("]", 1)[1].strip() not in out, f"没裁掉：{line}"
        assert "[00:20.00]歌词" in out


def re_match(line, role="作曲"):
    import re

    return re.compile(_CREDIT_RE_TEMPLATE % re.escape(role)).match(line) is not None


class Test抽作曲人:
    def test_半角冒号(self):
        got, _ = extract_credits(lrc("[00:01.00]作曲:大瀧詠一"), 10, ["作曲"])
        assert got == "大瀧詠一"

    def test_全角冒号(self):
        got, _ = extract_credits(lrc("[00:01.00]作曲：大瀧詠一"), 10, ["作曲"])
        assert got == "大瀧詠一"

    def test_没有作曲行就返回None(self):
        """NEVER 那首只有编曲，抽不到作曲就该是 None

        改动前它会抓到第一行 credit 当作曲，把编曲的人写进 composer 字段。
        """
        got, _ = extract_credits(
            lrc("[00:01.000] 编曲 : Asteroid Music Team"), 10, [*ROLES, "作曲"]
        )
        assert got is None, f"不该把编曲当作曲：{got}"

    def test_抽取时不删行(self):
        """抽与裁是两件事，抽的时候原文要留着"""
        text = lrc("[00:01.00]作曲：X", "[00:05.00]歌词")
        _, text2 = extract_credits(text, 10, ["作曲"])
        assert "作曲：X" in text2

    def test_超过扫描行数就不抽(self):
        text = "\n".join(["[00:00.00]词"] * 10 + ["[00:10.00]作曲：X"]) + "\n"
        got, _ = extract_credits(text, 10, ["作曲"])
        assert got is None


class Test裁剪:
    def test_全角冒号那行被裁掉(self):
        text = lrc("[00:08.75]作曲：残月", "[00:11.36]编曲：残月", "[00:20.00]歌词")
        out, _ = trim_lyrics(text, 10, prefixes=["作曲"])
        assert "作曲：残月" not in out
        assert "编曲：残月" in out, "只裁作曲，不该动编曲"
        assert "[00:20.00]歌词" in out

    def test_半角也一样(self):
        text = lrc("[00:08.75]作曲:残月", "[00:20.00]歌词")
        out, _ = trim_lyrics(text, 10, prefixes=["作曲"])
        assert "作曲:残月" not in out

    def test_空口令返回值(self):
        text = lrc("[00:01.00]纯音乐，请欣赏", "[00:02.00]纯音乐，请欣赏")
        _out, is_empty = trim_lyrics(text, 10, prefixes=["作曲"])
        assert is_empty

    def test_不传prefixes有兜底(self):
        out, _ = trim_lyrics(lrc("[00:01.00]作词：X", "[00:05.00]歌词"))
        assert "作词：X" not in out


class Test纯credit判断:
    def test_全是credit判True(self):
        text = lrc("[00:01.00]作词：X", "[00:02.00]作曲：Y")
        assert is_pure_credits(text, ROLES)

    def test_全角冒号也要认(self):
        """这一处也有一个半角硬编码的冒号，与 _CREDIT_RE_TEMPLATE 是同一个坑"""
        assert is_pure_credits(lrc("[00:01.00]作词：X", "[00:02.00]作曲：Y"), ROLES)

    def test_有歌词判False(self):
        text = lrc("[00:01.00]作词：X", "[00:05.00]这是歌词")
        assert not is_pure_credits(text, ROLES)

    def test_全角冒号加歌词判False(self):
        text = lrc("[00:01.00]作词：X", "[00:05.00]这是歌词")
        assert not is_pure_credits(text, ROLES)

    def test_不在白名单的角色不算credit(self):
        text = lrc("[00:01.00]钢琴：X")
        assert not is_pure_credits(text, ROLES)

    def test_空文本算纯credit(self):
        assert is_pure_credits("", ROLES)
