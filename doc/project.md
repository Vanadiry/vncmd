# 项目

## 流程

CLI (vnemd.py)：

- `api.py`：请求网易云 API，缓存歌曲/歌词
- `downloader.py`：编排下载流程
  - `download.py`：流式下载音频、封面、歌词
  - `image.py`：封面缩放压缩
  - `lyrics.py`：歌词交错/合并/分别
  - `metadata.py`：嵌入 MP3/FLAC 元数据
  - `audio.py`：文件名、路径

## 测试

```bash
pytest test/ [-v] [--cov] [-m "not network"]
```
