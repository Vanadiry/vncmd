"""--check 开关与 [download] check 配置的优先级"""

import pytest

from function import downloader
from function.config import get_check_enabled
from test.test_verify_order import AUDIO, run


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """记录解码校验是否被调用，并把 md5 校验固定成能通过"""
    calls = []

    def fake_fetch_audio(
        url, path, label, progress=None, task_id=None, total=0, use_curl=None
    ):
        with open(path, "wb") as f:
            f.write(AUDIO)
        return

    monkeypatch.setattr(downloader, "fetch_audio", fake_fetch_audio)
    monkeypatch.setattr(
        downloader, "check_audio", lambda _p: (calls.append("audio"), (True, ""))[1]
    )
    monkeypatch.setattr(downloader, "fetch_cover", lambda *_a, **_k: None)
    monkeypatch.setattr(downloader, "embed_metadata", lambda *_a, **_k: None)
    monkeypatch.setattr(downloader, "has_ffmpeg", lambda: True)
    return calls, str(tmp_path)


def test_flag_on_forces_decode(harness, monkeypatch):
    """--check 传了就一定要解码，哪怕配置是关的"""
    calls, tmp = harness
    monkeypatch.setattr(downloader, "get_check_enabled", lambda: False)
    ok, _msg, _ = run(tmp, run_check=True)
    assert ok
    assert calls == ["audio"]


def test_flag_absent_falls_back_to_config(harness, monkeypatch):
    """没传标志时必须读配置，不能当成关掉——那是 store_true 的老陷阱"""
    calls, tmp = harness
    monkeypatch.setattr(downloader, "get_check_enabled", lambda: True)
    ok, _msg, _ = run(tmp, run_check=None)
    assert ok
    assert calls == ["audio"]


def test_config_off_skips_decode(harness, monkeypatch):
    calls, tmp = harness
    monkeypatch.setattr(downloader, "get_check_enabled", lambda: False)
    ok, _msg, _ = run(tmp, run_check=None)
    assert ok
    assert calls == []


def test_explicit_false_beats_config_on(harness, monkeypatch):
    """显式关掉要能压过配置，这是命令行覆盖配置的应有之义"""
    calls, tmp = harness
    monkeypatch.setattr(downloader, "get_check_enabled", lambda: True)
    ok, _msg, _ = run(tmp, run_check=False)
    assert ok
    assert calls == []


def test_missing_ffmpeg_skips_decode_even_when_on(harness, monkeypatch):
    """开关打开但没装 ffmpeg 时自动降级，不能因此判失败"""
    calls, tmp = harness
    monkeypatch.setattr(downloader, "has_ffmpeg", lambda: False)
    ok, _msg, _ = run(tmp, run_check=True)
    assert ok
    assert calls == []


def test_md5_runs_regardless_of_check_flag(harness, monkeypatch):
    """size 与 md5 的校验不受开关影响，没装 ffmpeg 的用户靠它"""
    calls, tmp = harness
    monkeypatch.setattr(downloader, "get_check_enabled", lambda: False)
    seen = []
    from function.checker import check_md5 as real

    def spy(path, md5, size=0):
        seen.append("md5")
        return real(path, md5, size)

    monkeypatch.setattr(downloader, "check_md5", spy)
    ok, _msg, _ = run(tmp, run_check=False)
    assert ok
    assert seen == ["md5"]
    assert calls == []


class TestConfigGetter:
    def test_missing_key_defaults_on(self, monkeypatch):
        """老用户的配置文件里没有这个键，不能因此关掉校验"""
        monkeypatch.setattr(
            "function.config._get_cfg", lambda: {"download": {"dir": ""}}
        )
        assert get_check_enabled() is True

    def test_explicit_false_respected(self, monkeypatch):
        monkeypatch.setattr(
            "function.config._get_cfg", lambda: {"download": {"check": False}}
        )
        assert get_check_enabled() is False

    def test_explicit_true_respected(self, monkeypatch):
        monkeypatch.setattr(
            "function.config._get_cfg", lambda: {"download": {"check": True}}
        )
        assert get_check_enabled() is True


class TestParser:
    def _parse(self, argv):
        from vncmd import build_parser

        return build_parser().parse_args(argv)

    @pytest.mark.parametrize("cmd", ["song", "album", "playlist"])
    def test_flag_present_is_true(self, cmd):
        args = self._parse([cmd, "123", "--check"])
        assert args.check is True

    @pytest.mark.parametrize("cmd", ["song", "album", "playlist"])
    def test_flag_absent_is_none(self, cmd):
        """必须是 None 而不是 False，否则配置文件永远没机会生效"""
        args = self._parse([cmd, "123"])
        assert args.check is None
