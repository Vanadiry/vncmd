import json
from pathlib import Path

from function.config import get_cache_dir, is_cache_enabled


def _song_dir(song_id: int) -> Path:
    path = Path(get_cache_dir()) / "song" / str(song_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_song_cache_dir(song_id: int) -> Path:
    return _song_dir(song_id)


def get_song(song_id: int) -> dict | None:
    if not is_cache_enabled():
        return None
    path = _song_dir(song_id) / "info.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def put_song(song_id: int, data: dict) -> None:
    if not is_cache_enabled():
        return
    path = _song_dir(song_id) / "info.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def get_lyrics(song_id: int) -> dict | None:
    """Read lyrics from cache. Returns dict {lrc, tlyric} or None."""
    if not is_cache_enabled():
        return None
    d = _song_dir(song_id)
    lrc_path = d / "lyric.lrc"
    if not lrc_path.exists():
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
    if tlyric_text:
        (d / "tlyric.lrc").write_text(tlyric_text, encoding="utf-8")
