import io
from PIL import Image as PILImage
from function.image import process_cover


def _make_jpeg(size=800):
    buf = io.BytesIO()
    PILImage.new("RGB", (size, size), (128, 64, 200)).save(buf, "JPEG", quality=95)
    return buf.getvalue()


def test_quality_0_same_as_input():
    original = _make_jpeg()
    d0, _ = process_cover(original, "http://x.com/cover.jpg", "0")
    assert d0 == original


def test_quality_0_mime_jpeg():
    original = _make_jpeg()
    _, m0 = process_cover(original, "http://x.com/cover.jpg", "0")
    assert m0 == "image/jpeg"


def test_quality_1_mime_jpeg():
    original = _make_jpeg()
    _, m1 = process_cover(original, "http://x.com/cover.jpg", "1")
    assert m1 == "image/jpeg"


def test_quality_1_smaller():
    original = _make_jpeg()
    d1, _ = process_cover(original, "http://x.com/cover.jpg", "1")
    assert len(d1) < len(original)


def test_quality_1_max_dim():
    original = _make_jpeg()
    d1, _ = process_cover(original, "http://x.com/cover.jpg", "1")
    img = PILImage.open(io.BytesIO(d1))
    assert max(img.size) <= 500


def test_small_image_not_larger():
    buf = io.BytesIO()
    PILImage.new("RGB", (100, 100), (255, 0, 0)).save(buf, "PNG")
    small = buf.getvalue()
    d_small, _ = process_cover(small, "http://x.com/small.png", "1")
    assert len(d_small) <= max(len(small) * 2, 10000)


def test_rgba_to_jpeg():
    buf = io.BytesIO()
    PILImage.new("RGBA", (600, 600), (255, 0, 0, 128)).save(buf, "PNG")
    _, m = process_cover(buf.getvalue(), "http://x.com/cover.png", "1")
    assert m == "image/jpeg"


def test_rgba_valid():
    buf = io.BytesIO()
    PILImage.new("RGBA", (600, 600), (255, 0, 0, 128)).save(buf, "PNG")
    d, _ = process_cover(buf.getvalue(), "http://x.com/cover.png", "1")
    assert PILImage.open(io.BytesIO(d)) is not None
