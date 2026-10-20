"""从曲目缓存生成艺人列表

用法：python3 tools/artists_gen.py
"""

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


def main():
    vncmd_home = os.environ.get("VNCMD_HOME")
    if vncmd_home:
        cache_root = Path(vncmd_home) / "cache" / "song"
    else:
        cache_root = Path.home() / ".vSoft" / "vncmd" / "cache" / "song"

    if not cache_root.is_dir():
        print(f"未找到缓存目录：{cache_root}", file=sys.stderr)
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
        print("缓存中没有艺人", file=sys.stderr)
        sys.exit(1)

    date_str = datetime.now(UTC).strftime("%Y%m%d")
    script_dir = Path(__file__).resolve().parent
    out_path = script_dir / f"known_artists_{date_str}.txt"

    with open(out_path, "w", encoding="utf-8") as f:
        for name in sorted(artists):
            f.write(f"{name}\n")

    print(f"已写入 {len(artists)} 个艺人：{out_path}")


if __name__ == "__main__":
    main()
