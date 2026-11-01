"""下载前补全曲目详情"""

from types import SimpleNamespace

from vncmd import downloader

DETAIL = {
    "id": 1,
    "title": "T",
    "artist": "A",
    "album": "AL",
    "album_id": 9,
    "cover": "https://x/c.jpg",
    "publish_time": "2022-01-01 08:00:00",
    "duration": "3:00",
    "track_no": 3,
    "cd_no": 2,
}


def _run_batch(monkeypatch, tmp_path, tracks, content="alc", details=None):
    """跑一次不联网的批量下载，返回 download_song 收到的参数"""
    calls = []
    ids = []

    def fake_download(**kwargs):
        calls.append(kwargs)
        return True, "", None

    def fake_details(got_ids):
        ids.append(list(got_ids))
        if isinstance(details, Exception):
            raise details
        return details if details is not None else {}

    monkeypatch.setattr(
        downloader, "_setup_session", lambda *_a: (str(tmp_path), tracks, 0)
    )
    monkeypatch.setattr(downloader, "get_download_content", lambda: content)
    monkeypatch.setattr(downloader, "get_concurrency", lambda: 1)
    monkeypatch.setattr(
        downloader,
        "_fetch_source_with_retry",
        lambda *_a, **_k: SimpleNamespace(
            url="https://x/a.flac", size=0, md5="", level="exhigh"
        ),
    )
    monkeypatch.setattr(downloader, "download_song", fake_download)
    monkeypatch.setattr(downloader, "get_song_details_many", fake_details)
    monkeypatch.setattr(downloader.time, "sleep", lambda _s: None)

    downloader.download_song_batch(tracks, 320000, str(tmp_path), run_check=False)
    return calls, ids


class Test补全详情:
    def test_Tracker字段缺失时批量补全(self, monkeypatch, tmp_path):
        track = {
            "id": 1,
            "title": "T",
            "artist": "A",
            "publish_time": "2021-01-01 08:00:00",
        }
        calls, ids = _run_batch(monkeypatch, tmp_path, [track], details={1: DETAIL})

        assert ids == [[1]]
        assert calls[0]["song_album"] == "AL"
        assert calls[0]["cover_url"] == "https://x/c.jpg"
        assert calls[0]["track_no"] == 3
        assert calls[0]["cd_no"] == 2

    def test_详情里的空值不覆盖已有值(self, monkeypatch, tmp_path):
        track = {
            "id": 1,
            "title": "T",
            "artist": "A",
            "publish_time": "2021-01-01 08:00:00",
        }
        detail = {**DETAIL, "publish_time": ""}
        calls, _ids = _run_batch(monkeypatch, tmp_path, [track], details={1: detail})

        assert calls[0]["publish_time"] == "2021-01-01 08:00:00"

    def test_字段完整时不发详情请求(self, monkeypatch, tmp_path):
        track = {
            "id": 1,
            "title": "T",
            "artist": "A",
            "album": "AL",
            "cover": "https://x/c.jpg",
            "track_no": 3,
            "cd_no": 2,
        }
        calls, ids = _run_batch(
            monkeypatch,
            tmp_path,
            [track],
            details=RuntimeError("不该请求"),
        )

        assert ids == []
        assert calls[0]["song_album"] == "AL"

    def test_只对缺少字段的曲目请求(self, monkeypatch, tmp_path):
        full = {
            "id": 1,
            "title": "T1",
            "artist": "A",
            "album": "AL",
            "cover": "https://x/1.jpg",
            "track_no": 1,
            "cd_no": 1,
        }
        partial = {"id": 2, "title": "T2", "artist": "A"}
        calls, ids = _run_batch(
            monkeypatch,
            tmp_path,
            [full, partial],
            details={2: {**DETAIL, "id": 2, "title": "T2"}},
        )

        assert ids == [[2]]
        assert len(calls) == 2

    def test_详情失败时继续下载(self, monkeypatch, tmp_path):
        warns = []
        monkeypatch.setattr(downloader, "warning", warns.append)
        track = {"id": 1, "title": "T", "artist": "A"}

        calls, _ids = _run_batch(
            monkeypatch, tmp_path, [track], details=RuntimeError("网络坏了")
        )

        assert calls
        assert calls[0]["song_album"] == ""
        assert any("补全曲目详情失败" in w for w in warns)

    def test_没有返回详情时继续下载(self, monkeypatch, tmp_path):
        warns = []
        monkeypatch.setattr(downloader, "warning", warns.append)
        track = {"id": 1, "title": "T", "artist": "A"}

        calls, _ids = _run_batch(monkeypatch, tmp_path, [track], details={})

        assert calls
        assert any("未取到详情" in w for w in warns)

    def test_只下载歌词时不补详情(self, monkeypatch, tmp_path):
        track = {"id": 1, "title": "T", "artist": "A"}
        calls, ids = _run_batch(monkeypatch, tmp_path, [track], content="l")

        assert ids == []
        assert calls
        assert calls[0]["song_url"] == ""

    def test_只下载封面时补详情(self, monkeypatch, tmp_path):
        track = {"id": 1, "title": "T", "artist": "A"}
        calls, ids = _run_batch(
            monkeypatch, tmp_path, [track], content="c", details={1: DETAIL}
        )

        assert ids == [[1]]
        assert calls[0]["cover_url"] == "https://x/c.jpg"


class Test封面提示:
    def test_封面URL失败时提示(self, monkeypatch):
        warns = []
        monkeypatch.setattr(downloader, "warning", warns.append)

        assert downloader._process_cover(None, "https://x/c.jpg") == (
            None,
            None,
            None,
        )
        assert any("封面获取失败" in w for w in warns)

    def test_没有封面URL时不重复提示(self, monkeypatch):
        warns = []
        monkeypatch.setattr(downloader, "warning", warns.append)

        downloader._process_cover(None, "")

        assert warns == []

    def test_批量缺少封面时提示一次(self, monkeypatch, tmp_path):
        warns = []
        monkeypatch.setattr(downloader, "warning", warns.append)
        track = {"id": 1, "title": "T", "artist": "A"}
        detail = {**DETAIL, "cover": ""}

        _run_batch(monkeypatch, tmp_path, [track], details={1: detail})

        assert sum("没有封面" in w for w in warns) == 1


class Test缓存完整性:
    def test_缺键的旧缓存不算完整(self):
        from vncmd.net.api import _complete_details

        assert not _complete_details({"title": "x"})
        assert _complete_details(DETAIL)
