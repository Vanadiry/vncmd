"""tool embed-id 的曲目匹配"""

from vncmd.embed_id import build_index, decide_action, match_track


def index():
    return build_index(
        [
            {"id": 1, "title": "Alone", "artist": "Alan Walker"},
            {"id": 2, "title": "Alone", "artist": "Marshmello"},
            {"id": 3, "title": "星降る海", "artist": "Aqu3ra, 早見沙織"},
            {"id": 4, "title": "Same", "artist": "Artist"},
            {"id": 5, "title": "Same", "artist": "Artist"},
        ]
    )


class TestMatchTrack:
    def test_标题加艺术家唯一命中(self):
        result = match_track(index(), "alone", "alan walker")

        assert result.song_id == 1
        assert result.by_title_only is False
        assert result.ambiguous is False

    def test_标题加艺术家歧义不兜底(self):
        result = match_track(index(), "same", "artist")

        assert result.song_id is None
        assert result.ambiguous is True
        assert result.by_title_only is False
        assert result.candidates == (4, 5)

    def test_艺术家漂移后按标题兜底(self):
        result = match_track(index(), "星降る海", "新艺术家")

        assert result.song_id == 3
        assert result.by_title_only is True

    def test_标题歧义(self):
        result = match_track(index(), "alone", "未知艺术家")

        assert result.song_id is None
        assert result.ambiguous is True
        assert result.by_title_only is True
        assert result.candidates == (1, 2)

    def test_艺术家为空直接按标题(self):
        result = match_track(index(), "星降る海", "")

        assert result.song_id == 3
        assert result.by_title_only is True

    def test_对不上(self):
        result = match_track(index(), "不存在", "Artist")

        assert result.song_id is None
        assert result.ambiguous is False
        assert result.candidates == ()

    def test_归一化后命中(self):
        result = match_track(index(), "  ＡＬＯＮＥ ", "ＡＬＡＮ WALKER")

        assert result.song_id == 1
        assert result.by_title_only is False

    def test_精确命中优先于标题歧义(self):
        result = match_track(index(), "alone", "alan walker")

        assert result.song_id == 1
        assert result.candidates == ()


class TestDecideAction:
    def test_没有已有值时写入(self):
        action = decide_action(index(), "星降る海", "新艺术家", [])

        assert action.action == "write"
        assert action.song_id == 3
        assert action.by_title_only is True

    def test_已有相同值时是最新(self):
        action = decide_action(index(), "alone", "alan walker", ["1"])

        assert action.action == "latest"
        assert action.song_id == 1
        assert action.existing == ("1",)

    def test_已有不同值时冲突(self):
        action = decide_action(index(), "alone", "alan walker", ["999"])

        assert action.action == "conflict"
        assert action.song_id == 1
        assert action.existing == ("999",)

    def test_多个已有值不动(self):
        action = decide_action(index(), "alone", "alan walker", ["1", "2"])

        assert action.action == "multiple"
        assert action.song_id is None
        assert action.existing == ("1", "2")

    def test_没有已有值且歧义(self):
        action = decide_action(index(), "alone", "未知艺术家", [])

        assert action.action == "ambiguous"
        assert action.candidates == (1, 2)
        assert action.by_title_only is True

    def test_没有已有值且对不上(self):
        action = decide_action(index(), "不存在", "Artist", [])

        assert action.action == "not_found"
        assert action.candidates == ()

    def test_已有值但匹配歧义(self):
        action = decide_action(index(), "alone", "未知艺术家", ["999"])

        assert action.action == "ambiguous"
        assert action.existing == ("999",)

    def test_没有标题(self):
        action = decide_action(index(), "", "Artist", [])

        assert action.action == "no_title"
