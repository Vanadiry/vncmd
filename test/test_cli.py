import shutil
import subprocess
import sys

import pytest

from test.conftest import ALBUM_ID, PLAYLIST_ID, PROJECT_ROOT, SONG_ID
from vncmd.core.config import VNCMD_HOME


# 用 -m 启动：cli.py 在 src/vncmd 下，直接跑文件时 sys.path 里没有 src
def _run(args, timeout=30, **kwargs):
    return subprocess.run(
        [sys.executable, "-m", "vncmd", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=PROJECT_ROOT,
        check=False,
        **kwargs,
    )


@pytest.mark.network
class TestCliPreview:
    def test_no_args_shows_usage(self):
        r = _run([])
        assert "用法：" in r.stdout

    def test_search(self):
        r = _run(["search", "Beyond", "--count", "3"])
        assert r.returncode == 0
        assert "Beyond" in r.stdout

    def test_song_preview(self):
        r = _run(["song", str(SONG_ID)])
        assert r.returncode == 0

    def test_song_lyrics(self):
        r = _run(["song", str(SONG_ID), "--lyric"])
        assert r.returncode == 0

    def test_song_url(self):
        """取直链走 api 层，song 子命令没有 --url 选项"""
        from vncmd.net.api import get_song_url

        url = get_song_url(SONG_ID)
        assert url, "取不到单曲的直链"
        assert url.startswith("http")

    def test_playlist_preview(self):
        r = _run(["playlist", str(PLAYLIST_ID), "--count", "3"])
        assert r.returncode == 0

    def test_album_preview(self):
        r = _run(["album", str(ALBUM_ID), "--count", "3"])
        assert r.returncode == 0


@pytest.mark.network
@pytest.mark.slow
class TestCliDownload:
    def test_playlist_download(self, temp_dir):
        r = _run(
            [
                "--config",
                f"download.dir={temp_dir}",
                "playlist",
                str(PLAYLIST_ID),
                "-d",
                "--count",
                "1",
            ],
            timeout=120,
        )
        assert r.returncode == 0

    def test_album_download(self, temp_dir):
        r = _run(
            [
                "--config",
                f"download.dir={temp_dir}",
                "album",
                str(ALBUM_ID),
                "-d",
                "--count",
                "1",
            ],
            timeout=120,
        )
        assert r.returncode == 0


@pytest.mark.network
class TestCliTracker:
    TRACKER_NAME = "_test_cli_tracker"

    @classmethod
    def setup_class(cls):
        cls._tracker_dir = VNCMD_HOME / "tracker" / cls.TRACKER_NAME
        # Create tracker via CLI
        r = subprocess.run(
            [sys.executable, "-m", "vncmd", "tracker", cls.TRACKER_NAME],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=PROJECT_ROOT,
            input="y\n",
            check=False,
        )
        assert r.returncode == 0
        # “已创建”走 stderr，questionary 的提问与 info 在 stdout，要分开看
        assert "已创建" in r.stderr
        # Write settings
        with open(cls._tracker_dir / "settings.toml", "w") as f:
            f.write(f"""[tracker]
description = "CLI test"

[sources.song]
ids = [{SONG_ID}]

[sources.playlist]
ids = []

[sources.album]
ids = []
""")

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(cls._tracker_dir, ignore_errors=True)

    def test_show(self):
        r = _run(["tracker", self.TRACKER_NAME])
        assert r.returncode == 0

    def test_fetch_auto(self):
        """--fetch-auto 已拆成 --fetch 与 --auto-accept"""
        r = _run(["tracker", self.TRACKER_NAME, "--fetch", "--auto-accept"], timeout=60)
        assert r.returncode == 0

    def test_show_after_fetch(self):
        r = _run(["tracker", self.TRACKER_NAME])
        assert r.returncode == 0
        # Count depends on API availability; fetch may be empty if rate-limited
        assert "已缓存曲目" in r.stdout
