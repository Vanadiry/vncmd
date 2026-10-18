import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress
from datetime import datetime
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

from function.api import (
    EXPECTED_LEVEL,
    LEVEL_LABEL,
    get_audio_source,
    get_lyrics_url,
    get_song_details,
)
from function.audio import (
    build_filename,
    cover_ext,
    get_type_from_url,
    resolve_path,
)
from function.checker import (
    any_check_tool,
    check_audio,
    check_md5,
    check_tools,
    describe_missing_check_tools,
)
from function.checkpoint import (
    create_checkpoint,
    load_checkpoint,
    mark_downloaded,
    sync_checkpoint_tracks,
)
from function.config import (
    abbrev_home,
    get_auto_trim,
    get_check_enabled,
    get_concurrency,
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
    output_files as output_lyrics_files,
)
from function.lyrics import (
    process as process_lyrics,
)
from function.lyrics import (
    process_credits,
)
from function.metadata import embed as embed_metadata
from function.output import (
    console,
    err_console,
    error,
    info,
    success,
    warning,
)

_move_lock = Lock()

# 标签嵌入的重试次数，与批量下载的重试次数互相独立：
# 这里重试的是一次纯粹的标签写入，比重新下载一首便宜得多
_EMBED_ATTEMPTS = 3

# Ctrl+C 后让 worker 停止取新曲目，已经在下的这首跑完为止
_cancelled = Event()


def _move_unique(temp_path: str, base: str, ext: str, directory: str) -> str:
    """把临时文件移到最终文件名

    查可用名与落盘必须原子，否则同名曲目的并发线程会挑中同一个路径，
    后落盘的那个直接把先落盘的覆盖掉
    """
    with _move_lock:
        target = resolve_path(base, ext, directory)
        shutil.move(temp_path, target)
    return target


def _embed_with_retry(fn, *args) -> str:
    """嵌入元数据，失败后重试若干次，返回最后一次的错误说明或空串

    标签对音乐库很关键，值得再试几次：并发下的磁盘争用是偶发的，
    重试就能成；而文件本身损坏属于确定性失败，重试无果但
    代价只是几十毫秒。
    """
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
    """请求的音质与实际拿到的不一致时说一声

    服务端不会因为权限不足报错，只是悄悄降级，不提示的话用户
    只能等看到文件名后缀才发现。
    """
    global _downgrade_notified
    if not want_level or not got_level or got_level == want_level:
        return
    if _downgrade_notified:
        return
    _downgrade_notified = True
    want_label = LEVEL_LABEL.get(want_level, want_level)
    got_label = LEVEL_LABEL.get(got_level, got_level)
    warning(f"当前 Cookie 权限不支持{want_label}，本次已按{got_label}下载")


def _discard_temp(paths: list[str]) -> None:
    """丢弃残留的临时文件

    下载中断或内容校验不过时，半截文件或错误页会留在 _temp 里。
    这些文件既占地方又没用了，下一轮同名的歌还会撞上。
    """
    for p in paths:
        if not p:
            continue
        with suppress(OSError):
            Path(p).unlink()


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


def _progress_desc(text: str) -> str:
    """把进度条描述裁到固定显示宽度并转义 markup

    宽度按 cell_len 算而非 len，中日文与 emoji 都是多格字符，
    按字符数补齐会让进度条起始列随标题内容左右漂移。
    截断交给 Text.truncate，它按显示格切，不会切在半个宽字符中间。

    返回值直接交给 progress.update，那边按 markup 解析，
    歌名含 [Live] 这类标注时未转义会被当成样式标签，[/b] 这种不配对的直接抛异常。
    转义放在补齐之后，补齐量按转义前的显示宽度算，反斜杠不占渲染宽度。
    """
    limit = max(console.width - 60, 30)
    desc = Text(text, no_wrap=True, overflow="ellipsis")
    desc.truncate(limit)
    # 末格遇双格字符会空出来，补齐后各行起始列才一致
    return escape(desc.plain + " " * max(0, limit - cell_len(desc.plain)))


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
    if want_song:
        _notify_downgrade(EXPECTED_LEVEL.get(want_br, ""), song_level)
    want_lyrics = "1" in content
    want_cover = "2" in content

    filename_base, full_name = build_filename(song_title, song_artist)

    # --- Fetch lyrics ---
    lyric_text, tlyric_text = "", ""
    if (want_lyrics or want_song) and lyrics_api_url and source:
        lyric_text, tlyric_text = fetch_lyrics(lyrics_api_url, source)

    # --- Parse credits / auto trim ---
    auto_trim = get_auto_trim()
    scan_lines = get_credit_scan_lines()
    # 没音频可写的时候不抽 —— 抽出来的 credits 没人接收，而行又被裁掉等于白删
    collect = get_parse_credits() and want_song
    credits: dict[str, str] = {}

    if collect or auto_trim:
        credits, lyric_text = process_credits(
            lyric_text, scan_lines, collect, auto_trim
        )
        # 翻译歌词里没有 credit 行，只裁不抽，与 extract_credits 原来的行为一致
        if auto_trim:
            _, tlyric_text = process_credits(tlyric_text, scan_lines, False, True)

    # 裁完什么都不剩就不写 lrc 也不嵌空歌词。
    # 判的是「有没有内容」而不是「有没有带时间戳的行」——
    # parse() 要求时间戳是 [mm:ss.xx]，而上游给纯文本歌词、单数字分钟、
    # 没有小数的秒都是有的，那些判成「没内容」就是静默丢数据
    if not lyric_text.strip():
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
            song_url,
            temp_music_path,
            label,
            progress=progress,
            task_id=task_id,
            total=song_size,
            use_curl=use_curl,
        )
        if err:
            # 半截文件或错误页留着没用，还会占着 _temp 里的同名位置
            _discard_temp([temp_music_path])
            return False, f"下载失败：{err}", None
        if Path(temp_music_path).stat().st_size == 0:
            _discard_temp([temp_music_path])
            return False, "下载文件为空", None

        # 先用服务端声明的大小与 md5 过一道，纯读文件比全量解码快得多
        ok, msg = check_md5(temp_music_path, song_md5, song_size)
        if not ok:
            _discard_temp([temp_music_path])
            return False, f"完整性校验失败：{msg}", None

        if run_check is None:
            run_check = get_check_enabled()
        # 不再按 has_ffmpeg 整块门控 —— 装了 flac 没装 ffmpeg 的机器
        # 仍然能验 flac 文件，逐段跳过的判断挪进 check_audio 内部了
        if run_check and any_check_tool():
            ok, msg = check_audio(temp_music_path)
            if not ok:
                _discard_temp([temp_music_path])
                return False, f"完整性校验失败：{msg}", None

        # Process lyrics for embedding
        embed_mode = get_embed_lyrics_mode()
        if embed_mode == "2" or not tlyric_text:
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
            # 音频本身过了校验，标签嵌不上不该把整首判为下载失败，
            # 否则用户看到失败会重试，白白重下一遍。但重试过仍要出声告知，
            # 静默降级会让人以为标签已经嵌好
            warning(
                f"「{song_title} - {song_artist}」元数据嵌入失败"
                f"（已重试 {_EMBED_ATTEMPTS} 次），本次不带标签：{embed_err}"
            )

    # --- Save lyrics to temp ---
    # 裁空之后 lyric_text 是空串，这一项就挡住了，不必再单独判「是不是只有 credits」
    if want_lyrics and lyric_text:
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
    # 目录由调用方在开头统一打印一次，这里只报文件名，
    # 完整路径折行会把路径断在中间，复制不出来
    parts = []
    # 标签用中文而不是格式缩写，MP3 与 FLAC 就不再有宽窄差别，
    # 音频、歌词、封面同为四格，只有完整名字要补齐
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

    # 完整名字是四个汉字占八格，按显示宽度补齐箭头才能落在同一列。
    # 类型为空时整行没有标签，那种行不参与补齐也不留箭头
    width = max(cell_len(label) for label, _ in parts)
    lines = [
        f'{label}{" " * (width - cell_len(label))} → "{name}"' if label else f'"{name}"'
        for label, name in parts
    ]
    return True, "\n".join(lines), music_path


def _select_batch(
    tracks: list[dict], offset: int, limit: int | None
) -> tuple[list[dict], int]:
    """按 offset 与 limit 挑出本次要下的曲目

    单独抽出来是为了让测试能直接量到「切出来的」与「记进断点的」是两批：
    早先那段逻辑埋在 download_song_batch 中间，测它要驱动整个下载流程。
    """
    if not (offset or limit):
        return tracks, 0
    end = offset + limit if limit else None
    return tracks[offset:end], offset


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
    """Download a batch of songs with progress display and summary.

    Each track dict must at least have 'id'.  If 'artist' is missing,
    ``get_song_details()`` is called to resolve full metadata from the API.

    When ``dl_type`` and ``dl_id`` are provided, resume/checkpoint is enabled:
    progress is persisted to ``cache/download/<type>_<id>.json`` and
    already-downloaded tracks are skipped on re-run.

    ``limit`` 与 ``offset`` 只截断本次下载的曲目，断点仍记录全部曲目，
    否则全量下过之后再限数量会把其余曲目判成已移除并删掉。
    断点按专辑或歌单记、不按这一次的切片记，那是既有行为：
    要改成任务级另算一步

    Returns ``(success_count, fail_count, session_dir)``.
    """
    # 校验工具缺哪几样、因此少做哪几步，只在任务最开始说一次。
    # 放在这里而不是每首歌里，否则一个批次能刷出几百条一样的提示
    if (get_check_enabled() if run_check is None else run_check) and not all(
        check_tools().values()
    ):
        note = describe_missing_check_tools()
        if note:
            warning(note)

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
    selected, offset = _select_batch(tracks, offset, limit)
    if len(selected) < len(tracks):
        # limit 给得比曲目还多时切出来还是全量，不必报「剩余 0 首」
        info(
            f"只下载第 {offset + 1} 至 {offset + len(selected)} 首，"
            f"剩余 {len(tracks) - len(selected)} 首下次继续"
        )
    if dl_type is not None and dl_id is not None:
        track_map = {str(t["id"]): t.get("title", "?") for t in tracks}
        if is_resuming:
            pending_ids, has_changes = sync_checkpoint_tracks(dl_type, dl_id, track_map)
            if has_changes:
                info("发现未完成的下载，但曲目列表已变更，将以更新后的列表继续。")
            else:
                info("发现未完成的下载，将从中断处继续。")
            err_console.print()
            pending_set = set(pending_ids)
            selected = [t for t in selected if str(t["id"]) in pending_set]
        else:
            create_checkpoint(
                dl_type, dl_id, session_dir, [int(tid) for tid in track_map]
            )
    tracks = selected

    info(f'下载到 "{abbrev_home(session_dir)}"')

    want_song = "0" in get_download_content()
    total = len(tracks)
    _cancelled.clear()
    success_count = 0
    fail_count = 0
    fail_ids = []
    concurrency = get_concurrency()

    if total == 0:
        success(f"所有曲目已下载完毕，位于 {session_dir}")
        return success_count, fail_count, session_dir

    # --- Concurrent download with worker slots ---
    counter_lock = Lock()
    progress = Progress(
        TextColumn("  [progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=err_console,
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
        # rich 未提供切换任务可见性的接口，只能直接写属性。
        # 渲染侧只在取表格时读它，写入是单次属性赋值，最坏情况少渲染一帧
        progress.tasks[task_id].visible = False

    def _download_one(slot_id):
        nonlocal success_count, fail_count, fail_ids
        while True:
            if _cancelled.is_set():
                return
            try:
                track = queue.get_nowait()
            except Empty:
                return

            sid = track["id"]
            task_id = slots[slot_id]
            title = track.get("title", "?")
            artist = track.get("artist", "")
            # 见 _reset_slot 的注释，可见性只能直接写属性
            progress.tasks[task_id].visible = True

            try:
                if not artist:
                    progress.update(
                        task_id, description=_progress_desc(f"解析中…（ID: {sid}）")
                    )
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

                progress.update(
                    task_id, description=_progress_desc(f"{title} - {artist}")
                )

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
                    source = None
                    for attempt in range(1, 4):
                        source = get_audio_source(sid, quality=quality)
                        if source:
                            break
                        if attempt < 3:
                            progress.update(
                                task_id,
                                description=_progress_desc(
                                    f"{title} - {artist}（获取链接重试 {attempt}/3）"
                                ),
                            )
                    if not source:
                        _reset_slot(task_id)
                        warning(f"跳过 {title} - {artist} — 无法获取下载链接")
                        info(f"  请尝试 vncmd song {sid} 手动下载")
                        with counter_lock:
                            fail_count += 1
                            fail_ids.append(sid)
                        continue

                    lyrics_api = get_lyrics_url(sid)
                    for attempt in range(1, 4):
                        # URL 里带签名时间戳，expi 只有 20 分钟，
                        # 每次重试都重取，续传才不会拿着过期的链接去续
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
                            progress=progress,
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
                        progress.reset(task_id, total=None)
                        if attempt < 3:
                            progress.update(
                                task_id,
                                description=_progress_desc(
                                    f"{title} - {artist}（重试 {attempt}/3）"
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

    executor = ThreadPoolExecutor(max_workers=worker_count)
    interrupted = False
    with progress:
        try:
            futures = [executor.submit(_download_one, i) for i in range(worker_count)]
            # 不读 Future 的异常会被线程池吞掉，worker 死掉时队列里剩下的曲目就没人接了
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
        # 解释器退出时会 join 掉所有 worker，正在下的歌可能还要几十秒，
        # 这里直接结束进程，不再等待
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(130)

    err_console.print()
    parts = []
    if success_count:
        parts.append(f"[green]{success_count} 成功[/]")
    else:
        parts.append("[dim]0 成功[/]")
    if fail_count:
        parts.append(f"[red]{fail_count} 失败[/]")
    else:
        parts.append("[dim]0 失败[/]")
    err_console.print(f"完成：{'，'.join(parts)}")
    if fail_ids:
        err_console.print(f"失败 ID：{', '.join(str(i) for i in fail_ids)}")
    return success_count, fail_count, session_dir


def _mark_done(dl_type: str | None, dl_id: str | None, song_id: int) -> None:
    if dl_type is not None and dl_id is not None:
        mark_downloaded(dl_type, dl_id, song_id)
