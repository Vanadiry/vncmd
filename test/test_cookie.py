import pytest

from vncmd.core import config as config_mod
from vncmd.net import api as api_mod


@pytest.fixture
def session(monkeypatch, tmp_path):
    """写一个 cookie 文件，返回装好 cookie 的 session"""

    def _build(cookie: str):
        monkeypatch.setattr(config_mod, "COOKIE_FILE", tmp_path / "cookie")
        (tmp_path / "cookie").write_text(cookie, encoding="utf-8")
        monkeypatch.setattr(api_mod, "_session", None)
        return {c.name: c.value for c in api_mod._get_session().cookies}

    return _build


def test_正常cookie照常设置(session):
    assert session("MUSIC_U=abc123; __csrf=xyz") == {
        "MUSIC_U": "abc123",
        "__csrf": "xyz",
    }


def test_非latin1的值被跳过而不是截断(session, capsys):
    # 截断会把 MUSIC_U=你好世界 变成 MUSIC_U=，网易云认不出用户
    # 表现为登录态看着有却不生效
    got = session("MUSIC_U=你好世界; __csrf=ok")
    assert got == {"__csrf": "ok"}
    assert "MUSIC_U" not in got


def test_跳过时会出声(session, capsys):
    session("MUSIC_U=你好世界")
    out = capsys.readouterr().err
    assert "非 latin-1" in out
    # 要指明哪个 Cookie，否则用户不知道该改哪一条
    assert "MUSIC_U" in out


def test_一个坏值不影响其余(session):
    got = session("GOOD=abc; BAD=中文值; __csrf=ok")
    assert got == {"GOOD": "abc", "__csrf": "ok"}


def test_正常值不产生警告(session, capsys):
    session("MUSIC_U=abc123")
    assert capsys.readouterr().out == ""


def test_值里有等号只切第一个(session):
    assert session("A=B=C") == {"A": "B=C"}


def test_空值不设置(session):
    assert session("EMPTY=; __csrf=ok") == {"__csrf": "ok"}


def test_没有等号的片段跳过(session):
    assert session("garbage; __csrf=ok") == {"__csrf": "ok"}


def test_url编码过的中文仍可设置(session):
    # 浏览器复制出来的 Cookie 为 URL 编码后的 ASCII，不该被拦
    assert session("MUSIC_U=%E4%BD%A0%E5%A5%BD") == {"MUSIC_U": "%E4%BD%A0%E5%A5%BD"}


def test_没有cookie文件时为空(session, tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "COOKIE_FILE", tmp_path / "none")
    monkeypatch.setattr(api_mod, "_session", None)
    assert dict(api_mod._get_session().cookies) == {}
