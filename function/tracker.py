import json
import os
import re
import shutil
import sys
import time
import tomllib
from datetime import datetime, timezone

from function.api import (
    get_song_details,
    get_playlist_details,
    get_album_details,
    get_song_url,
)
from function.downloader import download_song
from function.output import (
    success,
    error,
    info,
    warning,
    console,
)
from function.config import (
    get_quality,
    get_download_dir,
    get_download_content,
    QUALITY_MAP,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACKER_DIR = os.path.join(PROJECT_ROOT, "tracker")

_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

DEFAULT_SETTINGS = """\
[tracker]
description = "Describe this tracker here"

[[sources]]
type = "song"
ids = []

[[sources]]
type = "playlist"
ids = []

[[sources]]
type = "album"
ids = []
"""


def _tracker_path(name):
    return os.path.join(TRACKER_DIR, name)


def _settings_path(name):
    return os.path.join(_tracker_path(name), "settings.toml")


def _songs_path(name):
    return os.path.join(_tracker_path(name), "songs.json")


def validate_name(name):
    if not _NAME_RE.match(name):
        error(f"Invalid tracker name: '{name}'")
        info(
            "Name may only contain letters (a-z, A-Z), "
            "digits (0-9), dashes (-), and underscores (_)."
        )
        sys.exit(1)


def load_settings(name):
    path = _settings_path(name)
    if not os.path.exists(path):
        error(f"Tracker '{name}' not found. Settings file missing: {path}")
        sys.exit(1)
    with open(path, "rb") as f:
        data = tomllib.load(f)
    tracker = data.get("tracker", {})
    description = tracker.get("description", "")
    sources = data.get("sources", [])
    result = []
    for src in sources:
        src_type = src.get("type", "")
        ids = src.get("ids", [])
        if src_type and ids:
            result.append({"type": src_type, "ids": ids})
    return {"description": description, "sources": result}


def create_tracker(name):
    validate_name(name)
    tdir = _tracker_path(name)
    if os.path.exists(tdir):
        error(f"Tracker '{name}' already exists at: {tdir}")
        sys.exit(1)
    os.makedirs(tdir, exist_ok=True)

    with open(_settings_path(name), "w", encoding="utf-8") as f:
        f.write(DEFAULT_SETTINGS)

    empty_db = {"updated_at": "", "songs": []}
    with open(_songs_path(name), "w", encoding="utf-8") as f:
        json.dump(empty_db, f, ensure_ascii=False, indent=2)

    success(f"Tracker '{name}' created at: {tdir}")
    info("Edit the settings.toml file to add song/playlist/album IDs to track.")


def load_songs_db(name):
    path = _songs_path(name)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("songs", [])


def backup_db(name):
    songs_path = _songs_path(name)
    bak_path = songs_path + ".bak"
    if os.path.exists(bak_path):
        os.remove(bak_path)
    if os.path.exists(songs_path):
        shutil.copy2(songs_path, bak_path)


def save_songs_db(name, songs):
    backup_db(name)
    data = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "songs": songs,
    }
    with open(_songs_path(name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def show_tracker(name):
    settings = load_settings(name)
    songs = load_songs_db(name)

    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich import box

    header = Text()
    header.append("Tracker: ", style="bold")
    header.append(f"{name}\n", style="bold bright_white")
    header.append("Description: ", style="dim")
    header.append(f"{settings['description']}", style="yellow")
    console.print(Panel(header, border_style="cyan", box=box.ROUNDED))

    if settings["sources"]:
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("#", style="dim", width=4)
        table.add_column("Type", style="green", width=12)
        table.add_column("IDs", style="bright_white")
        for i, src in enumerate(settings["sources"], 1):
            table.add_row(
                str(i), src["type"], ", ".join(str(sid) for sid in src["ids"])
            )
        console.print(table)
    else:
        info("No sources configured yet. Edit settings.toml to add sources.")

    console.print(f"  Cached songs: [green]{len(songs)}[/]")


def fetch_all_songs(settings):
    raw = {}  # id -> {id, title, sources: [(type, id)]}

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
                elif src_type == "album":
                    al = get_album_details(src_id)
                    for track in al["tracks"]:
                        _add_to_raw(raw, track, src_type, src_id)
            except Exception as e:
                warning(f"Failed to fetch {src_type} {src_id}: {e}")

    result = {}
    for sid, data in raw.items():
        entry = {
            "id": data["id"],
            "title": data["title"],
        }
        if len(data["sources"]) > 1:
            entry["at"] = data["sources"]
        result[sid] = entry
    return result


def _add_to_raw(raw, track, src_type, src_id):
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


def compare_songs(fresh, cached_list):
    cached = {s["id"]: s for s in cached_list}
    fresh_ids = set(fresh.keys())
    cached_ids = set(cached.keys())

    added_ids = fresh_ids - cached_ids
    removed_ids = cached_ids - fresh_ids
    common_ids = fresh_ids & cached_ids

    added = sorted(
        [fresh[sid] for sid in added_ids], key=lambda x: x.get("title", "")
    )
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


def _get_checkbox_style(color="green"):
    try:
        from questionary import Style
    except ImportError:
        return None
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


def resolve_conflicts(comparison, cached_list, fresh_dict):
    added = comparison["added"]
    removed = comparison["removed"]
    changed = comparison["changed"]

    if not added and not removed and not changed:
        success("Already up to date — no changes detected.")
        return None

    try:
        import questionary
    except ImportError:
        error(
            "questionary is required for interactive mode. "
            "Install it with: pip install questionary"
        )
        sys.exit(1)

    result = {s["id"]: s for s in cached_list}

    if added:
        console.print()
        console.print(
            f"  [bold green]Added[/] — {len(added)} songs, "
            f"[dim]enter to confirm, space to toggle, "
            f"a to select all, i to invert[/]"
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
            info("Cancelled.")
            sys.exit(0)
        for sid in selected:
            result[sid] = fresh_dict[sid]

    if removed:
        console.print()
        console.print(
            f"  [bold red]Removed[/] — {len(removed)} songs, "
            f"[dim]enter to confirm, space to toggle, "
            f"a to select all, i to invert[/]"
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
            info("Cancelled.")
            sys.exit(0)
        for sid in selected:
            result.pop(sid, None)

    if changed:
        from rich.panel import Panel
        from rich.text import Text

        for old, new in changed:
            text = Text()
            text.append("Old: ", style="red")
            text.append(f"{old.get('title', '?')}\n", style="red")
            text.append("New: ", style="green")
            text.append(f"{new.get('title', '?')}", style="green")
            console.print(
                Panel(
                    text,
                    title=f"Changed: ID {old['id']}",
                    border_style="yellow",
                )
            )
            if questionary.confirm(
                "Apply this change?", default=True
            ).ask():
                result[old["id"]] = fresh_dict[old["id"]]

    return sorted(result.values(), key=lambda x: x.get("title", ""))


def auto_resolve(comparison, cached_list, fresh_dict):
    added = comparison["added"]
    removed = comparison["removed"]
    changed = comparison["changed"]

    if not added and not removed and not changed:
        success("Already up to date — no changes detected.")
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
        summary_parts.append(f"[green]+ {len(added)} added[/]")
    if removed:
        summary_parts.append(f"[red]- {len(removed)} removed[/]")
    if changed:
        summary_parts.append(f"[yellow]~ {len(changed)} updated[/]")
    console.print(f"Auto-sync complete: {', '.join(summary_parts)}")

    return sorted(result.values(), key=lambda x: x.get("title", ""))


def _format_song_choice(s):
    return f"{s.get('title', '?')} (ID: {s['id']})"


def download_tracker(name, quality, output_dir):
    songs = load_songs_db(name)
    if not songs:
        error(f"No songs cached for tracker '{name}'. Run --fetch first.")
        sys.exit(1)

    want_song = "0" in get_download_content()
    total = len(songs)
    success_count = 0
    fail_count = 0
    fail_ids = []

    for i, s in enumerate(songs, 1):
        sid = s["id"]

        try:
            details = get_song_details(sid)
        except Exception as e:
            warning(
                f"[{i}/{total}] Skipping {s.get('title', '?')} "
                f"(ID: {sid}) — failed to get details: {e}"
            )
            fail_count += 1
            fail_ids.append(sid)
            continue

        info(f"[{i}/{total}] {details['title']} - {details['artist']}")

        song_url = ""
        if want_song:
            song_url = get_song_url(sid, quality=quality) or ""
            if not song_url:
                warning(f"  Skipping (no URL — VIP or unavailable): {sid}")
                fail_count += 1
                fail_ids.append(sid)
                continue

        lyrics_api = (
            f"http://music.163.com/api/song/lyric?os=pc&id={sid}&lv=-1&tv=1"
        )
        ok, msg, _ = download_song(
            song_url=song_url,
            song_title=details["title"],
            song_artist=details["artist"],
            song_album=details["album"],
            song_id=str(sid),
            cover_url=details["cover"],
            lyrics_api_url=lyrics_api,
            publish_time=details["publish_time"],
            download_dir=output_dir,
        )
        if ok:
            success_count += 1
            console.print("  [green]✓[/] Downloaded")
        else:
            fail_count += 1
            fail_ids.append(sid)
            console.print(f"  [red]✗[/] {msg}")

        time.sleep(0.3)

    console.print()
    console.print(
        f"Done: [green]{success_count} success[/], "
        f"[red]{fail_count} failed[/]"
    )
    if fail_ids:
        console.print(
            f"Failed IDs: {', '.join(str(i) for i in fail_ids)}"
        )


def cmd_tracker(args):
    name = args.name
    validate_name(name)

    tdir = _tracker_path(name)
    if not os.path.isdir(tdir):
        try:
            import questionary
            if questionary.confirm(
                f"Tracker '{name}' does not exist. Create it?",
                default=True,
            ).ask():
                create_tracker(name)
            else:
                info("Cancelled.")
        except ImportError:
            answer = (
                input(f"Tracker '{name}' does not exist. Create it? [Y/n]: ")
                .strip()
                .lower()
            )
            if answer in ("", "y", "yes"):
                create_tracker(name)
            else:
                info("Cancelled.")
        return

    if args.fetch or args.fetch_auto:
        settings = load_settings(name)
        if not settings["sources"]:
            error(
                "No sources configured. "
                "Edit settings.toml to add sources first."
            )
            sys.exit(1)

        info(f"Fetching all songs for tracker '{name}'...")
        fresh = fetch_all_songs(settings)

        if not fresh:
            warning("No songs fetched. Check your sources configuration.")
            return

        info(f"Fetched {len(fresh)} unique songs from sources.")
        cached = load_songs_db(name)
        comparison = compare_songs(fresh, cached)

        if args.fetch_auto:
            resolved = auto_resolve(comparison, cached, fresh)
        else:
            resolved = resolve_conflicts(comparison, cached, fresh)

        if resolved is not None:
            save_songs_db(name, resolved)
            success(f"Saved {len(resolved)} songs to database.")

    elif args.download:
        quality = QUALITY_MAP[args.quality] if args.quality else get_quality()
        output_dir = args.output if args.output else get_download_dir()
        download_tracker(name, quality, output_dir)

    else:
        show_tracker(name)
