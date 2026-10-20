import argparse
import json
import os
import re
import shutil
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import questionary
from rich.markup import escape

from vncmd.commands import _dump_json
from vncmd.core.config import (
    VNCMD_HOME,
    abbrev_home,
    get_download_dir,
    get_quality,
)
from vncmd.core.defaults import TRACKER_SETTINGS_TOML
from vncmd.core.jsonstore import read_json_safe, write_json_atomic
from vncmd.core.output import (
    _artist_text,
    _range_suffix,
    console,
    err_console,
    error,
    info,
    success,
    warning,
)
from vncmd.downloader import download_song_batch
from vncmd.net.api import (
    get_album_details,
    get_playlist_details,
    get_song_details,
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
        error(f"Tracker 名称不合法：{name}")
        info("名称只能包含字母 a-z、A-Z，数字 0-9，短划线 -，下划线 _")
        sys.exit(1)


def load_settings(name: str) -> dict:
    path = _settings_path(name)
    if not path.exists():
        error(f"Tracker“{name}”不存在，配置文件缺失：{path}")
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
        error(f"Tracker“{name}”已存在：{tdir}")
        sys.exit(1)
    tdir.mkdir(parents=True, exist_ok=True)

    _settings_path(name).write_text(TRACKER_SETTINGS_TOML, encoding="utf-8")

    empty_db = {"updated_at": "", "songs": []}
    _songs_path(name).write_text(
        json.dumps(empty_db, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    success(f"Tracker“{name}”已创建：{tdir}")
    info("settings.toml 用于添加需要跟踪的曲目、歌单或专辑 ID")


def load_songs_db_full(name: str) -> dict:
    """读曲目库全文，含 updated_at

    主文件损坏时退回备份
    """
    path = _songs_path(name)
    if not path.exists():
        return {"updated_at": "", "songs": []}
    data = read_json_safe(path, None, what="曲目库")
    if data is None:
        bak = path.with_name(f"{path.name}.bak")
        data = read_json_safe(bak, None, what="曲目库备份")
        if data is not None:
            warning(f"已改用备份：{bak}")
    if not isinstance(data, dict):
        return {"updated_at": "", "songs": []}
    return {"updated_at": data.get("updated_at", ""), "songs": data.get("songs", [])}


def load_songs_db(name: str) -> list[dict]:
    """读曲目库，主文件损坏时退回备份

    不能读成空列表，否则后续同步会当成无需下载
    """
    return load_songs_db_full(name)["songs"]


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
        "updated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "songs": songs,
    }
    write_json_atomic(_songs_path(name), data)


def save_diff(name: str, comparison: dict) -> None:
    diff = {
        "updated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "added": [s["id"] for s in comparison["added"]],
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
    empty = {"added": [], "removed": [], "changed": []}
    data = read_json_safe(path, None, what="变更记录")
    return data if isinstance(data, dict) else empty


def _display_songs(songs: list[dict], offset: int) -> None:
    """已缓存曲目的表

    序号从 offset 起算，表格占满终端
    """
    from rich import box
    from rich.table import Table

    # 曲目表占满终端
    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("#", style="dim")
    table.add_column("ID", style="dim")
    # 4:3 为标题与艺术家的退让顺序，避免最长列通吃
    table.add_column("标题", style="bright_white", ratio=4, overflow="fold")
    table.add_column("艺术家", style="bright_white", ratio=3, overflow="fold")
    for i, s in enumerate(songs, offset + 1):
        table.add_row(
            str(i),
            str(s["id"]),
            escape(s.get("title", "")),
            # 走 _artist_text 才有虚拟歌手的代表色
            _artist_text(s.get("artist", ""), "bright_white"),
        )
    console.print(table)


def show_tracker(
    name: str, updated_at: str = "", max_tracks: int = 10, offset: int = 0
) -> None:
    settings = load_settings(name)
    songs = load_songs_db(name)

    from rich import box
    from rich.panel import Panel
    from rich.text import Text

    total = len(songs)
    shown = songs[offset : offset + max_tracks]

    # 一行一项，避免竖线分隔挤掉最长项
    header = Text()
    header.append("描述：", style="dim")
    header.append(f"{settings['description']}\n", style="yellow")
    # 更新于只能从这里看出，旧库与刚拉的曲目表相同
    header.append("更新于：", style="dim")
    header.append(f"{updated_at}\n", style="green")
    header.append("已缓存曲目：", style="dim")
    header.append(f"{total}\n", style="green")
    # 来源由用户维护，这里只给设置文件路径
    header.append("设置：", style="dim")
    header.append(abbrev_home(_settings_path(name)), style="green")
    if not settings["sources"]:
        # 未配置来源时说明原因
        header.append("\n", style="dim")
        header.append("尚未配置来源，settings.toml 中没有来源", style="yellow")

    # 区间放在面板标题
    suffix = _range_suffix(offset, len(shown), total)
    console.print(
        Panel(
            header,
            title=f"[bold]Tracker - {name} - {suffix}[/]",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )

    if shown:
        _display_songs(shown, offset)


def tracker_payload(settings: dict, db: dict, args: argparse.Namespace) -> dict:
    """纯读视图的 JSON 形状

    信封与 song、album、playlist 一致，songs 直接取 songs.json
    """
    songs = db["songs"]
    if args.count is not None or args.offset:
        end = args.offset + args.count if args.count else None
        songs = songs[args.offset : end]
    return {
        "tracker": {
            "updated_at": db["updated_at"],
            "sources": settings["sources"],
            "songs": songs,
        }
    }


def fetch_all_songs(settings: dict) -> tuple[dict[str, dict], list[dict]]:
    raw = {}  # id 到曲目与来源的映射
    removed = []  # 歌单来源里已下架的曲目

    for src in settings["sources"]:
        src_type = src["type"]
        for src_id in src["ids"]:
            try:
                if src_type == "song":
                    song = get_song_details(src_id)
                    _add_to_raw(raw, song, src_type, src_id)
                elif src_type == "playlist":
                    pl = get_playlist_details(src_id)
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
                label = {"song": "曲目", "playlist": "歌单", "album": "专辑"}.get(
                    src_type, src_type
                )
                warning(f"获取{label} {src_id} 失败：{e}")

    result = {}
    for sid, data in raw.items():
        entry = {
            "id": data["id"],
            "title": data["title"],
            # 老条目缺 artist 时留空，下次 --fetch 补齐
            "artist": data.get("artist", ""),
            "publish_time": data.get("publish_time", ""),
        }
        if len(data["sources"]) > 1:
            entry["at"] = data["sources"]
        result[sid] = entry
    return result, removed


def _add_to_raw(raw: dict, track: dict, src_type: str, src_id: int) -> None:
    sid = track["id"]
    source_ref = {"type": src_type, "id": src_id}
    publish_time = track.get("publish_time") or ""
    if sid in raw:
        existing_sources = raw[sid]["sources"]
        if source_ref not in existing_sources:
            existing_sources.append(source_ref)
        # 第一次有值的为准，后面的源只补空日期，不覆盖已有值
        if not raw[sid].get("publish_time"):
            raw[sid]["publish_time"] = publish_time
    else:
        raw[sid] = {
            "id": sid,
            "title": track["title"],
            # artist 已在三种来源里解析好
            "artist": track.get("artist", ""),
            "publish_time": publish_time,
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
        success("未检测到变更")
        return None

    result = {s["id"]: s for s in cached_list}

    if added:
        console.print()
        console.print(
            f"  [bold green]新增[/] {len(added)} 首，"
            f"[dim]回车确认，空格切换，a 全选，i 反选[/]"
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
            info("已取消")
            sys.exit(0)
        for sid in selected:
            result[sid] = fresh_dict[sid]

    if removed:
        console.print()
        console.print(
            f"  [bold red]删除[/] {len(removed)} 首，"
            f"[dim]回车确认，空格切换，a 全选，i 反选[/]"
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
            info("已取消")
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
        success("未检测到变更")
        return None

    result = {s["id"]: s for s in cached_list}

    for s in added:
        result[s["id"]] = fresh_dict[s["id"]]
    for s in removed:
        result.pop(s["id"], None)
    for old, _ in changed:
        result[old["id"]] = fresh_dict[old["id"]]

    summary_parts = []
    if added:
        summary_parts.append(f"[green]{len(added)} 首新增[/]")
    if removed:
        summary_parts.append(f"[red]{len(removed)} 首删除[/]")
    if changed:
        summary_parts.append(f"[yellow]{len(changed)} 首更新[/]")
    console.print(f"自动同步完成：{'，'.join(summary_parts)}")

    return sorted(result.values(), key=lambda x: x.get("title", ""))


def _format_song_choice(s: dict) -> str:
    return f"{s.get('title', '?')}，ID {s['id']}"


def _apply_force(name: str, fresh: dict, comparison: dict) -> None:
    """无条件覆盖 songs.json，diff.json 有变化才更新

    compare_songs 只比标题，artist 变化不算 changed
    """
    save_songs_db(name, list(fresh.values()))
    success(f"已用上游覆盖 {len(fresh)} 首曲目")

    if any(comparison[k] for k in ("added", "removed", "changed")):
        save_diff(name, comparison)
    else:
        # 覆盖后 diff 未变时也要说明
        info("未检测到变更，diff 记录保持上次内容")


def download_tracker(name: str, quality: int, output_dir: str) -> None:
    songs = load_songs_db(name)
    if not songs:
        error(f"Tracker“{name}”未缓存曲目")
        sys.exit(1)

    download_song_batch(songs, quality, output_dir, dl_type="tracker", dl_id=name)


def _diff_note(diff: dict) -> str:
    """把 removed 与 changed 写成 changed.txt 的正文"""
    parts = []
    removed = diff.get("removed", [])
    changed = diff.get("changed", [])
    if removed:
        lines = "\n".join(f"{s['id']}  {s['title']}" for s in removed)
        parts.append(f"以下曲目已从 Tracker 移除，共 {len(removed)} 首：\n{lines}")
    if changed:
        lines = "\n".join(
            f"{s['id']}  {s['title_old']} 改为 {s['title_new']}" for s in changed
        )
        parts.append(f"以下曲目标题已变更，共 {len(changed)} 首：\n{lines}")
    return "\n\n".join(parts) + "\n"


def diff_payload(name: str) -> dict:
    """上次 --fetch 记下的差异，直接读 diff.json"""
    return load_diff(name)


def download_diff(name: str, quality: int, output_dir: str) -> None:
    diff = load_diff(name)
    added = diff.get("added", [])

    if not added and not diff.get("removed") and not diff.get("changed"):
        info("未找到 diff")
        return

    if added:
        # -fF 为升级前提，added 的 id 都在 songs.json 里
        songs_by_id = {s["id"]: s for s in load_songs_db(name)}
        added_songs = [songs_by_id[sid] for sid in added]
        _, _, session_dir = download_song_batch(
            added_songs,
            quality,
            output_dir,
            dl_type="tracker",
            dl_id=name,
        )
        note_dir = Path(session_dir)
    else:
        success("没有需要下载的新曲目")
        # 无新增时没有下载会话，changed.txt 落在输出目录
        note_dir = Path(output_dir)
        note_dir.mkdir(parents=True, exist_ok=True)

    note = _diff_note(diff)
    if note.strip():
        note_path = note_dir / "changed.txt"
        note_path.write_text(note, encoding="utf-8")
        parts = []
        if diff.get("removed"):
            parts.append(f"{len(diff['removed'])} 首已移除")
        if diff.get("changed"):
            parts.append(f"{len(diff['changed'])} 首标题变更")
        info(f"{'、'.join(parts)}，详见 {note_path}")


def cmd_tracker(args: argparse.Namespace) -> None:
    name = args.name

    # 修饰项必须在前面检查，避免先询问创建 Tracker
    if (args.auto_accept or args.force) and not args.fetch:
        which = "--auto-accept" if args.auto_accept else "--force"
        error(f"{which} 只能与 --fetch 同时使用")
        sys.exit(2)

    # --json 只用于纯读视图
    if args.json and not args.diff and (args.fetch or args.download):
        error("--json 只能用于纯读视图，与 --fetch、-d 互斥")
        sys.exit(2)

    # --diff 必须配合 -d 或 --json
    if args.diff and not (args.download or args.json):
        error("--diff 只能与 -d 或 --json 同时使用")
        sys.exit(2)

    validate_name(name)

    tdir = _tracker_path(name)
    if not tdir.is_dir():
        if questionary.confirm(
            f"Tracker“{name}”不存在，是否创建",
            default=False,
        ).ask():
            create_tracker(name)
        else:
            info("已取消")
        return

    if args.fetch:
        settings = load_settings(name)
        if not settings["sources"]:
            error("未配置来源，settings.toml 中没有来源")
            sys.exit(1)

        info(f"正在拉取 Tracker“{name}”的全部曲目")
        fresh, removed = fetch_all_songs(settings)

        if removed:
            err_console.print()
            warning(f"检测到 {len(removed)} 首已下架曲目，不计入 diff：")
            for r in removed:
                err_console.print(
                    f"    [dim]{r['id']}[/]  [red]{escape(r['title'])}[/]"
                    f"  [dim]{escape(r['artist'])}，{escape(r['album'])}[/]"
                )

        if not fresh:
            warning("未能提取曲目")
            return

        info(f"从来源提取 {len(fresh)} 首独立曲目")
        cached = load_songs_db(name)
        comparison = compare_songs(fresh, cached)

        if args.force:
            _apply_force(name, fresh, comparison)
        elif args.auto_accept:
            resolved = auto_resolve(comparison, cached, fresh)
            if resolved is not None:
                save_songs_db(name, resolved)
                save_diff(name, comparison)
                success(f"已保存 {len(resolved)} 首曲目")
        else:
            resolved = resolve_conflicts(comparison, cached, fresh)
            if resolved is not None:
                save_songs_db(name, resolved)
                save_diff(name, comparison)
                success(f"已保存 {len(resolved)} 首曲目")

    elif args.download:
        quality = get_quality()
        output_dir = get_download_dir()
        if args.diff:
            download_diff(name, quality, output_dir)
        else:
            download_tracker(name, quality, output_dir)

    else:
        # 只有纯读视图给 --json
        if args.json:
            if args.diff:
                # 与 -d --diff 读同一份 diff.json
                _dump_json({"tracker": {"diff": diff_payload(name)}})
                return
            db = load_songs_db_full(name)
            _dump_json(tracker_payload(load_settings(name), db, args))
            return
        show_tracker(
            name,
            load_songs_db_full(name)["updated_at"],
            max_tracks=args.count or 10,
            offset=args.offset,
        )
