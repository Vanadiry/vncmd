from pathlib import Path

from function.lyrics import clean, interleave, output_files, parse, process

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
    def test_line_single_file(self):
        r0 = process(LRC, TLYRIC, "line", 99999999)
        assert "lrc" in r0 and len(r0) == 1

    def test_block_merged_single_file(self):
        r1 = process(LRC, TLYRIC, "block", 99999999)
        assert "lrc" in r1 and len(r1) == 1

    def test_split_separate_two_files(self):
        r2 = process(LRC, TLYRIC, "split", 99999999)
        assert len(r2) == 2 and "lrc" in r2 and "2.lrc" in r2

    def test_split无译文时不出第二个文件(self):
        """出的是一个 0 字节的 .2.lrc，播放器会把它当成一首独立的翻译歌词。
        库里没有的译文很常见，而 clean() 只删 [by:] 行，所以这一路是空的"""
        r2 = process(LRC, "", "split", 99999999)
        assert list(r2) == ["lrc"]
        assert r2["lrc"].strip()

    def test_split译文只有空白也算没有(self):
        r2 = process(LRC, "\n  \n", "split", 99999999)
        assert list(r2) == ["lrc"]

    def test_line与block不受影响(self):
        """这两个模式两个流合成一个文件，本来就不分家"""
        for mode in ("line", "block"):
            assert list(process(LRC, "", mode, 99999999)) == ["lrc"]


class TestOutputFiles:
    def test_split无译文时不落盘空文件(self, temp_dir):
        r2 = process(LRC, "", "split", 99999999)
        base = str(Path(temp_dir) / "X")
        paths = output_files(r2, base)
        assert [Path(p).name for p in paths] == ["X.lrc"]
        assert not Path(base + ".2.lrc").exists()

    def test_split有译文时两个文件都在(self, temp_dir):
        base = str(Path(temp_dir) / "X")
        paths = output_files(process(LRC, TLYRIC, "split", 99999999), base)
        assert [Path(p).name for p in paths] == ["X.lrc", "X.2.lrc"]
        assert all(Path(p).stat().st_size > 0 for p in paths)

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


class TestProcessDrop:
    """save_mode = "drop"：只要原文的歌词文件，不写 .2.lrc

    产出的内容与 split 遇到没译文时一模一样，区别在语义：
    split 是「译文暂时没有」，drop 是「明确不要译文」
    """

    def test_drop有译文也不出第二个文件(self):
        r = process(LRC, TLYRIC, "drop", 99999999)
        assert list(r) == ["lrc"]
        assert "Nihao World" not in r["lrc"]

    def test_drop与split无译文时结果一致(self):
        无译文 = process(LRC, "", "split", 99999999)
        assert list(无译文) == ["lrc"]

    def test_drop落盘只有一个文件(self, temp_dir):
        base = str(Path(temp_dir) / "X")
        paths = output_files(process(LRC, TLYRIC, "drop", 99999999), base)
        assert [Path(p).name for p in paths] == ["X.lrc"]
        assert not Path(base + ".2.lrc").exists()
