"""校验工具缺失时的降级

三样工具各管一段，缺哪个只跳过那一段。以前整块门控开在调用方，
结果是装了 flac 没装 ffmpeg 的机器连 flac 那一步也一起不做。
"""

import subprocess
from functools import lru_cache
from unittest import mock

import pytest

from vncmd import checker


@pytest.fixture(autouse=True)
def tools(monkeypatch):
    """装上哪几样工具，返回一个设置函数"""

    def set_which(*names):
        wanted = set(names)
        monkeypatch.setattr(
            checker.shutil, "which", lambda n: "/usr/bin/" + n if n in wanted else None
        )
        checker.clear_check_tools_cache()

    return set_which


class Test工具探测:
    def test_三样分开判(self, tools):
        tools("ffprobe")
        assert checker.check_tools() == {
            "ffprobe": True,
            "ffmpeg": False,
            "flac": False,
        }

    def test_has_ffmpeg不再含ffprobe(self, tools):
        """以前 has_ffmpeg 是两个都要，那正是整块门控的由来"""
        tools("ffmpeg")
        assert checker.has_ffmpeg() is True
        assert checker.has_ffprobe() is False

    def test_any_check_tool(self, tools):
        tools()
        assert checker.any_check_tool() is False
        tools("flac")
        assert checker.any_check_tool() is True

    def test_missing顺序固定(self, tools):
        tools()
        assert checker.missing_check_tools() == ["ffprobe", "ffmpeg", "flac"]

    def test_加一样工具只需改一张表(self, tools, monkeypatch):
        """探测、提示文案、缓存清理全从 CHECK_TOOLS 派生。
        以前 check_tools() 与 clear_check_tools_cache() 各抄一份，
        只改其中一份时 missing_check_tools 会在运行中 KeyError"""
        calls = []

        @lru_cache(maxsize=1)
        def probe():
            calls.append(1)
            return False

        monkeypatch.setitem(
            checker.CHECK_TOOLS, "metaflac", (probe, "无损流元数据校验")
        )

        assert checker.check_tools()["metaflac"] is False
        assert "metaflac" in checker.missing_check_tools()
        assert "无损流元数据校验" in checker.describe_missing_check_tools()

        checker.clear_check_tools_cache()
        checker.check_tools()
        assert len(calls) == 2, "缓存清理漏了新加的那样工具"

    def test_每样工具都有探测函数与缺了会少做哪一步(self, tools):
        """漏了探测函数会在 check_tools 里 AttributeError，
        漏了说明会让提示变成「本次不会做。」这种空话"""
        for name, (probe, role) in checker.CHECK_TOOLS.items():
            assert callable(probe), name
            assert role.strip(), f"{name} 没有写它缺席时少做哪一步"


class Test提示文案:
    def test_三样都在时为空(self, tools):
        tools("ffprobe", "ffmpeg", "flac")
        assert checker.describe_missing_check_tools() == ""

    def test_只缺ffmpeg(self, tools):
        tools("ffprobe", "flac")
        msg = checker.describe_missing_check_tools()
        assert "ffmpeg" in msg
        assert "全量解码" in msg
        assert "ffprobe" not in msg.split("，")[0]
        assert "size 与 md5 的校验不受影响" in msg

    def test_全缺时三样都点到(self, tools):
        tools()
        msg = checker.describe_missing_check_tools()
        for name in ("ffprobe", "ffmpeg", "flac"):
            assert name in msg


class Test逐段降级:
    def _ok(self, _path):
        return ([], None)

    def test_全缺时直接放行(self, tools, tmp_path):
        """size 与 md5 已经对过了，一个工具都没有就没什么可做的"""
        tools()
        assert checker.check_audio(str(tmp_path / "a.flac")) == (True, "")

    def test_只装flac时flac仍被校验(self, tools, tmp_path):
        """这是整块门控挡住的那个场景：装了 flac 没装 ffmpeg 也要能验"""
        tools("flac")
        seen = []

        def fake_run(cmd, **kw):
            seen.append(cmd[0])
            return subprocess.CompletedProcess(cmd, 0, "", "")

        path = tmp_path / "a.flac"
        path.write_bytes(b"fLaC")
        with mock.patch.object(checker.subprocess, "run", fake_run):
            ok, msg = checker.check_audio(str(path))
        assert ok, msg
        assert seen == ["flac"]

    def test_只装ffprobe时ffprobe不算有工具(self, tools):
        """ffprobe 只给时长，要和 ffmpeg 的解码结果交叉比对才有意义。
        单独装它的话 check_audio 拿不到 actual，比对那步跳过，
        每首歌白 fork 一个 ffprobe 还一律放行"""
        tools("ffprobe")
        assert checker.any_check_tool() is False

    def test_只装flac时算有工具(self, tools):
        tools("flac")
        assert checker.any_check_tool() is True

    def test_ffmpeg与flac都缺才算没有(self, tools):
        tools("ffprobe")
        assert checker.any_check_tool() is False
        tools("ffprobe", "ffmpeg")
        assert checker.any_check_tool() is True

    def test_只装ffmpeg时不做flac那步(self, tools, tmp_path):
        tools("ffmpeg", "ffprobe")
        seen = []

        def fake_run(cmd, **kw):
            seen.append(cmd[0])
            return subprocess.CompletedProcess(cmd, 0, '{"format":{}}', "")

        path = tmp_path / "a.flac"
        path.write_bytes(b"fLaC")
        with mock.patch.object(checker.subprocess, "run", fake_run):
            ok, _msg = checker.check_audio(str(path))
        assert ok
        assert "flac" not in seen
        assert "ffmpeg" in seen

    def test_只装ffmpeg时跳过时长比对但不判失败(self, tools, tmp_path):
        """没有 ffprobe 就拿不到声明时长，那一步跳过，解码本身仍算通过"""
        tools("ffmpeg")

        def fake_run(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 0, "", "")

        path = tmp_path / "a.mp3"
        path.write_bytes(b"\xff\xfb")
        with mock.patch.object(checker.subprocess, "run", fake_run):
            ok, _msg = checker.check_audio(str(path))
        assert ok

    def test_ffmpeg起不来判失败(self, tools, tmp_path):
        """起不来不能当成通过，也不能当成「工具缺失」而跳过"""
        tools("ffmpeg", "ffprobe")

        def boom(cmd, **kw):
            raise OSError("No such file")

        path = tmp_path / "a.mp3"
        path.write_bytes(b"\xff\xfb")
        with mock.patch.object(checker.subprocess, "run", boom):
            ok, msg = checker.check_audio(str(path))
        assert not ok
        assert "无法运行 ffmpeg" in msg


class Test超时:
    def test_ffmpeg超时判失败(self, tools, tmp_path):
        tools("ffmpeg", "ffprobe")

        def slow(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 0))

        path = tmp_path / "a.mp3"
        path.write_bytes(b"\xff\xfb")
        with mock.patch.object(checker.subprocess, "run", slow):
            ok, msg = checker.check_audio(str(path))
        assert not ok, "超时被当成通过了"
        assert "超时" in msg

    def test_flac超时判失败(self, tools, tmp_path):
        tools("flac")

        def slow(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 0))

        path = tmp_path / "a.flac"
        path.write_bytes(b"fLaC")
        with mock.patch.object(checker.subprocess, "run", slow):
            ok, msg = checker.check_audio(str(path))
        assert not ok
        assert "超时" in msg
