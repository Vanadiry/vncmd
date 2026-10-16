import time
from pathlib import Path

from function.config import get_cache_dir, get_cache_ttl, is_cache_enabled
from function.jsonstore import read_json_safe, write_json_atomic


def _song_dir(song_id: int) -> Path:
    path = Path(get_cache_dir()) / "song" / str(song_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_stale(path: Path) -> bool:
    """缓存文件过了有效期就算未命中，ttl 为 0 时永不过期

    上游改歌名、换专辑或修歌词后，永久缓存会让 vncmd 一直看不到更新。
    取不到 mtime 时按过期处理，下一次访问会重新拉取并覆盖。
    """
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
    """Read lyrics from cache. Returns dict {lrc, tlyric} or None."""
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
    """Save lyrics to cache. data is {lrc: {lyric: str}, tlyric: {lyric: str}}."""
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
