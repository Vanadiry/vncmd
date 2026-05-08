# Project

## Architecture

CLI (vncmd.py):

- `api.py`: NetEase Cloud Music API client with caching
- `downloader.py`: Download orchestration
  - `download.py`: Streaming download (audio, cover, lyrics)
  - `image.py`: Cover resizing and compression
  - `lyrics.py`: Lyrics interleaving, merging, splitting
  - `metadata.py`: MP3/FLAC metadata embedding
  - `audio.py`: Filename and path utilities
- `checkpoint.py`: Download resume and progress tracking
- `tracker.py`: Playlist/album change tracking and sync

## Testing

```bash
pytest test/ [-v] [--cov] [-m "not network"]
```
