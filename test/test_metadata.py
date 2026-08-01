import io
import struct
from pathlib import Path
import eyed3
from PIL import Image as PILImage
from mutagen.flac import FLAC
from function.metadata import embed


def _cover_data():
    buf = io.BytesIO()
    PILImage.new("RGB", (100, 100), (255, 0, 0)).save(buf, "JPEG", quality=90)
    return buf.getvalue()


class TestMp3Embed:
    @classmethod
    def setup_class(cls):
        cls.cover = _cover_data()

    def test_embed_and_read(self, temp_dir):
        mp3_path = str(Path(temp_dir) / "test.mp3")
        with open(mp3_path, "wb") as f:
            f.write(b"\xff\xfb\x90\x00" + b"\x00" * 413)

        embed(
            mp3_path,
            "mp3",
            cover_data=self.cover,
            cover_mime="image/jpeg",
            lyric_text="[00:01.00]Test",
            song_id=12345,
            song_title="T",
            song_artist="A",
            song_album="AL",
            publish_time="2023-01-01 00:00:00",
            track_no=3,
            cd_no=2,
        )

        audio = eyed3.load(mp3_path)
        assert audio.tag.title == "T"
        assert audio.tag.artist == "A"
        assert audio.tag.album == "AL"
        assert audio.tag.track_num == (3, None)
        assert audio.tag.disc_num == (2, None)
        assert len(audio.tag.images) > 0
        assert any("Test" in (lyric.text or "") for lyric in audio.tag.lyrics)


class TestFlacEmbed:
    @classmethod
    def setup_class(cls):
        cls.cover = _cover_data()

    def test_embed_and_read(self, temp_dir):
        flac_path = str(Path(temp_dir) / "test.flac")
        si = struct.pack(
            ">HH3s3sQ16s",
            4096,
            4096,
            b"\x00\x00\x00",
            b"\x00\x00\x00",
            0xAC44020F00000000,
            b"\x00" * 16,
        )
        with open(flac_path, "wb") as f:
            f.write(b"fLaC\x80\x00\x00\x22" + si)

        embed(
            flac_path,
            "flac",
            cover_data=self.cover,
            cover_mime="image/jpeg",
            lyric_text="[00:01.00]FLACtest",
            song_id=67890,
            song_title="TF",
            song_artist="AF",
            song_album="ALF",
            publish_time="2024-06-15 00:00:00",
            track_no=5,
            cd_no=1,
        )

        flac = FLAC(flac_path)
        assert flac.get("title", [""])[0] == "TF"
        assert flac.get("artist", [""])[0] == "AF"
        assert flac.get("album", [""])[0] == "ALF"
        assert flac.get("tracknumber", [""])[0] == "5"
        assert flac.get("discnumber", [""])[0] == "1"
        assert len(flac.pictures) > 0
        assert "FLACtest" in flac.get("lyrics", [""])[0]
