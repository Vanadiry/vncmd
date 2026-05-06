import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Lyrics processing tests."""
import os
from test._runner import check, section, summary, reset

reset()
TMP = __import__("test._runner", fromlist=["tmp_dir"]).tmp_dir()

section("Lyrics processing")

from function.lyrics import clean, parse, interleave, process, output_files

LRC = """[by:Someone]
[00:00.000] 作词 : 测试
[00:05.100] Hello World
[00:10.200] Goodbye
[00:15.300]"""
TLYRIC = """[by:Tester]
[00:05.100] Nihao World
[00:10.200] Zaijian
[00:15.300]"""

# Clean
cl = clean(LRC)
ct = clean(TLYRIC)
check("clean removes [by:]", "[by:" not in ct)
check("clean keeps [00:00.000]", "[00:00.000]" in cl)

# Parse
p = parse(cl)
check("parse count", len(p) == 4)
check("parse first time 0.0", p[0][0] == 0.0)
check("parse second time 5.1", abs(p[1][0] - 5.1) < 0.001)
check("parse empty line kept", p[3][1] == "")

# Interleave
iv = interleave(cl, ct)
check("has original", "Hello World" in iv)
check("has translation", "Nihao World" in iv)
check("empty line preserved", "[00:15.300]" in iv)
check("metadata kept", "作词" in iv)
for i, line in enumerate(iv.splitlines()):
    if "Hello World" in line:
        check("ordering orig→tlyric", i + 1 < len(iv.splitlines()) and
              "Nihao World" in iv.splitlines()[i + 1])
        break

# Mode 0: interleaved → single .lrc
r0 = process(LRC, TLYRIC, "0", 99999999)
check("mode 0 single file", "lrc" in r0 and len(r0) == 1)

# Mode 1: merged → single .lrc
r1 = process(LRC, TLYRIC, "1", 99999999)
check("mode 1 merged single file", "lrc" in r1 and len(r1) == 1)

# Mode 2: separate → .lrc + .2.lrc
r2 = process(LRC, TLYRIC, "2", 99999999)
check("mode 2 separate two files", len(r2) == 2 and "lrc" in r2 and "2.lrc" in r2)

# output_files
paths = output_files({"lrc": "test content"}, os.path.join(TMP, "lyric_test"))
check("creates file", os.path.exists(paths[0]))
with open(paths[0]) as f:
    check("content correct", f.read() == "test content")

__import__("shutil").rmtree(TMP, ignore_errors=True)

failed = summary()
if __name__ == "__main__":
    raise SystemExit(failed)
