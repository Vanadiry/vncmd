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

section("CLI — tracker")

# Create a test tracker via CLI (pipe 'y' to stdin, non-TTY fallback path)
r = subprocess.run(
    [sys.executable, "vnemd.py", "tracker", "_test_cli_tracker"],
    capture_output=True,
    text=True,
    timeout=10,
    cwd=PROJECT_ROOT,
    input="y\n",
)
check("tracker create (new)", r.returncode == 0)
check("tracker created message", "created" in r.stdout.lower())

# Show existing tracker
r = run(["tracker", "_test_cli_tracker"])
check("tracker show", r.returncode == 0)

# Write a source file so fetch-auto has something to do
import shutil

_td = os.path.join(PROJECT_ROOT, "tracker", "_test_cli_tracker")
with open(os.path.join(_td, "settings.toml"), "w") as f:
    f.write(f"""[tracker]
description = "CLI test"

[[sources]]
type = "song"
ids = [{SONG_ID}]

[[sources]]
type = "playlist"
ids = []

[[sources]]
type = "album"
ids = []
""")

r = run(["tracker", "_test_cli_tracker", "--fetch-auto"], timeout=60)
check("tracker --fetch-auto", r.returncode == 0)

r = run(["tracker", "_test_cli_tracker"])
check("tracker show after fetch", "Cached songs: 1" in r.stdout)

# Cleanup
shutil.rmtree(_td, ignore_errors=True)

failed = summary()
if __name__ == "__main__":
    raise SystemExit(failed)
