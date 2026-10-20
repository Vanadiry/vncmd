"""校验工具 stderr 的解码与报错路径"""

import subprocess
from unittest import mock

import pytest

from vncmd.media import checker

# ffmpeg 打不开文件时把完整路径写进 stderr，这段为 UTF-8
FFMPEG_ERR = (
    b"Error opening input file "
    b"/tmp/x/\xe6\xae\x8b\xe6\x9c\x88-\xe3\x82\xab\xe3\x83\xaf\xe3\x82\xa4.mp3.\n"
)


@pytest.fixture(autouse=True)
def tools(monkeypatch):
    monkeypatch.setattr(
        checker.shutil, "which", lambda n: "/usr/bin/" + n if n else None
    )
    checker.clear_check_tools_cache()
    yield
    checker.clear_check_tools_cache()


def _run_returning(stderr: bytes, code: int):
    """模拟 subprocess 带 encoding 参数时的返回：stderr 已是解码后的 str"""

    def fake_run(cmd, **kw):
        # 断言参数本身：encoding 与 errors 必须显式给，不能靠 locale
        assert kw.get("encoding") == "utf-8", f"{cmd[0]} 没指定 encoding"
        assert kw.get("errors") == "replace", f"{cmd[0]} 没指定 errors"
        assert "text" not in kw, f"{cmd[0]} 还在用 text=True"
        return subprocess.CompletedProcess(
            cmd, code, "", stderr.decode("utf-8", errors="replace")
        )

    return fake_run


class Test解码:
    def test_ffprobe的stderr有中文也不抛(self, tmp_path):
        p = tmp_path / "残月-カワイヒデヒロ.mp3"
        p.write_bytes(b"\xff\xfb")
        with mock.patch.object(
            checker.subprocess, "run", _run_returning(FFMPEG_ERR, 1)
        ):
            assert checker.ffprobe_info(str(p)) is None

    def test_ffmpeg的stderr有中文也不抛(self, tmp_path):
        p = tmp_path / "残月-カワイヒデヒロ.mp3"
        p.write_bytes(b"\xff\xfb")
        with mock.patch.object(
            checker.subprocess, "run", _run_returning(FFMPEG_ERR, 1)
        ):
            errors, _ = checker.ffmpeg_decode(str(p))
        assert errors and "Error opening input file" in errors[0]

    def test_flac的stderr有中文也不抛(self, tmp_path):
        p = tmp_path / "残月.flac"
        p.write_bytes(b"fLaC")
        with mock.patch.object(
            checker.subprocess, "run", _run_returning(FFMPEG_ERR, 1)
        ):
            assert checker.flac_test(str(p)) is not None

    def test_check_audio整条路都不抛(self, tmp_path):
        """UnicodeDecodeError 抛给调用方时，downloader 的兜底 except 只说一句 codec 出错
        用户看不出原因，坏文件还留在 _temp 里
        """
        p = tmp_path / "残月-カワイヒデヒロ.mp3"
        p.write_bytes(b"\xff\xfb")
        with mock.patch.object(
            checker.subprocess, "run", _run_returning(FFMPEG_ERR, 1)
        ):
            ok, msg = checker.check_audio(str(p))
        assert not ok
        assert "codec" not in msg


class Test报错带文件名:
    def test_解码出错带文件名(self, tmp_path):
        p = tmp_path / "残月-カワイヒデヒロ.mp3"
        p.write_bytes(b"\xff\xfb")
        with mock.patch.object(
            checker.subprocess, "run", _run_returning(b"Invalid data found", 1)
        ):
            _ok, msg = checker.check_audio(str(p))
        assert "残月-カワイヒデヒロ.mp3" in msg

    def test_flac校验失败带文件名(self, tmp_path):
        p = tmp_path / "有種.flac"
        p.write_bytes(b"fLaC")

        def fake_run(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 1, "", "MD5 signature mismatch")

        with mock.patch.object(checker.subprocess, "run", fake_run):
            _ok, msg = checker.check_audio(str(p))
        assert "有種.flac" in msg
        assert "MD5 signature mismatch" in msg

    def test_截断带文件名(self, tmp_path):
        p = tmp_path / "短い曲.mp3"
        p.write_bytes(b"\xff\xfb")

        def fake_run(cmd, **kw):
            if cmd[0] == "ffprobe":
                return subprocess.CompletedProcess(
                    cmd, 0, '{"format":{"duration":"300.0"}}', ""
                )
            return subprocess.CompletedProcess(
                cmd, 0, "", "size=  1000kB time=00:00:30.00"
            )

        with mock.patch.object(checker.subprocess, "run", fake_run):
            _ok, msg = checker.check_audio(str(p))
        assert "短い曲.mp3" in msg
        assert "疑似截断" in msg
