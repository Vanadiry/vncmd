# 详细指南

[配置](config.md)  
[搜索](search.md)  
[单曲/歌单/专辑](music.md)  
[Tracker](tracker.md)  
[工具](tool.md)

[项目](project.md)

如果你不了解如何拼装参数，可以访问[命令构造器](https://vanadiry.com/wiki/vncmd/cmd_helper/)查看完整命令。

## 基本命令

| 命令 | 说明 |
| :--- | :--- |
| `search "关键词"` | 搜索单曲 |
| `song <ID>` | 预览单曲 |
| `playlist <ID>` | 预览歌单 |
| `album <ID>` | 预览专辑 |
| `tracker <名称>` | 新建或查看 Tracker |
| `cookie "..."` | 写入 Cookie |
| `cookie --check` | 检查 Cookie 状态 |
| `doctor` | 检查配置 |

对于 `song/playlist/album`，传入 `-d` 参数，可以下载对应内容。  
例如 `vncmd song 409926 -d`。

详细参数见 [music](music.md)。

### 查找 ID

曲目、歌单、专辑 ID 均位于链接的 `id` 参数中：
`https://.../song?id=409926`

官方客户端：分享 → 复制链接。短链请先在浏览器中打开，再复制地址栏。  
网页版：直接看地址栏。

## 完整性校验

如果系统中安装了 ffmpeg 和 flac 工具，程序会自动在下载完毕后校验音频完整性。

你还可以使用 vncmd 的完整性校验工作流，来检查其他目录下的音频。  
详细用法见 [工具](tool.md)。

## 其他

预览和下载时会在 `~/.vSoft/vncmd/cache/` 写入缓存，可随时删除。  
同一时间只能运行一个 vncmd 实例。
