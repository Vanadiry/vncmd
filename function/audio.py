import re
from pathlib import Path

from function.config import get_filename_format


def check_filename(name):
    return re.sub(r'[\\/:*?"<>|]', "-", name)


def get_type_from_url(url):
    pattern = r"((?!.*\.))([^?]+)"
    matches = re.search(pattern, url)
    if matches:
        ext = matches.group(0)
        if ext in ("mp3", "flac", "m4a", "wav", "ogg"):
            return ext
    return "mp3"


def cover_ext(cover_url):
    if not cover_url:
        return "jpg"
    ext = cover_url.rsplit("?", 1)[0].rsplit(".", 1)[-1].lower()
    return ext if ext in ("jpg", "jpeg", "png") else "jpg"


def build_filename(title, artist):
    fmt = get_filename_format()
    safe_title = check_filename(title)
    safe_artist = check_filename(artist)
    if fmt == "10":
        return f"{safe_title} - {safe_artist}"
    elif fmt == "01":
        return f"{safe_artist} - {safe_title}"
    else:
        return safe_title


def resolve_path(base, ext, directory):
    counter = 0
    while True:
        suffix = f"({counter})" if counter > 0 else ""
        path = Path(directory) / f"{base}{suffix}.{ext}"
        if not path.exists():
            return str(path)
        counter += 1
