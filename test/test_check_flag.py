"""run_check 参数与 [download] check 配置的优先级

命令行那个 --check 已经收了，现在只走 --config download.check。
但 download_song 这个参数还在，这几条测试守的是它的语义：
None 表示按配置走，True / False 表示显式压过配置。
"""

import pytest

from test.test_verify_order import AUDIO, run
from vncmd import downloader
from vncmd.core.config import get_check_enabled


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
    monkeypatch.setattr(downloader, "any_check_tool", lambda: True)
    return calls, str(tmp_path)


def test_flag_on_forces_decode(harness, monkeypatch):
    """显式传 True 就一定要解码，哪怕配置是关的"""
    calls, tmp = harness
    monkeypatch.setattr(downloader, "get_check_enabled", lambda: False)
    ok, _msg, _ = run(tmp, run_check=True)
    assert ok
    assert calls == ["audio"]


def test_flag_absent_falls_back_to_config(harness, monkeypatch):
    """传 None 时必须读配置，不能当成关掉 —— 那是 store_true 的老陷阱"""
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
    """显式关掉要能压过配置，这是覆盖的应有之义"""
    calls, tmp = harness
    monkeypatch.setattr(downloader, "get_check_enabled", lambda: True)
    ok, _msg, _ = run(tmp, run_check=False)
    assert ok
    assert calls == []


def test_missing_ffmpeg_skips_decode_even_when_on(harness, monkeypatch):
    """开关打开但没装 ffmpeg 时自动降级，不能因此判失败"""
    calls, tmp = harness
    monkeypatch.setattr(downloader, "any_check_tool", lambda: False)
    ok, _msg, _ = run(tmp, run_check=True)
    assert ok
    assert calls == []


def test_md5_runs_regardless_of_check_flag(harness, monkeypatch):
    """size 与 md5 的校验不受开关影响，没装 ffmpeg 的用户靠它"""
    calls, tmp = harness
    monkeypatch.setattr(downloader, "get_check_enabled", lambda: False)
    seen = []
    from vncmd.media.checker import check_md5 as real

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
            "vncmd.core.config._get_cfg", lambda: {"download": {"dir": ""}}
        )
        assert get_check_enabled() is True

    def test_explicit_false_respected(self, monkeypatch):
        monkeypatch.setattr(
            "vncmd.core.config._get_cfg", lambda: {"download": {"check": False}}
        )
        assert get_check_enabled() is False

    def test_explicit_true_respected(self, monkeypatch):
        monkeypatch.setattr(
            "vncmd.core.config._get_cfg", lambda: {"download": {"check": True}}
        )
        assert get_check_enabled() is True


class TestParser:
    """--check 不再是命令行参数

    它与配置项 download.check 干的是同一件事，两条路并存只会让
    「为什么我传了 --check 却没生效」这种问题多一个来源。
    现在只走 --config，而它比原来那个开关更完整 ——
    原来的 --check 只能开不能关。
    """

    def _parse(self, argv):
        from vncmd.cli import build_parser

        return build_parser().parse_args(argv)

    @pytest.mark.parametrize("cmd", ["song", "album", "playlist"])
    def test_check_arg不再接受(self, cmd):
        with pytest.raises(SystemExit) as e:
            self._parse([cmd, "123", "--check"])
        assert e.value.code == 2

    @pytest.mark.parametrize("cmd", ["song", "album", "playlist"])
    def test_check走config(self, cmd):
        args = self._parse(["--config", "download.check=true", cmd, "123"])
        assert args.config == ["download.check=true"]

    def test_cookie的check还在(self):
        """cookie --check 是「只查状态不写文件」，与下载校验无关，不受影响"""
        assert self._parse(["cookie", "--check"]).check is True


class Test命令行不再单独传校验开关:
    """--check 收了之后，commands 必须传 None 让配置说了算

    传 False 会变成「永远不解码」，传 True 会变成「永远解码」，
    两种都是把配置项架空 —— 而这条路上原来正好有 args.check，
    删参数时最容易顺手写成 args.check or False
    """

    def _捕获(self, monkeypatch, tmp_path):
        from vncmd import commands

        看到 = {}
        monkeypatch.setattr(
            commands,
            "get_song_details",
            lambda _i: {
                "id": 1,
                "title": "T",
                "artist": "A",
                "album": "B",
                "cover": "",
                "publish_time": "",
            },
        )
        monkeypatch.setattr(commands, "get_download_content", lambda: "a")
        monkeypatch.setattr(commands, "get_download_dir", lambda: str(tmp_path))
        monkeypatch.setattr(commands, "make_session_dir", lambda d: str(tmp_path))
        monkeypatch.setattr(commands, "display_song_detail", lambda *_a, **_k: None)
        monkeypatch.setattr(commands, "get_lyrics_url", lambda _i: "")
        monkeypatch.setattr(commands, "info", lambda *_a, **_k: None)
        monkeypatch.setattr(commands, "success", lambda *_a, **_k: None)
        monkeypatch.setattr(commands, "error", lambda *_a, **_k: None)

        class 假音源:
            url, size, md5, level = "http://x/a.flac", 0, "", "lossless"

        monkeypatch.setattr(commands, "get_audio_source", lambda *_a, **_k: 假音源())
        monkeypatch.setattr(
            commands,
            "download_song",
            lambda **kw: (看到.update(kw), (True, "", None))[1],
        )
        return 看到

    def test_run_check传None(self, monkeypatch, tmp_path):
        import argparse

        from vncmd import commands

        看到 = self._捕获(monkeypatch, tmp_path)
        commands.cmd_song(
            argparse.Namespace(
                id=1,
                json=False,
                dlink=False,
                lyric=False,
                translate=False,
                download=True,
            )
        )
        assert 看到["run_check"] is None, (
            "传 True / False 都会把配置项架空，只有 None 表示「按配置走」"
        )

    def test_use_curl传None(self, monkeypatch, tmp_path):
        import argparse

        from vncmd import commands

        看到 = self._捕获(monkeypatch, tmp_path)
        commands.cmd_song(
            argparse.Namespace(
                id=1,
                json=False,
                dlink=False,
                lyric=False,
                translate=False,
                download=True,
            )
        )
        assert 看到["use_curl"] is None


class Test音质名给人看那个:
    def test_返回配置里写的名字(self, monkeypatch):
        """提示里印 2147483647 没人看得懂，要印 max"""
        from vncmd.core import config as config_mod

        monkeypatch.setattr(
            config_mod, "_cfg", {"download": {"audio": {"quality": "max"}}}
        )
        assert config_mod.get_quality_name() == "max"
        assert config_mod.get_quality() == 2147483647

    def test_缺键时回落默认(self, monkeypatch):
        from vncmd.core import config as config_mod

        monkeypatch.setattr(config_mod, "_cfg", {})
        assert config_mod.get_quality_name() == "max"
