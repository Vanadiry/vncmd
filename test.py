"""Run all vnemd tests."""

import re
import subprocess
import sys
import os

from rich.console import Console
from rich.text import Text

console = Console()

TESTS = [
    "test_config",
    "test_cache",
    "test_api",
    "test_audio",
    "test_image",
    "test_lyrics",
    "test_metadata",
    "test_download",
    "test_cli",
    "test_errors",
]

HERE = os.path.dirname(os.path.abspath(__file__))
files_ok = 0
files_fail = 0
total_passed = 0
total_failed = 0

for name in TESTS:
    print(f"\n{'=' * 60}")
    print(f"  {name}")
    print(f"{'=' * 60}")
    env = os.environ.copy()
    env["FORCE_COLOR"] = "1"
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "test", f"{name}.py")],
        capture_output=True,
        text=True,
        cwd=HERE,
        env=env,
    )
    sys.stdout.write(r.stdout)
    if r.stderr:
        # Parse totals from machine-readable stderr
        for line in r.stderr.splitlines():
            m = re.match(r"__TOTALS__ (\d+) (\d+) (\d+)", line)
            if m:
                total_passed += int(m.group(1))
                total_failed += int(m.group(2))
            else:
                sys.stderr.write(line + "\n")

    if r.returncode == 0:
        files_ok += 1
    else:
        files_fail += 1

console.print()
console.print("=" * 60, style="bold")
t = Text()
t.append("  Total: ", style="bold")
t.append(f"{total_passed} passed", style="green")
t.append("  ", style="dim")
t.append(f"{total_failed} failed", style="red" if total_failed else "dim")
t.append(f"  ({len(TESTS)} files, {total_passed + total_failed} tests)", style="dim")
console.print(t)
console.print("=" * 60, style="bold")
sys.exit(1 if files_fail else 0)
