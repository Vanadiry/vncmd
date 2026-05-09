"""Scan downloaded audio files for problematic multi-artist tags.

A problematic tag is one where the first artist has 3+ CJK/Kana characters
followed by a separator (, / or &) and another artist — this crashes Petrichor.

Files with problematic tags are moved to a "problematic" subfolder alongside
their matching .lrc lyrics and .jpg cover files.

Usage:
    python3 scan_artists.py [/path/to/download/dir ...]
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path

VNCMD_HOME = Path(os.environ.get("VNCMD_HOME", Path.home() / ".vncmd"))
CACHE_DOWNLOAD = VNCMD_HOME / "cache" / "download"
CONFIG_FILE = VNCMD_HOME / "config.toml"

NON_LATIN = re.compile(r"[^\x00-\x7F]")
AUDIO_EXTS = {".flac", ".mp3", ".m4a", ".aac", ".ogg", ".wav", ".wma", ".opus", ".ape"}
LYRICS_EXTS = {".lrc", ".txt"}
COVER_EXTS = {".jpg", ".jpeg", ".png"}


def is_problematic(artist: str) -> bool:
    """Check if artist tag triggers the Petrichor CJK crash."""
    sep = None
    for s in (", ", " & ", " &", "/"):
        if s in artist:
            sep = s
            break
    if not sep:
        return False

    parts = [p.strip() for p in artist.split(sep)]
    counts = [len(NON_LATIN.findall(p)) for p in parts]

    first = counts[0]
    if first == 0:
        return False
    if first >= 3:
        return True

    # first == 1 or 2
    second = counts[1] if len(counts) > 1 else 0
    if first == 1:
        return second == 1
    if first == 2:
        return second <= 3
    return False


def load_download_dirs() -> list[Path]:
    """Collect download directories from cache and config."""
    dirs: list[Path] = []

    # From download cache
    if CACHE_DOWNLOAD.is_dir():
        for cache_file in CACHE_DOWNLOAD.glob("*.json"):
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                d = data.get("download_dir")
                if d:
                    dirs.append(Path(d))
            except (json.JSONDecodeError, OSError):
                pass

    # From config default
    if CONFIG_FILE.exists():
        try:
            import tomllib

            config = tomllib.loads(CONFIG_FILE.read_text())
            d = config.get("download", {}).get("dir")
            if d:
                dirs.append(Path(d))
        except Exception:
            pass

    # Deduplicate, keep existing dirs
    return [p for p in dict.fromkeys(dirs) if p.is_dir()]


def scan_dir(directory: Path, problem_dir: Path):
    """Scan a directory for audio files and check artist tags."""
    audio_files = [
        f for f in directory.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_EXTS
    ]

    if not audio_files:
        return

    try:
        from mutagen.flac import FLAC
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3
        from mutagen.mp4 import MP4
    except ImportError:
        print("mutagen is required: pip install mutagen", file=sys.stderr)
        sys.exit(1)

    count = 0
    found = 0

    for f in sorted(audio_files):
        count += 1

        # Read artist tag
        artist = None
        try:
            ext = f.suffix.lower()
            if ext == ".flac":
                audio = FLAC(f)
                artist = audio.get("artist", [""])[0]
            elif ext == ".mp3":
                audio = MP3(f, ID3=ID3)
                tag = audio.tags.get("TPE1") if audio.tags else None
                artist = tag.text[0] if tag else None
            elif ext in (".m4a", ".aac"):
                audio = MP4(f)
                artist = audio.get("\xa9ART", [None])[0]
        except Exception:
            artist = None

        # Inline progress
        print(f"\r  [{count}/{len(audio_files)}] {f.name[:60]}", end="", flush=True)

        if not artist or not is_problematic(artist):
            continue

        # Problematic — move files
        found += 1
        problem_dir.mkdir(exist_ok=True)

        # Move audio
        dest = problem_dir / f.name
        if dest.exists():
            dest = problem_dir / f"{f.stem}_{f.stat().st_mtime:.0f}{f.suffix}"
        shutil.move(str(f), str(dest))

        # Move matching lyrics/cover (same stem)
        for ext_set, label in [(LYRICS_EXTS, "lrc"), (COVER_EXTS, "cover")]:
            for ext in ext_set:
                sibling = f.with_suffix(ext)
                if sibling.exists():
                    shutil.move(str(sibling), str(problem_dir / sibling.name))
                    break

    print(f"\r  [{count}/{count}] scanned — {found} problematic", flush=True)


def main():
    dirs = load_download_dirs()
    if not dirs:
        print("No download directories found.", file=sys.stderr)
        sys.exit(1)

    for d in dirs:
        print(f"\nScanning: {d}")
        problem_dir = d / "problematic"
        scan_dir(d, problem_dir)


if __name__ == "__main__":
    main()
