CONFIG_TOML = """\
[download]
# 绝对路径、相对于 VNCMD_HOME 的路径，或留空使用 ~/Downloads
dir = ""
# 文件名格式：10=曲目-艺术家，01=艺术家-曲目，1=仅曲目
filename_format = "10"
# 下载内容：0=音频，1=歌词，2=封面（如 012=全部，12=歌词和封面）
content = "012"
# 并发下载数：1-16（默认 4）
concurrency = 4

[download.song]
# 音质：128、192、320、999（最高）
quality = "999"

[download.lyric]
# 嵌入歌词模式：0=交错，1=合并，2=仅原文
embed_mode = "2"
# 独立歌词文件模式：0=交错，1=合并，2=分离文件
save_mode = "0"

[download.cover]
# 嵌入封面质量：0=原图，1=缩放至最大 500x500 JPEG
embed_quality = "1"
# 独立封面文件质量：0=原图，1=缩放至最大 500x500 JPEG
save_quality = "0"

[cache]
# 启用本地缓存（曲目详情和歌词）
enabled = true
# 绝对路径，或相对于 VNCMD_HOME 的路径
dir = "cache"
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
