import os
import time
from pathlib import Path

import pytest

from vncmd.core import config as config_mod
from vncmd.net import cache as cache_mod


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

    from vncmd.core.defaults import CONFIG_TOML

    cfg = tomllib.loads(CONFIG_TOML)
    assert cfg["cache"]["ttl"] == 3


def test_旧配置没有ttl时用默认值(monkeypatch):
    monkeypatch.setattr(config_mod, "_cfg", {"cache": {"enabled": True}})
    assert config_mod.get_cache_ttl() == 3


def test_cache段里不再有dir():
    """dir 这个键拆掉了 —— 缓存固定在 VNCMD_HOME 下。

    留着它会让人以为改它有用，而它早就不被读了
    """
    import tomllib

    from vncmd.core.defaults import CONFIG_TOML

    assert "dir" not in tomllib.loads(CONFIG_TOML)["cache"]


@pytest.mark.parametrize("bad", ['"3"', "1.5", "true", "-1"])
def test_非法ttl被拦下(monkeypatch, tmp_path, bad):
    """ttl 写错类型要报出来

    这里必须用完整模板当基底、只替换 ttl 那一行。原来是把 cache 段
    单独写出来，那样有两个问题让它恒真：
    一是没写段头，写出的键落在顶层，cache.ttl 根本取不到值；
    二是用 repr() 拼值，布尔会写成 True 而 TOML 只认小写 true，
    整份文件在第一行就解析失败，于是走的是「解析失败」那条分支，
    ttl 的值从头到尾没被校验过 —— 撤掉 ttl 的校验它照样绿
    """
    from vncmd.core.defaults import CONFIG_TOML

    target = tmp_path / "config.toml"
    target.write_text(CONFIG_TOML.replace("ttl = 3", f"ttl = {bad}"), encoding="utf-8")
    monkeypatch.setattr(config_mod, "CONFIG_FILE", target)
    monkeypatch.setattr(config_mod, "_cfg", None)
    caught: list[list[str]] = []
    monkeypatch.setattr(config_mod, "_die", lambda lines: caught.append(list(lines)))
    config_mod.validate_config(quiet=True)
    assert any("ttl" in ln for 组 in caught for ln in 组), caught


def test_info_json不是合法JSON时按未命中处理(cached, capsys):
    # 坏文件不该让后续每次运行都崩，出声后退回重新拉取
    cache_mod.put_song(6, {"title": "x"})
    (cache_mod._song_dir(6) / "info.json").write_text("{坏", encoding="utf-8")
    assert cache_mod.get_song(6) is None
    assert "已损坏" in capsys.readouterr().err


def test_缓存文件损坏后能自愈(cached):
    # 返回 None 之后下一次写入会覆盖坏文件，不留死角
    cache_mod.put_song(7, {"title": "x"})
    (cache_mod._song_dir(7) / "info.json").write_text("{坏", encoding="utf-8")
    cache_mod.get_song(7)
    cache_mod.put_song(7, {"title": "y"})
    assert cache_mod.get_song(7) == {"title": "y"}
