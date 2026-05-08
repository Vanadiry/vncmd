from function.audio import (
    check_filename,
    get_type_from_url,
    cover_ext,
    build_filename,
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
        assert get_type_from_url("http://x.com/t.flac?p=1") == "flac"

    def test_mp3(self):
        assert get_type_from_url("http://x.com/t.mp3") == "mp3"

    def test_default(self):
        assert get_type_from_url("http://x.com/t.xyz") == "mp3"


class TestCoverExt:
    def test_jpg(self):
        assert cover_ext("http://x.com/img.jpg") == "jpg"

    def test_jpeg(self):
        assert cover_ext("http://x.com/img.jpeg") == "jpeg"

    def test_png(self):
        assert cover_ext("http://x.com/img.png?x=1") == "png"

    def test_default(self):
        assert cover_ext(None) == "jpg"


class TestBuildFilename:
    def test_no_illegal_chars(self):
        name = build_filename("Test/Title", "Artist:Name")
        assert "/" not in name
        assert ":" not in name

    def test_non_empty(self):
        name = build_filename("Title", "Artist")
        assert len(name) > 0


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
