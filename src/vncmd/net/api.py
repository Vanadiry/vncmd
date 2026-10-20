import datetime
import json
import re
import time
from contextlib import suppress
from threading import Lock
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from vncmd.core.config import get_cookie
from vncmd.core.output import warning
from vncmd.net.cache import (
    _STATE_KEYS,
    account_is_fresh,
    load_account,
    save_account,
)
from vncmd.net.cache import (
    get_lyrics as cache_get_lyrics,
)
from vncmd.net.cache import get_song as cache_get_song
from vncmd.net.cache import (
    put_lyrics as cache_put_lyrics,
)
from vncmd.net.cache import put_song as cache_put_song

_BASE_URL = "https://music.163.com"
# 批量查详情的分片大小，一次 100 个 id 的 URL 约 1300 字符
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
                # 含非 latin-1 的值设上去会静默失效，跳过并提示
                warning(f"Cookie {name} 含非 latin-1 字符，已跳过")
                continue
            if name and value:
                sess.cookies.set(name, value, domain="music.163.com")
    return sess


def _get_session() -> requests.Session:
    # 下载走线程池，双重检查避免常态加锁
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                _session = _build_session()
    return _session


def _fmt_publish_time(ts: int | None) -> str:
    # 上游的 0 与缺失都表示没有发行日期，不能格式化成 1970
    if not ts:
        return ""
    t = datetime.datetime.fromtimestamp(ts / 1000, tz=ZoneInfo("Asia/Shanghai"))
    return t.strftime("%Y-%m-%d %H:%M:%S")


def _fmt_duration(ms: int | None) -> str:
    if not ms:
        return ""
    total_sec = ms // 1000
    m, s = divmod(total_sec, 60)
    # 超过一小时补小时位，194:25 看不出量级
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _first_number(value) -> int | None:
    """提取值里的第一个整数"""
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
# HANGUL FILLER 被终端按宽字符渲染，表格按零宽计算会错位
_BLANK_FILLER = re.compile("ㅤ")


def _clean(text) -> str:
    if not isinstance(text, str):
        return text
    return _BLANK_FILLER.sub("", _INVISIBLE.sub("", text))


def _text(value) -> str:
    """取字符串字段，null 转空串

    null 不能传进 rich 的 Text.append，接口对无专辑的曲目会返回 name 为 null
    """
    return _clean(value) if isinstance(value, str) else ""


def _normalize_song(song: dict) -> dict:
    """把 v0 或 v1 返回的 song 对象转成统一结构"""
    if "ar" in song:
        song["artists"] = song.pop("ar")
    if "al" in song:
        song["album"] = song.pop("al")
    # v1 接口对部分歌曲返回 al 为 null，.get 的默认值不生效
    album = song.get("album") or {}
    return {
        "id": song["id"],
        "title": _text(song.get("name")),
        "artist": _clean(", ".join(a["name"] for a in song.get("artists") or [])),
        "album": _text(album.get("name")),
        # 无专辑的曲目返回 id 为 0，显示时按没有处理
        "album_id": album.get("id") or 0,
        "cover": _text(album.get("picUrl")),
        # 歌曲自己的发行日优先，没有才退回专辑日
        "publish_time": _fmt_publish_time(
            song.get("publishTime") or album.get("publishTime")
        ),
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

    # v1 有 cd 时补进 v0 结果
    if v1_data.get("songs"):
        v1_song = v1_data["songs"][0]
        if "cd" not in song and "cd" in v1_song:
            song["cd"] = v1_song["cd"]
    result = _normalize_song(song)
    cache_put_song(song_id, result)
    return result


def get_song_details_many(song_ids: list[int]) -> dict[int, dict]:
    """批量取曲目详情，缓存命中的部分不再请求"""
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


def get_publish_times(song_ids: list[int]) -> dict[int, str]:
    """批量补歌单缺失的发行日

    v0 的 song/detail 一次可查 100 个，歌曲日与专辑日都在响应里
    v1 批量没有日期，不写缓存，避免缺 cd 的 v0 数据污染单曲缓存
    """
    result: dict[int, str] = {}
    for start in range(0, len(song_ids), _DETAIL_BATCH_SIZE):
        chunk = song_ids[start : start + _DETAIL_BATCH_SIZE]
        ids = quote(json.dumps(chunk, separators=(",", ":")))
        with suppress(Exception):
            resp = (
                _get_session()
                .get(f"{_BASE_URL}/api/song/detail/?ids={ids}", timeout=20)
                .json()
            )
            for song in resp.get("songs") or []:
                sid = song.get("id")
                if not sid:
                    continue
                album = song.get("album") or {}
                result[sid] = _fmt_publish_time(
                    song.get("publishTime") or album.get("publishTime")
                )
    return result


def get_playlist_details(playlist_id: int) -> dict:
    # n 取多少都至少为 2000，限量由调用方在拿到完整列表后处理
    url = f"{_BASE_URL}/api/v6/playlist/detail/?id={playlist_id}&n=2000"
    resp = _get_session().get(url, timeout=15)
    data = resp.json()

    pl = data.get("playlist")
    if not pl:
        raise ValueError(f"歌单 {playlist_id} 未找到")

    full_tracks = pl.get("tracks", [])
    track_ids = pl.get("trackIds", [])
    total = pl.get("trackCount", len(track_ids))

    # trackIds 里不在 tracks 的多为已下架
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

    tracks = []
    missing_dates = []
    for t in full_tracks:
        ar = t.get("ar") or []
        al = t.get("al") or {}
        publish_time = _fmt_publish_time(t.get("publishTime") or al.get("publishTime"))
        if not publish_time:
            missing_dates.append(t["id"])
        tracks.append(
            {
                "id": t["id"],
                "title": _clean(t["name"]),
                "artist": _clean(", ".join(a["name"] for a in ar)),
                "album": _clean(al.get("name", "")),
                "cover": al.get("picUrl", ""),
                "publish_time": publish_time,
                "duration": _fmt_duration(t.get("dt")),
            }
        )

    # 歌单的 al 常常没有 publishTime，空日期只能再查一次 v0 批量
    if missing_dates:
        fallback = get_publish_times(missing_dates)
        for track in tracks:
            if not track["publish_time"]:
                track["publish_time"] = fallback.get(track["id"], "")

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
                "title": _clean(s["name"]),
                "artist": _clean(", ".join(a["name"] for a in s.get("ar", []))),
                "album": _clean(album.get("name", "")),
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


# 搜索单次上限，实测 100 可过、101 返回 code 400
SEARCH_LIMIT_MAX = 100


def search(q: str, limit: int = 10, offset: int = 0) -> dict:
    url = f"{_BASE_URL}/api/cloudsearch/pc"
    resp = _get_session().get(
        url, params={"type": 1, "s": q, "limit": limit, "offset": offset}, timeout=15
    )
    data = resp.json()
    if data.get("code") != 200:
        # 只返回接口原文，调用方还会加搜索失败前缀
        raise ValueError(str(data))

    songs = []
    for s in data.get("result", {}).get("songs", []):
        songs.append(
            {
                "id": s["id"],
                "title": _clean(s["name"]),
                "artist": _clean(", ".join(a["name"] for a in s.get("ar") or [])),
                "album": _clean((s.get("al") or {}).get("name", "")),
                "cover": (s.get("al") or {}).get("picUrl", ""),
                "publish_time": _fmt_publish_time(s.get("publishTime")),
                "duration": _fmt_duration(s.get("dt")),
                # 搜索结果里就有 fee，判断能不能下不必再发请求
                "fee": s.get("fee"),
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
    """一次取流的内容，含 url 与服务端校验字段"""

    __slots__ = ("expi", "level", "md5", "size", "url")

    def __init__(
        self, url: str, size: int = 0, md5: str = "", expi: int = 0, level: str = ""
    ) -> None:
        self.url = url
        self.size = size
        self.md5 = md5
        self.expi = expi
        # 服务端实际给的音质，可能因权限不足低于请求值
        self.level = level


def fetch_player_urls(
    song_ids: list[int], quality: int | None = None
) -> dict[int, dict]:
    """批量取 player/url 原始条目，按 id 索引

    缺的 id 不补条目，由调用方区分接口未返回与 url 为空
    一次发全部 id，实测 529 个 0.83 秒
    """
    if not song_ids:
        return {}
    br = quality if quality else 2147483647
    ids = ",".join(str(sid) for sid in song_ids)
    url = f"{_BASE_URL}/api/song/enhance/player/url?ids=[{ids}]&br={br}"
    data = _get_session().get(url, timeout=15).json()
    return {item["id"]: item for item in (data.get("data") or []) if item.get("id")}


def fetch_player_url(song_id: int, quality: int | None = None) -> dict:
    """取 player/url 原始条目，取不到链接时仍保留 fee 与 payed"""
    return fetch_player_urls([song_id], quality).get(song_id, {})


def get_audio_source(song_id: int, quality: int | None = None) -> AudioSource | None:
    """取下载链接，size 与 md5 缺失时给 0 与空串"""
    d = fetch_player_url(song_id, quality)
    if d.get("url"):
        return AudioSource(
            url=d["url"],
            size=d.get("size") or 0,
            md5=d.get("md5") or "",
            expi=d.get("expi") or 0,
            level=d.get("level") or "",
        )
    return None


def get_song_url(song_id: int, quality: int | None = None) -> str | None:
    src = get_audio_source(song_id, quality)
    return src.url if src else None


# br 对应的服务端 level，只有最高档会因权限不足被压回 exhigh
EXPECTED_LEVEL = {
    128000: "standard",
    192000: "higher",
    320000: "exhigh",
    2147483647: "lossless",
}

# 服务端 level 转中文标签
LEVEL_LABEL = {
    "standard": "标准音质",
    "higher": "高音质",
    "exhigh": "超高音质",
    "lossless": "无损音质",
}

_ACCOUNT_UNSET = object()
_account_state = _ACCOUNT_UNSET
_account_checked_at = 0
_account_from_cache = False


def get_account_info(force: bool = False) -> dict | None:
    """查登录态与会员档位，进程内与磁盘都缓存

    接口始终返回 code=200，登录态看 account 是否存在，会员看 vipType 非零
    查询失败返回 None，与查出来未登录分开。force 时不读缓存，失败也不回退旧值
    """
    global _account_state, _account_checked_at, _account_from_cache
    if not force and _account_state is not _ACCOUNT_UNSET:
        return _account_state

    cached = None if force else load_account()
    if cached and account_is_fresh(cached):
        _account_state = {k: cached[k] for k in _STATE_KEYS}
        _account_checked_at = cached["checked_at"]
        _account_from_cache = True
        return _account_state

    now = time.time()
    state = _fetch_account()
    if state is None:
        # 查失败时保留旧值并推进时间戳，避免一次抖动让用户整天看不到权限
        if cached:
            _account_state = {k: cached[k] for k in _STATE_KEYS}
            _account_checked_at = now
            _account_from_cache = True
            save_account(_account_state, now)
            return _account_state
        _account_state = None
        return None

    _account_state = state
    _account_checked_at = now
    _account_from_cache = False
    save_account(state, now)
    return state


def _fetch_account() -> dict | None:
    """发一次账号请求，失败返回 None"""
    try:
        resp = _get_session().get(f"{_BASE_URL}/api/nuser/account/get", timeout=15)
        acc = resp.json().get("account") or {}
    except Exception:
        return None

    if acc:
        return {
            "logged_in": True,
            "vip": bool(acc.get("vipType", 0)),
            "vip_type": acc.get("vipType", 0),
        }
    return {"logged_in": False, "vip": False, "vip_type": 0}


def account_stamp() -> tuple[int, bool]:
    """返回检查时间与是否来自缓存"""
    return _account_checked_at, _account_from_cache


def account_needs_check() -> bool:
    """这次调用是否会真的发请求

    判据与 get_account_info 一致，避免预告要查却读缓存
    """
    if _account_state is not _ACCOUNT_UNSET:
        return False
    cached = load_account()
    return not (cached and account_is_fresh(cached))


# 无会员时这两档都下不了，其余的无会员也能下
_FEE_NEED_VIP = {1, 4}


def permission_verdict(song: dict, account: dict | None) -> bool | None:
    """判断账号能否下载，True 为不能，False 为能，None 为无法判断

    账号状态或 fee 缺失时返回 None。有会员直接判能下，fee=4 是否已购无法从接口得知
    """
    if not account:
        return None
    if account.get("vip"):
        return False
    fee = song.get("fee")
    if fee is None:
        return None
    return fee in _FEE_NEED_VIP
