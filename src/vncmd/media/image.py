import io

from PIL import Image

_MIME_MAP = [
    (b"\xff\xd8\xff", "jpg", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
    (b"GIF87a", "gif", "image/gif"),
    (b"GIF89a", "gif", "image/gif"),
]
_HEAD_BYTES = max(len(sig) for sig, _, _ in _MIME_MAP)


def detect_format(data: bytes) -> tuple[str, str] | None:
    """按魔数判断图片格式，返回扩展名与 MIME"""
    head = data[:_HEAD_BYTES]
    for sig, ext, mime in _MIME_MAP:
        if head.startswith(sig):
            return ext, mime
    return None


def _mime_from_url(url: str | None) -> str:
    ext = (url or "").rsplit("?", 1)[0].rsplit(".", 1)[-1].lower()
    return "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"


def process_cover(
    cover_data: bytes, cover_url: str | None, compress: bool
) -> tuple[bytes, str]:
    """处理封面，返回数据与 MIME

    compress 为真时缩放到 500 并压成 JPEG
    """
    if not compress:
        fmt = detect_format(cover_data)
        if fmt:
            return cover_data, fmt[1]
        return cover_data, _mime_from_url(cover_url)

    # 缩放并压缩
    img = Image.open(io.BytesIO(cover_data))
    original_size = len(cover_data)
    w, h = img.size

    # 超过 500 像素时等比缩放
    if w > 500 or h > 500:
        scale = 500 / max(w, h)
        w, h = int(w * scale), int(h * scale)
        img = img.resize((w, h), Image.LANCZOS)

    # JPEG 需要 RGB
    if img.mode in ("RGBA", "P", "LA"):
        # P 与 LA 都要先转 RGBA，否则 alpha 通道被丢掉
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    best = None
    for q in (85, 75, 65, 60):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=q, optimize=True)
        data = buf.getvalue()
        if len(data) < original_size:
            best = data
            break

    # 四档都压不小就保留原图
    if best is None:
        fmt = detect_format(cover_data)
        return cover_data, fmt[1] if fmt else _mime_from_url(cover_url)
    return best, "image/jpeg"
