import sys
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from rich.progress import (
    Progress,
    BarColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
)

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
        resp = _get_dl_session().get(url, stream=True, timeout=60)
        total = int(resp.headers.get("content-length", 0))

        if resp.status_code != 200:
            return "请求失败"

        if progress is not None and task_id is not None:
            progress.update(task_id, total=total or None)
            progress.start_task(task_id)
            with open(path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
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
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                        p.update(task, advance=len(chunk))
        else:
            with open(path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
        return None
    except Exception as e:
        return str(e)


def fetch_cover(cover_url: str) -> bytes | None:
    """Download cover image. Returns bytes or None."""
    try:
        return _get_dl_session().get(cover_url, timeout=15).content
    except Exception:
        return None


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
