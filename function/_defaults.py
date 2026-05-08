CONFIG_TOML = """\
[download]
# Absolute path, relative to VNCMD_HOME, or empty for ~/Downloads
dir = ""
# Filename format: 10=Title-Artist, 01=Artist-Title, 1=Title only
filename_format = "10"
# Download content: 0=song, 1=lyrics, 2=cover (e.g. 012=all, 12=lyrics&cover)
content = "012"

[download.song]
# Audio quality: 128, 192, 320, 999 (highest)
quality = "999"

[download.lyric]
# Embedded lyrics mode: 0=interleaved, 1=merged, 2=original only
embed_mode = "2"
# Standalone lyrics file mode: 0=interleaved, 1=merged, 2=separate files
save_mode = "0"

[download.cover]
# Embedded cover quality: 0=original, 1=resize to max 500x500 JPEG
embed_quality = "1"
# Standalone cover file quality: 0=original, 1=resize to max 500x500 JPEG
save_quality = "0"

[cache]
# Enable local cache for song details and lyrics
enabled = true
# Absolute path, or relative to VNCMD_HOME
dir = "cache"
"""

TRACKER_SETTINGS_TOML = """\
[tracker]
description = "Describe this tracker here"

[sources.song]
ids = []

[sources.playlist]
ids = []

[sources.album]
ids = []
"""
