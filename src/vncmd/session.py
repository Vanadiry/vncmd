"""会话目录与断点"""

import shutil
from datetime import datetime
from pathlib import Path

from vncmd.checkpoint import (
    create_checkpoint,
    load_checkpoint,
    sync_checkpoint_tracks,
)
from vncmd.core.output import err_console, info, warning


def make_session_dir(base_dir):
    """建带时间戳的会话目录"""
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = Path(base_dir) / ts
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _is_within(path: str, parent: str) -> bool:
    """判断 path 是否为 parent 或子目录"""
    try:
        resolved = Path(path).expanduser().resolve()
        root = Path(parent).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    return resolved == root or root in resolved.parents


def _select_batch(
    tracks: list[dict], offset: int, limit: int | None
) -> tuple[list[dict], int]:
    """按 offset 与 limit 挑出本次要下的曲目"""
    if not (offset or limit):
        return tracks, 0
    end = offset + limit if limit else None
    return tracks[offset:end], offset


def _setup_session(
    tracks: list[dict],
    output_dir: str,
    dl_type: str | None,
    dl_id: str | None,
    limit: int | None,
    offset: int,
) -> tuple[str, list[dict], int]:
    """定本次下载目录、待下曲目与切片起点"""
    if dl_type is not None and dl_id is not None:
        cp = load_checkpoint(dl_type, dl_id)
        resume_dir = cp.get("download_dir") if cp else None
        if not resume_dir:
            info("开始全新下载")
            session_dir = make_session_dir(output_dir)
            is_resuming = False
        elif not Path(resume_dir).is_dir():
            info("发现未完成的下载，原目录已丢失，重新开始")
            session_dir = make_session_dir(output_dir)
            is_resuming = False
        elif not _is_within(resume_dir, output_dir):
            # 断点目录与本次输出目录不同时重新开始，避免落到未指定位置
            warning(
                f"未完成的下载在 {resume_dir}，"
                f"本次输出目录为 {output_dir}，重新开始下载"
            )
            session_dir = make_session_dir(output_dir)
            is_resuming = False
        else:
            session_dir = resume_dir
            is_resuming = True
    else:
        session_dir = make_session_dir(output_dir)
        is_resuming = False

    # 续传前清掉上一轮半截文件
    if is_resuming:
        temp = Path(session_dir) / "_temp"
        if temp.exists():
            shutil.rmtree(temp)
            temp.mkdir()

    selected, offset = _select_batch(tracks, offset, limit)
    if len(selected) < len(tracks):
        # limit 大于曲目数时不必提示剩余 0 首
        info(
            f"只下载第 {offset + 1} 至 {offset + len(selected)} 首，"
            f"剩余 {len(tracks) - len(selected)} 首留到下次"
        )
    if dl_type is not None and dl_id is not None:
        track_map = {str(t["id"]): t.get("title", "?") for t in tracks}
        if is_resuming:
            pending_ids, has_changes = sync_checkpoint_tracks(dl_type, dl_id, track_map)
            if has_changes:
                info("发现未完成的下载，曲目列表已变更，按更新后的列表继续")
            else:
                info("发现未完成的下载，从中断处继续")
            err_console.print()
            pending_set = set(pending_ids)
            selected = [t for t in selected if str(t["id"]) in pending_set]
        else:
            create_checkpoint(
                dl_type, dl_id, session_dir, [int(tid) for tid in track_map]
            )
    return session_dir, selected, offset


def _summarize(success_count: int, fail_count: int, fail_ids: list) -> None:
    """收尾打印成功与失败计数"""
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
        err_console.print(f"失败 ID：{'，'.join(str(i) for i in fail_ids)}")
