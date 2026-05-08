# Tracker

Trackers work like Git — a local record of your music lists that you can sync against upstream changes. You can manage multiple trackers, each combining songs, playlists, and albums.

## Creating

Run `vncmd tracker "name"` to create a new tracker. If the name already exists, it shows the current tracker info.

Tracker names are folder names under `.vncmd/tracker/`. Only letters, digits, hyphens, and underscores are allowed. Duplicate names are rejected.

After creation, edit `.vncmd/tracker/<name>/settings.toml` to add source IDs.

## Configuration

`[tracker].description` is a display-only label for your own reference.

The three `sources` sections hold IDs for songs, playlists, and albums. Each accepts multiple values in the `ids` array.

When fetching, sources are processed in order. If a song appears in multiple sources, the cache records an `at` field marking all of them.

## Usage

```bash
vncmd tracker "name" -f         # Fetch & interactive conflict resolution
vncmd tracker "name" -d         # Download all cached tracks
vncmd tracker "name" -d --diff  # Download only tracks added since last fetch
```

### Conflict Resolution

`-f` fetches changes and shows three categories for manual resolution:

- **Added**: present upstream, missing locally
- **Removed**: missing upstream, present locally
- **Changed**: same ID, different title

`--fetch-auto` accepts all changes automatically, mirroring the upstream. A backup is made before each write — restore from `.bak` if needed.

## Full Command

```bash
vncmd tracker <name> [-f | --fetch-auto] [-d] [--diff] [--dry-run] [-q quality] [-o dir]
```

| Flag | Short | Description |
| --- | --- | --- |
| `--fetch` | `-f` | Fetch and resolve conflicts interactively |
| `--fetch-auto` | `/` | Auto-sync, mirror upstream |
| `--diff` | `/` | Download only tracks added since last fetch (needs `-d`) |
| `--download` | `-d` | Download all cached tracks |
| `--dry-run` | `/` | Preview only, no actual download |

Without arguments, shows tracker info.
