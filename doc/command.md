# 命令参考

## search — 搜索

```
python vnemd.py search <关键词> [-n 数量] [--offset 偏移]
```

| 参数 | 简写 | 说明 |
|---|---|---|
| `--limit N` | `-n` | 返回数量，默认 30 |
| `--offset N` | — | 分页偏移 |

## song — 单曲

```
python vnemd.py song <ID> [-l] [-u] [-d] [-q 音质] [-o 目录]
```

默认预览元数据（标题、歌手、专辑、封面、时长）；加 `-d` 下载。

| 参数 | 简写 | 说明 |
|---|---|---|
| `--lyrics` | `-l` | 显示歌词 |
| `--tlyric` | — | 同时显示中文翻译 |
| `--url` | `-u` | 检查流 URL 是否可用 |
| `--download` | `-d` | 开始下载 |
| `--quality` | `-q` | 临时覆盖音质（128/192/320/999） |
| `--output` | `-o` | 临时覆盖输出目录 |

## playlist — 歌单

```
python vnemd.py playlist <ID> [-n 数量] [-d] [-q 音质] [-o 目录]
```

默认预览曲目表格；加 `-d` 批量下载。

| 参数 | 简写 | 说明 |
|---|---|---|
| `--limit` | `-n` | 预览条数 / 下载曲数（默认全部） |
| `--download` | `-d` | 开始下载 |
| `--quality` | `-q` | 临时覆盖音质 |
| `--output` | `-o` | 临时覆盖输出目录 |

## album — 专辑

```
python vnemd.py album <ID> [-n 数量] [-d] [-q 音质] [-o 目录]
```

默认预览曲目表格；加 `-d` 批量下载。参数同 playlist。
