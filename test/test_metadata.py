import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Metadata embedding tests."""
import os
import eyed3
from test._runner import check, section, summary, reset

reset()
TMP = __import__("test._runner", fromlist=["tmp_dir"]).tmp_dir()

section("Metadata embedding")

from function.metadata import embed
from function.image import process_cover
from PIL import Image as PILImage
import io

# Create test cover
buf = io.BytesIO()
PILImage.new("RGB", (100, 100), (255, 0, 0)).save(buf, "JPEG", quality=90)
cover_data = buf.getvalue()

# Test MP3
mp3_path = os.path.join(TMP, "test.mp3")
with open(mp3_path, "wb") as f:
    f.write(b"\xff\xfb\x90\x00" + b"\x00" * 413)

embed(
    mp3_path, "mp3",
    cover_data=cover_data, cover_mime="image/jpeg",
    lyric_text="[00:01.00]Test",
    song_id=12345, song_title="T", song_artist="A",
    song_album="AL", publish_time="2023-01-01 00:00:00",
)

audio = eyed3.load(mp3_path)
check("title", audio.tag.title == "T")
check("artist", audio.tag.artist == "A")
check("album", audio.tag.album == "AL")
check("copyright", audio.tag.copyright == "12345")
check("cover", len(audio.tag.images) > 0)
lyric_ok = any("Test" in (l.text or "") for l in audio.tag.lyrics)
check("lyrics", lyric_ok)
os.remove(mp3_path)

# Test FLAC — use a valid FLAC from mutagen itself
import struct
from mutagen.flac import FLAC

flac_path = os.path.join(TMP, "test.flac")
# Build valid FLAC: fLaC + STREAMINFO block (last, 34 bytes)
# sample_rate=44100(20b), channels-1=1(3b), bps-1=15(5b), total_samples=0(36b)
si = struct.pack(">HH3s3sQ16s",
    4096, 4096, b"\x00\x00\x00", b"\x00\x00\x00",
    0xAC44020F00000000,  # 44100Hz, 2ch, 16bps
    b"\x00" * 16)
with open(flac_path, "wb") as f:
    f.write(b"fLaC\x80\x00\x00\x22" + si)

embed(
    flac_path, "flac",
    cover_data=cover_data, cover_mime="image/jpeg",
    lyric_text="[00:01.00]FLACtest",
    song_id=67890, song_title="TF", song_artist="AF",
    song_album="ALF", publish_time="2024-06-15 00:00:00",
)

flac = FLAC(flac_path)
check("FLAC title", flac.get("title", [""])[0] == "TF")
check("FLAC artist", flac.get("artist", [""])[0] == "AF")
check("FLAC album", flac.get("album", [""])[0] == "ALF")
check("FLAC copyright", flac.get("copyright", [""])[0] == "67890")
check("FLAC cover", len(flac.pictures) > 0)
check("FLAC lyrics", "FLACtest" in flac.get("lyrics", [""])[0])
os.remove(flac_path)

__import__("shutil").rmtree(TMP, ignore_errors=True)

failed = summary()
if __name__ == "__main__":
    raise SystemExit(failed)
