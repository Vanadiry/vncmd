# Detailed Guide

[Configuration](config.md)  
[Search](search.md)  
[Songs / Playlists / Albums](music.md)  
[Tracker](tracker.md)  
[Project](project.md)  
[Other](other.md)

## Basic Commands

| Command | Description |
| :--- | :--- |
| `search <keyword>` | Search for songs |
| `song <ID>` | Preview a song |
| `playlist <ID>` | Preview a playlist |
| `album <ID>` | Preview an album |
| `tracker <name>` | Create / view a tracker |

For `song/playlist/album`:

- `-d`: Add `-d` to download.
- `-n`: Use `-n <number>` to limit results. Without it, preview defaults to 10 and download defaults to all.

See [music](music.md) for full parameter details.

## Cookie

Downloading VIP tracks or high-quality audio requires a Cookie. Obtain one yourself and paste it into `~/.vncmd/cookie`.

### Getting IDs

Track, playlist, and album IDs are in the URL's `id` parameter:
`https://.../song?id=409926`

- Official app: Share → copy link. For short links, open in a browser first, then copy the address bar.
- Web version: Check the address bar directly.

## Other

Preview and download operations write cache to `~/.vncmd/cache/`. You can delete this folder at any time.
