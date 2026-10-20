import pytest

from vncmd.core import config as config_mod


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setattr(config_mod, "VNCMD_HOME", h)
    return h


def cfg(download=None):
    c = {"download": {"dir": ""}}
    if download is not None:
        c["download"]["dir"] = download
    return c


def test_相对路径挂到配置目录下(home, monkeypatch):
    monkeypatch.setattr(config_mod, "_cfg", cfg(download="dl"))
    assert config_mod.get_download_dir() == str(home / "dl")


def _home() -> str:
    from pathlib import Path

    return str(Path.home())


def test_波浪号展开成用户主目录(home, monkeypatch):
    monkeypatch.setattr(config_mod, "_cfg", cfg(download="~/somewhere"))
    assert config_mod.get_download_dir() == _home() + "/somewhere"


def test_绝对路径不与配置目录拼接(home, monkeypatch):
    # 绝对路径直接使用，不依赖 pathlib 丢弃左操作数的行为
    monkeypatch.setattr(config_mod, "_cfg", cfg(download="/var/tmp/c"))
    assert config_mod.get_download_dir() == "/var/tmp/c"


def test_下载目录留空用默认位置(home, monkeypatch):
    monkeypatch.setattr(config_mod, "_cfg", cfg(download=""))
    from pathlib import Path

    assert config_mod.get_download_dir() == str(Path.home() / "Downloads" / "vncmd-dl")


def test_下载目录为波浪号时同样展开(home, monkeypatch):
    monkeypatch.setattr(config_mod, "_cfg", cfg(download="~/Music"))
    assert config_mod.get_download_dir() == _home() + "/Music"


def test_不存在的用户名不抛异常(home, monkeypatch):
    # os.path.expanduser 原样返回，Path.expanduser 会抛 RuntimeError
    monkeypatch.setattr(config_mod, "_cfg", cfg(download="~nobody_at_all/x"))
    assert config_mod.get_download_dir().endswith("~nobody_at_all/x")


def test_缓存固定在配置目录下(home, monkeypatch):
    """缓存位置只由 VNCMD_HOME 决定，不读配置；_cfg 为空时照样拿得到路径"""
    monkeypatch.setattr(config_mod, "_cfg", {})
    assert config_mod.get_cache_dir() == str(home / "cache")
