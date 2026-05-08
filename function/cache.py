import json
import os

from function.config import get_cache_dir, is_cache_enabled


def _song_dir(song_id):
    path = os.path.join(get_cache_dir(), "song", str(song_id))
    os.makedirs(path, exist_ok=True)
    return path


def get_song_cache_dir(song_id):
    return _song_dir(song_id)


def get_song(song_id):
    if not is_cache_enabled():
        return None
    path = os.path.join(_song_dir(song_id), "info.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.loads(f.read())


def put_song(song_id, data):
    if not is_cache_enabled():
        return
    path = os.path.join(_song_dir(song_id), "info.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def get_lyrics(song_id):
    """Read lyrics from cache. Returns dict {lrc, tlyric} or None."""
    if not is_cache_enabled():
        return None
    lrc_path = os.path.join(_song_dir(song_id), "lyric.lrc")
    if not os.path.exists(lrc_path):
        return None
    with open(lrc_path, "r", encoding="utf-8") as f:
        lrc_text = f.read()

    result = {"lrc": {"lyric": lrc_text}}
    tlyric_path = os.path.join(_song_dir(song_id), "tlyric.lrc")
    if os.path.exists(tlyric_path):
        with open(tlyric_path, "r", encoding="utf-8") as f:
            result["tlyric"] = {"lyric": f.read()}
    else:
        result["tlyric"] = {"lyric": ""}
    return result


def put_lyrics(song_id, data):
    """Save lyrics to cache. data is {lrc: {lyric: str}, tlyric: {lyric: str}}."""
    if not is_cache_enabled():
        return
    d = _song_dir(song_id)
    lrc_text = data.get("lrc", {}).get("lyric", "")
    with open(os.path.join(d, "lyric.lrc"), "w", encoding="utf-8") as f:
        f.write(lrc_text)

    tlyric_text = data.get("tlyric", {}).get("lyric", "")
    if tlyric_text:
        with open(os.path.join(d, "tlyric.lrc"), "w", encoding="utf-8") as f:
            f.write(tlyric_text)
