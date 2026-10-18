"""下载传输的超时设定

读超时踩过坑：原先 10 秒对 25 MB 单连接过于激进，传输中卡一下就被整个掐断，
真实下载时反复命中 ReadTimeout。这些测试把取值钉住，避免被顺手改回去。
"""

import inspect

import pytest

from vncmd.net.download import _get_dl_session


class _Resp:
    def __init__(self):
        self.status_code = 200
        self.headers = {"content-length": "4", "content-type": "audio/flac"}

    def iter_content(self, chunk_size=0):
        assert chunk_size, "流式下载必须带 chunk_size，否则会整块进内存"
        yield b"fLaC"

    def close(self):
        pass


class _Session:
    """记录调用参数，顺带返回一段像样的音频"""

    def __init__(self):
        self.timeout = None
        self.calls = 0

    def get(self, _url, **kwargs):
        self.timeout = kwargs.get("timeout")
        self.calls += 1
        return _Resp()


@pytest.fixture
def session(monkeypatch, tmp_path):
    import vncmd.net.download as dl

    fake = _Session()
    monkeypatch.setattr(dl, "_get_dl_session", lambda: fake)
    monkeypatch.setattr(dl, "get_downloader", lambda: "builtin")
    return fake, str(tmp_path / "a.flac")


def test_read_timeout_is_thirty_seconds(session, monkeypatch):
    import vncmd.net.download as dl

    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    fake, path = session
    assert dl.fetch_audio("http://x/a.flac", path, "T", use_curl=False) is None
    connect, read = fake.timeout
    assert connect == 15, "连接超时不该动"
    assert read == 30, f"读超时是 {read} 秒，太紧会把长连接掐断"


def test_read_timeout_matches_curl_speed_floor(session, monkeypatch):
    """两条路径对卡死的容忍度应当相当，curl 侧是 --speed-time 30"""
    import vncmd.net.download as dl

    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    fake, path = session
    dl.fetch_audio("http://x/a.flac", path, "T", use_curl=False)
    assert fake.timeout[1] == 30

    argv = dl._curl_argv("http://x/a.flac", path)
    assert argv[argv.index("--speed-time") + 1] == "30"


def test_builtin_still_retries_on_server_errors():
    """放宽读超时是改传输层的容错，不该动 5xx 的重试策略"""
    adapter = _get_dl_session().get_adapter("https://music.163.com")
    assert adapter.max_retries.total == 3
    assert 500 in adapter.max_retries.status_forcelist


def test_no_other_tight_timeouts_in_transfer_path():
    """封面对歌词用的是整请求超时，与流式读超时是两回事，别被一起改掉"""
    import vncmd.net.download as dl

    # 读超时现在住在续传循环里，不再在 fetch_audio 本体
    src = inspect.getsource(dl._fetch_audio_builtin)
    assert "timeout=(15, 30)" in src
    assert "timeout=(15, 10)" not in src
