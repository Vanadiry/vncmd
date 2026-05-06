import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Audio utilities tests."""
import os
from test._runner import check, section, summary, reset

reset()
TMP = __import__("test._runner", fromlist=["tmp_dir"]).tmp_dir()

section("Audio utilities")

from function.audio import (
    check_filename,
    get_type_from_url,
    cover_ext,
    build_filename,
    resolve_path,
)

# check_filename
check("normal unchanged", check_filename("Hello World") == "Hello World")
for ch in ("/", ":", "*", "?", '"', "<", ">", "|", "\\"):
    check(f"strip '{ch}'", ch not in check_filename(f"a{ch}b"))

# get_type_from_url
check("flac", get_type_from_url("http://x.com/t.flac?p=1") == "flac")
check("mp3", get_type_from_url("http://x.com/t.mp3") == "mp3")
check("default", get_type_from_url("http://x.com/t.xyz") == "mp3")

# cover_ext
check("jpg", cover_ext("http://x.com/img.jpg") == "jpg")
check("jpeg", cover_ext("http://x.com/img.jpeg") == "jpeg")
check("png", cover_ext("http://x.com/img.png?x=1") == "png")
check("default", cover_ext(None) == "jpg")

# build_filename
name = build_filename("Test/Title", "Artist:Name")
check("no illegal chars", "/" not in name and ":" not in name)
check("non-empty", len(name) > 0)

# resolve_path
p = resolve_path("__unique_test__", "tmp", TMP)
check("absolute", os.path.isabs(p))
check("ends with ext", p.endswith("__unique_test__.tmp"))
open(p, "w").close()
p2 = resolve_path("__unique_test__", "tmp", TMP)
check("dedup different", p2 != p)
os.remove(p)

__import__("shutil").rmtree(TMP, ignore_errors=True)

failed = summary()
if __name__ == "__main__":
    raise SystemExit(failed)
