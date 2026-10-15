import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Lock

from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
)

from function.api import get_lyrics_url, get_song_details, get_song_url
from function.audio import (
    build_filename,
    cover_ext,
    get_type_from_url,
    resolve_path,
)
from function.checker import check_audio, has_ffmpeg
from function.checkpoint import (
    create_checkpoint,
    load_checkpoint,
    mark_downloaded,
    sync_checkpoint_tracks,
)
from function.config import (
    get_auto_trim,
    get_concurrency,
    get_credit_prefixes,
    get_credit_scan_lines,
    get_download_content,
    get_download_dir,
    get_embed_cover_quality,
    get_embed_lyrics_mode,
    get_parse_credits,
    get_save_cover_quality,
    get_save_lyrics_mode,
)
from function.download import fetch_audio, fetch_cover, fetch_lyrics
from function.image import detect_format
from function.image import process_cover as process_cover_image
from function.lyrics import (
    extract_credits,
    is_pure_credits,
    trim_lyrics,
)
from function.lyrics import (
    output_files as output_lyrics_files,
)
from function.lyrics import (
    process as process_lyrics,
)
from function.metadata import embed as embed_metadata
from function.output import (
    console,
    error,
    info,
    success,
    warning,
)

_move_lock = Lock()


def _move_unique(temp_path: str, base: str, ext: str, directory: str) -> str:
    """把临时文件移到最终文件名

    查可用名与落盘必须原子，否则同名曲目的并发线程会挑中同一个路径，
    后落盘的那个直接把先落盘的覆盖掉
    """
    with _move_lock:
        target = resolve_path(base, ext, directory)
        shutil.move(temp_path, target)
    return target


def make_session_dir(base_dir):
    """Create a timestamped subdirectory and return its path."""
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = Path(base_dir) / ts
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _is_within(path: str, parent: str) -> bool:
    """判断 path 是否为 parent 本身或其子目录
    配置路径与 --output 写法可能不同，展开后才能判定为同一目录
    """
    try:
        resolved = Path(path).expanduser().resolve()
        root = Path(parent).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    return resolved == root or root in resolved.parents


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
) -> tuple[bool, str, str | None]:
    """
    Download a song with metadata, lyrics, and cover.

    Respects config: filename_format, download_content, lyrics_mode, cover_quality.
    Returns (success: bool, message: str, file_path: str | None)
    """
    if download_dir is None:
        download_dir = get_download_dir()
    Path(download_dir).mkdir(parents=True, exist_ok=True)

    temp_dir = Path(download_dir) / "_temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    content = get_download_content()
    want_song = "0" in content
    want_lyrics = "1" in content
    want_cover = "2" in content

    filename_base, full_name = build_filename(song_title, song_artist)

    # --- Fetch lyrics ---
    lyric_text, tlyric_text = "", ""
    if (want_lyrics or want_song) and lyrics_api_url and source:
        lyric_text, tlyric_text = fetch_lyrics(lyrics_api_url, source)

    # --- Parse credits / auto trim ---
    parse_credits = get_parse_credits()
    auto_trim = get_auto_trim()
    scan_lines = get_credit_scan_lines()
    prefixes = get_credit_prefixes()
    composer = None
    skip_lrc = False

    if parse_credits:
        composer, _ = extract_credits(lyric_text, scan_lines, [*prefixes, "作曲"])

    if parse_credits and auto_trim:
        lyric_text, _ = trim_lyrics(lyric_text, scan_lines, prefixes=["作曲"])
        if tlyric_text:
            tlyric_text, _ = trim_lyrics(tlyric_text, scan_lines, prefixes=["作曲"])
        skip_lrc = is_pure_credits(lyric_text, prefixes)
    elif auto_trim:
        lyric_text, is_empty = trim_lyrics(lyric_text, scan_lines, [])
        if tlyric_text:
            tlyric_text, _ = trim_lyrics(tlyric_text, scan_lines, [])
        if is_empty:
            lyric_text = ""
            tlyric_text = ""

    # --- Fetch and process cover ---
    cover_data = None
    if want_cover or want_song:
        cover_data = fetch_cover(cover_url)

    embed_cover_data, embed_cover_mime = None, None
    save_cover_data = None
    if cover_data:
        # 封面坏了不该连累音频，降级为不嵌封面
        try:
            embed_cover_data, embed_cover_mime = process_cover_image(
                cover_data, cover_url, get_embed_cover_quality()
            )
            save_cover_data, _ = process_cover_image(
                cover_data, cover_url, get_save_cover_quality()
            )
        except Exception as e:
            warning(f"封面处理失败，本次不嵌入封面：{e}")
            embed_cover_data = embed_cover_mime = save_cover_data = None

    music_type, temp_music_path = None, None
    temp_lyric_paths = []
    temp_cover_path = None

    # --- Download audio to temp ---
    if want_song:
        music_type = get_type_from_url(song_url)
        temp_music_path = str(temp_dir / f"{song_id}.{music_type}")
        label = f"{song_title} - {song_artist}"
        err = fetch_audio(
            song_url, temp_music_path, label, progress=progress, task_id=task_id
        )
        if err:
            return False, f"下载失败：{err}", None
        if Path(temp_music_path).stat().st_size == 0:
            Path(temp_music_path).unlink()
            return False, "下载文件为空", None

        if has_ffmpeg():
            ok, msg = check_audio(temp_music_path)
            if not ok:
                Path(temp_music_path).unlink()
                return False, f"完整性校验失败：{msg}", None

        # Process lyrics for embedding
        embed_mode = get_embed_lyrics_mode()
        if embed_mode == "2" or not tlyric_text:
            embed_lyric = lyric_text
        else:
            embed_result = process_lyrics(lyric_text, tlyric_text, embed_mode, song_id)
            embed_lyric = "\n".join(embed_result.values())

        embed_metadata(
            temp_music_path,
            music_type,
            embed_cover_data,
            embed_cover_mime,
            embed_lyric,
            song_id,
            song_title,
            song_artist,
            song_album,
            publish_time,
            track_no,
            cd_no,
            composer,
        )

    # --- Save lyrics to temp ---
    if want_lyrics and lyric_text and not skip_lrc:
        save_mode = get_save_lyrics_mode()
        base_path = str(temp_dir / str(song_id))
        result = process_lyrics(lyric_text, tlyric_text, save_mode, song_id)
        temp_lyric_paths = output_lyrics_files(result, base_path)

    # --- Save cover to temp ---
    if want_cover and save_cover_data:
        if get_save_cover_quality() == "1":
            cover_ext_val = "jpg"
        else:
            fmt = detect_format(save_cover_data)
            cover_ext_val = fmt[0] if fmt else cover_ext(cover_url)
        temp_cover_path = str(temp_dir / f"{song_id}.{cover_ext_val}")
        with open(temp_cover_path, "wb") as f:
            f.write(save_cover_data)

    # --- Move from temp to final ---
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

    # --- Result ---
    parts = []
    if music_path:
        parts.append(f'{music_type.upper() if music_type else ""} → "{music_path}"')
    for p in lyric_paths:
        parts.append(f'LRC → "{p}"')
    if cover_path:
        parts.append(f'封面 → "{cover_path}"')
    if note_path:
        parts.append(f'完整名字 → "{note_path}"')

    if not parts:
        return False, "未下载任何内容，请检查 download_content 配置", None
    return True, "\n".join(parts), music_path


def download_song_batch(
    tracks: list[dict],
    quality: int,
    output_dir: str,
    dl_type: str | None = None,
    dl_id: str | None = None,
    limit: int | None = None,
) -> tuple[int, int, str]:
    """Download a batch of songs with progress display and summary.

    Each track dict must have at least 'id'.  If 'artist' is missing,
    ``get_song_details()`` is called to resolve full metadata from the API.

    When ``dl_type`` and ``dl_id`` are provided, resume/checkpoint is enabled:
    progress is persisted to ``cache/download/<type>_<id>.json`` and
    already-downloaded tracks are skipped on re-run.

    ``limit`` 只截断本次下载的曲目，断点仍记录全部曲目，
    否则全量下过之后再限数量会把其余曲目判成已移除并删掉

    Returns ``(success_count, fail_count, session_dir)``.
    """
    # --- Resolve session directory (checkpoint or new) ---
    if dl_type is not None and dl_id is not None:
        cp = load_checkpoint(dl_type, dl_id)
        resume_dir = cp.get("download_dir") if cp else None
        if not resume_dir:
            info("开始全新下载。")
            session_dir = make_session_dir(output_dir)
            is_resuming = False
        elif not Path(resume_dir).is_dir():
            info("发现未完成的下载，但原目录已丢失，将重新开始下载。")
            session_dir = make_session_dir(output_dir)
            is_resuming = False
        elif not _is_within(resume_dir, output_dir):
            # 断点记录了上次运行的目录，output_dir 变了还沿用它会让文件落到
            # 用户没有指定的位置，且用户拿不到任何提示
            warning(
                f"未完成的下载在 {resume_dir}，"
                f"本次输出目录为 {output_dir}，将重新开始下载"
            )
            session_dir = make_session_dir(output_dir)
            is_resuming = False
        else:
            session_dir = resume_dir
            is_resuming = True
    else:
        session_dir = make_session_dir(output_dir)
        is_resuming = False

    # Clean temp dir when resuming
    if is_resuming:
        temp = Path(session_dir) / "_temp"
        if temp.exists():
            shutil.rmtree(temp)
            temp.mkdir()

    # --- Sync checkpoint tracks & filter to pending ---
    selected = tracks
    if limit and limit < len(tracks):
        # 断点记全量曲目，只截断本次要下的部分，
        # 否则全量下过之后再 -n 1 会把其余曲目判成已移除并删掉
        info(f"只下载前 {limit} 首，剩余 {len(tracks) - limit} 首下次继续")
        selected = tracks[:limit]
    if dl_type is not None and dl_id is not None:
        track_map = {str(t["id"]): t.get("title", "?") for t in tracks}
        if is_resuming:
            pending_ids, has_changes = sync_checkpoint_tracks(dl_type, dl_id, track_map)
            if has_changes:
                info("发现未完成的下载，但曲目列表已变更，将以更新后的列表继续。")
            else:
                info("发现未完成的下载，将从中断处继续。")
            console.print()
            pending_set = set(pending_ids)
            selected = [t for t in selected if str(t["id"]) in pending_set]
        else:
            create_checkpoint(
                dl_type, dl_id, session_dir, [int(tid) for tid in track_map]
            )
    tracks = selected

    want_song = "0" in get_download_content()
    total = len(tracks)
    success_count = 0
    fail_count = 0
    fail_ids = []
    concurrency = get_concurrency()

    if total == 0:
        success(f"所有曲目已下载完毕，位于 {session_dir}")
        return success_count, fail_count, session_dir

    def _desc(text):
        width = shutil.get_terminal_size().columns
        limit = max(width - 60, 30)
        if len(text) > limit:
            text = text[: limit - 1] + "…"
        return text.ljust(limit)

    # --- Concurrent download with worker slots ---
    counter_lock = Lock()
    progress = Progress(
        TextColumn("  [progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    )
    slots = []
    # 槽位数与提交的 worker 数必须一致，多提交的 worker 取到任务后
    # 索引越界，该曲目会随线程一起消失且不计入成功也不计入失败
    worker_count = min(concurrency, total)
    for _ in range(worker_count):
        tid = progress.add_task("", total=None, visible=False)
        slots.append(tid)

    queue = Queue()
    for track in tracks:
        queue.put(track)

    def _reset_slot(task_id):
        progress.update(task_id, description="")
        progress.reset(task_id, total=None)
        progress.tasks[task_id].visible = False

    def _download_one(slot_id):
        nonlocal success_count, fail_count, fail_ids
        while True:
            try:
                track = queue.get_nowait()
            except Empty:
                return

            sid = track["id"]
            task_id = slots[slot_id]
            title = track.get("title", "?")
            artist = track.get("artist", "")
            progress.tasks[task_id].visible = True

            try:
                if not artist:
                    progress.update(task_id, description=_desc(f"解析中…（ID: {sid}）"))
                    try:
                        track = get_song_details(sid)
                        title = track["title"]
                        artist = track["artist"]
                    except Exception as e:
                        _reset_slot(task_id)
                        warning(f"跳过 {title}（ID: {sid}）— 获取详情失败：{e}")
                        with counter_lock:
                            fail_count += 1
                            fail_ids.append(sid)
                        continue

                progress.update(task_id, description=_desc(f"⏳ {title} - {artist}"))

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
                    song_url = None
                    for attempt in range(1, 4):
                        song_url = get_song_url(sid, quality=quality)
                        if song_url:
                            break
                        if attempt < 3:
                            progress.update(
                                task_id,
                                description=_desc(
                                    f"⏳ {title} - {artist}（获取链接重试 {attempt}/3）"
                                ),
                            )
                    if not song_url:
                        _reset_slot(task_id)
                        warning(f"跳过 {title} - {artist} — 无法获取下载链接")
                        info(f"  请尝试 vncmd song {sid} 手动下载")
                        with counter_lock:
                            fail_count += 1
                            fail_ids.append(sid)
                        continue

                    lyrics_api = get_lyrics_url(sid)
                    for attempt in range(1, 4):
                        ok, msg, _ = download_song(
                            song_url=song_url,
                            song_title=title,
                            song_artist=artist,
                            song_album=track.get("album", ""),
                            song_id=sid,
                            cover_url=track.get("cover", ""),
                            lyrics_api_url=lyrics_api,
                            publish_time=track.get("publish_time", ""),
                            download_dir=session_dir,
                            progress=progress,
                            task_id=task_id,
                            track_no=track.get("track_no"),
                            cd_no=track.get("cd_no"),
                        )
                        if ok:
                            break
                        progress.reset(task_id, total=None)
                        if attempt < 3:
                            progress.update(
                                task_id,
                                description=_desc(
                                    f"⏳ {title} - {artist}（重试 {attempt}/3）"
                                ),
                            )

                _reset_slot(task_id)
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
                # 未预期的异常不能让 worker 死掉，它一死队列里剩下的曲目就没人接了
                _reset_slot(task_id)
                with counter_lock:
                    error(f"「{title} - {artist}」{type(e).__name__}: {e}")
                    fail_count += 1
                    fail_ids.append(sid)

    with progress, ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(_download_one, i) for i in range(worker_count)]
        # 不读 Future 的异常会被线程池吞掉，worker 死掉时队列里剩下的曲目就没人接了
        for future in as_completed(futures):
            exc = future.exception()
            if exc is not None:
                error(f"下载线程异常退出：{exc}")

    console.print()
    parts = []
    if success_count:
        parts.append(f"[green]{success_count} 成功[/]")
    else:
        parts.append("[dim]0 成功[/]")
    if fail_count:
        parts.append(f"[red]{fail_count} 失败[/]")
    else:
        parts.append("[dim]0 失败[/]")
    console.print(f"完成：{', '.join(parts)}")
    if fail_ids:
        console.print(f"失败 ID：{', '.join(str(i) for i in fail_ids)}")
    return success_count, fail_count, session_dir


def _mark_done(dl_type: str | None, dl_id: str | None, song_id: int) -> None:
    if dl_type is not None and dl_id is not None:
        mark_downloaded(dl_type, dl_id, song_id)
