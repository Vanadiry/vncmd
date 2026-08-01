from pathlib import Path
import pytest
from function.checker import has_ffmpeg, has_flac, check_audio, ffprobe_info


def _gen_valid_flac(path: Path) -> None:
    import subprocess

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            "0.5",
            "-acodec",
            "flac",
            str(path),
        ],
        capture_output=True,
        check=True,
    )


class TestChecker:
    def test_has_ffmpeg(self):
        assert isinstance(has_ffmpeg(), bool)

    def test_has_flac(self):
        assert isinstance(has_flac(), bool)

    @pytest.mark.skipif(not has_ffmpeg(), reason="需要 ffmpeg")
    def test_check_valid_flac(self, temp_dir):
        flac_path = Path(temp_dir) / "valid.flac"
        _gen_valid_flac(flac_path)
        ok, msg = check_audio(str(flac_path))
        assert ok, msg

    @pytest.mark.skipif(not has_ffmpeg(), reason="需要 ffmpeg")
    def test_check_corrupted(self, temp_dir):
        bad_path = Path(temp_dir) / "bad.mp3"
        bad_path.write_bytes(b"this is not audio at all")
        ok, msg = check_audio(str(bad_path))
        assert not ok

    @pytest.mark.skipif(not has_ffmpeg(), reason="需要 ffmpeg")
    def test_ffprobe_info(self, temp_dir):
        flac_path = Path(temp_dir) / "valid.flac"
        _gen_valid_flac(flac_path)
        info = ffprobe_info(str(flac_path))
        assert info is not None
        assert info["duration"] is not None
        assert info["duration"] > 0
