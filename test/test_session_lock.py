import threading

import pytest
import requests

from vncmd.core import config as config_mod
from vncmd.net import api as api_mod


@pytest.fixture(autouse=True)
def clean_session(monkeypatch):
    monkeypatch.setattr(api_mod, "_session", None)
    monkeypatch.setattr(
        config_mod, "COOKIE_FILE", __import__("pathlib").Path("/nonexistent")
    )
    yield


def test_并发调用只建一次session(monkeypatch):
    # 下载走线程池，多个 worker 会同时走到 _get_session，
    # 没锁时每个线程各建一个 Session，后建的把 cookie 覆盖掉
    built = []
    real = requests.Session

    def counting(*a, **kw):
        sess = real(*a, **kw)
        built.append(sess)
        # 拉长建 session 的窗口，让竞态更容易出现
        import time

        time.sleep(0.01)
        return sess

    monkeypatch.setattr(api_mod.requests, "Session", counting)

    got = []
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        got.append(api_mod._get_session())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(built) == 1, f"建了 {len(built)} 个 Session"
    assert len({id(s) for s in got}) == 1, "拿到的不是同一个 Session"


def test_已建好时直接返回同一个(monkeypatch):
    first = requests.Session()
    monkeypatch.setattr(api_mod, "_session", first)
    assert api_mod._get_session() is first
    assert api_mod._get_session() is first


def test_构建逻辑与取用分开(monkeypatch):
    # _build_session 单独可测，装配 Session 的过程不依赖全局状态
    monkeypatch.setattr(api_mod, "get_cookie", lambda: "A=1; B=2")
    sess = api_mod._build_session()
    assert sess.headers["User-Agent"].startswith("Mozilla")
    assert dict(sess.cookies)["A"] == "1"
    assert dict(sess.cookies)["B"] == "2"


def test_异常后不留半成品session(monkeypatch):
    # 建到一半失败时不能把半成品挂到全局，否则后续请求都拿它
    def boom():
        raise RuntimeError("cookie 读取炸了")

    monkeypatch.setattr(api_mod, "get_cookie", boom)
    with pytest.raises(RuntimeError):
        api_mod._get_session()
    assert api_mod._session is None
