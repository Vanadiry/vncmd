"""临时文件在失败路径上要清干净

下载中断或内容校验不过时，半截文件或错误页会留在 _temp 里。
这些文件既占地方，又会让下一轮同名的歌撞上。
"""

import hashlib
from pathlib import Path

import pytest

from function import downloader
from test.conftest import SAMPLE_MS  # noqa: F401  保�� conftest 会被加载

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
        """下载可能压根没落盘，清理不能因此抛异常把错误信息盖掉"""
        downloader._discard_temp([str(tmp_path / "never-existed")])

    def test_none_entries_skipped(self):
        downloader._discard_temp([None, ""])

    def test_readonly_or_locked_file_does_not_propagate(self, tmp_path):
        """清理是善后动作，失败不该盖掉真正的下载错误"""
        d = tmp_path / "dir"
        d.mkdir()
        # 传目录进去，unlink 会抛 IsADirectoryError
        downloader._discard_temp([str(d)])
        assert d.exists()
