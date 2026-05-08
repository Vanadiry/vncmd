# Songs / Playlists / Albums

`song`, `playlist`, and `album` let you preview and download individual tracks, playlists, or albums.

## Common Flags

These flags work across all three commands. `-q`/`-o`/`--dry-run` require `-d`.

| Flag | Short | Description |
| --- | --- | --- |
| `--download` | `-d` | Download |
| `--quality` | `-q` | Override audio quality (128 / 192 / 320 / 999) |
| `--output` | `-o` | Override output directory |
| `--dry-run` | `/` | Preview without downloading |

## song

```bash
vncmd song <ID> [-l] [--tlyric] [-u] [-d] [-q quality] [-o dir]
```

Shows track metadata (title, artist, album, cover URL, duration).

| Flag | Short | Description |
| --- | --- | --- |
| `--lyrics` | `-l` | Show original lyrics |
| `--tlyric` | `/` | Show translated lyrics |
| `--url` | `-u` | Check if stream URL is available |

## playlist / album

```bash
# Playlist
vncmd playlist <ID> [-n count] [-d] [-q quality] [-o dir]
# Album
vncmd album <ID> [-n count] [-d] [-q quality] [-o dir]
```

Displays tracks as a table. If the playlist contains removed tracks, they are listed separately.

| Flag | Short | Default | Description |
| --- | --- | --- | --- |
| `--limit` | `-n` | `10` | Preview count (display-only, API always fetches all); downloads all by default |
