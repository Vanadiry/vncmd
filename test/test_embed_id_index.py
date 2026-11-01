"""tool embed-id 的曲目索引"""

import json

import pytest

from vncmd.embed_id import (
    build_index,
    load_songs_file,
    load_tracker_songs,
    normalize,
)


class TestNormalize:
    def test_nfkc与casefold与空白合并(self):
        assert normalize("  Ａ  B\t\n") == "a b"

    def test_非字符串按空处理(self):
        assert normalize(None) == ""


class TestBuildIndex:
    def test_两层索引与id去重(self):
        index = build_index(
            [
                {"id": 1, "title": "Ａ Title", "artist": "Artist"},
                {"id": 1, "title": "a title", "artist": "artist"},
                {"id": 2, "title": "Alone", "artist": "Alan Walker"},
                {"id": 3, "title": "Alone", "artist": "Marshmello"},
                {"id": 4, "title": "No Artist"},
            ]
        )

        assert index.by_title["a title"] == {1}
        assert index.by_title["alone"] == {2, 3}
        assert index.by_title_artist[("alone", "alan walker")] == {2}
        assert index.by_title_artist[("alone", "marshmello")] == {3}
        assert ("no artist", "") not in index.by_title_artist
        assert index.entries[2] == ("Alone", "Alan Walker")

    def test_标题为空不进索引(self):
        index = build_index([{"id": 1, "title": "", "artist": "A"}])

        assert index.by_title == {}
        assert index.by_title_artist == {}

    def test_坏记录跳过(self):
        index = build_index([None, {"title": "T"}, {"id": "bad", "title": "T"}])

        assert index.by_title == {}


class TestLoadSongsFile:
    def test_正常读取(self, tmp_path):
        path = tmp_path / "songs.json"
        path.write_text(json.dumps({"songs": [{"id": 1}]}), encoding="utf-8")

        assert load_songs_file(path) == [{"id": 1}]

    def test_坏JSON报错(self, tmp_path):
        path = tmp_path / "songs.json"
        path.write_text("{坏", encoding="utf-8")

        with pytest.raises(ValueError, match="无法解析"):
            load_songs_file(path)

    def test_缺少songs列表报错(self, tmp_path):
        path = tmp_path / "songs.json"
        path.write_text("{}", encoding="utf-8")

        with pytest.raises(ValueError, match="缺少 songs"):
            load_songs_file(path)


class TestLoadTrackerSongs:
    def test_合并多个tracker(self, tmp_path):
        for name, song_id in (("like", 1), ("later", 2)):
            folder = tmp_path / name
            folder.mkdir()
            (folder / "songs.json").write_text(
                json.dumps({"songs": [{"id": song_id, "title": "T"}]}),
                encoding="utf-8",
            )

        assert sorted(s["id"] for s in load_tracker_songs(tmp_path)) == [1, 2]

    def test_任意一份损坏就报错(self, tmp_path):
        folder = tmp_path / "like"
        folder.mkdir()
        (folder / "songs.json").write_text("{坏", encoding="utf-8")

        with pytest.raises(ValueError, match="无法解析"):
            load_tracker_songs(tmp_path)

    def test_目录不存在时为空(self, tmp_path):
        assert load_tracker_songs(tmp_path / "missing") == []
