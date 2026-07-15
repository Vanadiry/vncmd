import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

TO_CLEAN = [
    ".pytest_cache",
    "cache",
    "downloads",
    "tracker",
    ".coverage",
    "htmlcov",
    ".ruff_cache",
    "dist",
]

TO_CLEAN_RECURSIVE = [
    "__pycache__",
]

for name in TO_CLEAN:
    path = PROJECT_ROOT / name
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        print(f"Removed dir:  {name}")
    elif path.is_file():
        path.unlink()
        print(f"Removed file: {name}")
    else:
        print(f"Skipped:      {name} (not found)")

for name in TO_CLEAN_RECURSIVE:
    count = 0
    for d in PROJECT_ROOT.rglob(name):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            count += 1
    if count:
        print(f"Removed:      {count} {name} dir(s)")
