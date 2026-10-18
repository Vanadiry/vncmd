import pytest

from vncmd import config as config_mod


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
    # 原来靠 pathlib 遇到绝对右操作数会丢弃左边才碰巧正确，现在写明
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


def test_输出目录不挂配置目录(monkeypatch):
    # resolve_output_dir 对 -o 传的是用户真实意图，拼 VNCMD_HOME 就错了
    monkeypatch.setattr(config_mod, "VNCMD_HOME", "/nonexistent_home")
    assert config_mod.resolve_output_dir("~/Music") == _home() + "/Music"
    assert config_mod.resolve_output_dir("/abs/Music") == "/abs/Music"
    assert config_mod.resolve_output_dir("rel/Music") == "rel/Music"


def test_输出目录留空时回落到下载目录(home, monkeypatch):
    monkeypatch.setattr(config_mod, "_cfg", cfg(download="dl"))
    assert config_mod.resolve_output_dir(None) == str(home / "dl")


def test_输出目录波浪号不会建出名为波浪号的目录(monkeypatch, tmp_path):
    out = config_mod.resolve_output_dir("~/Music")
    assert "~" not in out.split("/")[0]
    assert str(tmp_path) not in out


def test_缓存固定在配置目录下(home, monkeypatch):
    """配置项拆掉之后，缓存位置只由 VNCMD_HOME 决定。

    故意把 _cfg 设成空的 —— 配置里连 [cache] 段都没有，
    照样能拿到路径，说明它已经不读配置了。
    原来那个键也得走 _user_path，那条路的三个坑（相对路径、波浪号展开、
    绝对路径）现在只剩 download.dir 需要
    """
    monkeypatch.setattr(config_mod, "_cfg", {})
    assert config_mod.get_cache_dir() == str(home / "cache")
