import os
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

# Isolate all file I/O to a temp directory — set before anything imports config
_session_home = tempfile.mkdtemp(prefix="vncmd_home_")
os.environ["VNCMD_HOME"] = _session_home

# sys.path setup — needed so that `from function.xxx import ...` works in tests
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Shared test IDs (real NetEase Music IDs for integration tests)
PLAYLIST_ID = 17647459371
SONG_ID = 22699098
ALBUM_ID = 123388631

# 网易云给的是毫秒，这个值在 UTC 下是 2011-09-01 08:00:00，UTC+8 下是 16:00:00
SAMPLE_MS = 1314864000000


if hasattr(time, "tzset"):

    @contextmanager
    def as_tz(name):
        """Temporarily pin the process timezone, restoring it afterwards

        发行时间走的是 time.localtime，本地时区是有意为之的行为。
        但断言若直接写死某个时刻的墙上时间，等于把作者本机的时区
        当成了常量：写测试时是 UTC+8，换到 UTC 的 CI runner 上就成了
        08:00:00。断言前钉住时区，既有确定值又真正验证了换算本身。

        改了 TZ 必须调 tzset，否则 C 库不会重新读取。
        """
        old = os.environ.get("TZ")
        os.environ["TZ"] = name
        time.tzset()
        try:
            yield
        finally:
            if old is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = old
            time.tzset()

else:  # pragma: no cover - 仅 Windows 会走到

    @contextmanager
    def as_tz(_name):
        yield


def pytest_configure(config):
    config.addinivalue_line("markers", "network: tests that call the real NetEase API")
    config.addinivalue_line("markers", "slow: tests that download audio files")


@pytest.fixture
def temp_dir():
    """Temporary directory that is automatically cleaned up after the test."""
    d = tempfile.mkdtemp(prefix="vncmd_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(autouse=True)
def _reset_config_cache():
    """Reset the config module's cached _cfg so each test sees a fresh state."""
    import function.config

    function.config._cfg = None


@pytest.fixture(autouse=True)
def _reset_check_tools_cache():
    """checker 的三个 has_* 带 lru_cache，每条测试前后都清一次。

    那些测试会 monkeypatch shutil.which 来模拟「装没装」，
    不清就会拿到上一条测试留下的缓存值。
    """
    from function.checker import clear_check_tools_cache

    clear_check_tools_cache()
    yield
    clear_check_tools_cache()


@pytest.fixture(scope="session", autouse=True)
def _ensure_dirs():
    """Create default config and required directories for tests."""
    import function.config

    function.config.validate_config()
    for path in (function.config.get_download_dir(), function.config.get_cache_dir()):
        Path(path).mkdir(parents=True, exist_ok=True)
