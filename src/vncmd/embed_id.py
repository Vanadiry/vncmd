"""tool embed-id 的曲目索引"""

import json
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path


def normalize(text) -> str:
    """标题与艺术家归一化，只做 NFKC、casefold 与空白合并"""
    if not isinstance(text, str):
        text = ""
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(text.split())


@dataclass
class SongIndex:
    """标题与艺术家到曲目 id 的索引"""

    by_title_artist: dict[tuple[str, str], set[int]] = field(default_factory=dict)
    by_title: dict[str, set[int]] = field(default_factory=dict)


@dataclass(frozen=True)
class MatchResult:
    """一次匹配的结果

    song_id 为 None 时，candidates 为空表示对不上，非空表示歧义
    by_title_only 标记命中来自标题兜底
    """

    song_id: int | None
    by_title_only: bool = False
    candidates: tuple[int, ...] = ()

    @property
    def ambiguous(self) -> bool:
        return self.song_id is None and bool(self.candidates)


@dataclass(frozen=True)
class FileAction:
    """一份文件在自动匹配下应采取的动作"""

    action: str
    song_id: int | None = None
    by_title_only: bool = False
    candidates: tuple[int, ...] = ()
    existing: tuple[str, ...] = ()


def decide_action(
    index: SongIndex,
    title,
    artist,
    existing: list[str] | tuple[str, ...],
) -> FileAction:
    """根据已有 track_id 与匹配结果决定写入、跳过或报冲突"""
    existing = tuple(existing)
    if len(existing) > 1:
        return FileAction("multiple", existing=existing)

    match = match_track(index, title, artist)
    if existing:
        if match.song_id is None:
            action = "ambiguous" if match.ambiguous else "not_found"
            return FileAction(
                action,
                by_title_only=match.by_title_only,
                candidates=match.candidates,
                existing=existing,
            )
        if existing[0] == str(match.song_id):
            return FileAction("latest", match.song_id, existing=existing)
        return FileAction(
            "conflict",
            match.song_id,
            by_title_only=match.by_title_only,
            existing=existing,
        )

    if match.song_id is not None:
        return FileAction(
            "write",
            match.song_id,
            by_title_only=match.by_title_only,
        )
    action = "ambiguous" if match.ambiguous else "not_found"
    return FileAction(
        action,
        by_title_only=match.by_title_only,
        candidates=match.candidates,
    )


def match_track(index: SongIndex, title, artist) -> MatchResult:
    """按标题加艺术家匹配，失败后再用标题兜底"""
    title_key = normalize(title)
    artist_key = normalize(artist)

    if artist_key:
        candidates = index.by_title_artist.get((title_key, artist_key), set())
        if len(candidates) == 1:
            return MatchResult(next(iter(candidates)))
        if len(candidates) > 1:
            return MatchResult(None, False, tuple(sorted(candidates)))

    candidates = index.by_title.get(title_key, set())
    if len(candidates) == 1:
        return MatchResult(next(iter(candidates)), True)
    if len(candidates) > 1:
        return MatchResult(None, True, tuple(sorted(candidates)))
    return MatchResult(None)


def build_index(records: list[dict]) -> SongIndex:
    """按标题与艺术家建立两层索引，同一 id 去重"""
    index = SongIndex()
    for record in records:
        if not isinstance(record, dict):
            continue
        try:
            song_id = int(record["id"])
        except (KeyError, TypeError, ValueError):
            continue

        title = normalize(record.get("title"))
        artist = normalize(record.get("artist"))
        if not title:
            continue
        index.by_title.setdefault(title, set()).add(song_id)
        if artist:
            index.by_title_artist.setdefault((title, artist), set()).add(song_id)
    return index


def load_songs_file(path: Path) -> list[dict]:
    """读取一份 songs.json，损坏或形状不对时抛出 ValueError"""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"无法解析 {path}：{e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("songs"), list):
        raise ValueError(f"{path} 缺少 songs 列表")
    return data["songs"]


def load_tracker_songs(root: Path) -> list[dict]:
    """读取所有 Tracker 的 songs.json，按 id 合并"""
    records = []
    for path in sorted(Path(root).glob("*/songs.json")):
        records.extend(load_songs_file(path))
    return records
