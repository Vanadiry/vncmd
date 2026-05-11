# vncmd

NetEase Cloud Music CLI download tool.

Built because the old downloader stopped working and nothing else handled metadata embedding properly.

This project does not bypass DRM — you must be a VIP to download VIP content.
For educational and personal use only. Please delete downloaded data within 24 hours.

[Guide](guide.md) \| [简体中文](../guide.md)  
[GitHub](https://github.com/Vanadiry/vncmd) \| [PyPI](https://pypi.org/project/vncmd/) \| [Blog](https://magic.vanadiry.com/wiki/vncmd/)

> English documentation is machine-translated. Refer to [简体中文](../guide.md) for the original.

## Features

- Search for songs (with lyrics preview)
- Download songs, playlists, and albums (with embedded metadata and cover art, VIP/high-quality via Cookie)
- Bilingual lyrics in interleaved, merged, or original modes
- Tracker: track playlists/albums for changes and batch sync
- Download lyrics or cover art only
- Resume interrupted downloads with checkpoint progress

## Quick Start

```bash
pip install vncmd
vncmd init
```

Config and cache default to `~/.vSoft/vncmd/`, customizable via `VNCMD_HOME` environment variable.
Downloads default to `~/Downloads/vncmd-dl/`, configurable in `config.toml`.

```bash
# Search
vncmd search "Beyond"

# Preview & download — numbers are track IDs; add -d to download
# song / playlist / album
vncmd song 409926              # preview
vncmd song 409926 -d           # download
vncmd playlist 17647459371     # preview
vncmd playlist 17647459371 -d -n 5   # download first 5
vncmd album 405493 -d          # download

# Tracker
vncmd tracker my-list          # create / view
vncmd tracker my-list -f       # fetch & interactive merge
```

For known issues including third-party software compatibility, see [Other](other.md).
