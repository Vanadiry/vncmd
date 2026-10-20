CONFIG_TOML = """\
[download]
# 绝对路径，或相对于 VNCMD_HOME 的路径，留空使用 ~/Downloads
dir = ""
# 艺术家在文件名中的位置：back=曲目-艺术家，front=艺术家-曲目，drop=仅曲目
filename_artist = "back"
# 下载内容：a=音频，l=歌词，c=封面，任意组合（如 alc=全部，cl=歌词和封面）
content = "alc"
# 并发下载数：1-16（默认 4）
concurrency = 4
# 下载后是否做 ffmpeg/flac 全量解码校验
check = true
# 下载方式：builtin=内建下载实现，curl=系统 curl
downloader = "builtin"
# 追加给 curl 的参数
curl_arg = ""

[download.audio]
# 音质：128、192、320（kbps），或 max（可用的最高质量）
quality = "max"
# 从歌词头解析“作曲人”并嵌入元数据
parse_credits = false

[download.lyric]
# 嵌入译文时，与原文的合并模式：line=交错，block=拼接，drop=丢弃译文
embed_mode = "drop"
# 下载译文时，与原文的合并模式：line=交错，block=拼接，drop=丢弃译文，split=拆分文件
save_mode = "line"
# 自动裁剪无用歌词数据，如纯音乐占位行等
auto_trim = false
# parse_credits 扫描的歌词行数
credit_scan_lines = 10

[download.cover]
# 嵌入封面压缩：false=原图，true=缩放至最大 500x500 JPEG
embed_compress = true
# 独立封面文件压缩，规则同 embed_compress
save_compress = false

[cache]
# 启用本地缓存（曲目详情与歌词）
enabled = true
# 缓存有效期，单位为天，0 表示永不过期
ttl = 3

[display]
# 艺术家按各自代表色着色
artist_color = true
"""

TRACKER_SETTINGS_TOML = """\
[tracker]
description = "在此描述此 Tracker"

[sources.song]
ids = []

[sources.playlist]
ids = []

[sources.album]
ids = []
"""
