import time
from pathlib import Path

from vncmd.core.config import (
    COOKIE_FILE,
    get_cache_dir,
    get_cache_ttl,
    is_cache_enabled,
)
from vncmd.core.jsonstore import read_json_safe, write_json_atomic

# 账号状态一天查一次就够了，中间都从磁盘读
ACCOUNT_TTL = 86400
_STATE_KEYS = ("logged_in", "vip", "vip_type")


def _song_dir(song_id: int) -> Path:
    path = Path(get_cache_dir()) / "song" / str(song_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_stale(path: Path) -> bool:
    """缓存文件超过有效期算未命中，ttl 为 0 时永不过期"""
    ttl = get_cache_ttl()
    if ttl <= 0:
        return False
    try:
        return time.time() - path.stat().st_mtime > ttl * 86400
    except OSError:
        return True


def put_raw_lyrics(song_id: int, lrc_text: str, tlyric_text: str) -> None:
    """缓存清理前的原始歌词，供后续解析复用"""
    if not is_cache_enabled():
        return
    d = _song_dir(song_id)
    (d / "lyric.raw.lrc").write_text(lrc_text, encoding="utf-8")
    (d / "tlyric.raw.lrc").write_text(tlyric_text, encoding="utf-8")


def get_song(song_id: int) -> dict | None:
    if not is_cache_enabled():
        return None
    path = _song_dir(song_id) / "info.json"
    if not path.exists() or _is_stale(path):
        return None
    return read_json_safe(path, None, what=f"曲目 {song_id} 的缓存")


def put_song(song_id: int, data: dict) -> None:
    if not is_cache_enabled():
        return
    write_json_atomic(_song_dir(song_id) / "info.json", data, indent=None)


def get_lyrics(song_id: int) -> dict | None:
    """从缓存读歌词"""
    if not is_cache_enabled():
        return None
    d = _song_dir(song_id)
    lrc_path = d / "lyric.lrc"
    if not lrc_path.exists() or _is_stale(lrc_path):
        return None
    result = {"lrc": {"lyric": lrc_path.read_text(encoding="utf-8")}}
    tlyric_path = d / "tlyric.lrc"
    if tlyric_path.exists():
        result["tlyric"] = {"lyric": tlyric_path.read_text(encoding="utf-8")}
    else:
        result["tlyric"] = {"lyric": ""}
    return result


def put_lyrics(song_id: int, data: dict) -> None:
    """写歌词缓存"""
    if not is_cache_enabled():
        return
    d = _song_dir(song_id)
    lrc_text = data.get("lrc", {}).get("lyric", "")
    (d / "lyric.lrc").write_text(lrc_text, encoding="utf-8")

    tlyric_text = data.get("tlyric", {}).get("lyric", "")
    tlyric_path = d / "tlyric.lrc"
    if tlyric_text:
        tlyric_path.write_text(tlyric_text, encoding="utf-8")
    elif tlyric_path.exists():
        # 翻译被上游删掉时必须删掉旧的，否则 get_lyrics 会一直读到上一次的翻译
        tlyric_path.unlink()


def _account_path() -> Path:
    # 放在缓存根目录，cache --clear 全清时会顺带清掉，不用另外处理
    return Path(get_cache_dir()) / "account.json"


def load_account() -> dict | None:
    """读账号缓存，三个状态键缺一不可"""
    if not is_cache_enabled():
        return None
    state = read_json_safe(_account_path(), None, what="账号缓存")
    if not isinstance(state, dict) or not all(k in state for k in _STATE_KEYS):
        return None
    return state


def account_is_fresh(state: dict) -> bool:
    """判断账号缓存是否有效

    失效判据为 cookie 文件修改时间
    """
    checked_at = state.get("checked_at") or 0
    if time.time() - checked_at >= ACCOUNT_TTL:
        return False
    try:
        return COOKIE_FILE.stat().st_mtime <= checked_at
    except OSError:
        # cookie 文件不见了，等于换了一份，重新查
        return False


def save_account(state: dict, checked_at: int) -> None:
    """写账号缓存，失败不打断命令"""
    if not is_cache_enabled():
        return
    try:
        path = _account_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(path, {"checked_at": checked_at, **state})
    except OSError:
        pass
