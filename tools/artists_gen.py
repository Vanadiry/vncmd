"""Generate a known artists list from vncmd song cache.

Reads all cached song info.json files, extracts artist names,
and writes one normalized artist per line to a dated txt file.

Usage:
    python3 gen.py              # uses VNCMD_HOME or default ~/.vSoft/vncmd
    VNCMD_HOME=/path python3 gen.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def main():
    vncmd_home = os.environ.get("VNCMD_HOME")
    if vncmd_home:
        cache_root = Path(vncmd_home) / "cache" / "song"
    else:
        cache_root = Path.home() / ".vSoft" / "vncmd" / "cache" / "song"

    if not cache_root.is_dir():
        print(f"Cache directory not found: {cache_root}", file=sys.stderr)
        sys.exit(1)

    artists: set[str] = set()

    for info_path in cache_root.glob("*/info.json"):
        try:
            data = json.loads(info_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        raw = data.get("artist", "")
        if not raw:
            continue

        for name in raw.split(","):
            name = name.strip().lower()
            if name:
                artists.add(name)

    if not artists:
        print("No artists found in cache.", file=sys.stderr)
        sys.exit(1)

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    script_dir = Path(__file__).resolve().parent
    out_path = script_dir / f"known_artists_{date_str}.txt"

    with open(out_path, "w", encoding="utf-8") as f:
        for name in sorted(artists):
            f.write(f"{name}\n")

    print(f"Wrote {len(artists)} artists to {out_path}")


if __name__ == "__main__":
    main()
