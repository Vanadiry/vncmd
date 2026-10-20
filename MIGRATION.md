# 迁移说明

## v1

适用于从 0.x 迁移至 1.x。  
1.0.0 为大版本更新，配置键、命令行参数与 Tracker 数据结构都有不兼容变更。

### 升级前

1. 备份 `~/.vSoft/vncmd/`，至少包含 `config.toml`、`tracker/`
2. 关闭正在运行的 vncmd
3. 使用你安装时的方式，更新至 1.0.0

### 重建配置

建议将旧 `config.toml` 备份，执行 `vncmd --init` 生成新配置，然后手动迁移。

| 旧配置 | 新配置 |
| --- | --- |
| `filename_format = "10"` | `filename_artist = "back"` |
| `filename_format = "01"` | `filename_artist = "front"` |
| `filename_format = "1"` | `filename_artist = "drop"` |
| `content = "012"` | `content = "alc"`（与之前行为相同，可任意组合） |
| `[download.song]` | `[download.audio]` |
| `quality = "999"` | `quality = "max"` |
| `embed_mode = "0"` | `embed_mode = "line"` |
| `embed_mode = "1"` | `embed_mode = "block"` |
| `embed_mode = "2"` | `embed_mode = "drop"` |
| `save_mode = "0"` | `save_mode = "line"` |
| `save_mode = "1"` | `save_mode = "block"` |
| `save_mode = "2"` | `save_mode = "split"` |
| `embed_quality = "0"` | `embed_compress = false` |
| `embed_quality = "1"` | `embed_compress = true` |
| `save_quality = "0"` | `save_compress = false` |
| `save_quality = "1"` | `save_compress = true` |
| `virtual_singer_color = true` | `[display] artist_color = true` |
| `cache.dir` | 删除，缓存固定在 `VNCMD_HOME/cache` |
| `credit_prefixes` | 删除，由程序处理 |
| 新增 | `[download] check` |
| 新增 | `[download] downloader` |
| 新增 | `[download] curl_arg` |
| 新增 | `[cache] ttl` |

### 命令行参数

| 旧写法 | 新写法 |
| --- | --- |
| `vncmd init` | `vncmd --init` |
| `vncmd check <路径>` | `vncmd tool check <路径>` |
| `-n`、`--limit N` | `-c`、`--count N` |
| `--lyrics` | `--lyric`、`-l` |
| `--tlyric` | `--lyric --translate` |
| `--url` | `--dlink`、`-u` |
| `--fetch-auto` | `--fetch --auto-accept`、`-f -A` |
| `-q`、`--quality` | `--config download.audio.quality=...` |
| `-o`、`--output` | `--config download.dir=...` |

v1 新增的常用参数：

- `--version`、`-v`
- `--json`、`-j`
- `--dlink`、`-u`
- `--config`、`-C`
- `--force`、`-F`
- `--auto-accept`、`-A`
- `--diff`、`-x`

### Tracker 数据

每个 Tracker 都需要迁移。  
你需要先删除每个 Tracker 目录中的 `diff.json` 文件，清理缓存，然后覆盖更新。

```bash
vncmd tool cache --clear  # 清理缓存
vncmd tracker <name> -fF  # 强制刷新 Tracker 数据
```
