"""doctor 配置检查"""

import argparse
import sys
from pathlib import Path

import pytest

from vncmd import commands
from vncmd.core import config as config_mod
from vncmd.core.defaults import CONFIG_TOML


def ns(**kw):
    base = {"config_overrides": {}}
    base.update(kw)
    return argparse.Namespace(**base)


@pytest.fixture
def config_path(monkeypatch, tmp_path):
    path = tmp_path / "config.toml"
    monkeypatch.setattr(commands, "CONFIG_FILE", path)
    monkeypatch.setattr(config_mod, "CONFIG_FILE", path)
    return path


def _write(path: Path, text: str = CONFIG_TOML) -> None:
    path.write_text(text, encoding="utf-8")


class TestDoctor:
    def test_正常配置通过(self, config_path, capsys):
        _write(config_path)

        commands.cmd_doctor(ns())

        out = capsys.readouterr().out
        assert "状态：通过" in out
        assert "缺失 0 项" in out
        assert "错误 0 项" in out
        assert "未知配置项 0 项" in out

    def test_缺失项报告默认值(self, config_path, capsys):
        _write(config_path, CONFIG_TOML.replace("embed_track_id = true\n", ""))

        commands.cmd_doctor(ns())

        out = capsys.readouterr().out
        assert "缺失 1 项" in out
        assert "download.audio.embed_track_id = true" in out

    def test_坏类型失败(self, config_path, capsys):
        _write(config_path, CONFIG_TOML.replace("concurrency = 4", 'concurrency = "4"'))

        with pytest.raises(SystemExit) as exc:
            commands.cmd_doctor(ns())

        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "状态：失败" in out
        assert "错误 1 项" in out

    def test_未知项失败(self, config_path, capsys):
        _write(
            config_path,
            CONFIG_TOML.replace('curl_arg = ""', 'curl_arg = ""\nunknown = 1'),
        )

        with pytest.raises(SystemExit) as exc:
            commands.cmd_doctor(ns())

        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "未知配置项 1 项" in out
        assert "[download.unknown]" in out

    def test_配置文件缺失不创建(self, config_path, capsys):
        commands.cmd_doctor(ns())

        assert not config_path.exists()
        out = capsys.readouterr().out
        assert "状态：未找到" in out
        assert "首次运行时会写入默认配置" in out

    def test_config覆盖后不再算缺失(self, config_path, capsys):
        _write(config_path, CONFIG_TOML.replace("embed_track_id = true\n", ""))

        commands.cmd_doctor(
            ns(config_overrides={"download.audio.embed_track_id": True})
        )

        assert "缺失 0 项" in capsys.readouterr().out

    def test_config覆盖成坏值会失败(self, config_path, capsys):
        _write(config_path)

        with pytest.raises(SystemExit) as exc:
            commands.cmd_doctor(ns(config_overrides={"download.concurrency": 99}))

        assert exc.value.code == 1
        assert "错误 1 项" in capsys.readouterr().out


class TestParser:
    def test_doctor参数(self):
        from vncmd.cli import build_parser

        args = build_parser().parse_args(["doctor"])
        assert args.command == "doctor"

    def test_doctor不持锁也不校验配置(self, monkeypatch):
        import vncmd.cli as cli

        calls = []
        monkeypatch.setattr(cli, "acquire_lock", lambda: calls.append("lock"))
        monkeypatch.setattr(
            cli, "validate_config", lambda **kw: calls.append("validate")
        )
        monkeypatch.setattr(cli, "announce_account", lambda: calls.append("account"))
        monkeypatch.setattr(cli, "cmd_doctor", lambda _a: calls.append("doctor"))
        monkeypatch.setattr(sys, "argv", ["vncmd", "doctor"])

        cli.main()

        assert calls == ["doctor"]
