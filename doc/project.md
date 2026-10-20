# 项目

## 流程

CLI（`src/vncmd/cli.py`）：

- `cli.py`：入口、配置覆盖、参数互斥与命令分派
- `parser.py`：参数定义与帮助文案
- `commands.py`：各个子命令的实现
- `downloader.py`：编排下载流程
- `session.py`：会话目录与断点流程
- `checkpoint.py`：下载断点读写
- `tracker.py`：歌单/专辑变更追踪与同步
- `core/`
  - `config.py`：配置读取与校验
  - `schema.py`：配置键表，记录每一项的取值范围、默认值与报错措辞
  - `defaults.py`：默认配置模板，缺文件时用它写出
  - `jsonstore.py`：JSON 的容错读取与原子替换
  - `output.py`：终端输出，表格与进度条
  - `vocals.py`：虚拟歌手的代表色
- `net/`
  - `api.py`：请求网易云 API
  - `cache.py`：曲目详情、歌词与账号状态的磁盘缓存
  - `download.py`：流式下载音频、封面、歌词
- `media/`
  - `audio.py`：文件名、路径
  - `checker.py`：校验工具探测与音频完整性校验
  - `image.py`：封面缩放压缩
  - `lyrics.py`：歌词交错/合并/拆分，以及 credit 解析
  - `metadata.py`：嵌入 MP3/FLAC 元数据

## 环境

`python >= 3.11`，建议使用 `uv`。

```bash
uv sync
```

## 测试

```bash
uv run pytest test/ [-v] [-m "not network"] [--cov=vncmd --cov-report=term-missing]
```

## 发版

```bash
uv run tools/clean.py
# 更新 pyproject.toml version
uv lock
uv build
uv run twine upload dist/*
```
