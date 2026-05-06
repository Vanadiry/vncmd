import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""CLI command tests."""
import sys
import subprocess
from test._runner import (
    check,
    section,
    summary,
    reset,
    SONG_ID,
    PLAYLIST_ID,
    ALBUM_ID,
    PROJECT_ROOT,
)

reset()

section("CLI commands")


def run(args, timeout=30):
    return subprocess.run(
        [sys.executable, "vnemd.py"] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=PROJECT_ROOT,
    )


r = run([])
check("no args shows usage", "usage:" in (r.stdout + r.stderr).lower())

r = run(["search", "Beyond", "--limit", "3"])
check("search", r.returncode == 0 and "Beyond" in r.stdout)

r = run(["song", str(SONG_ID)])
check("song preview", r.returncode == 0)

r = run(["song", str(SONG_ID), "--lyrics"])
check("song --lyrics", r.returncode == 0)

r = run(["song", str(SONG_ID), "--url", "-q", "128"])
check("song --url -q 128", r.returncode == 0)

r = run(["playlist", str(PLAYLIST_ID), "--limit", "3"])
check("playlist preview", r.returncode == 0)

r = run(["album", str(ALBUM_ID), "--limit", "3"])
check("album preview", r.returncode == 0)

r = run(
    ["playlist", str(PLAYLIST_ID), "-d", "--limit", "1", "-o", "/tmp/vnemd_cli_test"],
    timeout=120,
)
check("playlist -d", r.returncode == 0)

r = run(
    ["album", str(ALBUM_ID), "-d", "--limit", "1", "-o", "/tmp/vnemd_cli_test"],
    timeout=120,
)
check("album -d", r.returncode == 0)

failed = summary()
if __name__ == "__main__":
    raise SystemExit(failed)
