import shutil
import subprocess
import sys

import pytest

from test.conftest import ALBUM_ID, PLAYLIST_ID, PROJECT_ROOT, SONG_ID
from vncmd.core.config import VNCMD_HOME


# 入口脚本原先在仓库根目录的 vncmd.py，现在并进了包内的 vncmd.cli。
# 用 -m 而不是直接跑文件：cli.py 在 src/vncmd/ 下，
# 而它的导入是绝对的，直接跑会因为 sys.path 里没有 src 而失败
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
        """取直链走 api 层，不走 CLI。

        这条原本写的是 `vncmd song --url`，而 song 子命令从来没有过 --url
        这个选项，重整之前的代码里也 grep 不到。取链路由 api.py 的单测管，
        那边不受 CLI 参数增删影响
        """
        from vncmd.net.api import get_song_url

        url = get_song_url(SONG_ID)
        assert url, "取不到单曲的直链"
        assert url.startswith("http")

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
        r = _run(
            [
                "--config",
                f"download.dir={temp_dir}",
                "playlist",
                str(PLAYLIST_ID),
                "-d",
                "--limit",
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
                "--limit",
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
        # 「已创建」走 stderr。questionary 的提问与 info 也都在 stdout，
        # 只有 success() 那些是 stderr，所以这里要分开看
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
        """`--fetch-auto` 在 fc99943 被拆成了 `--fetch` 加 `--auto-accept`，
        测试没跟着改，一直报 unrecognized arguments"""
        r = _run(["tracker", self.TRACKER_NAME, "--fetch", "--auto-accept"], timeout=60)
        assert r.returncode == 0

    def test_show_after_fetch(self):
        r = _run(["tracker", self.TRACKER_NAME])
        assert r.returncode == 0
        # Count depends on API availability; fetch may be empty if rate-limited
        assert "已缓存曲目" in r.stdout
