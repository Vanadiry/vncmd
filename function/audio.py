import re
from pathlib import Path

from function.config import get_filename_format

# Linux 的 ext4 单个文件名上限为 255 字节，macOS 的 APFS 为 255 字符，
# 按字节收敛最保险；Windows 的完整路径上限 260 字符还要扣掉目录与扩展名
_MAX_FILENAME_BYTES = 180

_MAX_PATH_CHARS = 250


def _truncate_bytes(s: str, limit: int) -> str:
    b = s.encode("utf-8")
    if len(b) <= limit:
        return s
    return b[:limit].decode("utf-8", errors="ignore")


def check_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]', " ", name)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def get_type_from_url(url: str) -> str:
    pattern = r"((?!.*\.))([^?]+)"
    matches = re.search(pattern, url)
    if matches:
        ext = matches.group(0)
        if ext in ("mp3", "flac", "m4a", "wav", "ogg"):
            return ext
    return "mp3"


def cover_ext(cover_url: str | None) -> str:
    if not cover_url:
        return "jpg"
    ext = cover_url.rsplit("?", 1)[0].rsplit(".", 1)[-1].lower()
    return ext if ext in ("jpg", "jpeg", "png") else "jpg"


def build_filename(title: str, artist: str) -> tuple[str, str | None]:
    """返回 (收敛后的文件名, 截断前的完整名字)

    完整名字仅在发生截断时返回，调用方据此写一份同名 txt
    """
    fmt = get_filename_format()
    safe_title = check_filename(title)
    safe_artist = check_filename(artist)
    if fmt == "10":
        name = f"{safe_title} - {safe_artist}"
    elif fmt == "01":
        name = f"{safe_artist} - {safe_title}"
    else:
        name = safe_title
    # 在拼接结果上截断而不是分别截断标题与歌手，分开截断会把歌手整段挤掉
    fitted = _truncate_bytes(name, _MAX_FILENAME_BYTES)
    return fitted, None if fitted == name else name


def resolve_path(base: str, ext: str, directory: str) -> str:
    # 目录越深，留给文件名的余量越少
    budget = _MAX_PATH_CHARS - len(directory) - len(ext) - 8
    base = _truncate_bytes(base, min(_MAX_FILENAME_BYTES, max(budget, 40)))
    counter = 0
    while True:
        suffix = f"({counter})" if counter > 0 else ""
        path = Path(directory) / f"{base}{suffix}.{ext}"
        if not path.exists():
            return str(path)
        counter += 1
