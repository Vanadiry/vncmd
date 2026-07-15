import argparse
import json
import os
import questionary
import re
import shutil
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from function.api import (
    get_song_details,
    get_playlist_details,
    get_album_details,
)
from function.downloader import download_song_batch
from function.output import (
    success,
    error,
    info,
    warning,
    console,
)
from rich.markup import escape
from function._defaults import TRACKER_SETTINGS_TOML
from function.config import (
    get_quality,
    get_download_dir,
    QUALITY_MAP,
    VNCMD_HOME,
)

TRACKER_DIR = VNCMD_HOME / "tracker"

_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _tracker_path(name: str) -> Path:
    return TRACKER_DIR / name


def _settings_path(name: str) -> Path:
    return _tracker_path(name) / "settings.toml"


def _songs_path(name: str) -> Path:
    return _tracker_path(name) / "songs.json"


def _diff_path(name: str) -> Path:
    return _tracker_path(name) / "diff.json"


def validate_name(name: str) -> None:
    if not _NAME_RE.match(name):
        error(f"无效的 Tracker 名称：「{name}」")
        info("名称只能包含字母（a-z、A-Z）、数字（0-9）、短划线（-）和下划线（_）。")
        sys.exit(1)


def load_settings(name: str) -> dict:
    path = _settings_path(name)
    if not path.exists():
        error(f"Tracker「{name}」不存在，配置文件缺失：{path}")
        sys.exit(1)
    with open(path, "rb") as f:
        data = tomllib.load(f)
    tracker = data.get("tracker", {})
    description = tracker.get("description", "")
    sources = data.get("sources", {})
    result = []
    for src_type, src_data in sources.items():
        ids = src_data.get("ids", [])
        if ids:
            result.append({"type": src_type, "ids": ids})
    return {"description": description, "sources": result}


def create_tracker(name: str) -> None:
    validate_name(name)
    tdir = _tracker_path(name)
    if tdir.exists():
        error(f"Tracker「{name}」已存在：{tdir}")
        sys.exit(1)
    tdir.mkdir(parents=True, exist_ok=True)

    _settings_path(name).write_text(TRACKER_SETTINGS_TOML, encoding="utf-8")

    empty_db = {"updated_at": "", "songs": []}
    _songs_path(name).write_text(
        json.dumps(empty_db, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    success(f"Tracker「{name}」已创建：{tdir}")
    info("请编辑 settings.toml 添加需要跟踪的曲目/歌单/专辑 ID。")


def load_songs_db(name: str) -> list[dict]:
    path = _songs_path(name)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("songs", [])


def backup_db(name: str) -> None:
    songs_path = _songs_path(name)
    if not songs_path.exists():
        return
    bak_path = songs_path.parent / (songs_path.name + ".bak")
    bak_tmp = songs_path.parent / (songs_path.name + ".bak.tmp")
    shutil.copy2(songs_path, bak_tmp)
    os.replace(bak_tmp, bak_path)


def save_songs_db(name: str, songs: list[dict]) -> None:
    backup_db(name)
    data = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "songs": songs,
    }
    _songs_path(name).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def save_diff(name: str, comparison: dict) -> None:
    diff = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "added": [{"id": s["id"], "title": s["title"]} for s in comparison["added"]],
        "removed": [
            {"id": s["id"], "title": s["title"]} for s in comparison["removed"]
        ],
        "changed": [
            {
                "id": old["id"],
                "title_old": old["title"],
                "title_new": new["title"],
            }
            for old, new in comparison["changed"]
        ],
    }
    _diff_path(name).write_text(
        json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_diff(name: str) -> dict:
    path = _diff_path(name)
    if not path.exists():
        return {"added": [], "removed": [], "changed": []}
    return json.loads(path.read_text(encoding="utf-8"))


def show_tracker(name: str) -> None:
    settings = load_settings(name)
    songs = load_songs_db(name)

    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich import box

    header = Text()
    header.append("Tracker：", style="bold")
    header.append(f"{name}\n", style="bold bright_white")
    header.append("描述：", style="dim")
    header.append(f"{settings['description']}", style="yellow")
    console.print(Panel(header, border_style="cyan", box=box.ROUNDED))

    if settings["sources"]:
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("#", style="dim", width=4)
        table.add_column("类型", style="green", width=12)
        table.add_column("ID", style="bright_white")
        for i, src in enumerate(settings["sources"], 1):
            table.add_row(
                str(i), src["type"], ", ".join(str(sid) for sid in src["ids"])
            )
        console.print(table)
    else:
        info("尚未配置来源，请编辑 settings.toml 添加来源。")

    console.print(f"  已缓存曲目：[green]{len(songs)}[/]")


def fetch_all_songs(settings: dict) -> tuple[dict[str, dict], list[dict]]:
    raw = {}  # id -> {id, title, sources: [(type, id)]}
    removed = []  # removed tracks from playlist sources

    for src in settings["sources"]:
        src_type = src["type"]
        for src_id in src["ids"]:
            try:
                if src_type == "song":
                    song = get_song_details(src_id)
                    _add_to_raw(raw, song, src_type, src_id)
                elif src_type == "playlist":
                    pl = get_playlist_details(src_id, limit=None)
                    for track in pl["tracks"]:
                        _add_to_raw(raw, track, src_type, src_id)
                    for rt in pl.get("removed_tracks", []):
                        removed.append(
                            {
                                "id": rt["id"],
                                "title": rt["title"],
                                "artist": rt.get("artist", ""),
                                "album": rt.get("album", ""),
                                "source_type": src_type,
                                "source_id": src_id,
                            }
                        )
                elif src_type == "album":
                    al = get_album_details(src_id)
                    for track in al["tracks"]:
                        _add_to_raw(raw, track, src_type, src_id)
            except Exception as e:
                warning(f"获取 {src_type} {src_id} 失败：{e}")

    result = {}
    for sid, data in raw.items():
        entry = {
            "id": data["id"],
            "title": data["title"],
        }
        if len(data["sources"]) > 1:
            entry["at"] = data["sources"]
        result[sid] = entry
    return result, removed


def _add_to_raw(raw: dict, track: dict, src_type: str, src_id: int) -> None:
    sid = track["id"]
    source_ref = {"type": src_type, "id": src_id}
    if sid in raw:
        existing_sources = raw[sid]["sources"]
        if source_ref not in existing_sources:
            existing_sources.append(source_ref)
    else:
        raw[sid] = {
            "id": sid,
            "title": track["title"],
            "sources": [source_ref],
        }


def compare_songs(fresh: dict[str, dict], cached_list: list[dict]) -> dict:
    cached = {s["id"]: s for s in cached_list}
    fresh_ids = set(fresh.keys())
    cached_ids = set(cached.keys())

    added_ids = fresh_ids - cached_ids
    removed_ids = cached_ids - fresh_ids
    common_ids = fresh_ids & cached_ids

    added = sorted([fresh[sid] for sid in added_ids], key=lambda x: x.get("title", ""))
    removed = sorted(
        [cached[sid] for sid in removed_ids], key=lambda x: x.get("title", "")
    )
    changed = []
    for sid in common_ids:
        old = cached[sid]
        new = fresh[sid]
        if old.get("title") != new.get("title"):
            changed.append((old, new))
    changed.sort(key=lambda x: x[0].get("title", ""))

    return {"added": added, "removed": removed, "changed": changed}


def _get_checkbox_style(color: str = "green") -> object:
    from questionary import Style

    return Style(
        [
            ("highlighted", "fg:ansicyan bold"),
            ("pointer", f"fg:ansi{color} bold"),
            ("checkbox-checked", f"fg:ansi{color} bold"),
            ("checkbox-unchecked", "fg:ansidarkgray"),
            ("selected", f"fg:ansi{color}"),
            ("text", ""),
        ]
    )


def resolve_conflicts(
    comparison: dict, cached_list: list[dict], fresh_dict: dict[str, dict]
) -> list[dict] | None:
    added = comparison["added"]
    removed = comparison["removed"]
    changed = comparison["changed"]

    if not added and not removed and not changed:
        success("已是最新，未检测到变更。")
        return None

    result = {s["id"]: s for s in cached_list}

    if added:
        console.print()
        console.print(
            f"  [bold green]新增[/] — {len(added)} 首，"
            f"[dim]回车确认、空格切换、a 全选、i 反选[/]"
        )
        choices = [
            questionary.Choice(
                title=_format_song_choice(s),
                value=s["id"],
                checked=False,
            )
            for s in added
        ]
        selected = questionary.checkbox(
            "",
            choices=choices,
            qmark="",
            instruction="",
            style=_get_checkbox_style("green"),
        ).ask()
        if selected is None:
            info("已取消。")
            sys.exit(0)
        for sid in selected:
            result[sid] = fresh_dict[sid]

    if removed:
        console.print()
        console.print(
            f"  [bold red]删除[/] — {len(removed)} 首，"
            f"[dim]回车确认、空格切换、a 全选、i 反选[/]"
        )
        choices = [
            questionary.Choice(
                title=_format_song_choice(s),
                value=s["id"],
                checked=False,
            )
            for s in removed
        ]
        selected = questionary.checkbox(
            "",
            choices=choices,
            qmark="",
            instruction="",
            style=_get_checkbox_style("red"),
        ).ask()
        if selected is None:
            info("已取消。")
            sys.exit(0)
        for sid in selected:
            result.pop(sid, None)

    if changed:
        from rich.panel import Panel
        from rich.text import Text

        for old, new in changed:
            text = Text()
            text.append("旧：", style="red")
            text.append(f"{old.get('title', '?')}\n", style="red")
            text.append("新：", style="green")
            text.append(f"{new.get('title', '?')}", style="green")
            console.print(
                Panel(
                    text,
                    title=f"已变更：ID {old['id']}",
                    border_style="yellow",
                )
            )
            if questionary.confirm("应用此变更？", default=True).ask():
                result[old["id"]] = fresh_dict[old["id"]]

    return sorted(result.values(), key=lambda x: x.get("title", ""))


def auto_resolve(
    comparison: dict, cached_list: list[dict], fresh_dict: dict[str, dict]
) -> list[dict] | None:
    added = comparison["added"]
    removed = comparison["removed"]
    changed = comparison["changed"]

    if not added and not removed and not changed:
        success("已是最新，未检测到变更。")
        return None

    result = {s["id"]: s for s in cached_list}

    for s in added:
        result[s["id"]] = fresh_dict[s["id"]]
    for s in removed:
        result.pop(s["id"], None)
    for old, new in changed:
        result[old["id"]] = fresh_dict[old["id"]]

    summary_parts = []
    if added:
        summary_parts.append(f"[green]+ {len(added)} 新增[/]")
    if removed:
        summary_parts.append(f"[red]- {len(removed)} 删除[/]")
    if changed:
        summary_parts.append(f"[yellow]~ {len(changed)} 更新[/]")
    console.print(f"自动同步完成：{', '.join(summary_parts)}")

    return sorted(result.values(), key=lambda x: x.get("title", ""))


def _format_song_choice(s: dict) -> str:
    return f"{s.get('title', '?')}（ID: {s['id']}）"


def download_tracker(
    name: str, quality: int, output_dir: str, dry_run: bool = False
) -> None:
    songs = load_songs_db(name)
    if not songs:
        error(f"Tracker「{name}」未缓存曲目，请先执行 --fetch。")
        sys.exit(1)

    download_song_batch(
        songs, quality, output_dir, dry_run=dry_run, dl_type="tracker", dl_id=name
    )


def download_diff(
    name: str, quality: int, output_dir: str, dry_run: bool = False
) -> None:
    diff = load_diff(name)
    added = diff.get("added", [])
    removed = diff.get("removed", [])

    if not added and not removed:
        info("未找到 diff，请先执行 --fetch。")
        return

    if not added:
        if removed:
            info(f"Tracker 中已删除 {len(removed)} 首曲目。")
        success("没有需要下载的新曲目。")
        return

    _, _, session_dir = download_song_batch(
        added,
        quality,
        output_dir,
        dry_run=dry_run,
        dl_type="tracker",
        dl_id=name,
    )

    if removed:
        removed_path = Path(session_dir) / "removed.txt"
        lines = [f"{s['id']}  {s['title']}" for s in removed]
        removed_path.write_text(
            "以下曲目已从 Tracker 中移除：\n" + "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        info(f"{len(removed)} 首曲目已移除，详见 {removed_path}")


def cmd_tracker(args: argparse.Namespace) -> None:
    name = args.name
    validate_name(name)

    tdir = _tracker_path(name)
    if not tdir.is_dir():
        if questionary.confirm(
            f"Tracker「{name}」不存在，是否创建？",
            default=False,
        ).ask():
            create_tracker(name)
        else:
            info("已取消。")
        return

    if args.fetch or args.fetch_auto:
        settings = load_settings(name)
        if not settings["sources"]:
            error("未配置来源，请先编辑 settings.toml 添加来源。")
            sys.exit(1)

        info(f"正在获取 Tracker「{name}」的所有曲目...")
        fresh, removed = fetch_all_songs(settings)

        if removed:
            console.print()
            warning(f"检测到 {len(removed)} 首已下架曲目（不包含在 diff 中）：")
            for r in removed:
                console.print(
                    f"    [dim]{r['id']}[/]  [red]{escape(r['title'])}[/]"
                    f"  [dim]— {escape(r['artist'])}  ·  {escape(r['album'])}[/]"
                )

        if not fresh:
            warning("未获取到曲目，请检查来源配置。")
            return

        info(f"从来源获取到 {len(fresh)} 首独立曲目。")
        cached = load_songs_db(name)
        comparison = compare_songs(fresh, cached)

        if args.fetch_auto:
            resolved = auto_resolve(comparison, cached, fresh)
        else:
            resolved = resolve_conflicts(comparison, cached, fresh)

        if resolved is not None:
            save_songs_db(name, resolved)
            save_diff(name, comparison)
            success(f"已保存 {len(resolved)} 首曲目到数据库。")

    elif args.download:
        quality = QUALITY_MAP[args.quality] if args.quality else get_quality()
        output_dir = args.output if args.output else get_download_dir()
        if args.diff:
            download_diff(name, quality, output_dir, dry_run=args.dry_run)
        else:
            download_tracker(name, quality, output_dir, dry_run=args.dry_run)

    else:
        show_tracker(name)
