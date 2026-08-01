import re
from pathlib import Path

from function.cache import get_song_cache_dir


_TIMESTAMP_RE = re.compile(r"^\[(\d{2}):(\d{2})[:.](\d{2,3})\](.*)")
_META_RE = re.compile(r"^\[(ti|ar|al|offset|length|re|ve):")
_CREDIT_RE_TEMPLATE = r"^\[\d{2}:\d{2}[:.]\d{2,3}\]\s*%s\s*:\s*(.+)$"
_PURE_MUSIC_RE = re.compile(r"纯音乐[，,]请欣赏")


def clean(text: str) -> str:
    """Remove [by:...] tag lines, keep everything else (including empty lines)."""
    return "\n".join(
        line for line in text.splitlines() if not re.match(r"^\[by:", line)
    )


def parse(text: str) -> list[tuple[float, str, str]]:
    """
    Parse cleaned LRC text into list of (time_float, text_content, original_line).
    Lines without timestamps are skipped.
    """
    result = []
    for line in text.splitlines():
        m = _TIMESTAMP_RE.match(line)
        if m:
            mins, secs, ms = int(m.group(1)), int(m.group(2)), m.group(3)
            ms_val = int(ms) if len(ms) == 3 else int(ms) * 10
            t = mins * 60 + secs + ms_val / 1000.0
            result.append((t, m.group(4), line))
    return result


def extract_credits(
    text: str, scan_lines: int = 10, prefixes: list[str] | None = None
) -> tuple[str | None, str]:
    """
    Scan first *scan_lines* for credit role lines. Returns (composer_name, text).
    Only extracts composer; does NOT remove any lines from text.
    """
    if prefixes is None:
        prefixes = ["作曲", "作词", "编曲", "制作人"]

    lines = text.splitlines()
    composer = None
    for i, line in enumerate(lines):
        if i >= scan_lines:
            break
        for role in prefixes:
            role_re = re.compile(_CREDIT_RE_TEMPLATE % re.escape(role))
            m = role_re.match(line)
            if m and role == "作曲":
                composer = m.group(1).strip()
                break
    return composer, text


def trim_lyrics(
    text: str, scan_lines: int = 10, prefixes: list[str] | None = None
) -> tuple[str, bool]:
    """
    Remove credit lines and 纯音乐. Returns (trimmed_text, is_empty).
    *prefixes* controls which credit roles to remove.
    """
    if prefixes is None:
        prefixes = ["作曲", "作词", "编曲", "制作人"]

    lines = text.splitlines()
    kept = []
    for i, line in enumerate(lines):
        if i < scan_lines:
            matched = False
            for role in prefixes:
                role_re = re.compile(_CREDIT_RE_TEMPLATE % re.escape(role))
                if role_re.match(line):
                    matched = True
                    break
            if matched:
                continue
        if _PURE_MUSIC_RE.search(line):
            continue
        kept.append(line)

    trimmed = "\n".join(kept)
    remaining = parse(trimmed)
    is_empty = len(remaining) == 0 and not trimmed.strip()
    return trimmed, is_empty


def has_meaningful_lyrics(text: str) -> bool:
    """Check if text has actual lyric lines (with timestamps)."""
    return len(parse(text)) > 0


def is_pure_credits(text: str, prefixes: list[str] | None = None) -> bool:
    """Check if text consists ONLY of credit lines (no actual lyrics)."""
    if prefixes is None:
        prefixes = ["作曲", "作词", "编曲", "制作人"]
    parsed = parse(text)
    if not parsed:
        return not text.strip()
    roles = set(prefixes)
    for _, content, _ in parsed:
        for role in roles:
            if re.match(rf"^\s*{re.escape(role)}\s*:", content):
                break
        else:
            return False
    return True


def interleave(lrc_text: str, tlyric_text: str, threshold: float = 0.3) -> str:
    """
    Interleave lrc with tlyric: for each lrc line, find a tlyric line within
    threshold seconds. Output lrc on top, tlyric below, both with lrc's timestamp.
    Empty lines pass through unchanged.
    Unmatched lrc lines are kept as-is. Unmatched tlyric lines are appended.
    """
    lrc_lines = parse(lrc_text)
    tlyric_lines = parse(tlyric_text)

    tlyric_by_time = list(enumerate(tlyric_lines))
    used_tlyric = set()

    # Collect meta headers to preserve
    meta_headers = []
    for line in lrc_text.splitlines():
        if _META_RE.match(line):
            meta_headers.append(line)

    out = list(meta_headers)
    for lrc_t, lrc_text_content, lrc_original in lrc_lines:
        mins = int(lrc_t // 60)
        secs = lrc_t % 60
        timestamp = f"[{mins:02d}:{secs:06.3f}]"

        best_idx = None
        for ti, (tlyric_t, tlyric_text_content, _) in tlyric_by_time:
            if ti in used_tlyric:
                continue
            if abs(lrc_t - tlyric_t) <= threshold:
                best_idx = ti
                break

        if best_idx is not None:
            used_tlyric.add(best_idx)
            t_trans = tlyric_lines[best_idx][1]
        else:
            t_trans = ""

        if lrc_text_content == "" and t_trans == "":
            out.append(lrc_original)
            continue

        if t_trans:
            out.append(f"{timestamp}{lrc_text_content}")
            out.append(f"{timestamp}{t_trans}")
        else:
            out.append(lrc_original)

    for ti, (t, text, original) in tlyric_by_time:
        if ti not in used_tlyric:
            out.append(original)

    return "\n".join(out)


def process(lrc_raw: str, tlyric_raw: str, mode: str, song_id: int) -> dict[str, str]:
    """
    Process lyrics according to mode. Caches raw cleaned lyrics.

    Returns dict of {suffix: text} for output_files():
      mode "0": {"lrc": interleaved_text}
      mode "1": {"lrc": lrc_clean + "\n" + tlyric_clean}
      mode "2": {"lrc": lrc_clean, "2.lrc": tlyric_clean}
    """
    lrc_clean = clean(lrc_raw)
    tlyric_clean = clean(tlyric_raw)

    # Cache raw cleaned lyrics
    d = get_song_cache_dir(song_id)
    (d / "lyric.raw.lrc").write_text(lrc_clean, encoding="utf-8")
    (d / "tlyric.raw.lrc").write_text(tlyric_clean, encoding="utf-8")

    if mode == "0":
        return {"lrc": interleave(lrc_clean, tlyric_clean)}
    elif mode == "1":
        return {"lrc": lrc_clean + "\n" + tlyric_clean}
    else:  # "2"
        return {"lrc": lrc_clean, "2.lrc": tlyric_clean}


def output_files(lyrics_result: dict[str, str], base_path: str) -> list[str]:
    """
    Write lyrics files from process() result dict.
    base_path: full path without extension (e.g. /downloads/Title - Artist)
    Returns list of written file paths.
    """
    written = []
    for suffix, text in lyrics_result.items():
        path = f"{base_path}.{suffix}"
        # Resolve duplicate filenames
        counter = 0
        while Path(path).exists():
            counter += 1
            path = f"{base_path}({counter}).{suffix}"
        Path(path).write_text(text, encoding="utf-8")
        written.append(path)
    return written
