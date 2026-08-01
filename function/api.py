import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from function.config import get_cookie
from function.cache import get_song as cache_get_song, put_song as cache_put_song
from function.cache import (
    get_lyrics as cache_get_lyrics,
    put_lyrics as cache_put_lyrics,
)

BASE_URL = "https://music.163.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://music.163.com/",
}

_session = None


def _get_session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(HEADERS)

        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods={"GET"},
        )
        adapter = HTTPAdapter(max_retries=retry)
        _session.mount("http://", adapter)
        _session.mount("https://", adapter)

        cookie = get_cookie()
        if cookie:
            for item in cookie.split(";"):
                item = item.strip()
                if "=" not in item:
                    continue
                name, value = item.split("=", 1)
                name = name.strip()
                value = value.strip()
                try:
                    value.encode("latin-1")
                except UnicodeEncodeError:
                    value = value.encode("latin-1", errors="ignore").decode("latin-1")
                if name and value:
                    _session.cookies.set(name, value, domain="music.163.com")
    return _session


def format_timestamp(ts: int | None) -> str:
    if ts is None:
        return ""
    t = time.localtime(ts / 1000)
    return time.strftime("%Y-%m-%d %H:%M:%S", t)


def _fmt_duration(ms: int | None) -> str:
    if not ms:
        return ""
    total_sec = ms // 1000
    m, s = divmod(total_sec, 60)
    return f"{m}:{s:02d}"


def _first_number(value) -> int | None:
    """Extract the first integer from a value (int, str like '05 [RAY]', or None)."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    import re

    m = re.search(r"\d+", str(value))
    return int(m.group()) if m else None


def _get_v1_song_detail(song_id: int) -> dict:
    url = f"{BASE_URL}/api/v1/song/detail/?id={song_id}&ids=%5B{song_id}%5D"
    resp = _get_session().get(url, timeout=15)
    return resp.json()


def get_song_details(song_id: int) -> dict:
    cached = cache_get_song(song_id)
    if cached:
        return cached

    v0_data = {}
    v1_data = {}
    try:
        v0_url = f"{BASE_URL}/api/song/detail/?id={song_id}&ids=%5B{song_id}%5D"
        v0_data = _get_session().get(v0_url, timeout=15).json()
    except Exception:
        pass
    try:
        v1_data = _get_v1_song_detail(song_id)
    except Exception:
        pass

    song = None
    if v0_data.get("songs"):
        song = v0_data["songs"][0]
    elif v1_data.get("songs"):
        song = v1_data["songs"][0]
        if "ar" in song:
            song["artists"] = song.pop("ar")
        if "al" in song:
            song["album"] = song.pop("al")

    if not song:
        raise ValueError(f"曲目 {song_id} 未找到")

    # Merge v1 fields not present in v0
    if v1_data.get("songs"):
        v1_song = v1_data["songs"][0]
        if "cd" not in song and "cd" in v1_song:
            song["cd"] = v1_song["cd"]
    result = {
        "id": song["id"],
        "title": song["name"],
        "artist": ", ".join(a["name"] for a in song.get("artists", [])),
        "album": song.get("album", {}).get("name", ""),
        "album_id": song.get("album", {}).get("id"),
        "cover": song.get("album", {}).get("picUrl", ""),
        "publish_time": format_timestamp(song.get("album", {}).get("publishTime")),
        "duration": _fmt_duration(song.get("duration")),
        "track_no": _first_number(song.get("no")),
        "cd_no": _first_number(song.get("cd")),
    }
    cache_put_song(song_id, result)
    return result


def get_playlist_details(playlist_id: int, limit: int | None = None) -> dict:
    n = max(2000, limit) if limit else 2000
    url = f"{BASE_URL}/api/v6/playlist/detail/?id={playlist_id}&n={n}"
    resp = _get_session().get(url, timeout=15)
    data = resp.json()

    pl = data.get("playlist")
    if not pl:
        raise ValueError(f"歌单 {playlist_id} 未找到")

    full_tracks = pl.get("tracks", [])
    track_ids = pl.get("trackIds", [])
    total = pl.get("trackCount", len(track_ids))

    # Detect removed tracks: in trackIds but not in tracks
    t_set = {t["id"] for t in full_tracks}
    removed_ids = []
    for tid in track_ids:
        sid = tid if isinstance(tid, int) else tid["id"]
        if sid not in t_set:
            removed_ids.append(sid)

    removed_tracks = []
    for sid in removed_ids:
        try:
            info = _get_removed_song_info(sid)
            if info:
                removed_tracks.append(info)
        except Exception:
            pass

    # Map tracks to standard format, apply programmatic limit
    raw_tracks = full_tracks[:limit] if limit else full_tracks
    tracks = []
    for t in raw_tracks:
        ar = t.get("ar", [])
        al = t.get("al", {})
        tracks.append(
            {
                "id": t["id"],
                "title": t["name"],
                "artist": ", ".join(a["name"] for a in ar),
                "album": al.get("name", ""),
                "cover": al.get("picUrl", ""),
                "publish_time": format_timestamp(al.get("publishTime")),
                "duration": _fmt_duration(t.get("dt")),
            }
        )

    creator = pl.get("creator", {})
    return {
        "id": pl["id"],
        "name": pl["name"],
        "creator": creator.get("nickname", ""),
        "cover": pl.get("coverImgUrl", ""),
        "track_count": total,
        "tracks": tracks,
        "removed_tracks": removed_tracks,
    }


def _get_removed_song_info(song_id: int) -> dict | None:
    data = _get_v1_song_detail(song_id)
    songs = data.get("songs", [])
    if not songs:
        return None
    s = songs[0]
    ar = s.get("ar", [])
    al = s.get("al", {})
    return {
        "id": s["id"],
        "title": s["name"],
        "artist": ", ".join(a["name"] for a in ar),
        "album": al.get("name", ""),
    }


def get_album_details(album_id: int) -> dict:
    url = f"{BASE_URL}/api/v1/album/{album_id}"
    resp = _get_session().get(url, timeout=15)
    data = resp.json()
    album = data.get("album")
    if not album:
        raise ValueError(f"专辑 {album_id} 未找到")

    tracks = []
    for s in data.get("songs", []):
        tracks.append(
            {
                "id": s["id"],
                "title": s["name"],
                "artist": ", ".join(a["name"] for a in s.get("ar", [])),
                "album": album.get("name", ""),
                "cover": album.get("picUrl", ""),
                "publish_time": format_timestamp(
                    s.get("publishTime") or album.get("publishTime")
                ),
                "duration": _fmt_duration(s.get("dt")),
            }
        )

    return {
        "id": album["id"],
        "name": album["name"],
        "artist": album.get("artist", {}).get("name", ""),
        "cover": album.get("picUrl", ""),
        "track_count": album.get("size", len(tracks)),
        "tracks": tracks,
    }


def search(q: str, limit: int = 30, offset: int = 0) -> dict:
    url = f"{BASE_URL}/api/cloudsearch/pc"
    resp = _get_session().get(
        url, params={"type": 1, "s": q, "limit": limit, "offset": offset}, timeout=15
    )
    data = resp.json()
    if data.get("code") != 200:
        raise ValueError(f"搜索失败：{data}")

    songs = []
    for s in data.get("result", {}).get("songs", []):
        songs.append(
            {
                "id": s["id"],
                "title": s["name"],
                "artist": ", ".join(a["name"] for a in s.get("ar", [])),
                "album": s.get("al", {}).get("name", ""),
                "cover": s.get("al", {}).get("picUrl", ""),
                "publish_time": format_timestamp(s.get("publishTime")),
                "duration": _fmt_duration(s.get("dt")),
            }
        )

    return {
        "total": data.get("result", {}).get("songCount", 0),
        "songs": songs,
    }


def get_lyrics_url(song_id: int) -> str:
    return f"{BASE_URL}/api/song/lyric?os=pc&id={song_id}&lv=-1&tv=1"


def get_lyrics(song_id: int) -> dict:
    cached = cache_get_lyrics(song_id)
    if cached:
        return cached

    url = get_lyrics_url(song_id)
    try:
        resp = _get_session().get(url, timeout=15)
        data = resp.json()
    except Exception:
        return {"lrc": {"lyric": ""}, "tlyric": {"lyric": ""}}

    if data.get("code") != 200:
        return {"lrc": {"lyric": ""}, "tlyric": {"lyric": ""}}

    result = {"lrc": data.get("lrc", {}), "tlyric": data.get("tlyric", {})}
    cache_put_lyrics(song_id, result)
    return result


def get_song_url(song_id: int, quality: int | None = None) -> str | None:
    br = quality if quality else 2147483647
    url = f"{BASE_URL}/api/song/enhance/player/url?ids=[{song_id}]&br={br}"
    resp = _get_session().get(url, timeout=15)
    data = resp.json()
    if data.get("data") and data["data"][0].get("url"):
        return data["data"][0]["url"]
    return None
