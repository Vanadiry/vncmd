import json
import re
import time
from contextlib import suppress
from threading import Lock
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from function.cache import (
    get_lyrics as cache_get_lyrics,
)
from function.cache import get_song as cache_get_song
from function.cache import (
    put_lyrics as cache_put_lyrics,
)
from function.cache import put_song as cache_put_song
from function.config import get_cookie
from function.output import warning

_BASE_URL = "https://music.163.com"
# 批量查详情的分片大小，一次 100 个 id 实测约 1300 字符的 URL
_DETAIL_BATCH_SIZE = 100
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://music.163.com/",
}

_session = None
_session_lock = Lock()


def _build_session() -> requests.Session:
    sess = requests.Session()
    sess.headers.update(HEADERS)

    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods={"GET"},
    )
    adapter = HTTPAdapter(max_retries=retry)
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)

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
                # 截断后的值与原值不同，设上去网易云认不出用户，
                # 表现是登录态看着有却不生效。这类值多半是复制时没做 URL 编码，
                # 宁可跳过并出声，不要静默塞一个错的值
                warning(f"Cookie {name} 含非 latin-1 字符，已跳过")
                continue
            if name and value:
                sess.cookies.set(name, value, domain="music.163.com")
    return sess


def _get_session() -> requests.Session:
    # 下载走线程池，多个 worker 可能同时走到这里。
    # 检查放在锁外让常态不加锁，真正要建的那次在锁内再确认一遍
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                _session = _build_session()
    return _session


def _fmt_publish_time(ts: int | None) -> str:
    if ts is None:
        return ""
    t = time.localtime(ts / 1000)
    return time.strftime("%Y-%m-%d %H:%M:%S", t)


def _fmt_duration(ms: int | None) -> str:
    if not ms:
        return ""
    total_sec = ms // 1000
    m, s = divmod(total_sec, 60)
    # 不足一小时的照旧，超过的补出小时位，
    # 194:25 这种写法看不出量级，串烧与长现场尤其吃亏
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _first_number(value) -> int | None:
    """Extract the first integer from a value (int, str like '05 [RAY]', or None)."""
    if value is None:
        return None
    if isinstance(value, int):
        return value

    m = re.search(r"\d+", str(value))
    return int(m.group()) if m else None


def _get_v1_song_detail(song_id: int) -> dict:
    url = f"{_BASE_URL}/api/v1/song/detail/?id={song_id}&ids=%5B{song_id}%5D"
    resp = _get_session().get(url, timeout=15)
    return resp.json()


# 网易云数据里混有零宽字符，肉眼看不见，但会被复制进文件名和元数据标签
_INVISIBLE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")


def _clean(text) -> str:
    return _INVISIBLE.sub("", text) if isinstance(text, str) else text


def _normalize_song(song: dict) -> dict:
    """把 v0 或 v1 返回的 song 对象转成统一结构"""
    if "ar" in song:
        song["artists"] = song.pop("ar")
    if "al" in song:
        song["album"] = song.pop("al")
    # 键存在但值为 null 时 .get 的默认值不生效，得用 or 兜住，
    # 网易云的 v1 接口对部分歌曲确实返回 al 为 null
    album = song.get("album") or {}
    return {
        "id": song["id"],
        "title": _clean(song["name"]),
        "artist": _clean(", ".join(a["name"] for a in song.get("artists") or [])),
        "album": _clean(album.get("name", "")),
        "album_id": album.get("id"),
        "cover": album.get("picUrl", ""),
        "publish_time": _fmt_publish_time(album.get("publishTime")),
        "duration": _fmt_duration(song.get("duration")),
        "track_no": _first_number(song.get("no")),
        "cd_no": _first_number(song.get("cd")),
    }


def get_song_details(song_id: int) -> dict:
    cached = cache_get_song(song_id)
    if cached:
        return cached

    v0_data = {}
    v1_data = {}
    # 两个端点互相兜底，任一失败都不影响另一个
    with suppress(Exception):
        v0_url = f"{_BASE_URL}/api/song/detail/?id={song_id}&ids=%5B{song_id}%5D"
        v0_data = _get_session().get(v0_url, timeout=15).json()
    with suppress(Exception):
        v1_data = _get_v1_song_detail(song_id)

    song = None
    if v0_data.get("songs"):
        song = v0_data["songs"][0]
    elif v1_data.get("songs"):
        song = v1_data["songs"][0]

    if not song:
        raise ValueError(f"曲目 {song_id} 未找到")

    # Merge v1 fields not present in v0
    if v1_data.get("songs"):
        v1_song = v1_data["songs"][0]
        if "cd" not in song and "cd" in v1_song:
            song["cd"] = v1_song["cd"]
    result = _normalize_song(song)
    cache_put_song(song_id, result)
    return result


def get_song_details_many(song_ids: list[int]) -> dict[int, dict]:
    """批量取曲目详情，命中缓存的部分不再请求

    逐个查询在歌单有大量下架曲目时不可用，几百次串行请求要按分钟计
    """
    result: dict[int, dict] = {}
    missing: list[int] = []
    for song_id in song_ids:
        cached = cache_get_song(song_id)
        if cached:
            result[song_id] = cached
        else:
            missing.append(song_id)

    for start in range(0, len(missing), _DETAIL_BATCH_SIZE):
        chunk = missing[start : start + _DETAIL_BATCH_SIZE]
        query = quote(json.dumps(chunk, separators=(",", ":")))
        with suppress(Exception):
            resp = (
                _get_session()
                .get(f"{_BASE_URL}/api/v1/song/detail/?ids={query}", timeout=20)
                .json()
            )
            for raw in resp.get("songs") or []:
                if not raw.get("id"):
                    continue
                detail = _normalize_song(dict(raw))
                result[detail["id"]] = detail
                cache_put_song(detail["id"], detail)
    return result


def get_playlist_details(playlist_id: int) -> dict:
    # n 取多少都至少是 2000，限量由调用方在拿到完整列表后处理
    url = f"{_BASE_URL}/api/v6/playlist/detail/?id={playlist_id}&n=2000"
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
    if removed_ids:
        details = get_song_details_many(removed_ids)
        removed_tracks = [
            {
                "id": sid,
                "title": details[sid]["title"],
                "artist": details[sid]["artist"],
                "album": details[sid]["album"],
            }
            for sid in removed_ids
            if sid in details
        ]

    # Map tracks to standard format
    tracks = []
    for t in full_tracks:
        ar = t.get("ar") or []
        al = t.get("al") or {}
        tracks.append(
            {
                "id": t["id"],
                "title": t["name"],
                "artist": ", ".join(a["name"] for a in ar),
                "album": al.get("name", ""),
                "cover": al.get("picUrl", ""),
                "publish_time": _fmt_publish_time(al.get("publishTime")),
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


def get_album_details(album_id: int) -> dict:
    url = f"{_BASE_URL}/api/v1/album/{album_id}"
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
                "publish_time": _fmt_publish_time(
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
    url = f"{_BASE_URL}/api/cloudsearch/pc"
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
                "artist": ", ".join(a["name"] for a in s.get("ar") or []),
                "album": (s.get("al") or {}).get("name", ""),
                "cover": (s.get("al") or {}).get("picUrl", ""),
                "publish_time": _fmt_publish_time(s.get("publishTime")),
                "duration": _fmt_duration(s.get("dt")),
            }
        )

    return {
        "total": data.get("result", {}).get("songCount", 0),
        "songs": songs,
    }


def get_lyrics_url(song_id: int) -> str:
    return f"{_BASE_URL}/api/song/lyric?os=pc&id={song_id}&lv=-1&tv=1"


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


class AudioSource:
    """一次取流返回的内容，url 之外还带上服务端给出的校验依据"""

    __slots__ = ("expi", "md5", "size", "url")

    def __init__(self, url: str, size: int = 0, md5: str = "", expi: int = 0) -> None:
        self.url = url
        self.size = size
        self.md5 = md5
        self.expi = expi


def get_audio_source(song_id: int, quality: int | None = None) -> AudioSource | None:
    """取下载链接，连同 size 与 md5 一起返回，缺失时按 0 与空串处理"""
    br = quality if quality else 2147483647
    url = f"{_BASE_URL}/api/song/enhance/player/url?ids=[{song_id}]&br={br}"
    resp = _get_session().get(url, timeout=15)
    data = resp.json()
    if data.get("data") and data["data"][0].get("url"):
        d = data["data"][0]
        return AudioSource(
            url=d["url"],
            size=d.get("size") or 0,
            md5=d.get("md5") or "",
            expi=d.get("expi") or 0,
        )
    return None


def get_song_url(song_id: int, quality: int | None = None) -> str | None:
    src = get_audio_source(song_id, quality)
    return src.url if src else None
