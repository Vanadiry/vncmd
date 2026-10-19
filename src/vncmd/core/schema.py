"""配置键表 —— 每个键能填什么

与 `defaults.py` 是刻意重复的两份，不是冗余：
`defaults.py` 给**人**读，注释是它的主要内容，缺配置时整体写出给用户看；
这张表给**机器**读，装着取值范围与默认值，注释反而是负担。
不由表生成 toml —— 两份绑死之后，改一句注释就得改代码。

现在只搬了 6 个枚举型键，缺键仍然报错。
缺键回落默认值是 TODO2 第 4 步的事，到那时才轮得到 `default` 派上用场。
"""

from dataclasses import dataclass
from typing import Any

# 缓存有效期默认天数。它原来是 config.py 的常量，而 ttl 的默认值
# 现在住在表里 —— 表不该反过来 import config，那是环。
# 值要与 config.py 里那个一致，同步测试会盯
DEFAULT_CACHE_TTL = 3

# 音质名到码率的映射。最大值那档用 int 上限占位 ——
# 服务端不认这个边界，发过去它自己降，所以那一档的真实规格逐曲不同
QUALITY_MAP = {
    "128": 128000,
    "192": 192000,
    "320": 320000,
    "max": 2147483647,
}

# 下载内容。三个字母任意组合，"alc" 是全要，"cl" 只要歌词和封面。
# 用字母而不是数字：数字串读起来就是个带前导零的数，
# 有人会当成整数写上引号就忘了，而 alc 一眼知道不是数字。
# 三个字母没有天然顺序，所以读的时候按包含判断，顺序无所谓
CONTENT_LETTERS = "alc"


@dataclass(frozen=True)
class Setting:
    """一个配置项。path 是点号路径

    kind 决定怎么校验：
    `enum` 查 values、`content` 走字母组合那套规则、
    `int` 查 minimum 与 maximum、`bool` 与 `str` 只查类型。

    default 是键缺失时的取值。每一项都有，缺键时 getter 按它回落 ——
    所以配置文件可以只写想改的键，缺键不再报错

    wrong_value 是值不对时的措辞，每项都不一样，不是一句模板套出来的：
    有几项带实际值、有一项写「只能是」，差别都是从 config.py 抄来的，
    那些措辞被既有测试断言着，改文案就是改行为

    **这一栏不许留空。** 留空了那一项就完全不校验 ——
    值写错时校验返回空串，`validate` 里 `if message:` 判不到，
    于是那一项静默放行。`test_wrong_value_措辞不空` 盯着这件事
    """

    path: str
    kind: str = "str"
    values: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    default: Any = None
    wrong_value: str = ""


def _enum(
    path: str,
    values: tuple[str, ...],
    default: str,
    wrong_value: str,
) -> Setting:
    return Setting(path, "enum", values, default=default, wrong_value=wrong_value)


def _content(path: str, default: str) -> Setting:
    """content 不填 values

    它的合法值是任意字母组合，不是一组枚举值 ——
    塞进 values 只会让人以为「alc」与「ca」是两个不同的枚举项。
    合法字母留在 CONTENT_LETTERS，那是 content 专有的规则

    **wrong_value 留空是对的**，这一项的措辞由 check_content 自己算：
    多余了哪些字母、哪个字母重复了，都得看实际值才能说，
    写成一句固定的话反而不如它现在说得具体
    """
    return Setting(path, "content", default=default)


SCHEMA = (
    # 艺术家在文件名里的位置。以前这个键叫 filename_format，
    # 但它管不到分隔符、大小写、扩展名，三个值全由这一个维度决定，
    # 名字比内容宽
    _enum(
        "download.filename_artist",
        ("front", "back", "drop"),
        "back",
        "必须为 front、back、drop",
    ),
    _content("download.content", "alc"),
    # 音质名到码率的映射，合法名就是它的键
    _enum(
        "download.audio.quality",
        tuple(QUALITY_MAP),
        "max",
        # 带实际值：写 quality = 320 的人看到的是「必须为 128、192、320」，
        # 只差一对引号，报错里不写实际值就让人以为键名也错了
        "必须为以下之一：{allowed}，实际是 {value!r}",
    ),
    # 译文歌词的处理方式。前两档两边相同、第三档含义不同 ——
    # embed 是不要译文，save 多一档 split 分两个文件。
    # 各写各的，共用一个元组就把这个差别盖住了，这正是要建表的原因
    _enum(
        "download.lyric.embed_mode",
        ("line", "block", "drop"),
        "drop",
        # 这两个键带实际值：写 2 的人看到的是「必须为 line、block、drop」，
        # 而 2 是上一版方案的旧值，报错里不写实际值就看不出自己没跟着改
        "必须为 line、block、drop，实际是 {value!r}",
    ),
    _enum(
        "download.lyric.save_mode",
        ("line", "block", "split", "drop"),
        "line",
        "必须为 line、block、split、drop，实际是 {value!r}",
    ),
    _enum(
        "download.downloader",
        ("builtin", "curl"),
        "builtin",
        '只能是 "builtin" 或 "curl"',
    ),
    # 下面 12 项是类型与范围。措辞从 config.py 逐字抄来的，
    # 每项的差别都不是随意的：
    # 带实际值的与不带的、缺键说「缺失」还是「缺失或不为布尔值」、
    # dir 判类型但空串合法 —— 那些都是既有测试断言着的
    # 留空表示用 ~/Downloads，所以只判类型不判非空。
    # 报错写的是类型名而不是实际值：路径类的值打出来是一长串，
    # 报出来用户也看不出哪里错，写 int、list 这种一眼能认的就行
    Setting(
        "download.dir",
        "str",
        default="",
        wrong_value="必须是字符串，实际是 {typename}",
        # 不带「或为空」：空串是合法的，缺键与写空串是两回事
    ),
    Setting(
        "download.concurrency",
        "int",
        minimum=1,
        maximum=16,
        default=4,
        # 带实际值：写成 0 或 true 的人看到这个才知道自己填了什么。
        # 缺键也用这句 —— 键本来就必须写，缺了与填了个 4 不该两样报错
        wrong_value="必须为 1-16 的整数，实际是 {value!r}",
    ),
    Setting(
        "download.check",
        "bool",
        default=True,
        wrong_value="必须为 true 或 false",
    ),
    Setting(
        "download.curl_arg",
        "str",
        default="",
        wrong_value="必须是字符串",
        # 缺了不算错：getter 取的是默认值空串，curl 用不到这个参数时
        # 本来就没有，所以这一项可以整条省略
    ),
    Setting(
        "download.audio.parse_credits",
        "bool",
        default=False,
        # 这一项缺键与写错值是同一句话：布尔没有「空」这个状态，
        # 缺了与填了个非布尔值在用户看来是一回事
        wrong_value="缺失或不为布尔值",
    ),
    Setting(
        "download.lyric.auto_trim",
        "bool",
        default=False,
        # 这一项缺键与写错值是同一句话：布尔没有「空」这个状态，
        # 缺了与填了个非布尔值在用户看来是一回事
        wrong_value="缺失或不为布尔值",
    ),
    Setting(
        "download.lyric.credit_scan_lines",
        "int",
        minimum=1,
        default=10,
        wrong_value="缺失或不为正整数",
    ),
    # 判缺失用「在不在」而不是「取到没有」：这两个键的合法值里有 false，
    # 那种写法会把 false 当成没写，而 false 恰好是「用原图」那一档
    Setting(
        "download.cover.embed_compress",
        "bool",
        default=True,
        wrong_value="必须为 true 或 false，实际是 {value!r}",
    ),
    Setting(
        "download.cover.save_compress",
        "bool",
        default=False,
        wrong_value="必须为 true 或 false，实际是 {value!r}",
    ),
    # enabled 要判类型：写成带引号的 "false" 时字符串非空、是真值，
    # 用户以为关了缓存实际照开，而这种错在界面上完全看不出来
    Setting(
        "cache.enabled",
        "bool",
        default=True,
        wrong_value="必须为 true 或 false，实际是 {value!r}",
    ),
    Setting(
        "cache.ttl",
        "int",
        minimum=0,
        default=DEFAULT_CACHE_TTL,
        wrong_value="不为非负整数",
    ),
    Setting(
        "display.artist_color",
        "bool",
        default=True,
        wrong_value="不为布尔值",
    ),
)

_BY_PATH = {s.path: s for s in SCHEMA}

# 从表里派生，不另写一份 —— 另写一份就成了表与它各说各话的第二个来源。
# 这两个名字仍被 cli、tracker 与测试 import，等各调用点跟着搬进 schema
# 之后再删掉
FILENAME_ARTIST = _BY_PATH["download.filename_artist"].values
LYRIC_MODES = {
    "embed_mode": _BY_PATH["download.lyric.embed_mode"].values,
    "save_mode": _BY_PATH["download.lyric.save_mode"].values,
}


def get(path: str) -> Setting | None:
    """查一项。查不到返回 None，那是还没进表的键"""
    return _BY_PATH.get(path)


def section_names() -> tuple[str, ...]:
    """表里用到的每一个段名，含子表

    从 SCHEMA 推而不是手写清单 —— 手写过一次就漏了 display，
    而漏掉的那一段写成标量时校验完全静默，是审查时才发现的。
    加了新的子表，这里自动跟着变
    """
    top = set()
    sub = set()
    for setting in SCHEMA:
        parts = setting.path.split(".")
        top.add(parts[0])
        for part in parts[1:-1]:
            sub.add(f"{parts[0]}.{part}")
    return tuple(sorted(top | sub))


def coerce(path: str, raw: str) -> Any:
    """把命令行的字符串按这一项的类型转成该有的样子

    CLI 传来的永远是字符串，而表里存的可能是整数或布尔。
    不转的话 `--config download.concurrency=4` 会让校验说
    「必须为 1-16 的整数，实际是 '4'」—— 用户明明写的是 4。

    字符串那一类必须原样留着：`quality` 的值是 "128"、`content` 是 "alc"，
    转成数字反而错。`bool` 只认小写 true/false，与 TOML 一致 ——
    `True` 在 TOML 里本来就不是合法值，照抄过去也过不了校验。

    路径不认识时抛 ValueError：命令行里写错一个键要立刻有话说，
    不该让它流到校验那一步再报成一个笼统的「未知键」
    """
    setting = get(path)
    if setting is None:
        raise ValueError(f"配置里没有 {path} 这一项")
    if setting.kind == "bool":
        if raw == "true":
            return True
        if raw == "false":
            return False
        raise ValueError(f"{path} 只能是 true 或 false，给的是 {raw!r}")
    if setting.kind == "int":
        try:
            return int(raw)
        except ValueError:
            raise ValueError(f"{path} 要整数，给的是 {raw!r}") from None
    return raw


def split_override(text: str) -> tuple[str, str]:
    """把 `键=值` 切开，只按第一个等号

    值里可能有等号：`curl_arg="-H X=1"`。
    没有等号或键为空都算写法错，立刻报 —— 否则会静默变成别的东西
    """
    if "=" not in text:
        raise ValueError(f"{text!r} 不是 键=值 的写法")
    key, value = text.split("=", 1)
    if not key:
        raise ValueError(f"{text!r} 少了等号前面的键")
    return key, value


def check_content(value: Any, letters: str) -> str | None:
    """content 的规则不是取值集合，返回错误说明或 None

    几个部分分开说，因为错的写法不一样：
    不是字符串的是漏了引号、其余的都是没填、多余的是打错字母、
    重复的是不知道每字母最多一次

    字符串那道检查不能省：content = 12 会被 tomllib 读成整数，
    下面 set() 它会抛 TypeError，用户看到的是一整段调用栈而不是配置写错了
    """
    if not isinstance(value, str) or not value:
        return "缺失或为空，且必须是带引号的字符串"
    extra = sorted(set(value) - set(letters))
    if extra:
        return f"只能包含 {'、'.join(letters)}，多余的字符：{'、'.join(extra)}"
    dup = sorted({c for c in value if value.count(c) > 1})
    if dup:
        return f"里 {'、'.join(dup)} 重复了，每个字母最多一次"
    return None


def check_enum(setting: Setting, value: Any) -> str | None:
    """枚举校验，返回值不对时的说明或 None

    措辞从 `wrong_value` 里来，`{allowed}` 换成值域、`{value}` 换成用户实际填的。
    带不带实际值每项不一样，所以它进得了模板而不是一句模板套所有
    """
    if value in setting.values:
        return None
    # 三个占位符各自可选，谁填了哪个看那一项的措辞。
    # 一次 format 而不是逐个 replace —— replace 会先把 {value!r} 替成 {value}，
    # 后面那道再替一次，结果占位符原样留在消息里
    return setting.wrong_value.format(
        allowed=", ".join(setting.values),
        value=value,
        typename=type(value).__name__,
    )


def check_int(setting: Setting, value: Any) -> str | None:
    """整数校验，返回值不对时的说明或 None

    **布尔要单独排除。** Python 里 isinstance(True, int) 为真，
    concurrency = true 会一路过类型检查，getter 拿到 True，
    min(True, 曲数) 得 1 —— 静默降成单线程还不给任何提示。
    这道检查原先只写在 config.py 的三处手写里，搬进 kind 就看不见了，
    所以它得在检查器内部，谁读表都不用记得
    """
    if not isinstance(value, int) or isinstance(value, bool):
        return setting.wrong_value.format(
            allowed="", value=value, typename=type(value).__name__
        )
    if setting.minimum is not None and value < setting.minimum:
        return setting.wrong_value.format(
            allowed="", value=value, typename=type(value).__name__
        )
    if setting.maximum is not None and value > setting.maximum:
        return setting.wrong_value.format(
            allowed="", value=value, typename=type(value).__name__
        )
    return None


def check_bool(setting: Setting, value: Any) -> str | None:
    """布尔校验

    必须用 isinstance 而不是「等于 true 或 false」：
    写成 enabled = 0 时 0 == false 为真，那样判会放行整数 0，
    而它取到的是 0（假值），恰好蒙对 —— 换个键就不一定了
    """
    if not isinstance(value, bool):
        return setting.wrong_value.format(
            allowed="", value=value, typename=type(value).__name__
        )
    return None


def check_str(setting: Setting, value: Any) -> str | None:
    """字符串校验

    **不判非空。** dir 留空是合法的，意思是「用 ~/Downloads」——
    这一项的空值有明确含义，判了就等于把默认行为判成错

    报错用 {typename} 而不是 {value}：路径类的值打出来是一长串，
    用户看不出哪里错，写 int、list 这种一眼能认的就行
    """
    if not isinstance(value, str):
        return setting.wrong_value.format(
            allowed="", value=value, typename=type(value).__name__
        )
    return None


def validate_entry(setting: Setting, value: Any) -> str | None:
    """按 kind 分派，返回这一项的错误说明或 None

    消息里只有值本身的部分，段名与键名由 validate 拼 ——
    那边才知道这一项在哪个段里
    """
    if setting.kind == "enum":
        return check_enum(setting, value)
    if setting.kind == "content":
        return check_content(value, CONTENT_LETTERS)
    if setting.kind == "int":
        return check_int(setting, value)
    if setting.kind == "bool":
        return check_bool(setting, value)
    if setting.kind == "str":
        return check_str(setting, value)
    return None


def _locate(cfg: dict, path: str) -> tuple[list[str], str, Any]:
    """按点号路径在配置里取值

    返回 (段名列表, 键名, 值)。段名多于一层时就是 download.audio 这种，
    `download.filename_artist` 那种两段的则是 download 本身作为段
    """
    parts = path.split(".")
    container = cfg
    for part in parts[:-1]:
        if not isinstance(container, dict):
            return [], path, None
        container = container.get(part, {})
    if not isinstance(container, dict):
        return [], path, None
    return parts[:-1], parts[-1], container.get(parts[-1], None)


def unknown_keys(cfg: dict) -> list[str]:
    """列出配置里表里没有的段与键

    未知键一律报错，不静默吞掉。这一轮改名改了八个键，
    照抄了新键名却忘了删旧的 —— 那种配置静默失效，
    用户以为改了其实没改，比直接报错难查得多

    碰到不认识的键就点名报出来，让用户自己对着文档改 ——
    项目还没发版，不做旧键到新键的对照表那种迁移提示

    tracker 的 settings.toml 里有 `[sources.song]` 这类段，
    但那份文件不经过 validate_config，两者不相干 ——
    所以这张表只管 config.toml 的键，不必给 tracker 的段留位置
    """
    extra = []
    for name, table in cfg.items():
        if not _has_known_keys(name):
            # 名字本身就不认识，无论它写在哪种形式里都要报 ——
            # 只报段名不报里面每一项：那一整段的键都要删，
            # 点名段名用户就知道该删哪里。空段也报，多半是加了段却忘了填。
            #
            # 这一段必须排在下面那个 isinstance 判断之前。调换过来就是
            # 一个静默漏洞：顶层写个拼错的键（`qualty = "max"`）不是表，
            # 会被那句 continue 跳过，于是什么都不报 —— 用户以为改了
            extra.append(f"[{name}]")
            continue
        if not isinstance(table, dict):
            # 名字认识却是标量，由 validate_config 报「必须是一段配置」，
            # 这里再报一遍就是重复了
            continue
        extra += _scan_table(name, table)
    return extra


def _scan_table(prefix: str, table: dict) -> list[str]:
    """查一层的键，子表递归下去

    参数是这一层自己的名字而不是叶子键 —— download.audio 传进来时
    prefix 是 "download.audio"，它里面的键才拼成 [download.audio] quality
    """
    extra = []
    for key, value in table.items():
        path = f"{prefix}.{key}"
        if path in _BY_PATH:
            # 认识的叶子键。它是子表的话继续往下查 ——
            # 键值都是 dict 的那种写法在 TOML 里不存在，防御一下
            if isinstance(value, dict):
                extra += _scan_table(path, value)
            continue
        if isinstance(value, dict):
            if _has_known_keys(path):
                # 是表里也有的子表，只是里面多了键
                extra += _scan_table(path, value)
            else:
                # 整段都不认识，含空段 —— 只报段名不报里面每一项：
                # 那一整段都要删，点名段名用户就知道该删哪里。
                # 空段也报，多半是加了段却忘了填
                extra.append(f"[{path}]")
        else:
            extra.append(f"[{path}]")
    return extra


def _has_known_keys(prefix: str) -> bool:
    """这个段下面有没有表里认得的键"""
    return any(s.path.startswith(f"{prefix}.") for s in SCHEMA)


def value_of(cfg: dict, path: str) -> Any:
    """按 path 取值，缺了就回落表里的 default

    这一步之后配置可以只写想改的键，其余的由默认值兜着。
    之前 getter 是直接下标取的，缺一个键就是 KeyError ——
    缺键在第 3 步之前会被校验拦下所以看不出来，而校验一放开就是真崩

    default 为 None 表示那一项还没有默认值可回落，取到 None 是应有之义
    """
    setting = get(path)
    if setting is None:
        # 不在表里的键：原样返回取到的值，让调用方自己处理。
        # 表搬完这个分支就没人走了，但留着比抛异常好
        return _locate(cfg, path)[2]
    _, _, value = _locate(cfg, path)
    if value is None:
        return setting.default
    return value


def validate(cfg: dict) -> list[str]:
    """校验表里全部 18 项，返回错误说明的列表

    **缺键不再报错。** 配置文件可以只写想改的键，其余由表里的
    default 兜着，getter 也照 default 取 —— 这是第 4 步。

    段本身不是表仍然报，那是另一回事：那一段整个写坏了，
    与「某个键没写」不同。这里跳过，交给 validate_config 的段检查
    """
    errors = []
    for setting in SCHEMA:
        parts, key, value = _locate(cfg, setting.path)
        if not setting.wrong_value and setting.kind != "content":
            # 这一栏漏填的话那一项就完全不校验 ——
            # 值错时校验器返回空串，下面 `if message:` 判不到，静默放行。
            # 宁可报一句含糊的，也不放过：这里出现是表写错了，不是配置写错了。
            #
            # content 是例外：它的措辞由 check_content 自己算，
            # 那要看实际值才说得出多余了哪个字母
            errors.append(f"[{setting.path}] 这一项没写值错时的提示，校验不会生效")
            continue
        if not parts:
            continue

        if value is None:
            continue

        message = validate_entry(setting, value)
        if message:
            name = "[" + ".".join(parts) + "]" if len(parts) > 1 else f"[{parts[0]}]"
            errors.append(f"{name} {key} {message}")
    return errors
