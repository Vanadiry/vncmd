# vncmd

网易云音乐 CLI 下载工具。

之前用的下载器不好使了，又找不到其他能嵌入元数据，还方便的工具，所以自己造了一个。

本项目不提供越权操作，如果你想下载 VIP 音乐，那你要确保你是 VIP。  
本项目仅供学习交流，严禁用于商业用途。使用本项目获取的数据，请于 24 小时内删除。

[GitHub](https://github.com/Vanadiry/vncmd)｜[PyPI](https://pypi.org/project/vncmd/)｜[Blog](https://magic.vanadiry.com/wiki/vncmd/)

## 功能

- 搜索单曲（同时支持预览歌词）
- 下载单曲/歌单/专辑（元数据嵌入、Cookie 高音质/VIP）
- 以交错/合并/原始模式处理双语歌词
- 追踪歌单等多来源，自动同步和批量下载
- 支持仅下载歌词/封面
- 并发下载，断点续传，自动重试，完整性校验
- 歌词增强解析，以及附加修正功能

## 快速开始

```bash
pip install vncmd
vncmd init
```

初次使用，请至少阅读[详细指南](doc/guide.md)。  

配置和缓存默认放在 `~/.vSoft/vncmd/`，可通过环境变量 `VNCMD_HOME` 自定义。  
下载目录默认 `~/Downloads/vncmd-dl/`，在配置文件中可修改。

vncmd 有各种方便的功能，但可能不适合所有用户，因此默认关闭。  
请阅读[配置](doc/config.md)来了解功能运作方式，以及配置方法。

```bash
# 搜索
vncmd search "Beyond"

# 使用。数字为曲目ID，专辑歌单同理。加入-d参数即为下载。
# 单曲：song｜歌单：playlist｜专辑：album。
vncmd song 409926           # 预览单曲
vncmd song 409926 -d        # 下载单曲
vncmd playlist 17647459371  # 预览歌单
vncmd playlist 17647459371 -d -n 5  # 下载歌单前5首
vncmd album 405493 -d       # 下载专辑

# 设置 Cookie
vncmd cookie "..."

# 追踪
vncmd tracker my-list          # 新建/查看追踪
vncmd tracker my-list -f       # 交互式更新

# 音频完整性检查
vncmd check ~/Music
```

## 二进制

vncmd 提供不依赖 Python 环境的二进制程序，打包了所有依赖，能够直接运行。  
你可以在 [GitHub Releases](https://github.com/Vanadiry/vncmd/releases) 下载，使用方式与 pip 安装的无差别。
