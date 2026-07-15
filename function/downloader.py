import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from queue import Queue
from threading import Lock

from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
)

from function.api import get_song_details, get_song_url, get_lyrics_url
from function.config import (
    get_download_dir,
    get_download_content,
    get_embed_lyrics_mode,
    get_save_lyrics_mode,
    get_embed_cover_quality,
    get_save_cover_quality,
    get_concurrency,
)
from function.audio import (
    get_type_from_url,
    cover_ext,
    build_filename,
    resolve_path,
)
from function.download import fetch_audio, fetch_cover, fetch_lyrics
from function.image import process_cover as process_cover_image
from function.lyrics import (
    process as process_lyrics,
    output_files as output_lyrics_files,
)
from function.metadata import embed as embed_metadata
from function.output import (
    info,
    warning,
    success,
    error,
    console,
)
from function.checkpoint import (
    load_checkpoint,
    create_checkpoint,
    mark_downloaded,
    sync_checkpoint_tracks,
)


def make_session_dir(base_dir):
    """Create a timestamped subdirectory and return its path."""
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = Path(base_dir) / ts
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


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
) -> tuple[bool, str, str | None]:
    """
    Download a song with metadata, lyrics, and cover.

    Respects config: filename_format, download_content, lyrics_mode, cover_quality.
    Returns (success: bool, message: str, file_path: str | None)
    """
    if download_dir is None:
        download_dir = get_download_dir()
    Path(download_dir).mkdir(parents=True, exist_ok=True)

    content = get_download_content()
    want_song = "0" in content
    want_lyrics = "1" in content
    want_cover = "2" in content

    filename_base = build_filename(song_title, song_artist)

    # --- Fetch lyrics ---
    lyric_text, tlyric_text = "", ""
    if want_lyrics or want_song:
        if lyrics_api_url and source:
            lyric_text, tlyric_text = fetch_lyrics(lyrics_api_url, source)

    # --- Fetch and process cover ---
    cover_data = None
    if want_cover or want_song:
        cover_data = fetch_cover(cover_url)

    embed_cover_data, embed_cover_mime = None, None
    save_cover_data = None
    if cover_data:
        embed_cover_data, embed_cover_mime = process_cover_image(
            cover_data, cover_url, get_embed_cover_quality()
        )
        save_cover_data, _ = process_cover_image(
            cover_data, cover_url, get_save_cover_quality()
        )

    music_path, music_type = None, None
    lyric_paths = []
    cover_path = None

    # --- Download audio ---
    if want_song:
        music_type = get_type_from_url(song_url)
        music_path = resolve_path(filename_base, music_type, download_dir)
        label = f"{song_title} - {song_artist}"
        err = fetch_audio(
            song_url, music_path, label, progress=progress, task_id=task_id
        )
        if err:
            return False, f"下载失败：{err}", None
        if Path(music_path).stat().st_size == 0:
            Path(music_path).unlink()
            return False, "下载文件为空，需要 VIP 或添加 Cookie", None
        # Process lyrics for embedding
        embed_mode = get_embed_lyrics_mode()
        if embed_mode == "2" or not tlyric_text:
            embed_lyric = lyric_text
        else:
            embed_result = process_lyrics(lyric_text, tlyric_text, embed_mode, song_id)
            embed_lyric = "\n".join(embed_result.values())

        embed_metadata(
            music_path,
            music_type,
            embed_cover_data,
            embed_cover_mime,
            embed_lyric,
            song_id,
            song_title,
            song_artist,
            song_album,
            publish_time,
        )

    # --- Save lyrics ---
    if want_lyrics and lyric_text:
        save_mode = get_save_lyrics_mode()
        base_path = str(Path(download_dir) / filename_base)
        result = process_lyrics(lyric_text, tlyric_text, save_mode, song_id)
        lyric_paths = output_lyrics_files(result, base_path)

    # --- Save cover ---
    if want_cover and save_cover_data:
        ext = "jpg" if get_save_cover_quality() == "1" else cover_ext(cover_url)
        cover_path = resolve_path(filename_base, ext, download_dir)
        with open(cover_path, "wb") as f:
            f.write(save_cover_data)

    # --- Result ---
    parts = []
    if music_path:
        parts.append(f"{music_type.upper() if music_type else ''} → {music_path}")
    for p in lyric_paths:
        parts.append(f"LRC → {p}")
    if cover_path:
        parts.append(f"封面 → {cover_path}")

    if not parts:
        return False, "未下载任何内容，请检查 download_content 配置", None
    return True, "\n".join(parts), music_path


def download_song_batch(
    tracks: list[dict],
    quality: int,
    output_dir: str,
    dry_run: bool = False,
    dl_type: str | None = None,
    dl_id: str | None = None,
) -> tuple[int, int, str]:
    """Download a batch of songs with progress display and summary.

    Each track dict must have at least 'id'.  If 'artist' is missing,
    ``get_song_details()`` is called to resolve full metadata from the API.

    When ``dl_type`` and ``dl_id`` are provided, resume/checkpoint is enabled:
    progress is persisted to ``cache/download/<type>_<id>.json`` and
    already-downloaded tracks are skipped on re-run.

    When ``dry_run=True``, only checks URL availability without downloading.
    Returns ``(success_count, fail_count, session_dir)``.
    """
    # --- Resolve session directory (checkpoint or new) ---
    if dl_type is not None and dl_id is not None:
        cp = load_checkpoint(dl_type, dl_id)
        if cp and cp.get("download_dir") and Path(cp["download_dir"]).is_dir():
            session_dir = cp["download_dir"]
            is_resuming = True
        elif cp:
            info("发现未完成的下载，但原目录已丢失，将重新开始下载。")
            session_dir = make_session_dir(output_dir)
            is_resuming = False
        else:
            info("开始全新下载。")
            session_dir = make_session_dir(output_dir)
            is_resuming = False
    else:
        session_dir = make_session_dir(output_dir)
        is_resuming = False

    # --- Sync checkpoint tracks & filter to pending ---
    if dl_type is not None and dl_id is not None:
        track_map = {str(t["id"]): t.get("title", "?") for t in tracks}
        if dry_run:
            # Read-only: check pending from checkpoint without modifying it
            if is_resuming:
                cp = load_checkpoint(dl_type, dl_id)
                done_set = (
                    {tid for tid, v in cp["tracks"].items() if v} if cp else set()
                )
                pending_set = set(track_map.keys()) - done_set
                tracks = [t for t in tracks if str(t["id"]) in pending_set]
        elif is_resuming:
            pending_ids, has_changes = sync_checkpoint_tracks(dl_type, dl_id, track_map)
            if has_changes:
                info("发现未完成的下载，但曲目列表已变更，将以更新后的列表继续。")
            else:
                info("发现未完成的下载，将从中断处继续。")
            console.print()
            pending_set = set(pending_ids)
            tracks = [t for t in tracks if str(t["id"]) in pending_set]
        else:
            create_checkpoint(
                dl_type, dl_id, session_dir, [int(tid) for tid in track_map]
            )

    want_song = "0" in get_download_content()
    total = len(tracks)
    success_count = 0
    fail_count = 0
    fail_ids = []
    concurrency = get_concurrency()

    if dry_run or total == 0:
        for i, track in enumerate(tracks, 1):
            sid = track["id"]
            if "artist" not in track:
                try:
                    track = get_song_details(sid)
                except Exception as e:
                    warning(
                        f"[{i}/{total}] 跳过 {track.get('title', '?')}"
                        f"（ID: {sid}）— 获取详情失败：{e}"
                    )
                    fail_count += 1
                    fail_ids.append(sid)
                    continue

            if dry_run:
                if not want_song:
                    console.print("  [dim]将下载（配置中音频已禁用）[/]")
                    success_count += 1
                else:
                    song_url = get_song_url(sid, quality=quality) or ""
                    if song_url:
                        success("URL 可用，将下载")
                        success_count += 1
                    else:
                        warning("URL 不可用（VIP 或地区限制），将跳过")
                        fail_count += 1
                        fail_ids.append(sid)
            elif total == 0:
                pass

        console.print()
        if dry_run:
            parts = []
            if success_count:
                parts.append(f"[green]{success_count} 将下载[/]")
            else:
                parts.append(f"[dim]0 将下载[/]")
            if fail_count:
                parts.append(f"[red]{fail_count} 将跳过[/]")
            else:
                parts.append(f"[dim]0 将跳过[/]")
            console.print(f"预览模式：{', '.join(parts)}")
        elif total == 0:
            success("所有曲目已下载完毕。")
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
    for _ in range(concurrency):
        tid = progress.add_task("", total=None)
        slots.append(tid)

    queue = Queue()
    for track in tracks:
        queue.put(track)

    def _download_one(slot_id):
        nonlocal success_count, fail_count, fail_ids
        while True:
            try:
                track = queue.get_nowait()
            except Exception:
                return

            sid = track["id"]
            task_id = slots[slot_id]
            title = track.get("title", "?")
            artist = track.get("artist", "")

            if not artist:
                progress.update(task_id, description=_desc(f"解析中…（ID: {sid}）"))
                try:
                    track = get_song_details(sid)
                    title = track["title"]
                    artist = track["artist"]
                except Exception as e:
                    progress.update(task_id, description="")
                    progress.reset(task_id, total=None)
                    warning(f"跳过「{title}」（ID: {sid}）— 获取详情失败：{e}")
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
                )
            else:
                song_url = get_song_url(sid, quality=quality) or ""
                if not song_url:
                    progress.update(task_id, description="")
                    progress.reset(task_id, total=None)
                    warning(f"跳过「{title} - {artist}」— 需要 VIP 或添加 Cookie")
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

            progress.update(task_id, description="")
            progress.reset(task_id, total=None)
            if ok:
                with counter_lock:
                    success(f"「{title} - {artist}」下载完成")
                    success_count += 1
                    _mark_done(dl_type, dl_id, sid)
            else:
                with counter_lock:
                    error(f"「{title} - {artist}」下载失败")
                    fail_count += 1
                    fail_ids.append(sid)

            time.sleep(0.3)

    with progress:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            for i in range(concurrency):
                executor.submit(_download_one, i)

    console.print()
    parts = []
    if success_count:
        parts.append(f"[green]{success_count} 成功[/]")
    else:
        parts.append(f"[dim]0 成功[/]")
    if fail_count:
        parts.append(f"[red]{fail_count} 失败[/]")
    else:
        parts.append(f"[dim]0 失败[/]")
    console.print(f"完成：{', '.join(parts)}")
    if fail_ids:
        console.print(f"失败 ID：{', '.join(str(i) for i in fail_ids)}")
    return success_count, fail_count, session_dir


def _mark_done(dl_type: str | None, dl_id: str | None, song_id: int) -> None:
    if dl_type is not None and dl_id is not None:
        mark_downloaded(dl_type, dl_id, song_id)
