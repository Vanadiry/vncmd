# 工具

这里是 vncmd 提供的小工具。
与下载音乐无关，但可以方便地维护你的音乐库。

## check

检查音频文件完整性。

```bash
vncmd tool check <目录或文件路径> [-r]
```

| 参数 | 简写 | 说明 |
| --- | --- | --- |
| `--recursive` | `-r` | 递归检查子目录（传入单个文件时会被忽略） |

目录默认只检查当前一层。  
支持格式：mp3、flac、m4a、wav、ogg、opus、wma、ape。

校验依赖系统中安装的 ffmpeg（全量解码）、ffprobe（时长交叉验证）、flac（FLAC 的 CRC 校验）。

## embed-id

为已有音频补写 track_id。  
仅支持 mp3 和 flac 格式音频。

```bash
vncmd tool embed-id <目录或文件路径> [--from <json>] [-r] [--set <id>]
```

| 参数 | 简写 | 说明 |
| --- | --- | --- |
| `--from` | | 指定一份 songs.json |
| `--recursive` | `-r` | 递归处理子目录 |
| `--set` | | 直接指定曲目 ID，只用于单个文件 |

此功能会改写音频的元数据，在自定义标签位添加 `track_id` 标签，记录上游的曲目 ID。

你需要一份形如 vncmd 的 Tracker 功能生成的，记录了“标题、艺术家、id”的 `songs.json`，并使用 `--from` 传入。  
没有指定 `--from` 时，vncmd 会合并所有 Tracker 的 `songs.json`。  
如果你之前使用 Tracker 功能来下载曲库，则不需要指定 `--from` 参数。

vncmd 读取你曲目元数据中的标题、艺术家，并与 `songs.json` 匹配，并写入 id。
可能无法精确的匹配到所有曲目，embed-id 工具会报告异常的文件。

对于 vncmd 无法匹配的文件，你可以自行核对，使用 `--set` 来手动设置 id。

## cache

查看或清理本地缓存。

```bash
vncmd tool cache [--stats] [--clear]
```

| 参数 | 说明 |
| --- | --- |
| `--stats` | 显示缓存目录、占用空间、文件数、曲目数与有效期 |
| `--clear` | 清空缓存目录，不询问确认 |
