import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import suppress
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

from vncmd.core.config import get_curl_arg, get_downloader
from vncmd.core.output import err_console
from vncmd.media.audio import looks_like_audio
from vncmd.media.image import detect_format
from vncmd.net.api import HEADERS

_dl_session = None

# 魔数校验只需前几个字节，MP4 的 ftyp 标记落在偏移 4
_HEAD_BYTES = 16

# 断流后按 Range 续传的重试次数
_RESUME_ATTEMPTS = 3

# curl 可续传的退出码，33 为不支持 Range
_CURL_RESUMABLE = {18, 28, 56}


def _get_dl_session():
    global _dl_session
    if _dl_session is None:
        _dl_session = requests.Session()
        # 与 API session 共用 UA，避免下载请求暴露为脚本
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


def _curl_argv(url: str, path: str, resume: bool = True) -> list[str]:
    """拼 curl 参数

    -o 放在用户参数后，--fail 挡错误页，-C - 自动续传
    """
    argv = ["curl", "-sSL", "--fail", "--speed-limit", "1024", "--speed-time", "30"]
    if resume:
        argv += ["-C", "-"]
    argv += [*shlex.split(get_curl_arg() or ""), "-o", path, url]
    return argv


def _file_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _wait_curl(proc, path: str, on_bytes, start: int = 0) -> None:
    """等 curl 退出，按文件增长更新进度

    start 为续传前长度，只统计新增部分
    """
    last = start
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
    """用系统 curl 下载，返回错误说明或 None"""
    for attempt in range(1, _RESUME_ATTEMPTS + 1):
        have = _file_size(path)
        # 服务端声明的大小已知且已经下齐，不必再发请求
        if total and have and have >= total:
            return None

        code, stderr = _run_curl(url, path, have, total, label, progress, task_id)
        if code == 0:
            break
        detail = stderr.decode("utf-8", "replace").strip()
        last_attempt = attempt >= _RESUME_ATTEMPTS
        # 33 为不支持 Range，丢掉残文件重来
        if code == 33 and not last_attempt:
            with suppress(OSError):
                os.unlink(path)
            continue
        # 传输中断留给下一轮续传
        if code in _CURL_RESUMABLE and not last_attempt:
            continue
        # 22 为 --fail 命中 HTTP 错误，单独说明比裸报退出码有用
        head = "curl 传输失败" if code == 22 else f"curl 退出码 {code}"
        return f"{head}：{detail}" if detail else head

    if _file_size(path) == 0:
        return "curl 未写出文件"

    # 补魔数校验，挡下以 200 返回的错误页
    try:
        with open(path, "rb") as f:
            blob = f.read(_HEAD_BYTES)
    except OSError as e:
        return f"无法读取下载结果：{e}"
    if not looks_like_audio(blob):
        return "服务器返回的不是音频"
    return None


def _run_curl(url, path, have, total, label, progress, task_id):
    """跑一次 curl，返回 (退出码, stderr)"""
    # stderr 落临时文件，避免管道写满导致死锁
    with tempfile.TemporaryFile() as errf:
        try:
            proc = subprocess.Popen(
                _curl_argv(url, path),
                stdout=subprocess.DEVNULL,
                stderr=errf,
            )
        except OSError:
            raise
        try:
            if progress is not None and task_id is not None:
                progress.update(task_id, total=total or None)
                progress.start_task(task_id)
                _wait_curl(
                    proc,
                    path,
                    lambda n: progress.update(task_id, advance=n),
                    start=have,
                )
            elif sys.stderr.isatty():
                with Progress(
                    "[progress.description]{task.description}",
                    BarColumn(),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn(),
                    transient=True,
                    console=err_console,
                ) as p:
                    task = p.add_task(escape(label[:40]), total=total or None)
                    _wait_curl(
                        proc, path, lambda n: p.update(task, advance=n), start=have
                    )
            else:
                _wait_curl(proc, path, lambda _n: None, start=have)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
        errf.seek(0)
        return proc.returncode, errf.read()


def fetch_audio(
    url: str,
    path: str,
    label: str,
    progress=None,
    task_id=None,
    total: int = 0,
    use_curl: bool | None = None,
) -> str | None:
    """流式下载音频，返回错误说明或 None

    use_curl 为 None 时读配置，total 为服务端声明大小
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

    # 读超时 30 秒，避免传输卡顿被掐断
    return _fetch_audio_builtin(
        url, path, label, progress=progress, task_id=task_id, expect_total=total
    )


def _drain(path: str, stream, mode: str, on_bytes) -> None:
    """把响应流落盘，边写边报增量"""
    with open(path, mode) as f:
        for chunk in stream:
            f.write(chunk)
            on_bytes(len(chunk))


def _fetch_audio_builtin(
    url: str,
    path: str,
    label: str,
    progress=None,
    task_id=None,
    expect_total: int = 0,
) -> str | None:
    """流式下载，断流后按 Range 续传"""
    last = ""
    for attempt in range(1, _RESUME_ATTEMPTS + 1):
        offset = _file_size(path)
        # 服务端声明的大小已知且已经下齐，不必再发请求
        if expect_total and offset and offset >= expect_total:
            return None

        resp = None
        try:
            headers = {"Range": f"bytes={offset}-"} if offset else {}
            resp = _get_dl_session().get(
                url, stream=True, timeout=(15, 30), headers=headers
            )
            if resp.status_code == 206:
                mode, fresh = "ab", False
            elif resp.status_code == 200:
                # 要了 Range 却拿到 200，说明服务端不认，只能从头来
                mode, fresh, offset = "wb", True, 0
            else:
                return f"请求失败：HTTP {resp.status_code}"

            total = expect_total or (
                offset + int(resp.headers.get("content-length", 0))
            )
            chunks = resp.iter_content(chunk_size=8192)
            head = next(chunks, b"")
            # 续传段并非文件开头，魔数只对全新内容有意义
            if fresh and not looks_like_audio(head):
                ctype = resp.headers.get("content-type", "未知类型")
                return f"服务器返回的不是音频：{ctype}"
            stream = chain([head], chunks)

            if progress is not None and task_id is not None:
                progress.update(task_id, total=total or None)
                progress.start_task(task_id)
                _drain(
                    path, stream, mode, lambda n: progress.update(task_id, advance=n)
                )
            elif sys.stderr.isatty():
                with Progress(
                    "[progress.description]{task.description}",
                    BarColumn(),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn(),
                    transient=True,
                    console=err_console,
                ) as p:
                    # 同 _progress_desc，未转义的歌名含 [Live] 会让进度条抛 MarkupError
                    task = p.add_task(escape(label[:40]), total=total or None)
                    _drain(
                        path,
                        stream,
                        mode,
                        lambda n, _p=p, _t=task: _p.update(_t, advance=n),
                    )
            else:
                _drain(path, stream, mode, lambda _n: None)
            return None
        except Exception as e:
            last = str(e)
            if attempt < _RESUME_ATTEMPTS:
                time.sleep(0.5 * attempt)
        finally:
            if resp is not None:
                resp.close()
    return last


def fetch_cover(cover_url: str) -> bytes | None:
    """下载封面图片，非图片内容返回 None"""
    try:
        data = _get_dl_session().get(cover_url, timeout=15).content
    except Exception:
        return None
    # CDN 失效时以 200 返回错误页，落盘前先验魔数
    return data if detect_format(data) else None


def fetch_lyrics(lyrics_api_url: str, source: str) -> tuple[str, str]:
    """从接口取歌词，返回原文与译文"""
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
