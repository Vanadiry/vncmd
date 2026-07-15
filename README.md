# vncmd

网易云音乐 CLI 下载工具。

之前用的下载器不好使了，又找不到其他能嵌入元数据，还方便的工具，所以自己造了一个。

本项目不提供越权操作，如果你想下载 VIP 音乐，那你要确保你是 VIP。  
本项目仅供学习交流，严禁用于商业用途。使用本项目获取的数据，请于 24 小时内删除。

[详细指南](doc/guide.md)｜[GitHub](https://github.com/Vanadiry/vncmd)｜[PyPI](https://pypi.org/project/vncmd/)｜[Blog](https://magic.vanadiry.com/wiki/vncmd/)

## 功能

- 搜索单曲（同时支持预览歌词）
- 下载单曲/歌单/专辑（支持元数据嵌入，支持使用 Cookie 下载高音质/会员曲目）
- 以交错/合并/原始模式处理双语歌词
- 追踪歌单等多来源，自动同步和批量下载
- 支持仅下载歌词/封面
- 断点续传，下载列表时自动记录进度

## 快速开始

```bash
pip install vncmd
vncmd init
```

配置和缓存默认放在 `~/.vSoft/vncmd/`，可通过环境变量 `VNCMD_HOME` 自定义。  
下载目录默认 `~/Downloads/vncmd-dl/`，在配置文件中可修改。

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

# 追踪
vncmd tracker my-list       # 新建/查看追踪
vncmd tracker my-list -f    # 交互式更新
```

与其他软件配合使用等已知问题，请查看[其他](doc/other.md)。
