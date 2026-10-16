import os
import shlex
import shutil
import subprocess
import sys
import time
from itertools import chain

import requests
from requests.adapters import HTTPAdapter
from rich.markup import escape
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from urllib3.util.retry import Retry

from function.api import HEADERS
from function.audio import looks_like_audio
from function.config import get_curl_arg, get_downloader
from function.image import detect_format

_dl_session = None


def _get_dl_session():
    global _dl_session
    if _dl_session is None:
        _dl_session = requests.Session()
        # 与 API session 保持一致，之前这里发的是 python-requests 的默认 UA，
        # 调 API 伪装浏览器、下载音频自曝为脚本，两边行为分裂
        _dl_session.headers.update(HEADERS)
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


def _curl_argv(url: str, path: str) -> list[str]:
    """拼 curl 的调用参数

    ``-o`` 放在用户参数之后，保证目标文件一定是我们的，
    用户误写了 ``-o`` 也只是覆盖不掉，不会把文件写到别处。
    ``--fail`` 必须带，否则 HTTP 错误页会被当正文写进文件并返回 0。
    """
    return [
        "curl",
        "-sSL",
        "--fail",
        "--speed-limit",
        "1024",
        "--speed-time",
        "30",
        *shlex.split(get_curl_arg() or ""),
        "-o",
        path,
        url,
    ]


def _file_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _wait_curl(proc, path: str, on_bytes) -> None:
    """等 curl 退出，顺带把目标文件的长大量喂给进度条

    curl 没有可供解析的进度输出，直接盯文件大小最省事，
    也让两条下载路径共用同一套进度接口。
    """
    last = 0
    while proc.poll() is None:
        size = _file_size(path)
        if size > last:
            on_bytes(size - last)
            last = size
        time.sleep(0.15)
    final = _file_size(path)
    if final > last:
        on_bytes(final - last)


def _fetch_audio_curl(
    url: str,
    path: str,
    label: str,
    total: int = 0,
    progress=None,
    task_id=None,
) -> str | None:
    """用系统 curl 下载，返回错误说明或 None

    与 ``fetch_audio`` 同签名好让上层无感切换。
    """
    try:
        proc = subprocess.Popen(
            _curl_argv(url, path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except OSError as e:
        return f"无法启动 curl：{e}"

    try:
        if progress is not None and task_id is not None:
            progress.update(task_id, total=total or None)
            progress.start_task(task_id)
            _wait_curl(proc, path, lambda n: progress.update(task_id, advance=n))
        elif sys.stdout.isatty():
            with Progress(
                "[progress.description]{task.description}",
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                transient=True,
            ) as p:
                task = p.add_task(escape(label[:40]), total=total or None)
                _wait_curl(proc, path, lambda n: p.update(task, advance=n))
        else:
            _wait_curl(proc, path, lambda _n: None)

        stderr = proc.communicate()[1] or b""
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    if proc.returncode != 0:
        detail = stderr.decode("utf-8", "replace").strip()
        code = proc.returncode
        # 22 是 --fail 命中 HTTP 错误，单独说明比裸报退出码有用
        head = "curl 传输失败" if code == 22 else f"curl 退出码 {code}"
        return f"{head}：{detail}" if detail else head

    if _file_size(path) == 0:
        return "curl 未写出文件"
    return None


def fetch_audio(
    url: str,
    path: str,
    label: str,
    progress=None,
    task_id=None,
    total: int = 0,
    use_curl: bool | None = None,
) -> str | None:
    """Stream download audio with progress bar. Returns error message or None.

    If *progress* and *task_id* are provided, they are used to update a shared
    Rich Progress instance.  Otherwise a per-file progress bar is created.

    ``use_curl`` 为 None 时读配置。``total`` 由服务端声明的大小填入，
    curl 这条路拿不到响应头，进度总量只能靠它。
    """
    if use_curl is None:
        use_curl = get_downloader() == "curl"
    if use_curl:
        # 配了 curl 却没装就直接说清楚，不静默退回内建，否则用户以为 --curl 生效了
        if not shutil.which("curl"):
            return (
                "找不到 curl，可执行 vncmd init 检查依赖，或把 downloader 改回 builtin"
            )
        return _fetch_audio_curl(
            url,
            path,
            label,
            total=total,
            progress=progress,
            task_id=task_id,
        )

    try:
        # 读超时给到 30 秒，原先的 10 秒对 25 MB 单连接过于激进，
        # 传输中只要卡一下就整个掐断。curl 那边用
        # --speed-limit 1024 --speed-time 30 表达同样的语义
        resp = _get_dl_session().get(url, stream=True, timeout=(15, 30))
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
                # 同 _progress_desc，未转义的歌名含 [Live] 会让进度条抛 MarkupError
                task = p.add_task(escape(label[:40]), total=total or None)
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
