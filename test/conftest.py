import sys
import os
import shutil
import tempfile

import pytest

# sys.path setup — needed so that `from function.xxx import ...` works in tests
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Shared test IDs (real NetEase Music IDs for integration tests)
PLAYLIST_ID = 17647459371
SONG_ID = 22699098
ALBUM_ID = 123388631


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "network: tests that call the real NetEase API"
    )
    config.addinivalue_line(
        "markers", "slow: tests that download audio files"
    )


@pytest.fixture
def temp_dir():
    """Temporary directory that is automatically cleaned up after the test."""
    d = tempfile.mkdtemp(prefix="vnemd_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(autouse=True)
def _reset_config_cache():
    """Reset the config module's cached _cfg so each test sees a fresh state."""
    import function.config

    function.config._cfg = None


@pytest.fixture(scope="session", autouse=True)
def _ensure_dirs():
    """Ensure required directories exist for tests."""
    import function.config
    import os

    for path in (function.config.get_download_dir(), function.config.get_cache_dir()):
        os.makedirs(path, exist_ok=True)
