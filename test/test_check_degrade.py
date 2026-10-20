"""校验工具缺失时的降级"""

import subprocess
from functools import lru_cache
from unittest import mock

import pytest

from vncmd.media import checker


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
        """has_ffmpeg 只判 ffmpeg，ffprobe 单独判"""
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
        """探测、提示文案、缓存清理全从 CHECK_TOOLS 派生
        两处各抄一份时，只改其中一份会让 missing_check_tools 出现 KeyError
        """
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
        """漏了探测函数会在 check_tools 里 AttributeError
        漏了说明会让提示只剩一句空话
        """
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
        """只装 flac 时 flac 那步仍要跑"""
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
        """起不来不能当成通过，也不能当成“工具缺失”而跳过"""
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


class Test三样都没有时放行:
    """check_audio 开头那道判断要与 any_check_tool 给出同一个答案
    两处写法不一致时差异只出现在“只装 ffprobe”，加一个调用点就会暴露
    """

    def test_只有ffprobe时不跑校验(self, tools, monkeypatch, tmp_path):
        """只装 ffprobe 时会白跑一次并给出假通过，比不做校验更坏"""
        跑过 = []
        monkeypatch.setattr(checker, "ffprobe_info", lambda p: 跑过.append(p))
        monkeypatch.setattr(
            checker,
            "check_tools",
            lambda: {"ffprobe": True, "ffmpeg": False, "flac": False},
        )
        f = tmp_path / "a.flac"
        f.write_bytes(b"x")
        assert checker.check_audio(str(f)) == (True, "")
        assert not 跑过, "没有能做校验的工具时不该 fork ffprobe"

    @pytest.mark.parametrize(
        ("装了", "该跑"),
        [
            ((), False),
            (("ffprobe",), False),
            (("ffmpeg",), True),
            (("flac",), True),
            (("ffprobe", "ffmpeg"), True),
            (("ffprobe", "flac"), True),
            (("ffprobe", "ffmpeg", "flac"), True),
        ],
    )
    def test_与any_check_tool问的是同一个问题(
        self, tools, 装了, 该跑, monkeypatch, tmp_path
    ):
        """两个函数对同一组工具要给同一个答案，不一致只在“只装 ffprobe”出现
        这里看 check_audio 有没有 fork ffprobe，解码本身不在验证范围
        """
        tools(*装了)
        assert checker.any_check_tool() is 该跑

        跑过 = []
        monkeypatch.setattr(checker, "ffprobe_info", lambda p: 跑过.append(p))
        f = tmp_path / "a.flac"
        f.write_bytes(b"x")
        checker.check_audio(str(f))
        # 没有可用校验工具时要立刻返回，fork ffprobe 也只能读时长而一律放行
        该fork = 该跑 and "ffprobe" in 装了
        assert bool(跑过) is 该fork, (
            f"ffmpeg/flac={该跑}、ffprobe={'ffprobe' in 装了}，"
            f"实际 fork 了 {bool(跑过)} 次"
        )


def _timeout_run(*_a, **kw):
    raise subprocess.TimeoutExpired(cmd="x", timeout=kw.get("timeout", 1))


def test_ffprobe超时返回空(monkeypatch):
    monkeypatch.setattr(checker.subprocess, "run", _timeout_run)
    assert checker.ffprobe_info("x.mp3") is None


def test_ffprobe超时时按超时值传下去(monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw)
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kw["timeout"])

    monkeypatch.setattr(checker.subprocess, "run", fake_run)
    checker.ffprobe_info("x.mp3")
    assert seen["timeout"] == 10


def test_ffprobe输出不是合法JSON(monkeypatch):
    class P:
        returncode = 0
        stdout = "not json"
        stderr = ""

    monkeypatch.setattr(checker.subprocess, "run", lambda *a, **k: P())
    assert checker.ffprobe_info("x.mp3") is None


def test_ffprobe输出是JSON数组(monkeypatch):
    class P:
        returncode = 0
        stdout = "[1, 2]"
        stderr = ""

    monkeypatch.setattr(checker.subprocess, "run", lambda *a, **k: P())
    assert checker.ffprobe_info("x.mp3") is None


def test_ffmpeg解码超时不能当成通过(monkeypatch):
    monkeypatch.setattr(checker.subprocess, "run", _timeout_run)
    errors, actual = checker.ffmpeg_decode("x.mp3")
    assert errors
    assert actual is None


def test_flac超时给可读原因(monkeypatch):
    monkeypatch.setattr(checker.shutil, "which", lambda n: "/usr/bin/flac")
    monkeypatch.setattr(checker.subprocess, "run", _timeout_run)
    assert checker.flac_test("x.flac") == "flac 校验超时"


def test_flac没有安装时返回空(monkeypatch):
    monkeypatch.setattr(checker.shutil, "which", lambda n: None)
    assert checker.flac_test("x.flac") is None


def test_子进程缺失不抛异常(monkeypatch):
    def boom(*_a, **_kw):
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr(checker.subprocess, "run", boom)
    assert checker.ffprobe_info("x.mp3") is None
