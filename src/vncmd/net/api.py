import json
import re
import time
from contextlib import suppress
from threading import Lock
from urllib.parse import quote

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
# HANGUL FILLER 看着是空白，实际是个宽字符：Unicode 标它为 Wide，
# 终端按宽渲染，而表格算列宽时按零宽算，两边对不上会把竖线错开。
# 它只是拿来顶替空白的填充字符，清掉即可。
# 同类的 U+2800 盲文空白字符也有这个问题，暂不处理。
_BLANK_FILLER = re.compile("ㅤ")


def _clean(text) -> str:
    if not isinstance(text, str):
        return text
    return _BLANK_FILLER.sub("", _INVISIBLE.sub("", text))


def _text(value) -> str:
    """取字符串字段，键存在但值为 null 时给空串

    _clean 遇到非字符串会原样返回，那是给意外类型兜底的，
    但字段值为 null 时不能把 None 传下去：它会一路流到面板里，
    rich 的 Text.append 只收 str 与 Text，收到 None 直接抛 TypeError。
    接口对没有专辑条目的曲目确实返回 name 为 null。
    """
    return _clean(value) if isinstance(value, str) else ""


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
        "title": _text(song.get("name")),
        "artist": _clean(", ".join(a["name"] for a in song.get("artists") or [])),
        "album": _text(album.get("name")),
        # 没有专辑条目的曲目接口返回 id 为 0，不是真的专辑，
        # 显示时要按「没有」处理而不是印一个 0 出去
        "album_id": album.get("id") or 0,
        "cover": _text(album.get("picUrl")),
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
                "title": _clean(t["name"]),
                "artist": _clean(", ".join(a["name"] for a in ar)),
                "album": _clean(al.get("name", "")),
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


# 搜索接口的单次上限，实测 100 能过而 101 直接回 {'code': 400}。
# 放这一层而不是 CLI：这是服务端的事实，绕过命令行直接调本模块的人
# 也该被拦住，而不是拿到一句对用户毫无意义的 {'code': 400}
SEARCH_LIMIT_MAX = 100


def search(q: str, limit: int = 10, offset: int = 0) -> dict:
    url = f"{_BASE_URL}/api/cloudsearch/pc"
    resp = _get_session().get(
        url, params={"type": 1, "s": q, "limit": limit, "offset": offset}, timeout=15
    )
    data = resp.json()
    if data.get("code") != 200:
        # 只给接口返回的东西，不在这里加「搜索失败」的前缀：
        # 调用方 cmd_search 还会包一层，两边都写就成了「搜索失败：搜索失败：…」
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
    """一次取流返回的内容，url 之外还带上服务端给出的校验依据"""

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
    """批量取 player/url 的原始条目，按 id 索引

    响应里每条都带自己的 id，所以缺哪几条、下架哪几条都能对上，
    不靠顺序猜。取不到的 id 不在这份结果里，由调用方补空条目 ——
    否则「接口没返回这条」与「返回了但 url 为空」会混成一种。

    一次发全部 id 不分批：实测 529 个一次 0.83 秒且全部返回。
    （早先记过「一次超过 500 个会返回 0 条」，那是撞上限流时的空响应，
    被当成了长度限制 —— 与这次实测矛盾，按实测来。）
    """
    if not song_ids:
        return {}
    br = quality if quality else 2147483647
    ids = ",".join(str(sid) for sid in song_ids)
    url = f"{_BASE_URL}/api/song/enhance/player/url?ids=[{ids}]&br={br}"
    data = _get_session().get(url, timeout=15).json()
    return {item["id"]: item for item in (data.get("data") or []) if item.get("id")}


def fetch_player_url(song_id: int, quality: int | None = None) -> dict:
    """取 player/url 的原始条目

    取不到链接时也返回，fee 与 payed 这些判定权限要用的字段照样在里面，
    所以判断为什么下不了不必再发一次请求。
    """
    return fetch_player_urls([song_id], quality).get(song_id, {})


def get_audio_source(song_id: int, quality: int | None = None) -> AudioSource | None:
    """取下载链接，连同 size 与 md5 一起返回，缺失时按 0 与空串处理"""
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


# br -> 服务端在有权限时应当返回的 level。实测 128/192/320 三档有无 VIP
# 结果一致，只有最高档会因权限不足被压回 exhigh，所以只有它需要提示。
EXPECTED_LEVEL = {
    128000: "standard",
    192000: "higher",
    320000: "exhigh",
    2147483647: "lossless",
}

# level 是服务端的英文字段名，直接嵌进提示里中英文硬拼，读着别扭
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

    返回 ``{"logged_in": bool, "vip": bool, "vip_type": int}``；
    查询本身失败时返回 None，与「查出来没登录」是两回事，提示不能混。

    磁盘那份一天至多刷新一次，中间的运行都从缓存读，省掉一次请求。
    失效判据是 cookie 文件的修改时间，见 account_is_fresh。
    checked_at 存的是浮点秒：截成整秒的话，同一秒内刚写下的 cookie
    会因为 mtime 带小数而显得比检查时间新，于是每次运行都重查。

    force=True 时既不读缓存，查失败也不拿旧值兜底：
    「强制检查」要的是当下的真相，拿一小时前的状态顶替等于没查。

    这个接口无论登录与否都返回 code=200，不能看 code，要看 account 有没有。
    实测登录但无会员的账号 account 同样存在，会员档位是 vipType 字段，
    非零即有会员。
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
        # 查失败时保留上一次的好值，只把时间戳推进。
        # 不这么做的话，一次网络抖动会让用户一整天看不到权限状态
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
    """实打实发一次请求，失败返回 None"""
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
    """（检查时间，是否来自缓存），供提示说明这份状态的新鲜度

    没查过就返回 (0, False)，调用方按「刚查的」处理。
    """
    return _account_checked_at, _account_from_cache


def account_needs_check() -> bool:
    """这次调用会不会真的发请求

    播报要在请求之前先说一声「正在检查」，不然那一下停顿看着像卡住了。
    判据必须与 get_account_info 用的是同一套，否则会出现
    「预告了要查，结果读的是缓存」这种前后不一。
    """
    if _account_state is not _ACCOUNT_UNSET:
        return False
    cached = load_account()
    return not (cached and account_is_fresh(cached))


# 无会员时这两档都下不了，其余的无会员也能下
_FEE_NEED_VIP = {1, 4}


def permission_verdict(song: dict, account: dict | None) -> bool | None:
    """判断当前账号能不能下这一首

    三态：True 为确定下不了，False 为确定能下，None 为看不出来。
    两处返回 None 的理由一样，都是信息不够而不是结论相反：

    - 查不出账号状态时无从判断，标成下不了是在编
    - 接口没给 fee 时同上，标成能下同样是在编

    有会员一律给 False。实测有会员时 fee=1 的 205 首全部能下，
    而 fee=4 要看专辑买没买过，接口不给这个信息，
    样本里「有会员但没买过」这个组合没出现过，没法证伪就不断言。
    """
    if not account:
        return None
    if account.get("vip"):
        return False
    fee = song.get("fee")
    if fee is None:
        return None
    return fee in _FEE_NEED_VIP
