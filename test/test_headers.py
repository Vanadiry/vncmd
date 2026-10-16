import pytest
import requests

from function import api as api_mod
from function import download as download_mod


@pytest.fixture(autouse=True)
def fresh_sessions(monkeypatch, tmp_path):
    monkeypatch.setattr(api_mod, "_session", None)
    monkeypatch.setattr(download_mod, "_dl_session", None)
    monkeypatch.setattr(api_mod, "get_cookie", lambda: "")
    yield


def test_两个session的UA一致():
    # 调 API 伪装浏览器、下载音频自曝为脚本，两边行为分裂会让 CDN 侧的风控口径不一致
    a = api_mod._get_session().headers
    d = download_mod._get_dl_session().headers
    assert a["User-Agent"] == d["User-Agent"]
    assert "Mozilla" in d["User-Agent"]
    assert "python-requests" not in d["User-Agent"]


def test_下载session带上Referer():
    d = download_mod._get_dl_session().headers
    assert d.get("Referer") == "https://music.163.com/"


def test_下载session保留自己的重试配置():
    d = download_mod._get_dl_session()
    adapter = d.get_adapter("https://music.163.com")
    assert adapter.max_retries.total == 3


def test_两个session各自独立():
    # 不能因为复用了请求头就变成同一个对象，cookie 与连接池要隔离
    assert api_mod._get_session() is not download_mod._get_dl_session()


def test_BASE_URL已私有化():
    # 与 _DETAIL_BATCH_SIZE 等内部常量统一前缀
    assert not hasattr(api_mod, "BASE_URL")
    assert api_mod._BASE_URL == "https://music.163.com"


def test_默认UA确实不是浏览器UA():
    assert requests.Session().headers["User-Agent"].startswith("python-requests")
