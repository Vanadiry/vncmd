import io

from PIL import Image as PILImage

from vncmd.media.image import process_cover


def _make_jpeg(size=800):
    buf = io.BytesIO()
    PILImage.new("RGB", (size, size), (128, 64, 200)).save(buf, "JPEG", quality=95)
    return buf.getvalue()


def test_no_compress_same_as_input():
    original = _make_jpeg()
    d0, _ = process_cover(original, "http://test.vanadiry.com/cover.jpg", False)
    assert d0 == original


def test_no_compress_mime_jpeg():
    original = _make_jpeg()
    _, m0 = process_cover(original, "http://test.vanadiry.com/cover.jpg", False)
    assert m0 == "image/jpeg"


def test_compress_mime_jpeg():
    original = _make_jpeg()
    _, m1 = process_cover(original, "http://test.vanadiry.com/cover.jpg", True)
    assert m1 == "image/jpeg"


def test_compress_smaller():
    original = _make_jpeg()
    d1, _ = process_cover(original, "http://test.vanadiry.com/cover.jpg", True)
    assert len(d1) < len(original)


def test_compress_max_dim():
    original = _make_jpeg()
    d1, _ = process_cover(original, "http://test.vanadiry.com/cover.jpg", True)
    img = PILImage.open(io.BytesIO(d1))
    assert max(img.size) <= 500


def test_small_image_not_larger():
    buf = io.BytesIO()
    PILImage.new("RGB", (100, 100), (255, 0, 0)).save(buf, "PNG")
    small = buf.getvalue()
    d_small, _ = process_cover(small, "http://test.vanadiry.com/small.png", True)
    assert len(d_small) <= max(len(small) * 2, 10000)


def test_rgba_to_jpeg():
    buf = io.BytesIO()
    PILImage.new("RGBA", (600, 600), (255, 0, 0, 128)).save(buf, "PNG")
    _, m = process_cover(buf.getvalue(), "http://test.vanadiry.com/cover.png", True)
    assert m == "image/jpeg"


def test_rgba_valid():
    buf = io.BytesIO()
    PILImage.new("RGBA", (600, 600), (255, 0, 0, 128)).save(buf, "PNG")
    d, _ = process_cover(buf.getvalue(), "http://test.vanadiry.com/cover.png", True)
    assert PILImage.open(io.BytesIO(d)) is not None
