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
    QUALITY_MAP,
    VNCMD_HOME,
    abbrev_home,
    get_quality,
    resolve_output_dir,
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


def load_songs_db_full(name: str) -> dict:
    """读整个曲目库文件，含 updated_at

    与 load_songs_db 同一个文件、同一个备份退回路径，只是不把 updated_at 丢掉 ——
    那是判断数据有多旧的唯一依据，纯读面板与 --json 都要它。
    面板与 JSON 都从这里取，不重新组装，两者不会漂。
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
    """读曲目库，主文件坏了退回 backup_db 留下的那份

    这里不能像缓存那样读不出来就当空：曲目库是用户攒下来的，
    返回空列表会被后续同步当成「没有需要下载的曲目」，等于静默清空。
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
    empty = {"added": [], "removed": [], "changed": []}
    data = read_json_safe(path, None, what="变更记录")
    return data if isinstance(data, dict) else empty


def _display_songs(songs: list[dict], offset: int) -> None:
    """已缓存曲目的表

    与 album、playlist 的曲目表同一套做法：序号报绝对序号、占满终端宽度。
    区间不再给这张表，而是放在上面那个面板的标题里 ——
    与「歌单详情 - 819104208 - 101-200/298」同一个位置、同一个读法。

    传进来的已经是切好的那几条，所以序号要从 offset 起算。
    """
    from rich import box
    from rich.table import Table

    # expand 与另外三个命令的曲目表一致：都是曲目表，都该占满终端。
    # 下面的来源表故意不给 expand —— 三列固定内容，拉到 150 列会散成一片空白
    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("#", style="dim")
    table.add_column("ID", style="dim")
    # ratio 与另外三个命令一致：4:3 是标题与艺术家的退让顺序，
    # 没有它时最长那列会通吃，标题能被压到三个汉字宽
    table.add_column("标题", style="bright_white", ratio=4, overflow="fold")
    table.add_column("艺术家", style="bright_white", ratio=3, overflow="fold")
    for i, s in enumerate(songs, offset + 1):
        table.add_row(
            str(i),
            str(s["id"]),
            escape(s.get("title", "")),
            # 走 _artist_text 才有虚拟歌手的代表色，与另外三张曲目表一致。
            # 直接给字符串就只有 bright_white，初音ミク与普通歌手长得一样
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

    # 三行一行一项，不再挤成「描述：X  |  曲目数：N」：
    # 现在有三项了，竖线分隔会让最长的一项被折行挤掉
    header = Text()
    header.append("描述：", style="dim")
    header.append(f"{settings['description']}\n", style="yellow")
    # 这库是什么时候拉的只能从这里看出来：三个月没更新的库，
    # 曲目表上与刚拉的完全一样
    header.append("更新于：", style="dim")
    header.append(f"{updated_at}\n", style="green")
    header.append("已缓存曲目：", style="dim")
    header.append(f"{total}\n", style="green")
    # 只给路径不给来源列表：来源是用户自己写的，每次跑一遍没有新信息，
    # 而 529 首的歌单一屏放不下。路径给了，要看或改直接开那个文件
    header.append("设置：", style="dim")
    header.append(abbrev_home(_settings_path(name)), style="green")
    if not settings["sources"]:
        # 一个来源都没配时那行路径是死的，得说清为什么
        header.append("\n", style="dim")
        header.append("尚未配置来源，请编辑 settings.toml 添加来源。", style="yellow")

    # 区间跟着曲目表走，所以放在它的面板标题上 —— 与「歌单详情」同一位置
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

    信封与 song、album、playlist 一致，不用裸的 {"updated_at", "songs"} ——
    那样切分页只能在外面套一层，返回形状也会与另外三个命令不一样，
    会让人以为这文件是某个命令的输出。

    songs 直接取 songs.json，不重新组装，面板与 JSON 出自同一份。
    切片按 4.1 那条统一规则：显式给了 limit 或 offset 才切。
    """
    songs = db["songs"]
    if args.limit is not None or args.offset:
        end = args.offset + args.limit if args.limit else None
        songs = songs[args.offset : end]
    return {
        "tracker": {
            "updated_at": db["updated_at"],
            "sources": settings["sources"],
            "songs": songs,
        }
    }


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
                warning(f"获取 {src_type} {src_id} 失败：{e}")

    result = {}
    for sid, data in raw.items():
        entry = {
            "id": data["id"],
            "title": data["title"],
            # 老条目没这个键，留空而不是回退到现查 API：
            # 529 首是 6 个批次，明显不划算，下次 --fetch 自然补齐
            "artist": data.get("artist", ""),
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
            # 三种来源都已经在 track 里解析过 artist 了，
            # 这里只是没往下带 —— removed 那条一直在用 rt.get("artist", "")
            "artist": track.get("artist", ""),
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
    for old, _ in changed:
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


def _apply_force(name: str, fresh: dict, comparison: dict) -> None:
    """无条件覆盖 songs.json，diff.json 有变化才更新

    两个文件的时间戳从此不同步，而这是对的：一个是当前状态，
    一个是上次变更的快照 —— 覆盖之后「上次变了什么」就再也拿不回来了，
    所以那次快照必须留住。

    它与两个 resolve 恰恰相反：那两个「无变更就什么都不动」，
    而这里恰恰要写库 —— compare_songs 只比 title，
    artist 变了不算 changed，两个 resolve 都会把它静默丢掉。
    """
    save_songs_db(name, list(fresh.values()))
    success(f"已用上游覆盖 {len(fresh)} 首曲目")

    if any(comparison[k] for k in ("added", "removed", "changed")):
        save_diff(name, comparison)
    else:
        # 「覆盖了但 diff 没变」用户看不到，不说就以为 diff 已经是新的了
        info("本次未检测到变更，diff 记录保持上次的内容")


def download_tracker(name: str, quality: int, output_dir: str) -> None:
    songs = load_songs_db(name)
    if not songs:
        error(f"Tracker「{name}」未缓存曲目，请先执行 --fetch。")
        sys.exit(1)

    download_song_batch(songs, quality, output_dir, dl_type="tracker", dl_id=name)


def _diff_note(diff: dict) -> str:
    """把 removed 与 changed 写成一个文件的正文

    两类都是「变了但不用下载」的，放一个文件里，跑一次 --diff 只拿一个。
    分开两个文件的话，用户得自己记得上次那个还在不在。
    """
    parts = []
    removed = diff.get("removed", [])
    changed = diff.get("changed", [])
    if removed:
        lines = "\n".join(f"{s['id']}  {s['title']}" for s in removed)
        parts.append(f"以下曲目已从 Tracker 中移除（{len(removed)} 首）：\n{lines}")
    if changed:
        lines = "\n".join(
            f"{s['id']}  {s['title_old']} -> {s['title_new']}" for s in changed
        )
        parts.append(f"以下曲目标题已变更（{len(changed)} 首）：\n{lines}")
    return "\n\n".join(parts) + "\n"


def diff_payload(name: str) -> dict:
    """上次 --fetch 记下的差异，直接取 diff.json 不重新组装

    与 -d --diff 读到的是同一份数据、同一套三类，一致是理由：
    --json 在别的命令上是「换成机器可读」，不是「换一批数据」。

    读的是上次 --fetch 时的结论，不是「现在相对 sources 的差异」——
    后者要联网，那是 --fetch 的事。不联网也正是这个途径的价值所在。
    """
    return load_diff(name)


def download_diff(name: str, quality: int, output_dir: str) -> None:
    diff = load_diff(name)
    added = diff.get("added", [])

    if not added and not diff.get("removed") and not diff.get("changed"):
        info("未找到 diff，请先执行 --fetch。")
        return

    if added:
        _, _, session_dir = download_song_batch(
            added,
            quality,
            output_dir,
            dl_type="tracker",
            dl_id=name,
        )
        note_dir = Path(session_dir)
    else:
        success("没有需要下载的新曲目。")
        # 没有新增就没有下载会话，changed.txt 落在输出目录本身
        note_dir = Path(output_dir)
        note_dir.mkdir(parents=True, exist_ok=True)

    # changed 原来一次都没读，改了标题的曲目被整个丢掉了
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

    # 两个修饰都是 --fetch 的修饰，单独给在代码里落不到任何分支。
    # 什么都不做也没有提示，与其静默，不如说清它要配合什么。
    # 检查放在最前面：放到 tracker 存在性判断之后的话，
    # 用户会先被问「是否创建 tracker」，才发现自己的参数写错了
    if (args.auto_accept or args.force) and not args.fetch:
        which = "--auto-accept" if args.auto_accept else "--force"
        error(f"{which} 需要配合 --fetch 使用，它是拉取的修饰而非独立动作")
        sys.exit(2)

    # --json 配 --diff 是合法组合：读本地 diff.json，给的是数据不是动作。
    # 其余动作的结果都是文件，给一份没人会读的动作结果 JSON，
    # 不如说清它只管纯读视图。
    if args.json and not args.diff and (args.fetch or args.download):
        error("--json 只用于纯读视图，与 --fetch、-d 不能同时使用")
        sys.exit(2)

    # --diff 是 -d 或 --json 的修饰，单独给它在代码里落不到任何分支，
    # 什么都不做也没有提示。与其静默，不如说清它要配合什么。
    if args.diff and not (args.download or args.json):
        error("--diff 需要配合 -d 或 --json 使用，只看上次拉取后的变更")
        sys.exit(2)

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

    if args.fetch:
        settings = load_settings(name)
        if not settings["sources"]:
            error("未配置来源，请先编辑 settings.toml 添加来源。")
            sys.exit(1)

        info(f"正在获取 Tracker「{name}」的所有曲目...")
        fresh, removed = fetch_all_songs(settings)

        if removed:
            err_console.print()
            warning(f"检测到 {len(removed)} 首已下架曲目（不包含在 diff 中）：")
            for r in removed:
                err_console.print(
                    f"    [dim]{r['id']}[/]  [red]{escape(r['title'])}[/]"
                    f"  [dim]— {escape(r['artist'])}  ·  {escape(r['album'])}[/]"
                )

        if not fresh:
            warning("未获取到曲目，请检查来源配置。")
            return

        info(f"从来源获取到 {len(fresh)} 首独立曲目。")
        cached = load_songs_db(name)
        comparison = compare_songs(fresh, cached)

        if args.force:
            _apply_force(name, fresh, comparison)
        elif args.auto_accept:
            resolved = auto_resolve(comparison, cached, fresh)
            if resolved is not None:
                save_songs_db(name, resolved)
                save_diff(name, comparison)
                success(f"已保存 {len(resolved)} 首曲目到数据库。")
        else:
            resolved = resolve_conflicts(comparison, cached, fresh)
            if resolved is not None:
                save_songs_db(name, resolved)
                save_diff(name, comparison)
                success(f"已保存 {len(resolved)} 首曲目到数据库。")

    elif args.download:
        quality = QUALITY_MAP[args.quality] if args.quality else get_quality()
        output_dir = resolve_output_dir(args.output)
        if args.diff:
            download_diff(name, quality, output_dir)
        else:
            download_tracker(name, quality, output_dir)

    else:
        # 四个动作结果都是文件，纯读视图的结果是数据，所以只有这里给 --json
        if args.json:
            if args.diff:
                # 与 -d --diff 读同一份 diff.json、同样的三类，
                # 用户拿它生成的链接与 -d --diff 下的完全一致
                _dump_json({"tracker": {"diff": diff_payload(name)}})
                return
            db = load_songs_db_full(name)
            _dump_json(tracker_payload(load_settings(name), db, args))
            return
        show_tracker(
            name,
            load_songs_db_full(name)["updated_at"],
            max_tracks=args.limit or 10,
            offset=args.offset,
        )
