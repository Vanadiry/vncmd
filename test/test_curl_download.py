"""--curl 开关、[download] downloader 配置与 curl 调用参数"""

import shutil
import subprocess
import threading

import pytest

from function import download
from function.config import get_curl_arg, get_downloader


class TestCurlArgv:
    def test_always_carries_fail(self):
        """没有 --fail，HTTP 错误页会被当正文写进文件并返回 0"""
        argv = download._curl_argv("http://x/a.flac", "/tmp/a.flac")
        assert "--fail" in argv

    def test_follows_redirects(self):
        """CDN 会重定向，必须跟；-sSL 是合并写法"""
        argv = download._curl_argv("http://x/a.flac", "/tmp/a.flac")
        assert any("L" in a for a in argv if a.startswith("-s"))

    def test_url_is_last_argument(self):
        url = "http://m10.music.126.net/2026/x.flac?param=1y2z"
        argv = download._curl_argv(url, "/tmp/a.flac")
        assert argv[-1] == url

    def test_url_is_single_argument(self):
        """url 里的 ? & = 绝不能被拆开或交给 shell 解释"""
        url = "http://x/a.flac?a=1&b=2"
        argv = download._curl_argv(url, "/tmp/a.flac")
        assert len([a for a in argv if a == url]) == 1

    def test_output_path_after_user_args(self, monkeypatch):
        """-o 放在用户参数之后，用户误写 -o 也覆盖不掉我们的目标文件"""
        monkeypatch.setattr(download, "get_curl_arg", lambda: "-o /tmp/evil")
        argv = download._curl_argv("http://x/a.flac", "/tmp/good.flac")
        assert argv[argv.index("/tmp/good.flac") + 1] == "http://x/a.flac"
        assert argv[-2] == "/tmp/good.flac"

    def test_quoted_user_arg_kept_whole(self, monkeypatch):
        """带空格的引号参数要保持完整，shlex 才能正确处理"""
        monkeypatch.setattr(download, "get_curl_arg", lambda: '-H "X-A: b"')
        argv = download._curl_argv("http://x/a.flac", "/tmp/a.flac")
        assert "X-A: b" in argv

    def test_speed_floor_present(self):
        """低速兜底对��内建读超时的等价物，防传输中途卡死"""
        argv = download._curl_argv("http://x/a.flac", "/tmp/a.flac")
        assert "--speed-limit" in argv
        assert "--speed-time" in argv

    def test_empty_curl_arg_works(self, monkeypatch):
        monkeypatch.setattr(download, "get_curl_arg", lambda: "")
        argv = download._curl_argv("http://x/a.flac", "/tmp/a.flac")
        assert "" not in argv


class TestFetchAudioDispatch:
    def test_flag_on_uses_curl(self, monkeypatch, tmp_path):
        seen = []
        monkeypatch.setattr(download.shutil, "which", lambda _x: "/usr/bin/curl")
        monkeypatch.setattr(
            download,
            "_fetch_audio_curl",
            lambda *a, **k: seen.append(k) or None,
        )
        err = download.fetch_audio(
            "http://x/a.flac", str(tmp_path / "a.flac"), "T", use_curl=True
        )
        assert err is None
        assert len(seen) == 1

    def test_flag_off_uses_builtin(self, monkeypatch, tmp_path):
        def boom(*_a, **_k):
            raise AssertionError("不该走 curl")

        monkeypatch.setattr(download, "_fetch_audio_curl", boom)
        monkeypatch.setattr(download, "_get_dl_session", lambda: _FakeSession())
        err = download.fetch_audio(
            "http://x/a.flac", str(tmp_path / "a.flac"), "T", use_curl=False
        )
        # 错误信息正是 builtin 分支那个替身抛的，说明确实走了内建这条路
        assert err == "builtin 分支不该被测到具体网络行为"

    def test_absent_falls_back_to_config(self, monkeypatch, tmp_path):
        """没传标志时必须读配置，否则 downloader = "curl" 永远不生效"""
        seen = []
        monkeypatch.setattr(download.shutil, "which", lambda _x: "/usr/bin/curl")
        monkeypatch.setattr(download, "get_downloader", lambda: "curl")
        monkeypatch.setattr(
            download,
            "_fetch_audio_curl",
            lambda *a, **k: seen.append(k) or None,
        )
        download.fetch_audio(
            "http://x/a.flac", str(tmp_path / "a.flac"), "T", use_curl=None
        )
        assert len(seen) == 1

    def test_missing_curl_is_an_error(self, monkeypatch, tmp_path):
        """配了 curl 却没装要直接报错，不能静默退回内建"""
        monkeypatch.setattr(download.shutil, "which", lambda _x: None)
        monkeypatch.setattr(
            download,
            "_fetch_audio_curl",
            lambda *a, **k: pytest.fail("没装 curl 时不该尝试调用"),
        )
        err = download.fetch_audio(
            "http://x/a.flac", str(tmp_path / "a.flac"), "T", use_curl=True
        )
        assert err is not None
        assert "curl" in err

    def test_total_reaches_curl_path(self, monkeypatch, tmp_path):
        """进度总量靠服务端声明的大小，必须传进去"""
        seen = {}
        monkeypatch.setattr(download.shutil, "which", lambda _x: "/usr/bin/curl")
        monkeypatch.setattr(
            download,
            "_fetch_audio_curl",
            lambda *a, **k: seen.update(k) or None,
        )
        download.fetch_audio(
            "http://x/a.flac",
            str(tmp_path / "a.flac"),
            "T",
            total=26995264,
            use_curl=True,
        )
        assert seen["total"] == 26995264


class TestConfigGetter:
    def test_missing_downloader_defaults_builtin(self, monkeypatch):
        monkeypatch.setattr(
            "function.config._get_cfg", lambda: {"download": {"dir": ""}}
        )
        assert get_downloader() == "builtin"

    def test_curl_value_respected(self, monkeypatch):
        monkeypatch.setattr(
            "function.config._get_cfg", lambda: {"download": {"downloader": "curl"}}
        )
        assert get_downloader() == "curl"

    def test_curl_arg_defaults_empty(self, monkeypatch):
        monkeypatch.setattr(
            "function.config._get_cfg", lambda: {"download": {"dir": ""}}
        )
        assert get_curl_arg() == ""


class TestParser:
    def _parse(self, argv):
        from vncmd import build_parser

        return build_parser().parse_args(argv)

    @pytest.mark.parametrize("cmd", ["song", "album", "playlist"])
    def test_curl_flag_absent_is_none(self, cmd):
        """必须是 None 而非 False，否则 downloader = "curl" 永远没机会生效"""
        assert self._parse([cmd, "123"]).curl is None

    @pytest.mark.parametrize("cmd", ["song", "album", "playlist"])
    def test_curl_flag_present_is_true(self, cmd):
        assert self._parse([cmd, "123", "--curl"]).curl is True

    @pytest.mark.parametrize("cmd", ["song", "album", "playlist"])
    def test_curl_and_check_coexist(self, cmd):
        args = self._parse([cmd, "123", "-d", "--curl", "--check"])
        assert args.curl is True
        assert args.check is True


class TestValidation:
    """配置校验。基准取自带模板，避免造残缺配置污染全局 _cfg"""

    @pytest.fixture(autouse=True)
    def _isolate(self, monkeypatch):
        import function.config as cfgmod

        saved = cfgmod._cfg

        def _die(errors):
            raise SystemExit(errors)

        monkeypatch.setattr(cfgmod, "_die", _die)
        yield
        cfgmod._cfg = saved

    def _base(self):
        import tomllib

        from function._defaults import CONFIG_TOML

        return tomllib.loads(CONFIG_TOML)

    def _check(self, **download_overrides):
        import function.config as cfgmod

        base = self._base()
        # validate_config 内部会调 load_config 并覆盖 _cfg，所以得替换读配置那一步
        cfg = {**base, "download": {**base["download"], **download_overrides}}
        import function.config as m

        orig = m.load_config
        m.load_config = lambda: cfg
        try:
            cfgmod.validate_config(quiet=True)
        finally:
            m.load_config = orig

    def test_shipped_template_passes(self):
        """模板自身必须过校验，否则新装用户直接起不来"""
        import function.config as cfgmod

        cfgmod._cfg = self._base()
        cfgmod.validate_config(quiet=True)

    def test_bad_downloader_rejected(self):
        with pytest.raises(SystemExit) as exc:
            self._check(downloader="wget")
        assert any("downloader" in e for e in exc.value.code)

    def test_builtin_accepted(self):
        self._check(downloader="builtin")

    def test_curl_accepted(self):
        self._check(downloader="curl")

    def test_non_string_curl_arg_rejected(self):
        with pytest.raises(SystemExit) as exc:
            self._check(curl_arg=123)
        assert any("curl_arg" in e for e in exc.value.code)

    def test_non_bool_check_rejected(self):
        with pytest.raises(SystemExit) as exc:
            self._check(check="yes")
        assert any("check" in e for e in exc.value.code)


class TestAgainstRealCurl:
    """真跑一次 curl，确认参数拼得对、退出码读得到"""

    def test_海量_stderr_不会阻塞(self, monkeypatch, tmp_path):
        """curl 写满 stderr 时必须照样下完，不能卡死在管道上

        管道缓冲区约 64 KB，超出后 curl 阻塞在 write，而 _wait_curl 只轮询
        returncode，两边死锁。--trace-ascii /dev/stderr 稳定复现。
        """
        if not shutil.which("curl"):
            pytest.skip("没装 curl")
        payload = b"fLaC" + b"x" * 3_000_000
        src = tmp_path / "big.bin"
        src.write_bytes(payload)
        dst = tmp_path / "out.bin"
        monkeypatch.setattr(
            download, "get_curl_arg", lambda: "--trace-ascii /dev/stderr"
        )

        box = []
        worker = threading.Thread(
            target=lambda: box.append(
                download._fetch_audio_curl(src.as_uri(), str(dst), "T")
            ),
            daemon=True,
        )
        worker.start()
        worker.join(timeout=45)
        if worker.is_alive():
            pytest.fail("curl 被 stderr 阻塞，45 秒仍未结束")

        assert box == [None], f"应下载成功，实际 {box}"
        assert dst.read_bytes() == payload

    def test_stderr_内容仍会带回错误信息(self, tmp_path):
        """改成临时文件后，报错里的 curl 原始输出不能丢"""
        if not shutil.which("curl"):
            pytest.skip("没装 curl")
        missing = tmp_path / "missing" / "x.flac"
        dst = tmp_path / "out.bin"
        err = download._fetch_audio_curl(missing.as_uri(), str(dst), "T")
        assert err is not None
        assert "curl" in err
        # 退出码说明之外还要带上 curl 自己的话，否则用户无从判断原因
        assert err.split("：", 1)[-1].strip(), "错误说明里没有 curl 的原始输出"

    def test_downloads_and_advances(self, tmp_path):
        if not shutil.which("curl"):
            pytest.skip("没装 curl")
        src = tmp_path / "payload"
        src.write_bytes(b"x" * 40000)
        dst = tmp_path / "out.bin"
        got = []
        proc = subprocess.Popen(
            download._curl_argv(src.as_uri(), str(dst)),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        download._wait_curl(proc, str(dst), got.append)
        assert proc.returncode == 0
        assert dst.read_bytes() == b"x" * 40000
        # 轮询必须真的吐过增量，否则进度条会一直是 0
        assert sum(got) == 40000

    def test_missing_source_reports_exit_code(self, tmp_path):
        if not shutil.which("curl"):
            pytest.skip("没装 curl")
        dst = tmp_path / "out.bin"
        err = download._fetch_audio_curl(f"file://{tmp_path}/nope.flac", str(dst), "T")
        assert err is not None
        assert "curl" in err

    def test_empty_result_reported(self, tmp_path):
        if not shutil.which("curl"):
            pytest.skip("没装 curl")
        err = download._fetch_audio_curl(
            (tmp_path / "nope").as_uri(), str(tmp_path / "o"), "T"
        )
        assert err is not None

    def test_错误页被魔数校验挡下(self, tmp_path):
        """200 带回 HTML 错误页时必须拒绝，否则会被当音频收下

        --fail 只看状态码，对这种 200 响应不起作用，
        内建路径靠 looks_like_audio 挡住，curl 这条路原先没有。
        """
        if not shutil.which("curl"):
            pytest.skip("没装 curl")
        page = tmp_path / "error.html"
        page.write_bytes(b"<!DOCTYPE html><html><body>error</body></html>" * 500)
        dst = tmp_path / "out.flac"
        err = download._fetch_audio_curl(page.as_uri(), str(dst), "T")
        assert err is not None
        assert "不是音频" in err
        # curl 自己认为传输成功，所以这条错只能由内容校验报出来
        assert "退出码" not in err

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param(b"fLaC" + b"\x00" * 4000, id="flac"),
            pytest.param(b"ID3\x04\x00" + b"\x00" * 4000, id="带 ID3 的 mp3"),
            pytest.param(b"\xff\xfb\x90\x00" + b"\x00" * 4000, id="裸 mp3 帧同步"),
            pytest.param(b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 4000, id="mp4 容器"),
        ],
    )
    def test_真实音频不被误伤(self, tmp_path, payload):
        """守卫只挡错误页，正常音频一个都不能误杀"""
        if not shutil.which("curl"):
            pytest.skip("没装 curl")
        src = tmp_path / "a.bin"
        src.write_bytes(payload)
        dst = tmp_path / "out.bin"
        assert download._fetch_audio_curl(src.as_uri(), str(dst), "T") is None
        assert dst.read_bytes() == payload

    def test_复用内建路径的同一个判定(self, monkeypatch, tmp_path):
        """两条路径必须共用 looks_like_audio，不能各判各的

        这里盯的是「调用了同一个函数」，不是重新实现一遍判定规则。
        """
        if not shutil.which("curl"):
            pytest.skip("没装 curl")
        src = tmp_path / "a.bin"
        src.write_bytes(b"fLaC" + b"\x00" * 4000)
        seen = []
        real = download.looks_like_audio

        def spy(head):
            seen.append(head)
            return real(head)

        monkeypatch.setattr(download, "looks_like_audio", spy)
        assert (
            download._fetch_audio_curl(src.as_uri(), str(tmp_path / "o.bin"), "T")
            is None
        )
        assert len(seen) == 1, "curl 路径没有调用 looks_like_audio"
        assert seen[0].startswith(b"fLaC")

    def test_读够魔数所需的字节(self, monkeypatch, tmp_path):
        """头部长度不能截断，MP4 的 ftyp 落在偏移 4，读太少就认不出"""
        assert download._HEAD_BYTES >= 8


class _FakeSession:
    """够用的替身，让 builtin 分支能跑完"""

    def get(self, *_a, **_k):
        raise RuntimeError("builtin 分支不该被测到具体网络行为")
