import io
import struct
from pathlib import Path
from typing import ClassVar

from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from PIL import Image as PILImage

from function.metadata import embed

# MPEG1 Layer3 128kbps 44100Hz 一帧：帧头 4 字节加 413 字节数据。
# mutagen 要连续两帧才认得出帧边界，一帧会抛 HeaderNotFoundError，
# 而改动前的 eyed3 一帧就能读
_FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 413


def _cover_data():
    buf = io.BytesIO()
    PILImage.new("RGB", (100, 100), (255, 0, 0)).save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _text(tags, frame_id):
    frames = tags.getall(frame_id)
    return frames[0].text[0] if frames else None


def _people(tags):
    return tags.getall("TIPL")[0].people


class TestMp3Embed:
    @classmethod
    def setup_class(cls):
        cls.cover = _cover_data()

    def _make(self, temp_dir):
        path = str(Path(temp_dir) / "test.mp3")
        with open(path, "wb") as f:
            f.write(_FRAME * 4)
        return path

    def test_embed_and_read(self, temp_dir):
        path = self._make(temp_dir)
        embed(
            path,
            "mp3",
            cover_data=self.cover,
            cover_mime="image/jpeg",
            lyric_text="[00:01.00]Test",
            song_title="T",
            song_artist="A",
            song_album="AL",
            publish_time="2023-01-01 00:00:00",
            track_no=3,
            cd_no=2,
        )

        tags = MP3(path).tags
        assert _text(tags, "TIT2") == "T"
        assert _text(tags, "TPE1") == "A"
        assert _text(tags, "TALB") == "AL"
        assert _text(tags, "TRCK") == "3"
        assert _text(tags, "TPOS") == "2"
        assert tags.getall("APIC")
        assert any("Test" in (fr.text or "") for fr in tags.getall("USLT"))

    def test_非mp3要报错(self, temp_dir):
        """改动前是 eyed3.load 返回 None 再抛，改成 mutagen 直接抛别的异常"""
        path = str(Path(temp_dir) / "broken.mp3")
        with open(path, "wb") as f:
            f.write(b"not an audio file")
        try:
            embed(path, "mp3", None, None, None, None, None, None, None, None)
        except ValueError as e:
            assert "可能不是 mp3" in str(e)
        else:
            raise AssertionError("该报错却没报")

    def test_日期只写TDRL(self, temp_dir):
        """只写 TDRL，不写 TDRC。

        publish_time 是发行时间，而 ID3v2.4 §4.2.5 里 TDRC 是录制时间、
        TDRL 才是发行时间 —— 填错语义比不填更糟。顺带解决 ffprobe 把两帧
        都映射成 date 那个键、导致它出现两次。

        日期帧是时间戳类，读回来时 mutagen 会把 T 归一空格，
        所以直接查文件里的字节，那才是落盘的样子
        """
        path = self._make(temp_dir)
        embed(
            path,
            "mp3",
            cover_data=None,
            cover_mime=None,
            lyric_text=None,
            song_title=None,
            song_artist=None,
            song_album=None,
            publish_time="2023-01-01 00:00:00",
        )
        raw = Path(path).read_bytes()
        assert b"TDRL" in raw
        assert b"\x032023-01-01T00:00" in raw
        assert b"TDRC" not in raw, "TDRC 是录制时间，不该拿发行时间去填"

    def test_publish_time为空时不写日期(self, temp_dir):
        path = self._make(temp_dir)
        embed(
            path,
            "mp3",
            cover_data=None,
            cover_mime=None,
            lyric_text=None,
            song_title="T",
            song_artist="A",
            song_album=None,
            publish_time="",
        )
        raw = Path(path).read_bytes()
        assert b"TDRL" not in raw


class TestMp3Credits:
    CREDITS: ClassVar = {
        "作曲": "大瀧詠一",
        "作词": "monii/Neuro-sama/Evil Neuro",
        "编曲": "wowaka",
        "制作人": "X",
        "混音": "Kolaa、Hanser",
        "录音": "D-Jin",
        "指挥": "Y",
    }

    def _embed(self, path, credits):
        embed(
            path,
            "mp3",
            cover_data=None,
            cover_mime=None,
            lyric_text=None,
            song_title="T",
            song_artist="A",
            song_album=None,
            publish_time=None,
            credits=credits,
        )

    def test_逐个角色写进对应的帧(self, temp_dir):
        path = str(Path(temp_dir) / "c.mp3")
        with open(path, "wb") as f:
            f.write(_FRAME * 4)
        self._embed(path, self.CREDITS)

        tags = MP3(path).tags
        assert _text(tags, "TCOM") == "大瀧詠一"
        assert _text(tags, "TEXT") == "monii/Neuro-sama/Evil Neuro"
        assert _text(tags, "TPE3") == "Y"
        people = dict(_people(tags))
        assert people["arranger"] == "wowaka"
        assert people["producer"] == "X"
        assert people["mix"] == "Kolaa、Hanser"
        assert people["engineer"] == "D-Jin"

    def test_TIPL只add一次(self, temp_dir):
        """连续 add 会互相覆盖，所以所有走 TIPL 的角色必须攒进一个 people 列表"""
        path = str(Path(temp_dir) / "t.mp3")
        with open(path, "wb") as f:
            f.write(_FRAME * 4)
        self._embed(path, self.CREDITS)

        tags = MP3(path).tags
        assert len(tags.getall("TIPL")) == 1
        assert len(_people(tags)) == 4

    def test_值是字符串不是列表(self, temp_dir):
        """多值在 Petrichor 与 ffprobe 上都只显示第一个，所以一律写整串"""
        path = str(Path(temp_dir) / "s.mp3")
        with open(path, "wb") as f:
            f.write(_FRAME * 4)
        self._embed(path, self.CREDITS)

        tags = MP3(path).tags
        assert _text(tags, "TCOM") == "大瀧詠一"
        assert _text(tags, "TEXT") == "monii/Neuro-sama/Evil Neuro"

    def test_重跑时后一遍的值盖掉前一遍(self, temp_dir):
        """downloader 的 _embed_with_retry 失败会重跑 embed，--force 重下也会再跑一遍。
        跑两遍之后文件里只能有后一遍的值，不能是两次的叠加"""
        path = str(Path(temp_dir) / "r.mp3")
        with open(path, "wb") as f:
            f.write(_FRAME * 4)
        self._embed(path, self.CREDITS)
        self._embed(path, {"作曲": "第二遍", "编曲": "第二遍编曲"})

        tags = MP3(path).tags
        assert len(tags.getall("TCOM")) == 1
        assert len(tags.getall("TIPL")) == 1
        assert len(tags.getall("TIT2")) == 1
        # 断言整个值列表而不是第一个值，否则「一个帧里塞两个值」照样能过
        assert tags.getall("TCOM")[0].text == ["第二遍"]
        assert dict(_people(tags)) == {"arranger": "第二遍编曲"}
        # embed 只写交给它的字段，没给的不会去清。
        # 实际不会累积：--force 重下是重新下载，上游文件不带任何 tag
        assert _text(tags, "TEXT") == "monii/Neuro-sama/Evil Neuro"


class TestFlacEmbed:
    @classmethod
    def setup_class(cls):
        cls.cover = _cover_data()

    def _make(self, temp_dir):
        path = str(Path(temp_dir) / "test.flac")
        si = struct.pack(
            ">HH3s3sQ16s",
            4096,
            4096,
            b"\x00\x00\x00",
            b"\x00\x00\x00",
            0xAC44020F00000000,
            b"\x00" * 16,
        )
        with open(path, "wb") as f:
            f.write(b"fLaC\x80\x00\x00\x22" + si)
        return path

    def test_embed_and_read(self, temp_dir):
        path = self._make(temp_dir)
        embed(
            path,
            "flac",
            cover_data=self.cover,
            cover_mime="image/jpeg",
            lyric_text="[00:01.00]FLACtest",
            song_title="TF",
            song_artist="AF",
            song_album="ALF",
            publish_time="2024-06-15 00:00:00",
            track_no=5,
            cd_no=1,
        )

        flac = FLAC(path)
        assert flac.get("title", [""])[0] == "TF"
        assert flac.get("artist", [""])[0] == "AF"
        assert flac.get("album", [""])[0] == "ALF"
        assert flac.get("tracknumber", [""])[0] == "5"
        assert flac.get("discnumber", [""])[0] == "1"
        assert len(flac.pictures) > 0
        assert "FLACtest" in flac.get("lyrics", [""])[0]

    def test_重跑不叠加封面(self, temp_dir):
        """add_picture 是追加语义。不清的话 embed 几次就叠几层 ——
        实测同一个文件连 embed 八次，文件从 23.7 KB 涨到 54.8 KB。
        _embed_with_retry 会重跑 embed，--force 重下也会再跑一遍，两条路都会命中"""
        path = self._make(temp_dir)
        embed(
            path,
            "flac",
            cover_data=self.cover,
            cover_mime="image/jpeg",
            lyric_text=None,
            song_title="T",
            song_artist="A",
            song_album=None,
            publish_time=None,
        )
        first_size = Path(path).stat().st_size

        for _ in range(5):
            embed(
                path,
                "flac",
                cover_data=self.cover,
                cover_mime="image/jpeg",
                lyric_text=None,
                song_title="T",
                song_artist="A",
                song_album=None,
                publish_time=None,
            )

        assert len(FLAC(path).pictures) == 1, "封面叠加了"
        assert Path(path).stat().st_size == first_size, "文件在变大，说明有多余的块"

    def test_换封面后不留下旧的(self, temp_dir):
        path = self._make(temp_dir)
        for cover in (self.cover, _cover_data()):
            embed(
                path,
                "flac",
                cover_data=cover,
                cover_mime="image/jpeg",
                lyric_text=None,
                song_title="T",
                song_artist="A",
                song_album=None,
                publish_time=None,
            )
        flac = FLAC(path)
        assert len(flac.pictures) == 1
        assert flac.pictures[0].data == _cover_data()

    def test_credits写进对应的键(self, temp_dir):
        path = self._make(temp_dir)
        embed(
            path,
            "flac",
            cover_data=None,
            cover_mime=None,
            lyric_text=None,
            song_title="T",
            song_artist="A",
            song_album=None,
            publish_time=None,
            credits=TestMp3Credits.CREDITS,
        )

        flac = FLAC(path)
        assert flac["composer"] == ["大瀧詠一"]
        assert flac["lyricist"] == ["monii/Neuro-sama/Evil Neuro"]
        assert flac["conductor"] == ["Y"]
        assert flac["arranger"] == ["wowaka"]
        assert flac["producer"] == ["X"]
        assert flac["mixer"] == ["Kolaa、Hanser"]
        assert flac["engineer"] == ["D-Jin"]

    def test_值是字符串不是列表(self, temp_dir):
        """Vorbis 的多值是复数个条目，多值在播放器上只显示第一个，所以只写一个"""
        path = self._make(temp_dir)
        embed(
            path,
            "flac",
            cover_data=None,
            cover_mime=None,
            lyric_text=None,
            song_title="T",
            song_artist="A",
            song_album=None,
            publish_time=None,
            credits={"作曲": "Asteroid Music Team（monii, Johnny R, Ari）"},
        )

        flac = FLAC(path)
        assert flac["composer"] == ["Asteroid Music Team（monii, Johnny R, Ari）"]
