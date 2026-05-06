import time
import requests

from function.config import get_cookie
from function.cache import get_song as cache_get_song, put_song as cache_put_song
from function.cache import (
    get_lyrics as cache_get_lyrics,
    put_lyrics as cache_put_lyrics,
)

BASE_URL = "http://music.163.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "http://music.163.com/",
}

_session = None


def _get_session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(HEADERS)
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


def format_timestamp(ts):
    if ts is None:
        return ""
    t = time.localtime(ts / 1000)
    return time.strftime("%Y-%m-%d %H:%M:%S", t)


def _fmt_duration(ms):
    if not ms:
        return ""
    total_sec = ms // 1000
    m, s = divmod(total_sec, 60)
    return f"{m}:{s:02d}"


def get_song_details(song_id):
    cached = cache_get_song(song_id)
    if cached:
        return cached

    url = f"{BASE_URL}/api/song/detail/?id={song_id}&ids=%5B{song_id}%5D"
    resp = _get_session().get(url, timeout=15)
    data = resp.json()
    if not data.get("songs"):
        raise ValueError(f"Song {song_id} not found")

    song = data["songs"][0]
    result = {
        "id": song["id"],
        "title": song["name"],
        "artist": ",".join(a["name"] for a in song.get("artists", [])),
        "album": song.get("album", {}).get("name", ""),
        "album_id": song.get("album", {}).get("id"),
        "cover": song.get("album", {}).get("picUrl", ""),
        "publish_time": format_timestamp(song.get("album", {}).get("publishTime")),
        "duration": _fmt_duration(song.get("duration")),
    }
    cache_put_song(song_id, result)
    return result


def get_playlist_details(playlist_id, limit=None):
    url = f"{BASE_URL}/api/v6/playlist/detail/?id={playlist_id}"
    resp = _get_session().get(url, timeout=15)
    data = resp.json()
    if not data.get("playlist"):
        raise ValueError(f"Playlist {playlist_id} not found")

    pl = data["playlist"]
    tracks = []

    full_tracks = pl.get("tracks") or []
    track_ids = pl.get("trackIds") or []
    ft_map = {t["id"]: t for t in full_tracks}

    # Limit resolution to what's needed
    resolve_count = min(limit, len(track_ids)) if limit else len(track_ids)

    if track_ids and resolve_count > 0:
        if resolve_count > len(full_tracks):
            print(f"Resolving {resolve_count} tracks...")
        for i, tid in enumerate(track_ids[:resolve_count]):
            sid = tid if isinstance(tid, int) else tid["id"]
            ft = ft_map.get(sid)
            if ft:
                tracks.append(
                    {
                        "id": ft["id"],
                        "title": ft["name"],
                        "artist": ", ".join(a["name"] for a in ft.get("ar", [])),
                        "album": ft.get("al", {}).get("name", ""),
                        "cover": ft.get("al", {}).get("picUrl", ""),
                        "publish_time": format_timestamp(
                            ft.get("publishTime") or ft.get("al", {}).get("publishTime")
                        ),
                        "duration": _fmt_duration(ft.get("dt")),
                    }
                )
            else:
                try:
                    song = get_song_details(sid)
                    tracks.append(
                        {
                            "id": song["id"],
                            "title": song["title"],
                            "artist": song["artist"],
                            "album": song["album"],
                            "cover": song["cover"],
                            "publish_time": song["publish_time"],
                            "duration": song["duration"],
                        }
                    )
                except Exception:
                    pass
            if (i + 1) % 20 == 0:
                print(f"  ... {i + 1}/{len(track_ids)}")
            time.sleep(0.1)
    elif full_tracks:
        for t in full_tracks:
            tracks.append(
                {
                    "id": t["id"],
                    "title": t["name"],
                    "artist": ", ".join(a["name"] for a in t.get("ar", [])),
                    "album": t.get("al", {}).get("name", ""),
                    "cover": t.get("al", {}).get("picUrl", ""),
                    "publish_time": format_timestamp(
                        t.get("publishTime") or t.get("al", {}).get("publishTime")
                    ),
                    "duration": _fmt_duration(t.get("dt")),
                }
            )

    result = {
        "id": pl["id"],
        "name": pl["name"],
        "creator": pl.get("creator", {}).get("nickname", ""),
        "cover": pl.get("coverImgUrl", ""),
        "track_count": pl.get("trackCount", len(tracks)),
        "tracks": tracks,
    }
    return result


def get_album_details(album_id):
    url = f"{BASE_URL}/api/v1/album/{album_id}"
    resp = _get_session().get(url, timeout=15)
    data = resp.json()
    album = data.get("album")
    if not album:
        raise ValueError(f"Album {album_id} not found")

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


def search(q, limit=30, offset=0):
    url = f"{BASE_URL}/api/cloudsearch/pc?type=1&s={q}&limit={limit}&offset={offset}"
    resp = _get_session().get(url, timeout=15)
    data = resp.json()
    if data.get("code") != 200:
        raise ValueError(f"Search failed: {data}")

    songs = []
    for s in data.get("result", {}).get("songs", []):
        songs.append(
            {
                "id": s["id"],
                "title": s["name"],
                "artist": ",".join(a["name"] for a in s.get("ar", [])),
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


def get_lyrics(song_id):
    cached = cache_get_lyrics(song_id)
    if cached:
        return cached

    url = f"{BASE_URL}/api/song/lyric?os=pc&id={song_id}&lv=-1&tv=1"
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


def get_song_url(song_id, quality=None):
    br = quality if quality else 2147483647
    url = f"{BASE_URL}/api/song/enhance/player/url?ids=[{song_id}]&br={br}"
    resp = _get_session().get(url, timeout=15)
    data = resp.json()
    if data.get("data") and data["data"][0].get("url"):
        return data["data"][0]["url"]
    return None
