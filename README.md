# vNetEaseMusicDownloader

`vnemd`，网易云音乐 CLI 工具。  
之前用的下载器不好使了，又找不到其他能嵌入元数据，还方便的工具，所以自己造了一个。

本项目不提供越权操作，如果你想下载 VIP 音乐，那你要确保你是 VIP。  
本项目仅供学习交流，严禁用于商业用途。使用本项目获取的数据，请于 24 小时内删除。

## 功能

- 搜索单曲
- 下载单曲/歌单/专辑
- 使用 Cookie 下载仅 VIP 及更高音质音频
- 将元数据嵌入音频（封面/歌词/曲目信息等）
- 预览歌词（原文/中文等）
- 合并双语歌词
- 支持仅下载歌词/封面

## 快速开始

确保你已安装好Python，并配置了环境变量。
确保你的终端已经位于当前项目文件夹。  

```bash
# 安装依赖（推荐使用虚拟环境）
pip install -r requirements.txt

# 如果运行pip和python时提示找不到命令，尝试改为pip3和python3。

# 搜索
python vnemd.py search "Beyond"

# 使用。数字为曲目ID，专辑歌单同理。加入-d参数即为下载。
# 单曲：song｜歌单：playlist｜专辑：album。
python vnemd.py song 409926           # 预览单曲
python vnemd.py song 409926 -d        # 下载单曲
python vnemd.py playlist 17647459371  # 预览歌单
python vnemd.py playlist 17647459371 -d -n 5  # 下载歌单前5首
python vnemd.py album 405493 -d       # 下载专辑
```

### 基本命令

| 命令 | 说明 |
|:---|:---|
| `search <关键词>` | 搜索单曲 |
| `song <ID>` | 预览单曲 |
| `playlist <ID>` | 预览歌单 |
| `album <ID>` | 预览专辑 |

对于 `song/playlist/album` 的参数：  

- `-d`：后面加入 `-d` 即为下载。  
- `-n`：使用 `-n <数字>` 可以限制下载或查询的数量。
  若不加这个参数，查询模式默认为 10，下载模式默认为全量。

功能还有很多，完整参数见 [doc/command](doc/command.md)，配置说明见 [doc/config](doc/config.md)，建议完整阅读这两个文档。

### Cookie

下载 VIP 曲目，或者更高音质内容，需要 Cookie。  
请自行搜索如何获取 Cookie，并将获取到的内容复制到 `config/cookie` 文件中。

## 其他

预览和下载内容时，会在预设目录 `cache/` 中写入缓存。  
你可以运行 `python clean.py` 来删掉 `cache/` 和 `downloads/` 目录里的内容。
