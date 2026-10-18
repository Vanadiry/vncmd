"""credit 行的识别、搬走与裁剪

`process_credits` 一个函数管两件事：把认得出的角色搬进 credits，
并按开关决定删不删那些行。两个开关的四种组合逐格断言，
因为它们之间最容易出现「搬走了却没删」或者「没搬走却删了」这类不一致。

行的样子全部取自 2026-10-17 的实测（用户真实曲库 528 首、307 个 lrc），
不是凭空编的。
"""

import hashlib
from pathlib import Path

import pytest

from vncmd import downloader
from vncmd.downloader import download_song
from vncmd.lyrics import CREDIT_COMBOS, process_credits


def lrc(*lines):
    return "\n".join(lines) + "\n"


# 实测里出现过的那几行，繁体与全角冒号都有
REAL = [
    "[00:08.75]作曲：残月",
    "[00:01.30]编曲：emon(Tes.)",
    "[00:00.94]编曲：カワイヒデヒロ(fox capture plan)",
    "[00:09.14]混音：Kolaa、Hanser",
    "[00:03.578]编曲：ilem",
    "[00:02.00]作詞：狐夢想(COOL&CREATE)",
    "[00:03.10]編曲：大久保薫",
]

# 含表内角色但按规格不处理的连写，一个都不能碰
COMBO_OUT = [
    ("[00:01.00]配唱制作人：金大洲", "配唱制作人"),
    ("[00:01.00]人声录音：郑晓桐", "人声录音"),
    ("[00:01.00]母带制作：Ten Jensen@Sterling Sound", "母带制作"),
    ("[00:01.00]音乐制作发行：北京听见时代娱乐传媒有限公司", "音乐制作发行"),
]

ALIASES = [
    ("[00:01.00]作曲：X", "作曲", "X"),
    ("[00:01.00]作词：X", "作词", "X"),
    ("[00:01.00]作詞：X", "作词", "X"),
    ("[00:01.00]编曲：X", "编曲", "X"),
    ("[00:01.00]編曲：X", "编曲", "X"),
    ("[00:01.00]制作人：X", "制作人", "X"),
    ("[00:01.00]製作人：X", "制作人", "X"),
    ("[00:01.00]Producer: X", "制作人", "X"),
    ("[00:01.00]混音：X", "混音", "X"),
    ("[00:01.00]Mixer: X", "混音", "X"),
    ("[00:01.00]录音：X", "录音", "X"),
    ("[00:01.00]錄音：X", "录音", "X"),
    ("[00:01.00]指挥：X", "指挥", "X"),
    ("[00:01.00]指揮：X", "指挥", "X"),
]

COMBO_PAIRS = [
    ("[00:01.00]作/編曲：ARM(IOSYS)", "ARM(IOSYS)"),
    ("[00:01.00]作/编曲：ARM(IOSYS)", "ARM(IOSYS)"),
    ("[00:01.00]作編曲：ARM(IOSYS)", "ARM(IOSYS)"),
    ("[00:01.00]作编曲：ARM(IOSYS)", "ARM(IOSYS)"),
    ("[00:01.00]作曲/编曲：ARM(IOSYS)", "ARM(IOSYS)"),
    ("[00:01.00]作曲/編曲：ARM(IOSYS)", "ARM(IOSYS)"),
]


class Test角色表:
    @pytest.mark.parametrize("line,role,value", ALIASES)
    def test_逐行命中(self, line, role, value):
        credits, _ = process_credits(lrc(line), 10, True, False)
        assert credits == {role: value}

    @pytest.mark.parametrize("colon", [":", "："])
    def test_两种冒号都认(self, colon):
        credits, _ = process_credits(lrc(f"[00:01.00]作词{colon}赵武"), 10, True, False)
        assert credits == {"作词": "赵武"}

    def test_冒号前后有空格也认(self):
        """实测「作词 : 赵武」这种带空格的写法在库里有五处"""
        credits, _ = process_credits(lrc("[00:01.00] 作词 : 赵武"), 10, True, False)
        assert credits == {"作词": "赵武"}

    @pytest.mark.parametrize("line", REAL)
    def test_实测那几行改动后不再被漏(self, line):
        credits, rest = process_credits(lrc(line, "[00:20.00]歌词"), 10, True, True)
        assert credits, f"没搬走：{line}"
        assert line not in rest, f"没裁掉：{line}"
        assert "[00:20.00]歌词" in rest

    def test_七个角色一次全中(self):
        text = lrc(
            "[00:00.000]作曲：大瀧詠一",
            "[00:01.000]作詞：畑亜貴",
            "[00:02.000]编曲：wowaka",
            "[00:03.000]製作人：X",
            "[00:04.000]混音：Mike Truman",
            "[00:05.000]錄音：D-Jin",
            "[00:06.000]指揮：X",
            "[00:07.000]歌词",
        )
        credits, rest = process_credits(text, 10, True, True)
        assert credits == {
            "作曲": "大瀧詠一",
            "作词": "畑亜貴",
            "编曲": "wowaka",
            "制作人": "X",
            "混音": "Mike Truman",
            "录音": "D-Jin",
            "指挥": "X",
        }
        assert rest == "[00:07.000]歌词"

    def test_同角色两行取后一个(self):
        """库里这样写的五个文件全是同一个人写了两遍，其中一行更详细"""
        text = lrc(
            "[00:00.00]编曲：カワイヒデヒロ",
            "[00:01.00]编曲：カワイヒデヒロ(fox capture plan)",
        )
        credits, _ = process_credits(text, 10, True, False)
        assert credits == {"编曲": "カワイヒデヒロ(fox capture plan)"}


class Test值原样:
    def test_括号里的逗号不动(self):
        """踩过：按逗号切会把这个团队名切成三片碎片"""
        raw = "[00:00.000]作曲：Asteroid Music Team（monii, Johnny R, Ari）"
        credits, _ = process_credits(lrc(raw), 10, True, False)
        assert credits == {"作曲": "Asteroid Music Team（monii, Johnny R, Ari）"}

    def test_斜杠分隔不动(self):
        raw = "[00:00.000]作词：monii/Neuro-sama/Evil Neuro"
        credits, _ = process_credits(lrc(raw), 10, True, False)
        assert credits == {"作词": "monii/Neuro-sama/Evil Neuro"}

    def test_值是字符串不是列表(self):
        """多值在 Petrichor 与 ffprobe 上都只显示第一个，所以一律写整串"""
        credits, _ = process_credits(
            lrc("[00:00.00]混音：Kolaa、Hanser"), 10, True, False
        )
        assert isinstance(credits["混音"], str)
        assert credits["混音"] == "Kolaa、Hanser"


class Test连写表:
    @pytest.mark.parametrize("line,value", COMBO_PAIRS)
    def test_六个字符串都记两个角色并整行删(self, line, value):
        credits, rest = process_credits(lrc(line, "[00:20.00]歌词"), 10, True, True)
        assert credits == {"作曲": value, "编曲": value}
        assert line not in rest
        assert "[00:20.00]歌词" in rest

    def test_混音母带记混音并留母带(self):
        credits, rest = process_credits(
            lrc("[00:00.000]混音/母带：Johnny R", "[00:05.000]歌词"), 10, True, True
        )
        assert credits == {"混音": "Johnny R"}
        assert rest == "[00:00.000]母带：Johnny R\n[00:05.000]歌词"

    def test_没搬走就不改角色名(self):
        """只开 trim 没开 collect 时，删掉「混音/」而它没进任何地方就是白丢"""
        credits, rest = process_credits(
            lrc("[00:00.000]混音/母带：Johnny R"), 10, False, True
        )
        assert credits == {}
        assert rest == "[00:00.000]混音/母带：Johnny R"

    def test_没搬走就不删连写行(self):
        _, rest = process_credits(lrc("[00:01.00]作編曲：ARM(IOSYS)"), 10, False, True)
        assert "作編曲：ARM(IOSYS)" in rest

    @pytest.mark.parametrize("line,role", COMBO_OUT)
    def test_规格外的一律不动(self, line, role):
        """`人声录音` 整体是「录人声的那个录音师」，不是「人声」加「录音」"""
        credits, rest = process_credits(lrc(line), 10, True, True)
        assert credits == {}
        assert role in rest

    def test_表里没有的单字作不认(self):
        """「作」不是角色名，它只是「作词」与「作曲」的省略写法"""
        credits, rest = process_credits(lrc("[00:00.00]作：X"), 10, True, True)
        assert credits == {}
        assert "作：X" in rest

    def test_表与规格一致(self):
        assert set(CREDIT_COMBOS) == {
            "作/編曲",
            "作/编曲",
            "作編曲",
            "作编曲",
            "作曲/编曲",
            "作曲/編曲",
            "混音/母带",
        }


class Test删除类:
    def test_纯音乐在头部时被删(self):
        text = lrc("[00:00.000]纯音乐，请欣赏", "[00:05.000]歌词")
        _, rest = process_credits(text, 10, False, True)
        assert "纯音乐" not in rest
        assert "[00:05.000]歌词" in rest

    def test_半角逗号也认(self):
        _, rest = process_credits(lrc("[00:00.000]纯音乐,请欣赏"), 10, False, True)
        assert rest == ""

    @pytest.mark.parametrize("line", ["[00:00.000] 作词 : 无", "[00:00.00]作词：无"])
    def test_值为无被删(self, line):
        _, rest = process_credits(lrc(line, "[00:01.00]歌词"), 10, True, True)
        assert "无" not in rest
        assert "[00:01.00]歌词" in rest

    @pytest.mark.parametrize("line", ["[00:00.000]作词 : 无", "[00:00.00]作词：无"])
    def test_值为无不写进tag(self, line):
        """没有内容可写，写进去是脏数据"""
        credits, _ = process_credits(lrc(line), 10, True, False)
        assert credits == {}

    @pytest.mark.parametrize("line", ["[00:00.000]作詞：無", "[00:00.00]作词：無"])
    def test_繁体無也算无(self, line):
        """只认简体的话，繁体歌词会把「無」原样写进 lyricist"""
        credits, rest = process_credits(lrc(line), 10, True, True)
        assert credits == {}
        assert "無" not in rest

    def test_不搬走时值为无的行也留着(self, line="[00:00.000]作词：无"):
        """值为无是角色行的属性，没搬走就不该裁 —— 与其他角色行同一口径"""
        _credits, rest = process_credits(lrc(line), 10, False, True)
        assert "作词：无" in rest

    @pytest.mark.parametrize(
        "line",
        [
            "[00:00.000]我：无",
            "[00:00.000]旁白：无",
            "[00:00.000]念白： 无 ",
            "[00:00.000]全员：无",
        ],
    )
    def test_歌词里的冒号加无不被当占位(self, line):
        """早先用裸正则 search，前 N 行里任何以冒号加「无」收尾的行都会被删，
        连歌词都被吃掉。判定该只对认得出的角色行生效"""
        credits, rest = process_credits(lrc(line, "[00:05.000]歌词"), 10, True, True)
        assert credits == {}
        assert line in rest

    def test_正文提到纯音乐不再连作曲人一起吃掉(self):
        """早先用「含即删」，正文里提到这六个字也会被删。
        那一行是 credit 行，于是整行没了而作曲人也没进 tag ——
        两头落空。判定改成整行相等之后，作曲人能正常搬走"""
        credits, rest = process_credits(
            lrc("[00:00.000]作曲：他说纯音乐，请欣赏", "[00:05.000]歌词"),
            10,
            True,
            True,
        )
        assert credits == {"作曲": "他说纯音乐，请欣赏"}
        # 行照删 —— 作曲人已经搬进 tag 了，留着就是重复
        assert "他说纯音乐，请欣赏" not in rest
        assert "[00:05.000]歌词" in rest

    def test_纯音乐只认整行(self):
        _, rest = process_credits(
            lrc("[00:00.000]插曲：纯音乐，请欣赏"), 10, False, True
        )
        assert "纯音乐" in rest

    def test_值里含无不算无(self):
        """无名氏是真名，不能当占位删掉"""
        credits, _ = process_credits(lrc("[00:00.000]作词：无名氏"), 10, True, False)
        assert credits == {"作词": "无名氏"}

    @pytest.mark.parametrize("role", ["歌词翻译", "歌詞翻譯"])
    def test_歌词翻译被删(self, role):
        _, rest = process_credits(lrc(f"[00:00.000]{role}：@老肯LK"), 10, False, True)
        assert rest == ""

    def test_正文出现歌词翻译三字但没冒号不删(self):
        text = lrc("[00:01.00]歌词翻译这三字出现在歌里", "[00:02.00]歌词")
        _, rest = process_credits(text, 10, False, True)
        assert "歌词翻译这三字出现在歌里" in rest

    def test_删除类不写进tag(self):
        credits, _ = process_credits(lrc("[00:00.000]歌词翻译：X"), 10, True, False)
        assert credits == {}

    @pytest.mark.parametrize("line,keep", COMBO_OUT)
    def test_母带制作不被当成值为无(self, line, keep):
        _, rest = process_credits(lrc(line), 10, False, True)
        assert keep in rest


class Test行号限制:
    def test_角色行越界就不搬也不裁(self):
        text = "\n".join(f"[00:{i:02d}.000]歌词{i}" for i in range(10))
        text += "\n[00:10.000]作词：越界\n"
        credits, rest = process_credits(text, 10, True, True)
        assert credits == {}
        assert "越界" in rest

    def test_放宽行数就搬走(self):
        text = "\n".join(f"[00:{i:02d}.000]歌词{i}" for i in range(10))
        text += "\n[00:10.000]作词：越界\n"
        credits, rest = process_credits(text, 11, True, True)
        assert credits == {"作词": "越界"}
        assert "越界" not in rest

    def test_歌词翻译也受限(self):
        text = "\n".join(f"[00:{i:02d}.000]歌词{i}" for i in range(10))
        text += "\n[00:10.000]歌词翻译：越界\n"
        _, rest = process_credits(text, 10, False, True)
        assert "歌词翻译：越界" in rest

    def test_纯音乐也受限(self):
        """实测这行只在整首没歌词的歌里出现，混着有歌词的歌里没见过"""
        text = "\n".join(f"[00:{i:02d}.000]歌词{i}" for i in range(10))
        text += "\n[00:10.000]纯音乐，请欣赏\n"
        _, rest = process_credits(text, 10, False, True)
        assert "纯音乐" in rest

    def test_元数据行不占配额(self):
        """clean() 在这一步之后才跑，扫的时候 [ti:] 那几行还在。
        标准 LRC 头四行会白吃掉默认 10 行里的四行"""
        text = "[ti:歌名]\n[ar:歌手]\n[al:专辑]\n[by:工具]\n"
        text += "[00:00.00]歌词\n[00:01.00]作词：X\n"
        credits, _ = process_credits(text, 5, True, False)
        assert credits == {"作词": "X"}, "第 5 行的作词该算头部内"

    def test_元数据行不够多时配额照常数(self):
        text = "[ti:歌名]\n" + "\n".join(f"[00:{i:02d}.000]歌词{i}" for i in range(5))
        text += "\n[00:06.00]作词：X\n"
        credits, _ = process_credits(text, 5, True, False)
        assert credits == {}, "歌词已经用掉五行配额，第 6 行该越界"

    def test_时间戳行不会被当成元数据(self):
        """[00:01.00] 里的 00 是数字不是字母，不能被 _META_TAG_RE 吃掉配额"""
        text = "\n".join(f"[00:{i:02d}.000]歌词{i}" for i in range(5))
        text += "\n[00:05.000]作词：越界\n"
        credits, _ = process_credits(text, 5, True, False)
        assert credits == {}

    def test_放宽行数就删掉(self):
        text = "\n".join(f"[00:{i:02d}.000]歌词{i}" for i in range(10))
        text += "\n[00:10.000]纯音乐，请欣赏\n"
        _, rest = process_credits(text, 11, False, True)
        assert "纯音乐" not in rest


class Test四格矩阵:
    ROLE_LINE = "[00:01.00]作词：X"
    PLACEHOLDER = "[00:02.00]纯音乐，请欣赏"
    LYRIC = "[00:03.00]这是歌词"

    @pytest.mark.parametrize(
        "collect,trim,role_kept,credit",
        [
            (False, False, True, False),
            (True, False, True, True),
            (False, True, True, False),
            (True, True, False, True),
        ],
    )
    def test_逐格(self, collect, trim, role_kept, credit):
        text = lrc(self.ROLE_LINE, self.PLACEHOLDER, self.LYRIC)
        credits, rest = process_credits(text, 10, collect, trim)
        assert (self.ROLE_LINE in rest) is role_kept
        assert (self.PLACEHOLDER in rest) is (not trim)
        assert (self.LYRIC in rest) is True
        assert (credits.get("作词") == "X") is credit

    def test_两个都关时原文一字不动(self):
        text = lrc(self.ROLE_LINE, self.PLACEHOLDER, self.LYRIC)
        credits, rest = process_credits(text, 10, False, False)
        assert credits == {}
        assert rest == text.rstrip("\n")

    def test_裁空之后剩下空串(self):
        """上游整首只有 credits 时不写 lrc 文件也不嵌空歌词"""
        credits, rest = process_credits(lrc(self.ROLE_LINE), 10, True, True)
        assert credits == {"作词": "X"}
        assert rest == ""

    def test_留白行原样保留(self):
        """上游 lrc 里有空时间戳行，裁的时候不能顺手删掉"""
        text = lrc("[00:00.00]", "[00:01.00]作词：X", "[00:02.00]")
        _credits, rest = process_credits(text, 10, True, True)
        assert rest == "[00:00.00]\n[00:02.00]"

    def test_歌词里带冒号不该被搬走(self):
        """实测库里有一批歌词本身就带冒号（全员、在了一起之类）"""
        text = lrc("[00:00.00]全员：在一起!", "[00:05.00]歌词")
        credits, rest = process_credits(text, 10, True, True)
        assert credits == {}
        assert "全员：在一起!" in rest

    def test_署名类的英文不搬(self):
        """Written by 分不清词曲，硬分是编"""
        credits, rest = process_credits(lrc("[00:00.00]Written by: X"), 10, True, True)
        assert credits == {}
        assert "Written by: X" in rest

    def test_歌词翻译不搬但Vocal搬不到也不动(self):
        for line in (
            "[00:00.00]Vocal：Neuro-sama",
            "[00:00.00]Composed and mixed by：X",
        ):
            credits, rest = process_credits(lrc(line), 10, True, True)
            assert credits == {}
            assert line in rest


AUDIO = b"fLaC" + b"vncmd" * 5000
CREDIT_LYRIC = (
    "[00:00.000] 作曲 : 大瀧詠一\n"
    "[00:01.000] 作词 : monii/Neuro-sama/Evil Neuro\n"
    "[00:05.000] 纯音乐，请欣赏\n"
    "[00:15.920]YOU BURNED MY SOUL AGAIN\n"
)


class TestDownloader接线:
    """这一层测两个开关怎么接到 process_credits 上，逻辑本身上面已测过"""

    @pytest.fixture
    def run(self, tmp_path, monkeypatch):
        state = {
            "content": "alc",
            "lyrics": (CREDIT_LYRIC, ""),
            "credits": None,
            "mode": "line",
            "embed_mode": "drop",
            "embed_lyric": None,
        }

        def fake_fetch(url, path, label, progress=None, task_id=None, **kw):
            Path(path).write_bytes(AUDIO)

        # _embed_with_retry 调的是 fn(*args)，所以第一个参数是音乐路径不是函数
        def fake_embed(_music_path, *args):
            state["credits"] = args[-1]
            state["embed_lyric"] = args[3]

        monkeypatch.setattr(downloader, "fetch_audio", fake_fetch)
        monkeypatch.setattr(downloader, "fetch_lyrics", lambda *_a: state["lyrics"])
        monkeypatch.setattr(downloader, "fetch_cover", lambda *_a: b"\x89PNG")
        monkeypatch.setattr(downloader, "embed_metadata", fake_embed)
        monkeypatch.setattr(downloader, "get_check_enabled", lambda: False)
        monkeypatch.setattr(
            downloader, "get_download_content", lambda: state["content"]
        )
        monkeypatch.setattr(downloader, "get_parse_credits", lambda: True)
        monkeypatch.setattr(downloader, "get_auto_trim", lambda: True)
        monkeypatch.setattr(downloader, "get_save_lyrics_mode", lambda: state["mode"])
        monkeypatch.setattr(
            downloader, "get_embed_lyrics_mode", lambda: state["embed_mode"]
        )

        def go(content="alc", lyrics=None, mode="line", embed_mode="drop"):
            if lyrics is not None:
                state["lyrics"] = lyrics
            state["mode"] = mode
            state["embed_mode"] = embed_mode
            state["content"] = content
            # 每次换个目录，否则 output_lyrics_files 会写成 xxx(1).lrc
            dl = tmp_path / f"dl{content}{len(state['lyrics'][0])}"
            ok, msg, _ = download_song(
                song_url="http://x/a.flac",
                song_title="歌",
                song_artist="人",
                song_album="专",
                song_id=1,
                cover_url="http://x/c.png",
                lyrics_api_url="http://x/l",
                publish_time="",
                download_dir=str(dl),
                song_md5=hashlib.md5(AUDIO).hexdigest(),
            )
            assert ok, msg
            return sorted(p.read_text() for p in dl.glob("*.lrc")), state["credits"]

        go.state = state
        return go

    def test_裁完只剩空行时不写lrc(self, run):
        """裁光之后 "\n".join([]) 是空串，但上游多给几个空行时是 "\\n" 这种非空串，
        只判字符串空不空会写出一个只有空行的 lrc 文件"""
        texts, _ = run("alc", ("[00:00.000]纯音乐，请欣赏\n\n\n", ""))
        assert texts == [], f"该不写却写了：{texts}"

    def test_裁完没内容时译文也一起清掉(self, run):
        """原文没歌词只有译文时一并清掉，免得留下有 2.lrc 没 lrc 的怪状态"""
        texts, _ = run("alc", ("[00:00.000]纯音乐，请欣赏\n", "[00:00.000]译文\n"))
        assert texts == [], f"该不写却写了：{texts}"

    @pytest.mark.parametrize(
        "lyric",
        [
            "这是一首纯文本的歌词\n第二行\n",
            "[1:02.34]一位分钟\n[2:03.45]也是\n",
            "[00:01.5]一位小数\n[00:02.5]也是\n",
            "[00:01]没有小数\n[00:02]也是\n",
            "[ti:歌名]\n[ar:歌手]\n[al:专辑]\n",
        ],
        ids=["纯文本", "单数字分钟", "一位小数", "无小数", "只有元数据行"],
    )
    def test_解析不出时间戳的歌词照样要写(self, run, lyric):
        """parse() 要求时间戳是 [mm:ss.xx]，上游给别的形态是有的。
        拿 parse 的结果判「有没有内容」会把它们整份丢掉 ——
        只在 save_mode 为 1 与 2 时验：0 是交错，那一档的 interleave
        本来就只保留带时间戳的行，写出空文件是既有行为，与这次改动无关。
        mode 为 2 时会多产出一个空的 2.lrc（既有问题），所以断言「原文在不在」
        而不是「第一个文件是不是原文」
        """
        texts, _ = run("alc", (lyric, ""), mode="2")
        assert lyric.rstrip("\n") in texts, f"歌词被丢了：{lyric!r}，写出的是 {texts}"

    def test_两个开关开时搬走并裁掉(self, run):
        texts, credits = run("alc")
        assert credits == {
            "作曲": "大瀧詠一",
            "作词": "monii/Neuro-sama/Evil Neuro",
        }
        assert len(texts) == 1
        assert "大瀧詠一" not in texts[0]
        assert "YOU BURNED MY SOUL AGAIN" in texts[0]
        assert "纯音乐" not in texts[0]

    def test_仅歌词时角色行不裁(self, run):
        """content 为 1 时不会下音频，抽出来的 credits 没人接收，
        而行被裁掉就是白删。改动前丢的是作曲一行，改动后会丢七个角色"""
        texts, credits = run("l")
        assert credits is None, "没有音频可写，不该去抽"
        assert len(texts) == 1
        assert "作曲 : 大瀧詠一" in texts[0]
        assert "YOU BURNED MY SOUL AGAIN" in texts[0]

    def test_仅歌词时删除类照裁(self, run):
        """值为无、歌词翻译、纯音乐这三类不依赖标签，该删还是删"""
        texts, _ = run("l")
        assert "纯音乐" not in texts[0]

    # 译文与原文同一个时间戳，line 模式才能配成对
    _两路 = (CREDIT_LYRIC, "[00:15.920]THIS IS THE TRANSLATION")

    def test_embed为drop时只嵌原文(self, run):
        """drop 是不要译文。短路写错会掉进 process 的兜底分支，
        那个分支是 split，于是原文加译文一起嵌进去。

        这一条是被反向验证逼出来的：夹具里那个 embed_mode 写的是早已
        不存在的值，短路永远不触发，改名之后那条判断一度谁都没测到
        """
        run("alc", lyrics=self._两路, embed_mode="drop")
        嵌的 = run.state["embed_lyric"]
        assert "YOU BURNED MY SOUL AGAIN" in 嵌的
        assert "TRANSLATION" not in 嵌的

    @pytest.mark.parametrize("mode", ["line", "block"])
    def test_embed为line与block时两路都嵌(self, run, mode):
        run("alc", lyrics=self._两路, embed_mode=mode)
        嵌的 = run.state["embed_lyric"]
        assert "YOU BURNED MY SOUL AGAIN" in 嵌的
        assert "TRANSLATION" in 嵌的

    @pytest.mark.parametrize("mode", ["drop", "line", "block"])
    def test_没有译文时三档都只嵌原文(self, run, mode):
        """没译文就别折腾。drop 的短路本来也挡住了，
        而 line 与 block 是 process 里 interleave 与拼接的结果，天然只剩原文"""
        run("alc", lyrics=(CREDIT_LYRIC, ""), embed_mode=mode)
        嵌的 = run.state["embed_lyric"]
        assert "YOU BURNED MY SOUL AGAIN" in 嵌的
        assert "TRANSLATION" not in 嵌的
