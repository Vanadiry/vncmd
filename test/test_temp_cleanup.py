"""失败路径上的临时文件清理"""

import hashlib
from pathlib import Path

import pytest

from test.conftest import SAMPLE_MS  # noqa: F401  保证 conftest 会被加载
from vncmd import downloader

AUDIO = b"fLaC" + b"vncmd-audio" * 500


def _params(tmp_path, **kw):
    p = {
        "song_url": "http://example.com/a.flac",
        "song_title": "T",
        "song_artist": "A",
        "song_album": "B",
        "song_id": 7,
        "cover_url": "",
        "lyrics_api_url": "",
        "publish_time": "",
        "download_dir": str(tmp_path),
    }
    p.update(kw)
    return p


@pytest.fixture
def scaffold(tmp_path, monkeypatch):
    """把外部依赖换成可控替身，只留下临时文件的生灭可观察"""
    state = {"fetch_err": None, "audio": AUDIO}

    def fake_fetch_audio(url, path, label, progress=None, task_id=None, **kw):
        if state["audio"] is not None:
            Path(path).write_bytes(state["audio"])
        return state["fetch_err"]

    monkeypatch.setattr(downloader, "fetch_audio", fake_fetch_audio)
    monkeypatch.setattr(downloader, "fetch_cover", lambda *_a, **_k: None)
    monkeypatch.setattr(downloader, "embed_metadata", lambda *_a, **_k: None)
    monkeypatch.setattr(downloader, "get_check_enabled", lambda: False)
    return state, tmp_path / "_temp" / "7.flac"


class TestFailedFetchCleansUp:
    def test_传输失败不留残file(self, scaffold):
        state, temp = scaffold
        state["fetch_err"] = "curl 传输失败：超时"
        ok, msg, _ = downloader.download_song(**_params(temp.parent.parent))
        assert not ok
        assert "下载失败" in msg
        assert not temp.exists(), f"失败后仍留下 {temp}"

    def test_下载到错误页要清掉(self, scaffold):
        """CDN 以 200 带回 HTML 时 fetch_audio 会报错，文件同样要清掉"""
        state, temp = scaffold
        state["fetch_err"] = "服务器返回的不是音频"
        state["audio"] = b"<!DOCTYPE html><html>error</html>"
        ok, _msg, _ = downloader.download_song(**_params(temp.parent.parent))
        assert not ok
        assert not temp.exists()

    def test_内容校验失败要清掉(self, scaffold):
        """md5 对不上时文件留着没用"""
        _state, temp = scaffold
        ok, msg, _ = downloader.download_song(
            **_params(temp.parent.parent, song_md5="0" * 32, song_size=len(AUDIO))
        )
        assert not ok
        assert "md5" in msg
        assert not temp.exists()

    def test_空文件要清掉(self, scaffold):
        state, temp = scaffold
        state["audio"] = b""
        ok, _msg, _ = downloader.download_song(**_params(temp.parent.parent))
        assert not ok
        assert not temp.exists()

    def test_成功后临时文件是被搬走而非删掉(self, scaffold):
        """成功路径走 _move_unique 搬去最终位置，临时位置理应空着"""
        _state, temp = scaffold
        ok, _msg, final = downloader.download_song(
            **_params(temp.parent.parent, song_md5=hashlib.md5(AUDIO).hexdigest())
        )
        assert ok
        assert not temp.exists(), "临时位置应已腾空"
        assert final and Path(final).exists(), "最终文件没落地"


class TestDiscardHelper:
    def test_removes_existing(self, tmp_path):
        a, b = tmp_path / "a", tmp_path / "b"
        a.write_text("x")
        b.write_text("y")
        downloader._discard_temp([str(a), str(b)])
        assert not a.exists() and not b.exists()

    def test_missing_path_is_not_an_error(self, tmp_path):
        """下载可能没有落盘，清理不能因此抛异常把错误信息盖掉"""
        downloader._discard_temp([str(tmp_path / "never-existed")])

    def test_none_entries_skipped(self):
        downloader._discard_temp([None, ""])

    def test_readonly_or_locked_file_does_not_propagate(self, tmp_path):
        """清理为善后动作，失败不该盖掉真正的下载错误"""
        d = tmp_path / "dir"
        d.mkdir()
        # 传目录进去，unlink 会抛 IsADirectoryError
        downloader._discard_temp([str(d)])
        assert d.exists()


class TestEmbedFailureDegrades:
    """元数据嵌不上不该判为下载失败，但要重试过再放弃
    音频已过 md5 校验，报失败会让用户重下
    """

    @pytest.fixture
    def wired(self, tmp_path, monkeypatch):
        audio = b"fLaC" + b"x" * 20000
        calls = {"n": 0}
        monkeypatch.setattr(
            downloader,
            "fetch_audio",
            # fetch_audio 的约定为“错误说明或 None”，成功返回 None 而非字节数
            lambda url, path, label, progress=None, task_id=None, **kw: (
                Path(path).write_bytes(audio),
                None,
            )[1],
        )
        monkeypatch.setattr(downloader, "fetch_cover", lambda *a, **k: None)
        monkeypatch.setattr(downloader, "get_check_enabled", lambda: False)
        monkeypatch.setattr(downloader.time, "sleep", lambda _s: None)
        return tmp_path, hashlib.md5(audio).hexdigest(), calls

    @staticmethod
    def _failing(calls, times=99):
        def fn(*_a, **_k):
            calls["n"] += 1
            if calls["n"] <= times:
                raise ValueError("音频标签无法读取，可能不是 mp3")

        return fn

    def _run(self, root, digest, sid):
        return downloader.download_song(**_params(root, song_id=sid, song_md5=digest))

    def test_仍算成功且文件落地(self, wired, monkeypatch):
        _root, digest, calls = wired
        monkeypatch.setattr(downloader, "embed_metadata", self._failing(calls))
        ok, _msg, final = self._run(_root, digest, 11)
        assert ok, "标签嵌不上不该让整首判为失败"
        assert final and Path(final).exists(), "音频文件没落地"

    def test_确实走到了嵌入这一步(self, wired, monkeypatch):
        """上面的通过不能靠没调嵌入骗到手"""
        root, digest, calls = wired
        monkeypatch.setattr(downloader, "embed_metadata", self._failing(calls))
        self._run(root, digest, 12)
        assert calls["n"] >= 1

    def test_失败会重试而不是一次就放弃(self, wired, monkeypatch):
        """标签对音乐库很关键，一次失败就降级等于把有用的东西扔了"""
        root, digest, calls = wired
        monkeypatch.setattr(downloader, "embed_metadata", self._failing(calls))
        self._run(root, digest, 13)
        assert calls["n"] == downloader._EMBED_ATTEMPTS

    def test_偶发失败能被重试救回(self, wired, monkeypatch, capsys):
        """前两次失败第三次成功时不该有任何警告"""
        root, digest, calls = wired
        monkeypatch.setattr(downloader, "embed_metadata", self._failing(calls, times=2))
        ok, _msg, final = self._run(root, digest, 14)
        assert ok
        assert final and Path(final).exists()
        assert calls["n"] == 3
        assert "元数据嵌入失败" not in capsys.readouterr().out

    def test_一次成功不重试(self, wired, monkeypatch):
        """正常路径不能白白多跑两遍"""
        root, digest, calls = wired
        monkeypatch.setattr(downloader, "embed_metadata", self._failing(calls, times=0))
        self._run(root, digest, 15)
        assert calls["n"] == 1

    def test_重试用尽仍失败要出声告知(self, wired, monkeypatch, capsys):
        """静默降级会让用户以为标签已经嵌好"""
        root, digest, calls = wired
        monkeypatch.setattr(downloader, "embed_metadata", self._failing(calls))
        self._run(root, digest, 16)
        out = capsys.readouterr().err
        assert "元数据嵌入失败" in out
        assert str(downloader._EMBED_ATTEMPTS) in out, "要说明重试过几次"


class TestEmbedRetryHelper:
    def test_returns_empty_on_success(self):
        assert downloader._embed_with_retry(lambda *_a: None) == ""

    def test_returns_error_after_exhausting(self):
        err = downloader._embed_with_retry(
            lambda *_a: (_ for _ in ()).throw(RuntimeError("炸了"))
        )
        assert "RuntimeError" in err
        assert "炸了" in err

    def test_arguments_forwarded(self):
        seen = []
        downloader._embed_with_retry(lambda *a: seen.append(a), 1, "x", None)
        assert seen == [(1, "x", None)]

    def test_stops_at_first_success(self):
        n = {"i": 0}

        def fn(*_a):
            n["i"] += 1
            if n["i"] < 2:
                raise OSError("临时")

        assert downloader._embed_with_retry(fn) == ""
        assert n["i"] == 2

    def test_backoff_is_not_burst(self, monkeypatch):
        """重试之间要有间隔，否则并发时等于空转"""
        waits = []
        monkeypatch.setattr(downloader.time, "sleep", waits.append)
        downloader._embed_with_retry(lambda *_a: (_ for _ in ()).throw(OSError("x")))
        assert waits and all(w > 0 for w in waits)
        assert len(waits) == downloader._EMBED_ATTEMPTS - 1
