from vncmd.media.audio import (
    _MAX_FILENAME_BYTES,
    build_filename,
    check_filename,
    cover_ext,
    get_type_from_url,
    resolve_path,
)


class TestCheckFilename:
    def test_normal_unchanged(self):
        assert check_filename("Hello World") == "Hello World"

    def test_strips_special_chars(self):
        for ch in ("/", ":", "*", "?", '"', "<", ">", "|", "\\"):
            assert ch not in check_filename(f"a{ch}b")


class TestGetTypeFromUrl:
    def test_flac(self):
        assert get_type_from_url("http://test.vanadiry.com/t.flac?p=1") == "flac"

    def test_mp3(self):
        assert get_type_from_url("http://test.vanadiry.com/t.mp3") == "mp3"

    def test_未知扩展名保留原样(self, capsys):
        # 归成 mp3 会产出错扩展名的文件，改成保留真实扩展名并出声
        assert get_type_from_url("http://test.vanadiry.com/t.xyz") == "xyz"
        assert "暂不支持元数据嵌入" in capsys.readouterr().err

    def test_末段不是扩展名时归mp3(self, capsys):
        assert get_type_from_url("http://test.vanadiry.com/abcdef") == "mp3"
        assert capsys.readouterr().out == ""


class TestCoverExt:
    def test_jpg(self):
        assert cover_ext("http://test.vanadiry.com/img.jpg") == "jpg"

    def test_jpeg(self):
        assert cover_ext("http://test.vanadiry.com/img.jpeg") == "jpeg"

    def test_png(self):
        assert cover_ext("http://test.vanadiry.com/img.png?x=1") == "png"

    def test_default(self):
        assert cover_ext(None) == "jpg"


class TestBuildFilename:
    def test_no_illegal_chars(self):
        name, full = build_filename("Test/Title", "Artist:Name")
        assert "/" not in name
        assert ":" not in name
        assert full is None

    def test_non_empty(self):
        name, full = build_filename("Title", "Artist")
        assert len(name) > 0
        assert full is None

    def test_truncated_name_fits_byte_limit(self):
        name, full = build_filename("曲" * 500, "歌手" * 500)
        assert len(name.encode("utf-8")) <= _MAX_FILENAME_BYTES
        assert full == "曲" * 500 + " - " + "歌手" * 500

    def test_truncated_name_keeps_extension_room(self):
        name, _ = build_filename("曲" * 500, "歌手" * 500)
        assert len(f"{name}(999).flac".encode()) <= 255

    def test_short_name_not_truncated(self):
        name, full = build_filename("标题", "歌手")
        assert name == "标题 - 歌手"
        assert full is None


class TestResolvePath:
    def test_absolute(self, temp_dir):
        p = resolve_path("__unique_test__", "tmp", temp_dir)
        assert p.startswith(temp_dir)

    def test_ends_with_ext(self, temp_dir):
        p = resolve_path("__unique_test__", "tmp", temp_dir)
        assert p.endswith("__unique_test__.tmp")

    def test_dedup_different(self, temp_dir):
        p1 = resolve_path("__unique_test__", "tmp", temp_dir)
        open(p1, "w").close()
        p2 = resolve_path("__unique_test__", "tmp", temp_dir)
        assert p1 != p2
