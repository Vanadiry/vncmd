import json
import os
import time
from pathlib import Path

import pytest

from function import cache as cache_mod
from function import config as config_mod


@pytest.fixture
def cached(tmp_path, monkeypatch):
    """把缓存目录指到临时位置，ttl 交给测试控制"""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(
        config_mod, "_cfg", {"cache": {"dir": "cache", "ttl": 3, "enabled": True}}
    )
    monkeypatch.setattr(config_mod, "VNCMD_HOME", home)
    monkeypatch.setattr(config_mod, "is_cache_enabled", lambda: True)
    monkeypatch.setattr(config_mod, "get_cache_dir", lambda: str(home / "cache"))
    monkeypatch.setattr(cache_mod, "is_cache_enabled", lambda: True)
    monkeypatch.setattr(cache_mod, "get_cache_dir", lambda: str(home / "cache"))
    return home


def _age(path: Path, days: float) -> None:
    """把文件的修改时间往前挪，模拟放置了 days 天"""
    t = time.time() - days * 86400
    os.utime(path, (t, t))


def test_新建的缓存命中(cached):
    cache_mod.put_song(1, {"title": "x"})
    assert cache_mod.get_song(1) == {"title": "x"}


def test_超过有效期视为未命中(cached):
    cache_mod.put_song(1, {"title": "x"})
    _age(cache_mod._song_dir(1) / "info.json", 4)
    assert cache_mod.get_song(1) is None


def test_未超有效期仍命中(cached):
    cache_mod.put_song(1, {"title": "x"})
    _age(cache_mod._song_dir(1) / "info.json", 2)
    assert cache_mod.get_song(1) == {"title": "x"}


def test_ttl为零永不过期(cached, monkeypatch):
    monkeypatch.setattr(cache_mod, "get_cache_ttl", lambda: 0)
    cache_mod.put_song(1, {"title": "x"})
    _age(cache_mod._song_dir(1) / "info.json", 3650)
    assert cache_mod.get_song(1) == {"title": "x"}


def test_歌词同样受有效期约束(cached):
    cache_mod.put_lyrics(2, {"lrc": {"lyric": "a"}, "tlyric": {"lyric": "b"}})
    _age(cache_mod._song_dir(2) / "lyric.lrc", 4)
    assert cache_mod.get_lyrics(2) is None


def test_翻译变空时删掉旧文件(cached):
    # 不删的话 get_lyrics 会一直读到上一次的翻译
    cache_mod.put_lyrics(3, {"lrc": {"lyric": "a"}, "tlyric": {"lyric": "旧翻译"}})
    tpath = cache_mod._song_dir(3) / "tlyric.lrc"
    assert tpath.exists()

    cache_mod.put_lyrics(3, {"lrc": {"lyric": "a"}, "tlyric": {"lyric": ""}})
    assert not tpath.exists()
    assert cache_mod.get_lyrics(3)["tlyric"]["lyric"] == ""


def test_翻译非空时正常写入(cached):
    cache_mod.put_lyrics(4, {"lrc": {"lyric": "a"}, "tlyric": {"lyric": "新翻译"}})
    assert cache_mod.get_lyrics(4)["tlyric"]["lyric"] == "新翻译"


def test_默认配置含ttl():
    import tomllib

    from function._defaults import CONFIG_TOML

    cfg = tomllib.loads(CONFIG_TOML)
    assert cfg["cache"]["ttl"] == config_mod.DEFAULT_CACHE_TTL == 3


def test_旧配置没有ttl时用默认值(monkeypatch):
    monkeypatch.setattr(config_mod, "_cfg", {"cache": {"dir": "cache"}})
    assert config_mod.get_cache_ttl() == 3


@pytest.mark.parametrize("bad", ["3", 1.5, True, -1])
def test_非法ttl被拦下(monkeypatch, tmp_path, bad):
    import tomllib

    from function._defaults import CONFIG_TOML

    cfg = tomllib.loads(CONFIG_TOML)
    cfg["cache"]["ttl"] = bad
    target = tmp_path / "config.toml"
    target.write_text(
        "\n".join(f"{k} = {v!r}" for k, v in cfg["cache"].items()), encoding="utf-8"
    )
    monkeypatch.setattr(config_mod, "CONFIG_FILE", target)
    monkeypatch.setattr(config_mod, "_cfg", None)
    with pytest.raises(SystemExit):
        config_mod.validate_config(quiet=True)


def test_info_json不是合法JSON会抛(cached):
    # 读端的容错归 #26，这里锁住当前行为不被顺手改掉
    cache_mod.put_song(6, {"title": "x"})
    (cache_mod._song_dir(6) / "info.json").write_text("{坏", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        cache_mod.get_song(6)
