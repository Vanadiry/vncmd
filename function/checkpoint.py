import json
import os

from function.config import get_cache_dir
from function.output import info

_CHECKPOINT_DIR = None


def _get_checkpoint_dir():
    global _CHECKPOINT_DIR
    if _CHECKPOINT_DIR is None:
        _CHECKPOINT_DIR = os.path.join(get_cache_dir(), "download")
    os.makedirs(_CHECKPOINT_DIR, exist_ok=True)
    return _CHECKPOINT_DIR


def get_checkpoint_path(dl_type, dl_id):
    return os.path.join(_get_checkpoint_dir(), f"{dl_type}_{dl_id}.json")


def load_checkpoint(dl_type, dl_id):
    path = get_checkpoint_path(dl_type, dl_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_checkpoint(dl_type, dl_id, data):
    path = get_checkpoint_path(dl_type, dl_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def create_checkpoint(dl_type, dl_id, download_dir, track_ids):
    data = {
        "type": dl_type,
        "id": dl_id,
        "download_dir": download_dir,
        "tracks": {str(tid): False for tid in track_ids},
    }
    save_checkpoint(dl_type, dl_id, data)
    return data


def mark_downloaded(dl_type, dl_id, song_id):
    cp = load_checkpoint(dl_type, dl_id)
    if cp is None:
        return
    cp["tracks"][str(song_id)] = True
    save_checkpoint(dl_type, dl_id, cp)


def sync_checkpoint_tracks(dl_type, dl_id, current_tracks):
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
            title = current_tracks.get(tid, current_tracks.get(int(tid), "?"))
            info(f"  New track in {dl_type}: {title} (ID {tid})")
        for tid in sorted(removed_ids):
            info(f"  Track removed from {dl_type}: ID {tid}")
        info(
            "  Tip: if this list changes often, consider using the tracker feature"
            " (vnemd tracker --help)"
        )

    for tid in removed_ids:
        del cp["tracks"][tid]
    save_checkpoint(dl_type, dl_id, cp)

    pending = [tid for tid, done in cp["tracks"].items() if not done]
    return pending, has_changes
