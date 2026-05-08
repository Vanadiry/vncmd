import re
import os

from function.cache import get_song_cache_dir


_TIMESTAMP_RE = re.compile(r"^\[(\d{2}):(\d{2})\.(\d{2,3})\](.*)")


def clean(text):
    """Remove [by:...] tag lines, keep everything else (including empty lines)."""
    return "\n".join(
        line for line in text.splitlines() if not re.match(r"^\[by:", line)
    )


def parse(text):
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


def interleave(lrc_text, tlyric_text, threshold=0.3):
    """
    Interleave lrc with tlyric: for each lrc line, find a tlyric line within
    threshold seconds. Output lrc on top, tlyric below, both with lrc's timestamp.
    Empty lines pass through unchanged.
    Unmatched lrc lines are kept as-is. Unmatched tlyric lines are appended.
    """
    lrc_lines = parse(lrc_text)
    tlyric_lines = parse(tlyric_text)

    # Index tlyric by index (for removal) and by nearby time
    tlyric_by_time = list(enumerate(tlyric_lines))
    used_tlyric = set()

    out = []
    for lrc_t, lrc_text_content, lrc_original in lrc_lines:
        # Rebuild timestamp
        mins = int(lrc_t // 60)
        secs = lrc_t % 60
        timestamp = f"[{mins:02d}:{secs:06.3f}]"

        # Find best matching tlyric within threshold
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

    # Append unmatched tlyric
    for ti, (t, text, original) in tlyric_by_time:
        if ti not in used_tlyric:
            out.append(original)

    return "\n".join(out)


def process(lrc_raw, tlyric_raw, mode, song_id):
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
    with open(os.path.join(d, "lyric.raw.lrc"), "w", encoding="utf-8") as f:
        f.write(lrc_clean)
    with open(os.path.join(d, "tlyric.raw.lrc"), "w", encoding="utf-8") as f:
        f.write(tlyric_clean)

    if mode == "0":
        return {"lrc": interleave(lrc_clean, tlyric_clean)}
    elif mode == "1":
        return {"lrc": lrc_clean + "\n" + tlyric_clean}
    else:  # "2"
        return {"lrc": lrc_clean, "2.lrc": tlyric_clean}


def output_files(lyrics_result, base_path):
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
        while os.path.exists(path):
            counter += 1
            path = f"{base_path}({counter}).{suffix}"
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        written.append(path)
    return written
