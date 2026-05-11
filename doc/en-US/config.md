# Configuration

Config file: `~/.vSoft/vncmd/config.toml`
Cookie file: `~/.vSoft/vncmd/cookie` (plain text)

On startup, the config is validated. Missing or invalid keys will cause an error.

## Global Config

### [download]

| Key | Default | Description |
| --- | --- | --- |
| `dir` | `""` | Download directory.<br>Supports absolute paths and paths relative to `~/.vSoft/vncmd`. |
| `filename_format` | `10` | Filename format.<br>`10`: Title - Artist \| `01`: Artist - Title \| `1`: Title only |
| `content` | `012` | What to download (combinable, e.g. `01`).<br>`0`: audio \| `1`: lyrics \| `2`: cover art |

#### [download.song]

| Key | Default | Description |
| --- | --- | --- |
| `quality` | `999` | Audio quality.<br>128/192/320 kbps, or 999 for lossless. |

#### [download.lyric]

| Key | Default | Description |
| --- | --- | --- |
| `embed_mode` | `2` | Lyrics mode for embedded tags.<br>`0`: interleaved \| `1`: merged \| `2`: original only |
| `save_mode` | `0` | Lyrics mode for standalone files.<br>`0`: interleaved \| `1`: merged \| `2`: separate streams |

Some songs have multiple lyric streams, especially foreign-language tracks (original and translation).

**Mode 0 (interleaved):** Lines are interleaved by timestamp, with a 300ms tolerance for matching.

**Mode 1 (merged):** The translation stream is appended below the original.

**Mode 2 (original):** For embedded tags, only the original stream is embedded. For standalone files, all streams are saved separately with `.2`, `.3` suffixes.

#### [download.cover]

| Key | Default | Description |
| --- | --- | --- |
| `embed_quality` | `1` | Cover art in embedded tags.<br>`0`: as-is \| `1`: max 500px JPEG |
| `save_quality` | `0` | Standalone cover file.<br>`0`: as-is \| `1`: max 500px JPEG |

Use mode `1` when embedding cover art into audio files.

With mode `1`, covers with any side larger than 500px are resized. All formats are converted to JPEG, transparency replaced with white, and quality set to 60 for small file size.

### [cache]

Don't touch this if you're not sure what it does.

| Key | Default | Description |
| --- | --- | --- |
| `enabled` | `true` | Whether caching is enabled |
| `dir` | `cache` | Cache directory. Supports absolute paths and paths relative to `~/.vSoft/vncmd`. |
