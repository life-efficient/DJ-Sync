# YouTube to Dropbox DJ Sync

This project is a local CLI that:

- reads liked items from YouTube
- filters out obvious non-music items
- downloads MP3 audio with `yt-dlp`
- keeps the library flat, not nested in artist folders
- uploads the same flat files into Dropbox
- remembers what it has already processed so reruns are incremental

## Install

From a GitHub release artifact:

```bash
pip install https://github.com/life-efficient/DJ-Sync/releases/download/v0.2.0/ytm_dropbox_dj_sync-0.2.0-py3-none-any.whl
```

From source during development:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv sync
```

## Current Behavior

- Output files are named as `Artist - Title.mp3`
- YouTube `Topic` suffixes are stripped from artist names
- Files stay flat in both the local library and Dropbox
- Dropbox uploads go to the configured `DROPBOX_ROOT`
- Regular `sync` behaves like a forward incremental sync and stops when it reaches the first existing uploaded music file
- `backfill` imports older missing tracks in bounded batches without relying on historical sync state
- Duplicate prevention currently works at the destination-path level and by stopping at the first known uploaded track during forward sync

## Setup

1. Create `.env`:

```bash
GOOGLE_CLIENT_ID=your_google_oauth_client_id
GOOGLE_CLIENT_SECRET=your_google_oauth_client_secret
DROPBOX_APP_KEY=your_dropbox_app_key
DROPBOX_APP_SECRET=your_dropbox_app_secret
DROPBOX_ROOT=/Music
YTDLP_COOKIES_FROM_BROWSER=
```

2. Create one Google OAuth app and one Dropbox app:

- Google: create an OAuth client and copy its client ID and secret
- Dropbox: create an app with file read/write scopes and copy its app key and secret

3. Connect both services once:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ytm-dropbox-dj-sync auth-youtube
UV_CACHE_DIR=/tmp/uv-cache uv run ytm-dropbox-dj-sync auth-dropbox
```

This stores refreshable auth in `.secrets/` so future runs can renew access automatically.

4. Preview a run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ytm-dropbox-dj-sync sync --dry-run --limit 25
```

5. Run the real sync:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ytm-dropbox-dj-sync sync --limit 200
```

6. Optional: backfill older missing tracks in batches:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ytm-dropbox-dj-sync backfill --count 25 --limit 1000
```

7. Optional: install automatic background syncing on macOS:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ytm-dropbox-dj-sync install-launch-agent --interval-minutes 30
```

## What Gets Created

- `library/`: local DJ-ready files
- `.data/sync-state.json`: processed and failed history
- `.secrets/ytmusic-oauth.json`: Google OAuth token
- `.secrets/dropbox-oauth.json`: Dropbox OAuth token

## Automation

If an agent is setting this up inside another environment, direct it to:

- [FOR_AGENTS.md](/Users/harryberg/projects/ytm-dropbox-dj-sync/FOR_AGENTS.md)

That document explains how to:

- clone or locate the repo
- install the CLI
- copy the `dj-sync` skill into the agent workspace skills directory
- validate with a dry run
- install a recurring daily cron job

## Notes

- Dropbox uses a refresh-token flow, so you should not need to replace expiring access tokens by hand.
- If secret files are missing, the CLI can also bootstrap them from environment variables such as `GOOGLE_REFRESH_TOKEN` and `DROPBOX_REFRESH_TOKEN`.
- If a file already exists at the target Dropbox path, it is skipped by default.
- If some videos need browser cookies to download, set `YTDLP_COOKIES_FROM_BROWSER` to `chrome`, `brave`, or `safari`.
- Borderline items are excluded unless you pass `--include-borderline`.
- If your Dropbox app is an App Folder app, the configured path may appear under `Apps/...` in Dropbox rather than true root.
