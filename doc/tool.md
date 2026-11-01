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

## cache

查看或清理本地缓存。

```bash
vncmd tool cache [--stats] [--clear]
```

| 参数 | 说明 |
| --- | --- |
| `--stats` | 显示缓存目录、占用空间、文件数、曲目数与有效期 |
| `--clear` | 清空缓存目录，不询问确认 |
