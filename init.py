#!/usr/bin/env python3
"""Environment check for vNetEaseMusicDownloader.

Run this first:  python init.py
"""

import os
import sys

REQUIRED_FILES = [
    "vnemd.py",
    "requirements.txt",
]

REQUIRED_DIRS = [
    "config",
    "function",
]

REQUIRED_CONFIG_FILES = [
    "config.toml",
]


def _green(s):
    return f"\033[32m{s}\033[0m"


def _red(s):
    return f"\033[31m{s}\033[0m"


def _yellow(s):
    return f"\033[33m{s}\033[0m"


def _bold(s):
    return f"\033[1m{s}\033[0m"


def check_python():
    version = sys.version_info
    if version < (3, 11):
        print(
            _red("✗")
            + f" Python {version.major}.{version.minor}.{version.micro} "
            + "is too old (3.11+ required)"
        )
        print("  Install Python 3.11 or newer: " + "https://www.python.org/downloads/")
        return False
    print(_green("✓") + f" Python {version.major}.{version.minor}.{version.micro}")
    return True


def check_cwd():
    cwd = os.getcwd()
    all_ok = True

    for f in REQUIRED_FILES:
        path = os.path.join(cwd, f)
        if not os.path.isfile(path):
            print(_red("✗") + f" Missing file: {f}")
            all_ok = False

    for d in REQUIRED_DIRS:
        path = os.path.join(cwd, d)
        if not os.path.isdir(path):
            print(_red("✗") + f" Missing directory: {d}/")
            all_ok = False

    if not all_ok:
        print()
        print(
            _yellow("!")
            + " You are not in the project root, or the project is incomplete."
        )
        print(f"  Current directory: {cwd}")
        print("  cd to the vNetEaseMusicDownloader directory and try again.")
        print("  If files are missing, clone again.")
        return False

    print(_green("✓") + f" Project root: {cwd}")
    return True


def check_config():
    cwd = os.getcwd()
    config_dir = os.path.join(cwd, "config")
    all_ok = True

    if not os.path.isdir(config_dir):
        print(_red("✗") + " config/ directory is missing")
        print(
            "  The config/ folder is not tracked in git by default.\n"
            "  Copy it from your backup, or clone the repo and follow\n"
            "  the setup guide to recreate config/config.toml."
        )
        return False

    for f in REQUIRED_CONFIG_FILES:
        path = os.path.join(config_dir, f)
        if not os.path.isfile(path):
            print(_red("✗") + f" config/{f} is missing")
            all_ok = False

    if not all_ok:
        print()
        print(_yellow("!") + " Config files are missing inside config/.")
        print(
            "  Either restore them from a backup, or get them from the\n"
            "  project repository and place them in the config/ folder."
        )
        return False

    print(_green("✓") + " config/ is present and configured")
    return True


def main():
    print()
    print(_bold("vNetEaseMusicDownloader — environment check"))
    print()

    ok = True
    ok &= check_python()
    print()
    ok &= check_cwd()
    print()
    ok &= check_config()
    print()

    if ok:
        print(_green(_bold("All checks passed. You can now run:")))
        print("  python vnemd.py --help")
        return 0
    else:
        print(_red(_bold("Some checks failed. Fix the issues above and re-run:")))
        print("  python init.py")
        return 1


if __name__ == "__main__":
    sys.exit(main())
