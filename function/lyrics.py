import re
from pathlib import Path

from function.cache import put_raw_lyrics

_TIMESTAMP_RE = re.compile(r"^\[(\d{2}):(\d{2})[:.](\d{2,3})\](.*)")
_META_RE = re.compile(r"^\[(ti|ar|al|offset|length|re|ve):")
# 纯音乐。整行去掉时间戳之后正好是这一句才算，早先用「含即删」，
# 正文里出现这六个字也会被删 —— 连 credit 行都会被吃掉：
# `作曲：他说纯音乐，请欣赏` 整行没了而作曲人也没进 tag
_PURE_MUSIC_RE = re.compile(r"^纯音乐[，,]请欣赏$")
# 值为「无」的行没有内容可写，写进 tag 是脏数据。
# 繁体「無」同理 —— 只认简体的话，繁体歌词会把「無」原样写进 lyricist
_NO_VALUES = frozenset({"无", "無"})
# 歌词翻译与歌词无关而 mp3 与 flac 都没有对应字段，只能丢。带冒号才认，
# 否则正文里出现「歌词翻译」三个字的普通歌词会被误删
_TRANSLATION_RE = re.compile(
    r"^\[\d{2}:\d{2}[:.]\d{2,3}\]\s*(?:歌词翻译|歌詞翻譯)\s*[:：]"
)
# 冒号要同时认半角与全角：中文歌词里「作词：XX」比「作词:XX」常见得多，
# 只认半角会让这些行被当成普通歌词，裁不掉也搬不走
_CREDIT_LINE_RE = re.compile(
    r"^\[\d{2}:\d{2}[:.]\d{2,3}\]\s*(?P<role>[^:：\[\]]{1,20}?)\s*[:：]\s*(?P<value>.+)$"
)

# 内部名 → (mp3 写法, flac 键, 歌词里会怎么写)。
# 简体与繁体共用同一个 tag 键，所以只列一次键名
# 母带不进表，mp3 与 flac 都没有标准字段，不硬塞
# 乐器不进表，上游写的是具体乐器名而不是「乐器」这个角色
# 演唱不进表，库里三行的值与文件已有的 artist 全部不一致
CREDIT_ROLES = {
    "作曲": ("TCOM", "composer", ("作曲",)),
    "作词": ("TEXT", "lyricist", ("作词", "作詞")),
    "编曲": ("TIPL:arranger", "arranger", ("编曲", "編曲")),
    "制作人": ("TIPL:producer", "producer", ("制作人", "製作人", "Producer")),
    "混音": ("TIPL:mix", "mixer", ("混音", "Mixer")),
    "录音": ("TIPL:engineer", "engineer", ("录音", "錄音")),
    "指挥": ("TPE3", "conductor", ("指挥", "指揮")),
}

# 歌词里的写法 → 内部名。匹配时是拿歌词那一行的角色名去查，所以要倒排。
# 繁体必须一起认，否则繁体歌词的 credit 行会被当成歌词。
# 「作曲」的繁体与简体同形，「作词」的繁体是「作詞」，两者不撞车
ROLE_ALIASES = {
    written: role
    for role, (_mp3, _flac, writings) in CREDIT_ROLES.items()
    for written in writings
}

# 连写角色名 → (要记的角色, 保留后剩下的角色名)。
# 剩下的为 None 表示整行删掉。
# 库里只有这七种，逐个写死。库里的六种含表内角色的连写里，
# 「配唱制作人」与「人声录音」不在这张表里 —— 前者的「制作人」匹配不上整名，
# 后者整体是「录人声的那个录音师」而不是「人声」加「录音」两件事
CREDIT_COMBOS = {
    "作/編曲": (("作曲", "编曲"), None),
    "作/编曲": (("作曲", "编曲"), None),
    "作編曲": (("作曲", "编曲"), None),
    "作编曲": (("作曲", "编曲"), None),
    "作曲/编曲": (("作曲", "编曲"), None),
    "作曲/編曲": (("作曲", "编曲"), None),
    "混音/母带": (("混音",), "母带"),
}


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


def _is_pure_music_placeholder(line: str) -> bool:
    """去掉时间戳之后整行正好是那句占位符

    与 credit 行判定的口径一致 —— 都要求这一行就是它自己，
    不靠「含」来判断，免得正文里提到这六个字时被当成占位删掉
    """
    m = _TIMESTAMP_RE.match(line)
    content = m.group(4) if m else line
    return bool(_PURE_MUSIC_RE.match(content.strip()))


def process_credits(
    text: str, scan_lines: int = 10, collect: bool = False, trim: bool = False
) -> tuple[dict[str, str], str]:
    """
    扫歌词头部，把角色行搬进 credits，并按开关决定删不删那些行。

    *collect* 为真时把值收进 credits，为假时一个角色都不收。
    *trim* 为真时删掉三类占位与所有已处理的角色行，为假时一行不动。

    值原样保留不拆 —— 上游用到的分隔符在播放器里本来就拆得开，
    拆成多值反而只剩第一个。

    同一角色在头部出现多行时后一个覆盖前一个。库里这样写的五个文件全是
    同一个人写了两遍，其中「カワイヒデヒロ(fox capture plan)」那行更详细，
    所以覆盖不丢东西。
    """
    credits: dict[str, str] = {}
    kept: list[str] = []
    for i, line in enumerate(text.splitlines()):
        head = i < scan_lines
        m = _CREDIT_LINE_RE.match(line)
        role = m.group("role") if m else None
        value = m.group("value") if m else None

        # 前两类是独立占位，与角色行无关，所以放在角色判定之前
        if head and (_is_pure_music_placeholder(line) or _TRANSLATION_RE.match(line)):
            if trim:
                continue
        elif head and role in CREDIT_COMBOS:
            roles, leftover = CREDIT_COMBOS[role]
            # 角色名改写与删行都只在角色真被搬走时才做。
            # 没搬走就改掉「混音/」或者整行删掉，删掉的部分没进任何地方，是白丢
            if collect:
                if value.strip() not in _NO_VALUES:
                    for r in roles:
                        credits[r] = value
                if trim:
                    if leftover is None:
                        continue
                    line = line[: m.start("role")] + leftover + line[m.end("role") :]
        elif head and collect and role in ROLE_ALIASES:
            # 与连写同理：没搬走就裁掉，这一行就是白丢。
            # 只开 auto_trim 不开 parse_credits 时角色行要留着 ——
            # 改动前那一格走的是空 prefixes，同样不裁角色行
            #
            # 值为「无」不写进 tag，行照删。判定放在角色匹配之后，
            # 早先用裸正则 search，前 N 行里任何以「：无」收尾的行都会被删，
            # 连歌词都被吃掉
            if value.strip() not in _NO_VALUES:
                credits[ROLE_ALIASES[role]] = value
            if trim:
                continue

        kept.append(line)

    return credits, "\n".join(kept)


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
        for ti, (tlyric_t, _text, _) in tlyric_by_time:
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

    for ti, (_, _, original) in tlyric_by_time:
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
    put_raw_lyrics(song_id, lrc_clean, tlyric_clean)

    if mode == "0":
        return {"lrc": interleave(lrc_clean, tlyric_clean)}
    if mode == "1":
        return {"lrc": lrc_clean + "\n" + tlyric_clean}
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
