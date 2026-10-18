from pathlib import Path

from vncmd.core.config import get_cache_dir
from vncmd.core.jsonstore import read_json_safe, write_json_atomic
from vncmd.core.output import info

_CHECKPOINT_DIR = None


def _get_checkpoint_dir():
    global _CHECKPOINT_DIR
    if _CHECKPOINT_DIR is None:
        _CHECKPOINT_DIR = Path(get_cache_dir()) / "download"
    _CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    return _CHECKPOINT_DIR


def get_checkpoint_path(dl_type: str, dl_id: str) -> Path:
    return _get_checkpoint_dir() / f"{dl_type}_{dl_id}.json"


def load_checkpoint(dl_type: str, dl_id: str) -> dict | None:
    path = get_checkpoint_path(dl_type, dl_id)
    if not path.exists():
        return None
    # 坏掉的断点会带着整个专辑永远下不完，读不出来时当作没有断点重新开始
    return read_json_safe(path, None, what="下载断点")


def save_checkpoint(dl_type: str, dl_id: str, data: dict) -> None:
    write_json_atomic(get_checkpoint_path(dl_type, dl_id), data)


def create_checkpoint(
    dl_type: str, dl_id: str, download_dir: str, track_ids: list[int]
) -> dict:
    data = {
        "type": dl_type,
        "id": dl_id,
        "download_dir": download_dir,
        "tracks": {str(tid): False for tid in track_ids},
    }
    save_checkpoint(dl_type, dl_id, data)
    return data


def mark_downloaded(dl_type: str, dl_id: str, song_id: int) -> None:
    cp = load_checkpoint(dl_type, dl_id)
    if cp is None:
        return
    cp["tracks"][str(song_id)] = True
    save_checkpoint(dl_type, dl_id, cp)


def sync_checkpoint_tracks(
    dl_type: str, dl_id: str, current_tracks: dict[str, str]
) -> tuple[list[str], bool]:
    """Sync checkpoint tracks with current API list.

    ``current_tracks`` is a dict of ``{id: title}``.
    Returns ``(pending_ids, has_changes)``.
    For album/playlist: notifies about added/removed tracks with titles.
    For tracker: silently updates.
    """
    cp = load_checkpoint(dl_type, dl_id)
    if cp is None:
        return list(current_tracks.keys()), False

    current_ids = {str(tid) for tid in current_tracks}
    cp_ids = set(cp["tracks"].keys())
    new_ids = current_ids - cp_ids
    removed_ids = cp_ids - current_ids

    # Update checkpoint: add new tracks, remove gone tracks
    for tid in new_ids:
        cp["tracks"][tid] = False
    has_changes = bool(new_ids or removed_ids)

    # Notify for album/playlist
    if dl_type in ("album", "playlist") and has_changes:
        for tid in sorted(new_ids):
            # current_tracks 的键恒为 str，int(tid) 那一路永远取不到值
            title = current_tracks.get(tid, "?")
            info(f"  {dl_type} 新增曲目：{title}（ID {tid}）")
        for tid in sorted(removed_ids):
            info(f"  {dl_type} 曲目已移除：ID {tid}")
        info("  提示：如果列表经常变动，建议使用 Tracker 功能（vncmd tracker --help）")

    for tid in removed_ids:
        del cp["tracks"][tid]
    save_checkpoint(dl_type, dl_id, cp)

    pending = [tid for tid, done in cp["tracks"].items() if not done]
    return pending, has_changes
