import re
from pathlib import Path

from vncmd.net.cache import put_raw_lyrics

_TIMESTAMP_RE = re.compile(r"^\[(\d{2}):(\d{2})[:.](\d{2,3})\](.*)")
_META_RE = re.compile(r"^\[(ti|ar|al|offset|length|re|ve):")
# 元数据行不占扫描配额，比 _META_RE 多认 by:
_META_TAG_RE = re.compile(r"^\[[a-zA-Z]+:")
# 纯音乐占位符，整行匹配，避免误删正文
_PURE_MUSIC_RE = re.compile(r"^纯音乐[，,]请欣赏$")
# 值为无的行不写标签，简繁都认
_NO_VALUES = frozenset({"无", "無"})
# 歌词翻译行没有对应标签字段，带冒号才认
_TRANSLATION_RE = re.compile(
    r"^\[\d{2}:\d{2}[:.]\d{2,3}\]\s*(?:歌词翻译|歌詞翻譯)\s*[:：]"
)
# 冒号同时认半角与全角
_CREDIT_LINE_RE = re.compile(
    r"^\[\d{2}:\d{2}[:.]\d{2,3}\]\s*(?P<role>[^:：\[\]]{1,20}?)\s*[:：]\s*(?P<value>.+)$"
)

# 内部角色对应 MP3 帧、FLAC 键与歌词写法
CREDIT_ROLES = {
    "作曲": ("TCOM", "composer", ("作曲",)),
    "作词": ("TEXT", "lyricist", ("作词", "作詞")),
    "编曲": ("TIPL:arranger", "arranger", ("编曲", "編曲")),
    "制作人": ("TIPL:producer", "producer", ("制作人", "製作人", "Producer")),
    "混音": ("TIPL:mix", "mixer", ("混音", "Mixer")),
    "录音": ("TIPL:engineer", "engineer", ("录音", "錄音")),
    "指挥": ("TPE3", "conductor", ("指挥", "指揮")),
}

# 歌词写法到内部角色，繁体一并认
ROLE_ALIASES = {
    written: role
    for role, (_mp3, _flac, writings) in CREDIT_ROLES.items()
    for written in writings
}

# 连写角色映射，左为内部角色，右为保留的剩余角色名
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
    """去掉 [by:] 标签行，保留空行"""
    return "\n".join(
        line for line in text.splitlines() if not re.match(r"^\[by:", line)
    )


def parse(text: str) -> list[tuple[float, str, str]]:
    """解析 LRC 为时间、内容与原行，无时间戳行跳过"""
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
    """去掉时间戳后整行正好为纯音乐占位符"""
    m = _TIMESTAMP_RE.match(line)
    content = m.group(4) if m else line
    return bool(_PURE_MUSIC_RE.match(content.strip()))


def process_credits(
    text: str, scan_lines: int = 10, collect: bool = False, trim: bool = False
) -> tuple[dict[str, str], str]:
    """扫描歌词头部，把角色行搬进 credits，并按开关裁剪

    collect 为真时收集，trim 为真时删除占位与已处理角色行
    scan_lines 只数非元数据行
    """
    credits: dict[str, str] = {}
    kept: list[str] = []
    quota = scan_lines
    for line in text.splitlines():
        head = quota > 0
        if head and not _META_TAG_RE.match(line):
            quota -= 1
        m = _CREDIT_LINE_RE.match(line)
        role = m.group("role") if m else None
        value = m.group("value") if m else None

        # 占位行与角色行无关，先处理
        if head and (_is_pure_music_placeholder(line) or _TRANSLATION_RE.match(line)):
            if trim:
                continue
        elif head and role in CREDIT_COMBOS:
            roles, leftover = CREDIT_COMBOS[role]
            # 角色名改写与删行只在搬走时做
            if collect:
                if value.strip() not in _NO_VALUES:
                    for r in roles:
                        credits[r] = value
                if trim:
                    if leftover is None:
                        continue
                    line = line[: m.start("role")] + leftover + line[m.end("role") :]
        elif head and collect and role in ROLE_ALIASES:
            # 没搬走就裁会白丢；只开 auto_trim 时保留角色行
            # 值为无时不写标签，行照删
            if value.strip() not in _NO_VALUES:
                credits[ROLE_ALIASES[role]] = value
            if trim:
                continue

        kept.append(line)

    return credits, "\n".join(kept)


def interleave(lrc_text: str, tlyric_text: str, threshold: float = 0.3) -> str:
    """按时间戳交错原文与译文，未匹配的译文追加在末尾"""
    lrc_lines = parse(lrc_text)
    tlyric_lines = parse(tlyric_text)

    tlyric_by_time = list(enumerate(tlyric_lines))
    used_tlyric = set()

    # 保留 LRC 头部元数据
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
    """按模式处理歌词，返回后缀到文本的映射

    line 交错，block 拼接，split 分文件，drop 只留原文
    """
    lrc_clean = clean(lrc_raw)
    tlyric_clean = clean(tlyric_raw)

    # 缓存清洗后的歌词
    put_raw_lyrics(song_id, lrc_clean, tlyric_clean)

    if mode == "line":
        return {"lrc": interleave(lrc_clean, tlyric_clean)}
    if mode == "block":
        return {"lrc": lrc_clean + "\n" + tlyric_clean}
    if mode == "drop":
        # 只要原文
        return {"lrc": lrc_clean}
    # split 无译文时只出原文，避免 0 字节的 .2.lrc
    # 键顺序决定 output_files 的写入顺序
    if not tlyric_clean.strip():
        return {"lrc": lrc_clean}
    return {"lrc": lrc_clean, "2.lrc": tlyric_clean}


def output_files(lyrics_result: dict[str, str], base_path: str) -> list[str]:
    """写出歌词文件，返回路径列表"""
    written = []
    for suffix, text in lyrics_result.items():
        path = f"{base_path}.{suffix}"
        # 同名文件加序号
        counter = 0
        while Path(path).exists():
            counter += 1
            path = f"{base_path}({counter}).{suffix}"
        Path(path).write_text(text, encoding="utf-8")
        written.append(path)
    return written
