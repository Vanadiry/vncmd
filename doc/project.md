# 项目

## 流程

CLI（`src/vncmd/cli.py`）：

- `cli.py`：参数解析与命令分派，控制台入口
- `commands.py`：各个子命令的实现
- `api.py`：请求网易云 API
- `cache.py`：曲目详情与歌词的磁盘缓存
- `jsonstore.py`：JSON 的容错读取与原子替换
- `downloader.py`：编排下载流程
  - `download.py`：流式下载音频、封面、歌词
  - `image.py`：封面缩放压缩
  - `lyrics.py`：歌词交错/合并/分别，以及 credit 抽取
  - `metadata.py`：嵌入 MP3/FLAC 元数据
  - `audio.py`：文件名、路径
- `checker.py`：校验工具探测与音频完整性校验
- `checkpoint.py`：下载断点续传
- `tracker.py`：歌单/专辑变更追踪与同步
- `output.py`：终端输出，表格与进度条
- `config.py`：配置读取与校验
- `schema.py`：配置键表，记录每一项的取值范围、默认值与报错措辞
- `defaults.py`：默认配置模板，缺文件时用它写出
- `vocals.py`：虚拟歌手的代表色

## 环境

`python >= 3.11`，建议使用 `uv`。

```bash
uv sync
```

## 测试

```bash
pytest test/ [-v] [--cov] [-m "not network"]
```

## 发版

```bash
uv run tools/clean.py
# 更新 pyproject.toml version
uv build
uv run twine upload dist/*
```
