"""credit 行的识别、搬走与裁剪"""

import hashlib
from pathlib import Path

import pytest

from vncmd import downloader
from vncmd.downloader import download_song
from vncmd.media.lyrics import CREDIT_COMBOS, process_credits


def lrc(*lines):
    return "\n".join(lines) + "\n"


# 库里出现过的几行，繁体与全角冒号都有
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
        """库里出现五处“作词 : 赵武”这种带空格的写法"""
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
        """库里这样写的五个文件全为同一个人写了两遍，其中一行更详细"""
        text = lrc(
            "[00:00.00]编曲：カワイヒデヒロ",
            "[00:01.00]编曲：カワイヒデヒロ(fox capture plan)",
        )
        credits, _ = process_credits(text, 10, True, False)
        assert credits == {"编曲": "カワイヒデヒロ(fox capture plan)"}


class Test值原样:
    def test_括号里的逗号不动(self):
        """按逗号切会把这个团队名切成三片碎片"""
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
        """只开 trim 没开 collect 时，删掉“混音/”却没写进任何地方等于白丢"""
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
        """人声录音 整体为“录人声的录音师”，不能拆成“人声”加“录音”"""
        credits, rest = process_credits(lrc(line), 10, True, True)
        assert credits == {}
        assert role in rest

    def test_表里没有的单字作不认(self):
        """“作”为“作词”与“作曲”的省略写法，不算角色名"""
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
        """没有内容可写，写进去为脏数据"""
        credits, _ = process_credits(lrc(line), 10, True, False)
        assert credits == {}

    @pytest.mark.parametrize("line", ["[00:00.000]作詞：無", "[00:00.00]作词：無"])
    def test_繁体無也算无(self, line):
        """只认简体的话，繁体歌词会把“無”原样写进 lyricist"""
        credits, rest = process_credits(lrc(line), 10, True, True)
        assert credits == {}
        assert "無" not in rest

    def test_不搬走时值为无的行也留着(self, line="[00:00.000]作词：无"):
        """值为无为角色行的属性，没搬走就不该裁，与其他角色行同一口径"""
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
        """裸正则 search 会把前 N 行里任何以冒号加“无”收尾的行删掉
        判定只应对认得出的角色行生效"""
        credits, rest = process_credits(lrc(line, "[00:05.000]歌词"), 10, True, True)
        assert credits == {}
        assert line in rest

    def test_正文提到纯音乐不再连作曲人一起吃掉(self):
        """判定要用整行相等，按“含即删”会把正文连同作曲人一起删掉"""
        credits, rest = process_credits(
            lrc("[00:00.000]作曲：他说纯音乐，请欣赏", "[00:05.000]歌词"),
            10,
            True,
            True,
        )
        assert credits == {"作曲": "他说纯音乐，请欣赏"}
        # 作曲人已搬进 tag，整行留着就重复
        assert "他说纯音乐，请欣赏" not in rest
        assert "[00:05.000]歌词" in rest

    def test_纯音乐只认整行(self):
        _, rest = process_credits(
            lrc("[00:00.000]插曲：纯音乐，请欣赏"), 10, False, True
        )
        assert "纯音乐" in rest

    def test_值里含无不算无(self):
        """无名氏为真名，不能当占位删掉"""
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
        """这行只在整首没歌词的歌里出现，有歌词的歌里未见过"""
        text = "\n".join(f"[00:{i:02d}.000]歌词{i}" for i in range(10))
        text += "\n[00:10.000]纯音乐，请欣赏\n"
        _, rest = process_credits(text, 10, False, True)
        assert "纯音乐" in rest

    def test_元数据行不占配额(self):
        """clean() 在此之后才跑，扫的时候 [ti:] 那几行还在，不能占掉 10 行配额"""
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
        """[00:01.00] 里的 00 为数字，不能被 _META_TAG_RE 当成元数据吃掉配额"""
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
        """歌词本身带冒号的不少，不能因为像角色行就搬走"""
        text = lrc("[00:00.00]全员：在一起!", "[00:05.00]歌词")
        credits, rest = process_credits(text, 10, True, True)
        assert credits == {}
        assert "全员：在一起!" in rest

    def test_署名类的英文不搬(self):
        """Written by 分不清词曲，不能硬归到编曲"""
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

        # _embed_with_retry 调用 fn(*args)，第一个参数为音乐路径
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
        """裁光后上游多给几个空行时字符串非空，只判空会写出只有空行的 lrc"""
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
        """parse() 只认 [mm:ss.xx]，拿它的结果判“有没有内容”会整份丢掉
        mode 为 2 时会多出一个空的 2.lrc，所以断言原文在不在"""
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
        """content 只含 l 时不下音频，credits 无人接收，裁掉角色行等于白删"""
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
        """drop 为不要译文，短路写错会掉进 process 的兜底分支 split
        夹具里 embed_mode 若写成不存在的值，短路永不触发"""
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
        """drop 的短路会挡住，line 与 block 经 interleave 与拼接后天然只剩原文"""
        run("alc", lyrics=(CREDIT_LYRIC, ""), embed_mode=mode)
        嵌的 = run.state["embed_lyric"]
        assert "YOU BURNED MY SOUL AGAIN" in 嵌的
        assert "TRANSLATION" not in 嵌的
