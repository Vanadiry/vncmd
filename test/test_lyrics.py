from pathlib import Path
from function.lyrics import clean, parse, interleave, process, output_files

LRC = """[by:Someone]
[00:00.000] 作词 : 测试
[00:05.100] Hello World
[00:10.200] Goodbye
[00:15.300]"""
TLYRIC = """[by:Tester]
[00:05.100] Nihao World
[00:10.200] Zaijian
[00:15.300]"""


class TestClean:
    def test_removes_by(self):
        ct = clean(TLYRIC)
        assert "[by:" not in ct

    def test_keeps_timestamps(self):
        cl = clean(LRC)
        assert "[00:00.000]" in cl


class TestParse:
    @classmethod
    def setup_class(cls):
        cls.parsed = parse(clean(LRC))

    def test_count(self):
        assert len(self.parsed) == 4

    def test_first_time(self):
        assert self.parsed[0][0] == 0.0

    def test_second_time(self):
        assert abs(self.parsed[1][0] - 5.1) < 0.001

    def test_empty_line_kept(self):
        assert self.parsed[3][1] == ""


class TestInterleave:
    @classmethod
    def setup_class(cls):
        cls.iv = interleave(clean(LRC), clean(TLYRIC))

    def test_has_original(self):
        assert "Hello World" in self.iv

    def test_has_translation(self):
        assert "Nihao World" in self.iv

    def test_empty_line_preserved(self):
        assert "[00:15.300]" in self.iv

    def test_metadata_kept(self):
        assert "作词" in self.iv

    def test_ordering_orig_before_tlyric(self):
        lines = self.iv.splitlines()
        for i, line in enumerate(lines):
            if "Hello World" in line:
                assert i + 1 < len(lines)
                assert "Nihao World" in lines[i + 1]
                break


class TestProcess:
    def test_mode_0_single_file(self):
        r0 = process(LRC, TLYRIC, "0", 99999999)
        assert "lrc" in r0 and len(r0) == 1

    def test_mode_1_merged_single_file(self):
        r1 = process(LRC, TLYRIC, "1", 99999999)
        assert "lrc" in r1 and len(r1) == 1

    def test_mode_2_separate_two_files(self):
        r2 = process(LRC, TLYRIC, "2", 99999999)
        assert len(r2) == 2 and "lrc" in r2 and "2.lrc" in r2


class TestOutputFiles:
    def test_creates_file(self, temp_dir):
        paths = output_files(
            {"lrc": "test content"}, str(Path(temp_dir) / "lyric_test")
        )
        assert Path(paths[0]).exists()

    def test_content_correct(self, temp_dir):
        paths = output_files(
            {"lrc": "test content"}, str(Path(temp_dir) / "lyric_test")
        )
        assert Path(paths[0]).read_text(encoding="utf-8") == "test content"
