import sys
from itertools import chain

import requests
from requests.adapters import HTTPAdapter
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from urllib3.util.retry import Retry

from function.audio import looks_like_audio
from function.image import detect_format

_dl_session = None


def _get_dl_session():
    global _dl_session
    if _dl_session is None:
        _dl_session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods={"GET"},
        )
        adapter = HTTPAdapter(max_retries=retry)
        _dl_session.mount("http://", adapter)
        _dl_session.mount("https://", adapter)
    return _dl_session


def fetch_audio(
    url: str, path: str, label: str, progress=None, task_id=None
) -> str | None:
    """Stream download audio with progress bar. Returns error message or None.

    If *progress* and *task_id* are provided, they are used to update a shared
    Rich Progress instance.  Otherwise a per-file progress bar is created.
    """
    try:
        resp = _get_dl_session().get(url, stream=True, timeout=(15, 10))
        total = int(resp.headers.get("content-length", 0))

        if resp.status_code != 200:
            return f"请求失败：HTTP {resp.status_code}"

        # 200 也会带回错误页，落盘前先看内容是不是音频
        chunks = resp.iter_content(chunk_size=8192)
        head = next(chunks, b"")
        if not looks_like_audio(head):
            ctype = resp.headers.get("content-type", "未知类型")
            return f"服务器返回的不是音频：{ctype}"

        stream = chain([head], chunks)
        if progress is not None and task_id is not None:
            progress.update(task_id, total=total or None)
            progress.start_task(task_id)
            with open(path, "wb") as f:
                for chunk in stream:
                    f.write(chunk)
                    progress.update(task_id, advance=len(chunk))
        elif sys.stdout.isatty():
            with Progress(
                "[progress.description]{task.description}",
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                transient=True,
            ) as p:
                task = p.add_task(label[:40], total=total or None)
                with open(path, "wb") as f:
                    for chunk in stream:
                        f.write(chunk)
                        p.update(task, advance=len(chunk))
        else:
            with open(path, "wb") as f:
                for chunk in stream:
                    f.write(chunk)
        return None
    except Exception as e:
        return str(e)
    finally:
        if "resp" in locals():
            resp.close()


def fetch_cover(cover_url: str) -> bytes | None:
    """下载封面图片，非图片内容返回 None"""
    try:
        data = _get_dl_session().get(cover_url, timeout=15).content
    except Exception:
        return None
    # CDN 失效时以 200 返回错误页，落盘前先验魔数
    return data if detect_format(data) else None


def fetch_lyrics(lyrics_api_url: str, source: str) -> tuple[str, str]:
    """Fetch lyrics from API. Returns (lrc_text, tlyric_text)."""
    try:
        resp = _get_dl_session().get(lyrics_api_url, timeout=15)
        if resp.text and source == "netease":
            data = resp.json()
            lyric = data.get("lrc", {}).get("lyric", "")
            tlyric = data.get("tlyric", {}).get("lyric", "")
            return lyric, tlyric
    except Exception:
        pass
    return "", ""
