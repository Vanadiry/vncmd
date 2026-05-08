import sys
import shutil
import subprocess
import pytest
from test.conftest import PROJECT_ROOT, SONG_ID, PLAYLIST_ID, ALBUM_ID


def _run(args, timeout=30, **kwargs):
    return subprocess.run(
        [sys.executable, "vncmd.py"] + args,
        capture_output=True, text=True, timeout=timeout, cwd=PROJECT_ROOT, **kwargs
    )


@pytest.mark.network
class TestCliPreview:
    def test_no_args_shows_usage(self):
        r = _run([])
        assert "usage:" in (r.stdout + r.stderr).lower()

    def test_search(self):
        r = _run(["search", "Beyond", "--limit", "3"])
        assert r.returncode == 0
        assert "Beyond" in r.stdout

    def test_song_preview(self):
        r = _run(["song", str(SONG_ID)])
        assert r.returncode == 0

    def test_song_lyrics(self):
        r = _run(["song", str(SONG_ID), "--lyrics"])
        assert r.returncode == 0

    def test_song_url(self):
        r = _run(["song", str(SONG_ID), "--url", "-q", "128"])
        assert r.returncode == 0

    def test_playlist_preview(self):
        r = _run(["playlist", str(PLAYLIST_ID), "--limit", "3"])
        assert r.returncode == 0

    def test_album_preview(self):
        r = _run(["album", str(ALBUM_ID), "--limit", "3"])
        assert r.returncode == 0


@pytest.mark.network
@pytest.mark.slow
class TestCliDownload:
    def test_playlist_download(self, temp_dir):
        r = _run(["playlist", str(PLAYLIST_ID), "-d", "--limit", "1", "-o", temp_dir], timeout=120)
        assert r.returncode == 0

    def test_album_download(self, temp_dir):
        r = _run(["album", str(ALBUM_ID), "-d", "--limit", "1", "-o", temp_dir], timeout=120)
        assert r.returncode == 0


@pytest.mark.network
class TestCliTracker:
    TRACKER_NAME = "_test_cli_tracker"

    @classmethod
    def setup_class(cls):
        cls._tracker_dir = PROJECT_ROOT / "tracker" / cls.TRACKER_NAME
        # Create tracker via CLI
        r = subprocess.run(
            [sys.executable, "vncmd.py", "tracker", cls.TRACKER_NAME],
            capture_output=True, text=True, timeout=10, cwd=PROJECT_ROOT, input="y\n",
        )
        assert r.returncode == 0
        assert "created" in r.stdout.lower()
        # Write settings
        with open(cls._tracker_dir / "settings.toml", "w") as f:
            f.write(f"""[tracker]
description = "CLI test"

[[sources]]
type = "song"
ids = [{SONG_ID}]

[[sources]]
type = "playlist"
ids = []

[[sources]]
type = "album"
ids = []
""")

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(cls._tracker_dir, ignore_errors=True)

    def test_show(self):
        r = _run(["tracker", self.TRACKER_NAME])
        assert r.returncode == 0

    def test_fetch_auto(self):
        r = _run(["tracker", self.TRACKER_NAME, "--fetch-auto"], timeout=60)
        assert r.returncode == 0

    def test_show_after_fetch(self):
        r = _run(["tracker", self.TRACKER_NAME])
        assert r.returncode == 0
        # Count depends on API availability; fetch may be empty if rate-limited
        assert "Cached songs:" in r.stdout
