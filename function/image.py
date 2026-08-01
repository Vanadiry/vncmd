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
    """Detect image format from magic bytes. Returns (ext, mime) or None."""
    head = data[:_HEAD_BYTES]
    for sig, ext, mime in _MIME_MAP:
        if head.startswith(sig):
            return ext, mime
    return None


def _mime_from_url(url: str | None) -> str:
    ext = (url or "").rsplit("?", 1)[0].rsplit(".", 1)[-1].lower()
    return "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"


def process_cover(
    cover_data: bytes, cover_url: str | None, quality: str
) -> tuple[bytes, str]:
    """
    Process cover image.

    quality "0": return as-is.
    quality "1": resize to max 500x500, convert to JPEG, compress smaller than
                 original without being too blurry.

    Returns (data: bytes, mime_type: str)
    """
    if quality == "0":
        fmt = detect_format(cover_data)
        if fmt:
            return cover_data, fmt[1]
        return cover_data, _mime_from_url(cover_url)

    # quality "1": resize + compress
    img = Image.open(io.BytesIO(cover_data))
    original_size = len(cover_data)
    w, h = img.size

    # Resize if any dimension exceeds 500
    if w > 500 or h > 500:
        scale = 500 / max(w, h)
        w, h = int(w * scale), int(h * scale)
        img = img.resize((w, h), Image.LANCZOS)

    # Convert to RGB (required for JPEG)
    if img.mode in ("RGBA", "P", "LA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Try qualities from 85 down to 60, stop when smaller than original
    for q in (85, 75, 65, 60):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=q, optimize=True)
        result = buf.getvalue()
        if len(result) < original_size or q == 60:
            break

    return result, "image/jpeg"
