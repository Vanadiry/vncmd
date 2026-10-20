# 详细指南

[配置](config.md)  
[搜索](search.md)  
[单曲/歌单/专辑](music.md)  
[Tracker](tracker.md)  
[项目](project.md)  
[其他](other.md)

## 基本命令

| 命令 | 说明 |
| :--- | :--- |
| `search "关键词"` | 搜索单曲 |
| `song <ID>` | 预览单曲 |
| `playlist <ID>` | 预览歌单 |
| `album <ID>` | 预览专辑 |
| `tracker <名称>` | 新建/查看 Tracker |
| `cookie "..."` | 写入 Cookie |
| `cookie --check` | 不写文件，只检查当前 Cookie 状态 |
| `tool check "文件或目录"` | 校验音频完整性 |

对于 `song/playlist/album` 的参数：

- `-d`：加入 `-d` 即为下载。
- `-n`：使用 `-n <数字>` 限制下载或查询数量。不加时查询默认 10，下载默认全量。

详细参数见 [music](music.md)。

### 查找 ID

曲目、歌单、专辑 ID 均位于链接的 `id` 参数中：
`https://.../song?id=409926`

官方客户端：分享 → 复制链接。短链请先在浏览器中打开，再复制地址栏。  
网页版：直接看地址栏。

## 完整性校验

如果系统中安装了 ffmpeg 和 flac 工具，程序会自动在下载完毕后校验音频完整性。  
你可以使用 `vncmd tool check "文件或目录"` 来校验其他目录下的音频。

支持格式：mp3、flac、m4a、wav、ogg、opus、wma、ape。  

## 其他

预览和下载时会在 `~/.vSoft/vncmd/cache/` 写入缓存，可随时删除。  
同一时间只能运行一个 vncmd 实例。

与其他软件配合使用等已知问题，请查看[其他](other.md)。
