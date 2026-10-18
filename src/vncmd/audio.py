import re
from pathlib import Path

from vncmd.config import get_filename_artist
from vncmd.output import warning

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


# 网易云实际只返回 mp3 与 flac，白名单里的 m4a、wav、ogg 走不到，
# 留着只会让它们静默跳过元数据嵌入。遇到没见过的格式要出声，
# 上游改了编码格式时能立刻看到，而不是产出一个错扩展名的文件
_METADATA_TYPES = ("mp3", "flac")


def get_type_from_url(url: str) -> str:
    ext = url.rsplit("?", 1)[0].rsplit(".", 1)[-1].lower()
    if ext in _METADATA_TYPES:
        return ext
    # 没有扩展名的 URL 会把末段整串当成扩展名，长度与字符集都对不上时仍归 mp3
    if ext.isalnum() and len(ext) <= 5:
        warning(f"未预期的音频格式 .{ext}，该格式暂不支持元数据嵌入")
        return ext
    return "mp3"


def looks_like_audio(head: bytes) -> bool:
    """判断内容是否为音频，用于挡下服务器以 200 返回的错误页"""
    if not head:
        return False
    if head.startswith((b"ID3", b"RIFF", b"OggS", b"fLaC")):
        return True
    # MP4 容器前 4 字节是 box 长度，ftyp 标记在偏移 4
    if head[4:8] == b"ftyp":
        return True
    # 没有 ID3 标签的 MP3 以帧同步开头
    return head[0] == 0xFF and len(head) > 1 and head[1] & 0xE0 == 0xE0


def cover_ext(cover_url: str | None) -> str:
    if not cover_url:
        return "jpg"
    ext = cover_url.rsplit("?", 1)[0].rsplit(".", 1)[-1].lower()
    return ext if ext in ("jpg", "jpeg", "png") else "jpg"


def build_filename(title: str, artist: str) -> tuple[str, str | None]:
    """返回 (收敛后的文件名, 截断前的完整名字)

    完整名字仅在发生截断时返回，调用方据此写一份同名 txt
    """
    fmt = get_filename_artist()
    safe_title = check_filename(title)
    safe_artist = check_filename(artist)
    # 艺术家为空时一律只留标题，拼接会多出一个待分隔的连字符
    if fmt == "front" and safe_artist:
        name = f"{safe_artist} - {safe_title}"
    elif fmt == "back" and safe_artist:
        name = f"{safe_title} - {safe_artist}"
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
