import re

COLORS: dict[str, tuple[str, ...]] = {
    "#39C5BB": ("初音ミク", "初音未来"),
    "#FFCC11": ("鏡音リン", "镜音铃"),
    "#FFEE11": ("鏡音レン", "镜音连"),
    "#FFBBCC": ("巡音ルカ", "巡音流歌"),
    "#DD4444": ("MEIKO",),
    "#3366CC": ("KAITO",),
    "#66CCFF": ("洛天依",),
    "#EE0000": ("乐正绫",),
    "#00A86B": ("GUMI",),
    "#C8484E": ("重音テト",),
    "#FF5500": ("足立レイ",),
    "#00FFCC": ("言和",),
    "#006666": ("乐正龙牙",),
    "#FFFF00": ("墨清弦",),
    "#0080FF": ("徵羽摩柯",),
    "#33AAEE": ("星乃一歌",),
    "#FFDD44": ("天馬咲希", "天马咲希"),
    "#EE6666": ("望月穗波", "望月穂波"),
    "#BBDD22": ("日野森志歩", "日野森志步"),
    "#FFCCAA": ("花里みのり", "花里实乃理"),
    "#99CCFF": ("桐谷遥",),
    "#FFAACC": ("桃井愛莉", "桃井爱莉"),
    "#99EEDD": ("日野森雫",),
    "#FF6699": ("小豆沢こはね", "小豆泽心羽"),
    "#00BBDD": ("白石杏",),
    "#FF7722": ("東雲彰人", "东云彰人"),
    "#0077DD": ("青柳冬弥",),
    "#FFBB00": ("天馬司", "天马司"),
    "#FF66BB": ("鳳えむ", "凤笑梦"),
    "#33DD99": ("草薙寧々", "草薙宁宁"),
    "#BB88EE": ("神代類", "神代类"),
    "#BB6688": ("宵崎奏",),
    "#8888CC": ("朝比奈まふゆ", "朝比奈真冬"),
    "#CCAA88": ("東雲絵名", "东云绘名"),
    "#DDAACC": ("暁山瑞希", "晓山瑞希"),
}

# 查表用，导入时把色值展开成名字到色值的映射
NAME_TO_COLOR: dict[str, str] = {
    name: color for color, names in COLORS.items() for name in names
}

# 名字后面常跟版本号或官方后缀，剥掉这些再查表
_TAIL = re.compile(r"(?:[VvＶ][0-9０-９]+[XxＸ]?|[XxＸ][0-9０-９]*|AI|ＡＩ|Official)+$")

# 艺人串的分隔符，切开后逐段查表
_SEP = re.compile(r"[,、，/&＆|｜]|\s+(?:feat|ft|featuring)\.?\s+")


def _lookup(chunk: str) -> str | None:
    """查一个片段的代表色，查不到返回 None"""
    name = chunk.strip()
    if not name:
        return None
    color = NAME_TO_COLOR.get(name)
    if color:
        return color
    stripped = _TAIL.sub("", name).strip()
    if stripped and stripped != name:
        return NAME_TO_COLOR.get(stripped)
    return None


def colorize(artist: str) -> list[tuple[str, str | None]]:
    """把艺术家串按分隔符切开，逐段查代表色

    返回片段与色值组成的列表，合起来覆盖原串的全部字符。
    色值为 None 的片段表示照原样显示，调用方自己决定用什么样式。
    """
    segments: list[list[str | None]] = []
    pos = 0
    for m in _SEP.finditer(artist):
        if m.start() > pos:
            segments.append([artist[pos : m.start()], _lookup(artist[pos : m.start()])])
        segments.append([m.group(), None])
        pos = m.end()
    if pos < len(artist):
        segments.append([artist[pos:], _lookup(artist[pos:])])

    merged: list[tuple[str, str | None]] = []
    for text, color in segments:
        if merged and merged[-1][1] == color:
            merged[-1] = (merged[-1][0] + str(text), color)
        else:
            merged.append((str(text), color))
    return merged
