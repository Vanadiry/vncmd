import os
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

# 文件读写全部隔离到临时目录，必须在导入 config 之前设置
_session_home = tempfile.mkdtemp(prefix="vncmd_home_")
os.environ["VNCMD_HOME"] = _session_home

# 把 src 加入 sys.path，测试里才能导入 vncmd
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# 共享测试 ID，为真实网易云 ID，供联网测试用
PLAYLIST_ID = 17647459371
SONG_ID = 22699098
ALBUM_ID = 123388631

# 网易云返回毫秒，这个值在 UTC 下为 2011-09-01 08:00:00，上海时间为 16:00:00
SAMPLE_MS = 1314864000000


if hasattr(time, "tzset"):

    @contextmanager
    def as_tz(name):
        """临时固定进程时区并还原，验证结果不受本机时区影响
        改 TZ 后必须调 tzset，否则 C 库不会重新读取
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

else:  # pragma: no cover，仅 Windows 会走到

    @contextmanager
    def as_tz(_name):
        yield


def pytest_configure(config):
    config.addinivalue_line("markers", "network: tests that call the real NetEase API")
    config.addinivalue_line("markers", "slow: tests that download audio files")


@pytest.fixture
def temp_dir():
    """临时目录，测试结束后自动删除"""
    d = tempfile.mkdtemp(prefix="vncmd_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(autouse=True)
def _reset_config_cache():
    """清掉 config 模块缓存的 _cfg，让每条测试拿到干净状态"""
    import vncmd.core.config

    vncmd.core.config._cfg = None


@pytest.fixture(autouse=True)
def _reset_check_tools_cache():
    """清掉 checker 里带 lru_cache 的 has_ 系列函数
    测试会 monkeypatch shutil.which 模拟装没装
    """
    from vncmd.media.checker import clear_check_tools_cache

    clear_check_tools_cache()
    yield
    clear_check_tools_cache()


@pytest.fixture(scope="session", autouse=True)
def _ensure_dirs():
    """创建默认配置与测试所需目录"""
    import vncmd.core.config

    vncmd.core.config.validate_config()
    for path in (
        vncmd.core.config.get_download_dir(),
        vncmd.core.config.get_cache_dir(),
    ):
        Path(path).mkdir(parents=True, exist_ok=True)
