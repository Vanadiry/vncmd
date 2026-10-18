"""断流后按 Range 续传

CDN 实测支持 Accept-Ranges: bytes，续传比从零重下省流量。
关键在三条边界：服务端不认 Range 时会回 200 而不是 206；
curl 对这种情况退出码 33 且不会自己从头来；续传段的魔数不该再验。
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest

from vncmd import download


def _read(p):
    with open(p, "rb") as f:
        return f.read()


_HTML_HEADERS = {"content-type": "text/html", "content-length": "5"}
PAYLOAD = b"fLaC" + bytes(range(256)) * 200  # 51209 字节
CUT_AT = 20000


class _Server:
    """可控的本地源，支持在指定字节处掐断或完全无视 Range"""

    def __init__(self, respect_range=True, cut_once=False):
        self.respect_range = respect_range
        self.cut_once = cut_once
        self.requests = []
        self.served = 0
        outer = self

        class H(BaseHTTPRequestHandler):
            # 必须用 1.0：1.1 会保持连接，requests 的 session 一直不放手，
            # handler 就阻塞在等下一个请求上，shutdown() 永远等不到
            protocol_version = "HTTP/1.0"

            def do_GET(self):
                rng = self.headers.get("Range")
                outer.requests.append(rng)
                start = 0
                if outer.respect_range and rng and rng.startswith("bytes="):
                    start = int(rng[6:].split("-")[0])
                body = PAYLOAD[start:]
                if outer.cut_once and outer.served == 0:
                    outer.served = 1
                    # 声称发全量却只给一半再挂断，这才是真实的断流；
                    # 若 Content-Length 按实际给的量写，客户端会以为传输正常完成
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(PAYLOAD)))
                    self.end_headers()
                    self.wfile.write(body[:CUT_AT])
                    self.wfile.flush()
                    self.close_connection = True
                    self.connection.close()
                    return
                if start:
                    self.send_response(206)
                    self.send_header(
                        "Content-Range",
                        f"bytes {start}-{len(PAYLOAD) - 1}/{len(PAYLOAD)}",
                    )
                else:
                    self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.httpd.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/a.bin"

    def __enter__(self):
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(download.time, "sleep", lambda _s: None)


@pytest.fixture
def dst(tmp_path):
    return str(tmp_path / "out.flac")


class TestBuiltinResume:
    def test_断流后续上传齐(self, dst):
        with _Server(cut_once=True) as s:
            err = download._fetch_audio_builtin(
                s.url, dst, "T", expect_total=len(PAYLOAD)
            )
        assert err is None, err
        assert _read(dst) == PAYLOAD

    def test_续传请求带了Range(self, dst):
        with _Server(cut_once=True) as s:
            download._fetch_audio_builtin(s.url, dst, "T", expect_total=len(PAYLOAD))
        assert s.requests[0] is None
        offset = int(s.requests[1][len("bytes=") :].split("-")[0])
        # 偏移量取磁盘上的真实大小：连接断在块边界，落盘的可能少于服务端给的量
        assert 0 < offset <= CUT_AT
        assert offset % 8192 == 0, "偏移应是已落盘的完整块"

    def test_续传省下的流量看得见(self, dst):
        """第二次只取剩下的部分，总传输量小于全量两遍"""
        with _Server(cut_once=True) as s:
            download._fetch_audio_builtin(s.url, dst, "T", expect_total=len(PAYLOAD))
        total_served = CUT_AT + (len(PAYLOAD) - CUT_AT)
        assert total_served < len(PAYLOAD) * 2

    def test_服务端不认Range时从头写(self, dst):
        """回 200 而不是 206 时必须丢弃已有内容，不能追加出坏文件"""
        with _Server(respect_range=False, cut_once=True) as s:
            err = download._fetch_audio_builtin(s.url, dst, "T")
        assert err is None, err
        assert _read(dst) == PAYLOAD, "追加会拼出损坏的文件"

    def test_已有完整文件时不发请求(self, dst):
        with open(dst, "wb") as f:
            f.write(PAYLOAD)
        with _Server() as s:
            assert (
                download._fetch_audio_builtin(
                    s.url, dst, "T", expect_total=len(PAYLOAD)
                )
                is None
            )
        assert s.requests == []

    def test_续传段不再验魔数(self, dst):
        """续传段不是文件开头，拿它当文件头验会误判"""
        with open(dst, "wb") as f:
            f.write(PAYLOAD[:CUT_AT])
        with _Server() as s:
            err = download._fetch_audio_builtin(
                s.url, dst, "T", expect_total=len(PAYLOAD)
            )
        assert err is None, err

    def test_三次都失败才放弃(self, dst, monkeypatch):
        calls = {"n": 0}

        class Dead:
            def get(self, *_a, **_k):
                calls["n"] += 1
                raise OSError("连不上")

        monkeypatch.setattr(download, "_get_dl_session", lambda: Dead())
        err = download._fetch_audio_builtin("http://x/a", dst, "T")
        assert err and "连不上" in err
        assert calls["n"] == download._RESUME_ATTEMPTS

    def test_错误页仍然被拦下(self, dst):
        class Html:
            def get(self, *_a, **_k):
                return _Html()

        class _Html:
            status_code = 200
            headers: ClassVar[dict] = dict(_HTML_HEADERS)

            def iter_content(self, chunk_size=0):
                yield b"<!DOC"

            def close(self):
                pass

        with open(dst, "wb") as f:
            f.write(b"fLaC")
        import vncmd.download as dl

        old = dl._get_dl_session
        dl._get_dl_session = lambda: Html()
        try:
            err = download._fetch_audio_builtin("http://x/a", dst, "T")
        finally:
            dl._get_dl_session = old
        assert err and "不是音频" in err


class TestCurlResume:
    def test_argv里带续传开关(self):
        argv = download._curl_argv("http://x/a", "/tmp/a")
        i = argv.index("-C")
        assert argv[i + 1] == "-"

    def test_关掉续传时不带(self):
        argv = download._curl_argv("http://x/a", "/tmp/a", resume=False)
        assert "-C" not in argv

    @pytest.mark.skipif(not download.shutil.which("curl"), reason="没装 curl")
    def test_断流后续上传齐(self, dst):
        with _Server(cut_once=True) as s:
            err = download._fetch_audio_curl(s.url, dst, "T", total=len(PAYLOAD))
        assert err is None, err
        assert _read(dst) == PAYLOAD

    @pytest.mark.skipif(not download.shutil.which("curl"), reason="没装 curl")
    def test_服务端不认Range时删残file重来(self, dst):
        """curl 退出码 33 会把残file 原封不动留着，得我们自己丢"""
        with open(dst, "wb") as f:
            f.write(PAYLOAD[:CUT_AT])
        with _Server(respect_range=False) as s:
            err = download._fetch_audio_curl(s.url, dst, "T")
        assert err is None, err
        assert _read(dst) == PAYLOAD


class TestWaitCurlAccounting:
    def test_续传只算新增字节(self, tmp_path):
        """进度条不能把已有的部分再算一遍，否则会冲过总量"""
        p = tmp_path / "f"
        p.write_bytes(b"x" * 500)
        got = []

        class Done:
            returncode = 0

            def poll(self):
                return 0

        download._wait_curl(Done(), str(p), got.append, start=500)
        assert sum(got) == 0

    def test_续传期间只报新增(self, tmp_path):
        p = tmp_path / "f"
        p.write_bytes(b"x" * 100)
        got = []

        class Running:
            def __init__(self):
                self.n = 0

            def poll(self):
                self.n += 1
                if self.n == 1:
                    with open(p, "ab") as f:
                        f.write(b"y" * 50)
                    return None
                return 0

        download._wait_curl(Running(), str(p), got.append, start=100)
        assert sum(got) == 50
