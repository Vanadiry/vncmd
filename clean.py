"""Clear cache and download directories — keeps folders, removes contents."""
import os
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
DIRS = ["cache", "downloads"]


def clear_dir(path):
    if not os.path.isdir(path):
        return
    for entry in os.listdir(path):
        full = os.path.join(path, entry)
        if os.path.isdir(full):
            shutil.rmtree(full)
        else:
            os.remove(full)


if __name__ == "__main__":
    for d in DIRS:
        target = os.path.join(ROOT, d)
        clear_dir(target)
        print(f"Cleared: {target}")
