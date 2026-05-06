import sys
import requests
from rich.progress import (
    Progress,
    BarColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
)


def fetch_audio(url, path, label):
    """Stream download audio with progress bar. Returns error message or None."""
    try:
        resp = requests.get(url, stream=True, timeout=60)
        total = int(resp.headers.get("content-length", 0))

        if resp.status_code != 200:
            return "Request failed"

        if sys.stdout.isatty():
            # Terminal mode: show animated progress bar
            with Progress(
                "[progress.description]{task.description}",
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                transient=True,
            ) as progress:
                task = progress.add_task(label[:40], total=total or None)
                with open(path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))
        else:
            # Pipe mode (test): download silently
            with open(path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
        return None
    except Exception as e:
        return str(e)


def fetch_cover(cover_url):
    """Download cover image. Returns bytes or None."""
    try:
        return requests.get(cover_url, timeout=15).content
    except Exception:
        return None


def fetch_lyrics(lyrics_api_url, source):
    """Fetch lyrics from API. Returns (lrc_text, tlyric_text)."""
    try:
        resp = requests.get(lyrics_api_url, timeout=15)
        if resp.text and source == "netease":
            data = resp.json()
            lyric = data.get("lrc", {}).get("lyric", "")
            tlyric = data.get("tlyric", {}).get("lyric", "")
            return lyric, tlyric
    except Exception:
        pass
    return "", ""
