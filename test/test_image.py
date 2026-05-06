import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Image processing tests."""
import io
from PIL import Image as PILImage
from test._runner import check, section, summary, reset

reset()

section("Image processing")

from function.image import process_cover

# Create test images
buf = io.BytesIO()
PILImage.new("RGB", (800, 800), (128, 64, 200)).save(buf, "JPEG", quality=95)
original = buf.getvalue()

# Quality 0: as-is
d0, m0 = process_cover(original, "http://x.com/cover.jpg", "0")
check("quality 0 same as input", d0 == original)
check("quality 0 mime jpeg", m0 == "image/jpeg")

# Quality 1: resized + compressed
d1, m1 = process_cover(original, "http://x.com/cover.jpg", "1")
check("quality 1 mime jpeg", m1 == "image/jpeg")
check("quality 1 smaller", len(d1) < len(original), f"{len(d1)} vs {len(original)}")
img1 = PILImage.open(io.BytesIO(d1))
check("quality 1 max dim <= 500", max(img1.size) <= 500, f"size={img1.size}")

# Quality 1 on small image (should not blow up)
buf2 = io.BytesIO()
PILImage.new("RGB", (100, 100), (255, 0, 0)).save(buf2, "PNG")
small_data = buf2.getvalue()
d_small, _ = process_cover(small_data, "http://x.com/small.png", "1")
check("small image not larger", len(d_small) <= max(len(small_data) * 2, 10000),
      f"{len(d_small)} vs {len(small_data)}")

# Quality 1 on RGBA PNG
buf3 = io.BytesIO()
PILImage.new("RGBA", (600, 600), (255, 0, 0, 128)).save(buf3, "PNG")
d_rgba, m_rgba = process_cover(buf3.getvalue(), "http://x.com/cover.png", "1")
check("RGBA → JPEG", m_rgba == "image/jpeg")
check("RGBA valid", PILImage.open(io.BytesIO(d_rgba)) is not None)

failed = summary()
if __name__ == "__main__":
    raise SystemExit(failed)
