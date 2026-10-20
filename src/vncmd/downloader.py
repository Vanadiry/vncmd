import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock

from rich.cells import cell_len
from rich.markup import escape
from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
)
from rich.text import Text

from vncmd.checkpoint import (
    mark_downloaded,
)
from vncmd.core.config import (
    abbrev_home,
    get_auto_trim,
    get_check_enabled,
    get_concurrency,
    get_cookie,
    get_credit_scan_lines,
    get_download_content,
    get_download_dir,
    get_embed_cover_compress,
    get_embed_lyrics_mode,
    get_parse_credits,
    get_save_cover_compress,
    get_save_lyrics_mode,
)
from vncmd.core.output import (
    console,
    err_console,
    error,
    info,
    success,
    warning,
)
from vncmd.media.audio import (
    build_filename,
    cover_ext,
    get_type_from_url,
    resolve_path,
)
from vncmd.media.checker import (
    any_check_tool,
    check_audio,
    check_md5,
    check_tools,
    describe_missing_check_tools,
)
from vncmd.media.image import detect_format
from vncmd.media.image import process_cover as process_cover_image
from vncmd.media.lyrics import (
    output_files as output_lyrics_files,
)
from vncmd.media.lyrics import (
    process as process_lyrics,
)
from vncmd.media.lyrics import (
    process_credits,
)
from vncmd.media.metadata import embed as embed_metadata
from vncmd.net.api import (
    EXPECTED_LEVEL,
    LEVEL_LABEL,
    get_audio_source,
    get_lyrics_url,
    get_song_details,
)
from vncmd.net.download import fetch_audio, fetch_cover, fetch_lyrics
from vncmd.session import _setup_session, _summarize

_move_lock = Lock()

# 标签嵌入的重试次数，重试一次写入比重新下载便宜
_EMBED_ATTEMPTS = 3

# Ctrl+C 后让 worker 停止取新曲目，已经在下的这首跑完为止
_cancelled = Event()


def _move_unique(temp_path: str, base: str, ext: str, directory: str) -> str:
    """把临时文件移到最终文件名

    查名与落盘必须原子，避免并发线程选中同一路径
    """
    with _move_lock:
        target = resolve_path(base, ext, directory)
        shutil.move(temp_path, target)
    return target


def _embed_with_retry(fn, *args) -> str:
    """嵌入元数据，失败后重试，返回最后一次错误或空串"""
    last = ""
    for attempt in range(1, _EMBED_ATTEMPTS + 1):
        try:
            fn(*args)
            return ""
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            if attempt < _EMBED_ATTEMPTS:
                time.sleep(0.3 * attempt)
    return last


_downgrade_notified = False


def _notify_downgrade(want_level: str, got_level: str) -> None:
    """请求音质与实际拿到的不同时提示

    未登录与权限不足分开提示，判据为本地是否有 Cookie
    """
    global _downgrade_notified
    if not want_level or not got_level or got_level == want_level:
        return
    if _downgrade_notified:
        return
    _downgrade_notified = True
    want_label = LEVEL_LABEL.get(want_level, want_level)
    got_label = LEVEL_LABEL.get(got_level, got_level)
    if get_cookie():
        warning(f"当前 Cookie 权限不支持{want_label}，本次已按{got_label}下载")
    else:
        warning(f"未登录，本次只能按最高可用的{got_label}下载")


def _discard_temp(paths: list[str]) -> None:
    """删除残留临时文件，避免占位与同名冲突"""
    for p in paths:
        if not p:
            continue
        with suppress(OSError):
            Path(p).unlink()


def _progress_desc(text: str) -> str:
    """按显示宽度裁剪进度条描述并转义 markup

    宽度用 cell_len 计算，避免中日文与 emoji 让起始列漂移
    """
    limit = max(console.width - 60, 30)
    desc = Text(text, no_wrap=True, overflow="ellipsis")
    desc.truncate(limit)
    # 末格遇双格字符会空出来，补齐后各行起始列才一致
    return escape(desc.plain + " " * max(0, limit - cell_len(desc.plain)))


def _process_cover(cover_data, cover_url):
    """把封面分成嵌入用与保存用两份，失败时返回三个 None"""
    if not cover_data:
        return None, None, None
    try:
        embed_data, embed_mime = process_cover_image(
            cover_data, cover_url, get_embed_cover_compress()
        )
        save_data, _ = process_cover_image(
            cover_data, cover_url, get_save_cover_compress()
        )
    except Exception as e:
        warning(f"封面处理失败，本次不嵌入封面：{e}")
        return None, None, None
    return embed_data, embed_mime, save_data


def _download_and_verify(
    path: str,
    song_url: str,
    label: str,
    song_size: int,
    song_md5: str,
    progress=None,
    task_id=None,
    use_curl: bool | None = None,
    run_check: bool | None = None,
) -> str | None:
    """下载到 path 并逐道校验，返回失败原因或 None

    每道失败先删半截文件，md5 与 size 在解码前检查
    """
    err = fetch_audio(
        song_url,
        path,
        label,
        progress=progress,
        task_id=task_id,
        total=song_size,
        use_curl=use_curl,
    )
    if err:
        _discard_temp([path])
        return f"下载失败：{err}"

    if Path(path).stat().st_size == 0:
        _discard_temp([path])
        return "下载文件为空"

    ok, msg = check_md5(path, song_md5, song_size)
    if not ok:
        _discard_temp([path])
        return f"完整性校验失败：{msg}"

    if run_check is None:
        run_check = get_check_enabled()
    if run_check and any_check_tool():
        ok, msg = check_audio(path)
        if not ok:
            _discard_temp([path])
            return f"完整性校验失败：{msg}"
    return None


def download_song(
    song_url: str,
    song_title: str,
    song_artist: str,
    song_album: str,
    song_id: int,
    cover_url: str,
    lyrics_api_url: str,
    publish_time: str,
    source: str = "netease",
    download_dir: str | None = None,
    progress=None,
    task_id=None,
    track_no: int | None = None,
    cd_no: int | None = None,
    song_size: int = 0,
    song_md5: str = "",
    run_check: bool | None = None,
    use_curl: bool | None = None,
    song_level: str = "",
    want_br: int = 0,
) -> tuple[bool, str, str | None]:
    """下载一首歌，写入音频、歌词与封面

    返回成功标记、消息与音频路径
    """
    if download_dir is None:
        download_dir = get_download_dir()
    Path(download_dir).mkdir(parents=True, exist_ok=True)

    temp_dir = Path(download_dir) / "_temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    content = get_download_content()
    want_song = "a" in content
    if want_song:
        _notify_downgrade(EXPECTED_LEVEL.get(want_br, ""), song_level)
    want_lyrics = "l" in content
    want_cover = "c" in content

    filename_base, full_name = build_filename(song_title, song_artist)

    # 取歌词
    lyric_text, tlyric_text = "", ""
    if (want_lyrics or want_song) and lyrics_api_url and source:
        lyric_text, tlyric_text = fetch_lyrics(lyrics_api_url, source)

    # 解析制作信息并按需裁剪
    auto_trim = get_auto_trim()
    scan_lines = get_credit_scan_lines()
    # 不写音频时不抽制作信息，避免裁掉后无人接收
    collect = get_parse_credits() and want_song
    credits: dict[str, str] = {}

    if collect or auto_trim:
        credits, lyric_text = process_credits(
            lyric_text, scan_lines, collect, auto_trim
        )
        # 翻译歌词没有制作信息，只裁不抽
        if auto_trim:
            _, tlyric_text = process_credits(tlyric_text, scan_lines, False, True)

    # 裁完无内容就不写 lrc，按 strip 后的内容判断，避免丢掉无时间戳歌词
    if not lyric_text.strip():
        lyric_text = ""
        tlyric_text = ""

    # 取封面
    cover_data = None
    if want_cover or want_song:
        cover_data = fetch_cover(cover_url)

    embed_cover_data, embed_cover_mime, save_cover_data = _process_cover(
        cover_data, cover_url
    )

    music_type, temp_music_path = None, None
    temp_lyric_paths = []
    temp_cover_path = None

    # 下载音频到临时目录
    if want_song:
        music_type = get_type_from_url(song_url)
        temp_music_path = str(temp_dir / f"{song_id}.{music_type}")
        verify_err = _download_and_verify(
            temp_music_path,
            song_url=song_url,
            label=f"{song_title} - {song_artist}",
            progress=progress,
            task_id=task_id,
            song_size=song_size,
            use_curl=use_curl,
            song_md5=song_md5,
            run_check=run_check,
        )
        if verify_err is not None:
            return False, verify_err, None

        # 处理嵌入用歌词
        embed_mode = get_embed_lyrics_mode()
        if embed_mode == "drop" or not tlyric_text:
            embed_lyric = lyric_text
        else:
            embed_result = process_lyrics(lyric_text, tlyric_text, embed_mode, song_id)
            embed_lyric = "\n".join(embed_result.values())

        embed_err = _embed_with_retry(
            embed_metadata,
            temp_music_path,
            music_type,
            embed_cover_data,
            embed_cover_mime,
            embed_lyric,
            song_title,
            song_artist,
            song_album,
            publish_time,
            track_no,
            cd_no,
            credits or None,
        )
        if embed_err:
            # 音频已通过校验，标签失败不判整首失败，但要提示
            warning(
                f"「{song_title} - {song_artist}」元数据嵌入失败"
                f"（已重试 {_EMBED_ATTEMPTS} 次），本次不带标签：{embed_err}"
            )

    # 保存歌词，lyric_text 为空时已在上方挡住
    if want_lyrics and lyric_text:
        save_mode = get_save_lyrics_mode()
        base_path = str(temp_dir / str(song_id))
        result = process_lyrics(lyric_text, tlyric_text, save_mode, song_id)
        temp_lyric_paths = output_lyrics_files(result, base_path)

    # 保存封面
    if want_cover and save_cover_data:
        if get_save_cover_compress():
            cover_ext_val = "jpg"
        else:
            fmt = detect_format(save_cover_data)
            cover_ext_val = fmt[0] if fmt else cover_ext(cover_url)
        temp_cover_path = str(temp_dir / f"{song_id}.{cover_ext_val}")
        with open(temp_cover_path, "wb") as f:
            f.write(save_cover_data)

    # 从临时目录移到最终目录
    music_path = None
    lyric_paths = []
    cover_path = None
    if temp_music_path:
        music_path = _move_unique(
            temp_music_path, filename_base, music_type, download_dir
        )
    for tp in temp_lyric_paths:
        suffix = Path(tp).suffix
        lp = _move_unique(tp, filename_base, suffix.lstrip("."), download_dir)
        lyric_paths.append(lp)
    if temp_cover_path:
        ext = Path(temp_cover_path).suffix.lstrip(".")
        cover_path = _move_unique(temp_cover_path, filename_base, ext, download_dir)

    note_path = None
    if full_name:
        note_tmp = temp_dir / f"{song_id}.name"
        note_tmp.write_text(full_name, encoding="utf-8")
        note_path = _move_unique(str(note_tmp), filename_base, "txt", download_dir)

    # 组装结果，目录由调用方打印，这里只报文件名
    parts = []
    # 标签用中文，MP3 与 FLAC 的宽度一致
    if music_path:
        parts.append(("音频" if music_type else "", Path(music_path).name))
    for p in lyric_paths:
        parts.append(("歌词", Path(p).name))
    if cover_path:
        parts.append(("封面", Path(cover_path).name))
    if note_path:
        parts.append(("完整名字", Path(note_path).name))

    if not parts:
        return False, "未下载任何内容，请检查 download_content 配置", None

    # 按显示宽度补齐箭头，类型为空的行不留标签
    width = max(cell_len(label) for label, _ in parts)
    lines = [
        f'{label}{" " * (width - cell_len(label))} → "{name}"' if label else f'"{name}"'
        for label, name in parts
    ]
    return True, "\n".join(lines), music_path


# 取下载链接的重试次数。服务端偶发返回空 url，重试一次多半就好
_LINK_ATTEMPTS = 3


def _fetch_source_with_retry(sid: int, quality: int, on_retry=None):
    """取下载链接，三次失败返回 None

    on_retry 只在还有下一次尝试时调用；取不到链接按单首失败处理
    """
    for attempt in range(1, _LINK_ATTEMPTS + 1):
        source = get_audio_source(sid, quality=quality)
        if source:
            return source
        if attempt < _LINK_ATTEMPTS and on_retry:
            on_retry(attempt)
    return None


@dataclass
class _Workers:
    """一批下载的并发环境，收拢进度条、槽位与队列"""

    progress: Progress
    slots: list[int]
    queue: Queue
    count: int

    def show(self, task_id: int) -> None:
        """占上槽位并显示任务"""
        self.progress.tasks[task_id].visible = True

    def describe(self, task_id: int, text: str) -> None:
        self.progress.update(task_id, description=_progress_desc(text))

    def restart(self, task_id: int) -> None:
        """同一首重来时清掉总长，保留槽位显示"""
        self.progress.reset(task_id, total=None)

    def release(self, task_id: int) -> None:
        """这一首结束，释放槽位给下一首"""
        self.progress.update(task_id, description="")
        self.progress.reset(task_id, total=None)
        self.progress.tasks[task_id].visible = False


def _prepare_workers(tracks: list[dict], concurrency: int) -> _Workers:
    """建进度条、按并发数开槽位、把曲目装进队列

    槽位数与 worker 数一致，避免索引越界
    """
    progress = Progress(
        TextColumn("  [progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=err_console,
    )
    count = min(concurrency, len(tracks))
    slots = []
    for _ in range(count):
        tid = progress.add_task("", total=None, visible=False)
        slots.append(tid)

    queue = Queue()
    for track in tracks:
        queue.put(track)

    return _Workers(progress=progress, slots=slots, queue=queue, count=count)


def download_song_batch(
    tracks: list[dict],
    quality: int,
    output_dir: str,
    dl_type: str | None = None,
    dl_id: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    run_check: bool | None = None,
    use_curl: bool | None = None,
) -> tuple[int, int, str]:
    """批量下载，显示进度并汇总结果

    dl_type 与 dl_id 同时给出时启用断点；limit 与 offset 只截断本次下载
    """
    # 校验工具缺失只在任务开始时提示一次
    if (get_check_enabled() if run_check is None else run_check) and not all(
        check_tools().values()
    ):
        note = describe_missing_check_tools()
        if note:
            warning(note)

    session_dir, tracks, offset = _setup_session(
        tracks, output_dir, dl_type, dl_id, limit, offset
    )

    info(f'下载到 "{abbrev_home(session_dir)}"')

    want_song = "a" in get_download_content()
    total = len(tracks)
    _cancelled.clear()
    success_count = 0
    fail_count = 0
    fail_ids = []
    concurrency = get_concurrency()

    if total == 0:
        success(f"所有曲目已下载完毕，位于 {session_dir}")
        return success_count, fail_count, session_dir

    workers = _prepare_workers(tracks, concurrency)
    # 成功数、失败数与失败 id 为多个 worker 共享，写入必须串行
    counter_lock = Lock()

    def _download_one(slot_id):
        nonlocal success_count, fail_count, fail_ids
        while True:
            if _cancelled.is_set():
                return
            try:
                track = workers.queue.get_nowait()
            except Empty:
                return

            sid = track["id"]
            task_id = workers.slots[slot_id]
            title = track.get("title", "?")
            artist = track.get("artist", "")
            workers.show(task_id)

            try:
                if not artist:
                    workers.describe(task_id, f"解析中…（ID: {sid}）")
                    try:
                        track = get_song_details(sid)
                        title = track["title"]
                        artist = track["artist"]
                    except Exception as e:
                        workers.release(task_id)
                        warning(f"跳过 {title}（ID: {sid}）— 获取详情失败：{e}")
                        with counter_lock:
                            fail_count += 1
                            fail_ids.append(sid)
                        continue

                workers.describe(task_id, f"{title} - {artist}")

                if not want_song:
                    lyrics_api = get_lyrics_url(sid)
                    ok, msg, _ = download_song(
                        song_url="",
                        song_title=title,
                        song_artist=artist,
                        song_album=track.get("album", ""),
                        song_id=sid,
                        cover_url=track.get("cover", ""),
                        lyrics_api_url=lyrics_api,
                        publish_time=track.get("publish_time", ""),
                        download_dir=session_dir,
                        track_no=track.get("track_no"),
                        cd_no=track.get("cd_no"),
                    )
                else:
                    source = _fetch_source_with_retry(
                        sid,
                        quality,
                        # 默认参数绑定循环变量，避免闭包捕获
                        lambda n, t=task_id, ti=title, ar=artist: workers.describe(
                            t, f"{ti} - {ar}（获取链接重试 {n}/{_LINK_ATTEMPTS}）"
                        ),
                    )
                    if not source:
                        workers.release(task_id)
                        warning(f"跳过 {title} - {artist} — 无法获取下载链接")
                        info(f"  请尝试 vncmd song {sid} 手动下载")
                        with counter_lock:
                            fail_count += 1
                            fail_ids.append(sid)
                        continue

                    lyrics_api = get_lyrics_url(sid)
                    for attempt in range(1, 4):
                        # URL 签名 20 分钟过期，每次重试都重取
                        fresh = get_audio_source(sid, quality=quality)
                        if fresh:
                            source = fresh
                        ok, msg, _ = download_song(
                            song_url=source.url,
                            song_title=title,
                            song_artist=artist,
                            song_album=track.get("album", ""),
                            song_id=sid,
                            cover_url=track.get("cover", ""),
                            lyrics_api_url=lyrics_api,
                            publish_time=track.get("publish_time", ""),
                            download_dir=session_dir,
                            progress=workers.progress,
                            task_id=task_id,
                            track_no=track.get("track_no"),
                            cd_no=track.get("cd_no"),
                            song_size=source.size,
                            song_md5=source.md5,
                            run_check=run_check,
                            use_curl=use_curl,
                            song_level=source.level,
                            want_br=quality,
                        )
                        if ok:
                            break
                        workers.restart(task_id)
                        if attempt < 3:
                            workers.describe(
                                task_id, f"{title} - {artist}（重试 {attempt}/3）"
                            )

                workers.release(task_id)
                if ok:
                    with counter_lock:
                        success(f"{title} - {artist}")
                        success_count += 1
                        _mark_done(dl_type, dl_id, sid)
                else:
                    with counter_lock:
                        error(f"「{title} - {artist}」{msg}")
                        fail_count += 1
                        fail_ids.append(sid)

                time.sleep(0.3)
            except Exception as e:
                # 未预期异常不能让 worker 退出，否则队列剩余曲目无人处理
                workers.release(task_id)
                with counter_lock:
                    error(f"「{title} - {artist}」{type(e).__name__}: {e}")
                    fail_count += 1
                    fail_ids.append(sid)

    executor = ThreadPoolExecutor(max_workers=workers.count)
    interrupted = False
    with workers.progress:
        try:
            futures = [executor.submit(_download_one, i) for i in range(workers.count)]
            # Future 异常必须读取，否则线程池会吞掉
            for future in as_completed(futures):
                exc = future.exception()
                if exc is not None:
                    error(f"下载线程异常退出：{exc}")
        except KeyboardInterrupt:
            interrupted = True
            _cancelled.set()
            executor.shutdown(wait=False, cancel_futures=True)
        finally:
            if not interrupted:
                executor.shutdown(wait=True)

    if interrupted:
        left = total - success_count - fail_count
        info(f"已中断，完成 {success_count + fail_count} 首，剩余 {left} 首未下载")
        info("再次下载会从断点继续")
        # 解释器退出会 join worker，正在下载的歌可能拖几十秒，直接结束进程
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(130)

    _summarize(success_count, fail_count, fail_ids)
    return success_count, fail_count, session_dir


def _mark_done(dl_type: str | None, dl_id: str | None, song_id: int) -> None:
    if dl_type is not None and dl_id is not None:
        mark_downloaded(dl_type, dl_id, song_id)
