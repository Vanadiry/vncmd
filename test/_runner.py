"""Shared test utilities."""
import os
import sys
import tempfile
import shutil

from rich.console import Console
from rich.text import Text

console = Console()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

PLAYLIST_ID = 17647459371
SONG_ID = 22699098
ALBUM_ID = 405493

_passed = 0
_failed = 0


def reset():
    global _passed, _failed
    _passed = 0
    _failed = 0


def check(label, condition, detail=""):
    global _passed, _failed
    ok = condition if isinstance(condition, bool) else bool(condition)
    # Escape [ ] for rich markup
    label = label.replace("[", "\\[").replace("]", "\\]")
    if ok:
        _passed += 1
        suffix = f": {condition}" if not isinstance(condition, bool) else ""
        detail_safe = str(suffix).replace("[", "\\[").replace("]", "\\]")
        console.print(f"  [green]✓[/] {label}[dim]{detail_safe}[/]")
    else:
        _failed += 1
        info = f" → {detail}" if detail else ""
        info_safe = str(info).replace("[", "\\[").replace("]", "\\]")
        console.print(f"  [red]✗[/] {label}[red]{info_safe}[/]")


def section(title):
    console.print()
    console.print(f"[bold cyan]{title}[/]")
    console.print("[dim]" + "─" * 50 + "[/]")


def summary():
    console.print()
    t = Text()
    t.append(f"  Passed: {_passed}  ", style="green")
    t.append(f"Failed: {_failed}  ", style="red" if _failed else "dim")
    t.append(f"Total: {_passed + _failed}")
    console.print(t)
    # Machine-parseable summary for aggregator
    sys.stderr.write(f"__TOTALS__ {_passed} {_failed} {_passed + _failed}\n")
    sys.stderr.flush()
    return _failed


def tmp_dir():
    d = tempfile.mkdtemp(prefix="vnemd_test_")
    return d


def cleanup(path):
    shutil.rmtree(path, ignore_errors=True)
