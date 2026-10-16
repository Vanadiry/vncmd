"""download_song 里两道校验的先后与在无 ffmpeg 环境下的表现"""

import hashlib

import pytest

from function import downloader
from function.checker import check_md5 as real_check_md5

AUDIO = b"vncmd-test-audio" * 1000


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """把 download_song 的外部依赖换成可控的替身，只留下校验逻辑本身"""
    calls = []

    def fake_fetch_audio(
        url, path, label, progress=None, task_id=None, total=0, use_curl=None
    ):
        with open(path, "wb") as f:
            f.write(AUDIO)
        return

    def fake_check_md5(path, expect_md5, expect_size=0):
        calls.append(("md5", expect_md5, expect_size))
        return real_check_md5(path, expect_md5, expect_size)

    def fake_check_audio(path):
        calls.append(("audio",))
        return True, ""

    monkeypatch.setattr(downloader, "fetch_audio", fake_fetch_audio)
    monkeypatch.setattr(downloader, "check_md5", fake_check_md5)
    monkeypatch.setattr(downloader, "check_audio", fake_check_audio)
    monkeypatch.setattr(downloader, "fetch_cover", lambda *_a, **_k: None)
    monkeypatch.setattr(downloader, "embed_metadata", lambda *_a, **_k: None)

    return calls, str(tmp_path)


def run(download_dir, **kw):
    params = {
        "song_url": "http://example.com/a.flac",
        "song_title": "T",
        "song_artist": "A",
        "song_album": "B",
        "song_id": 1,
        "cover_url": "",
        "lyrics_api_url": "",
        "publish_time": "",
        "download_dir": download_dir,
    }
    params.update(kw)
    return downloader.download_song(**params)


def test_md5_runs_before_full_decode(harness, monkeypatch):
    """md5 是纯读文件，必须排在全量解码前面，否则快的那道白排了"""
    calls, tmp = harness
    monkeypatch.setattr(downloader, "has_ffmpeg", lambda: True)
    ok, _msg, _ = run(tmp)
    assert ok
    assert [c[0] for c in calls] == ["md5", "audio"]


def test_both_checks_run_when_ffmpeg_present(harness, monkeypatch):
    """两道都要过，md5 过不代表文件一定能解码"""
    calls, tmp = harness
    monkeypatch.setattr(downloader, "has_ffmpeg", lambda: True)
    ok, _msg, _ = run(
        tmp, song_size=len(AUDIO), song_md5=hashlib.md5(AUDIO).hexdigest()
    )
    assert ok
    assert [c[0] for c in calls] == ["md5", "audio"]


def test_md5_runs_without_ffmpeg(harness, monkeypatch):
    """没有 ffmpeg 时以前完全不校验，现在 md5 仍然把关"""
    calls, tmp = harness
    monkeypatch.setattr(downloader, "has_ffmpeg", lambda: False)
    ok, _msg, _ = run(
        tmp, song_size=len(AUDIO), song_md5=hashlib.md5(AUDIO).hexdigest()
    )
    assert ok
    assert [c[0] for c in calls] == ["md5"]


def test_bad_md5_rejected_without_ffmpeg(harness, monkeypatch):
    """无 ffmpeg 且 md5 不符时必须判失败，不能悄悄放行"""
    _calls, tmp = harness
    monkeypatch.setattr(downloader, "has_ffmpeg", lambda: False)
    ok, msg, _ = run(tmp, song_size=len(AUDIO), song_md5="0" * 32)
    assert not ok
    assert "md5 不符" in msg


def test_bad_md5_skips_decode(harness, monkeypatch):
    """md5 已经判定不符就不必再解码，提示要指向 md5 而不是解码错误"""
    calls, tmp = harness
    monkeypatch.setattr(downloader, "has_ffmpeg", lambda: True)
    ok, msg, _ = run(tmp, song_size=len(AUDIO), song_md5="0" * 32)
    assert not ok
    assert "md5 不符" in msg
    assert [c[0] for c in calls] == ["md5"]


def test_decode_failure_still_caught_when_md5_passes(harness, monkeypatch):
    """服务端自己的文件坏掉时 md5 会通过，解码这道还得留"""
    _calls, tmp = harness
    monkeypatch.setattr(downloader, "has_ffmpeg", lambda: True)
    monkeypatch.setattr(downloader, "check_audio", lambda _p: (False, "解码出错: boom"))
    ok, msg, _ = run(tmp, song_size=len(AUDIO), song_md5=hashlib.md5(AUDIO).hexdigest())
    assert not ok
    assert "解码出错" in msg


def test_expectations_reach_the_checker(harness, monkeypatch):
    """服务端声明的值要原样传下去，不能在中途丢掉"""
    calls, tmp = harness
    monkeypatch.setattr(downloader, "has_ffmpeg", lambda: False)
    digest = hashlib.md5(AUDIO).hexdigest()
    ok, _msg, _ = run(tmp, song_size=len(AUDIO), song_md5=digest)
    assert ok
    assert calls[0] == ("md5", digest, len(AUDIO))


def test_no_expectations_still_decodes(harness, monkeypatch):
    """服务端没给校验依据时退回原有行为，只跑解码"""
    calls, tmp = harness
    monkeypatch.setattr(downloader, "has_ffmpeg", lambda: True)
    ok, _msg, _ = run(tmp)
    assert ok
    assert calls == [("md5", "", 0), ("audio",)]
