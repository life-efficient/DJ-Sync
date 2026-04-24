# YouTube to Dropbox DJ Sync

This project is a local CLI that:

- reads liked items from YouTube
- filters out obvious non-music items
- downloads MP3 audio with `yt-dlp`
- keeps the library flat, not nested in artist folders
- uploads the same flat files into Dropbox
- remembers what it has already processed so reruns are incremental

## Current Behavior

- Output files are named as `Artist - Title.mp3`
- YouTube `Topic` suffixes are stripped from artist names
- Files stay flat in both the local library and Dropbox
- Dropbox uploads go to the configured `DROPBOX_ROOT`
- Duplicate prevention currently works at the source-video and destination-path level

## Setup

1. Install dependencies:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv sync
```

2. Create `.env`:

```bash
GOOGLE_CLIENT_ID=your_google_oauth_client_id
GOOGLE_CLIENT_SECRET=your_google_oauth_client_secret
DROPBOX_APP_KEY=your_dropbox_app_key
DROPBOX_APP_SECRET=your_dropbox_app_secret
DROPBOX_ROOT=/Music
YTDLP_COOKIES_FROM_BROWSER=
```

3. Create one Google OAuth app and one Dropbox app:

- Google: create an OAuth client and copy its client ID and secret
- Dropbox: create an app with file read/write scopes and copy its app key and secret

4. Connect both services once:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ytm-dropbox-dj-sync auth-youtube
UV_CACHE_DIR=/tmp/uv-cache uv run ytm-dropbox-dj-sync auth-dropbox
```

This stores refreshable auth in `.secrets/` so future runs can renew access automatically.

5. Preview a run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ytm-dropbox-dj-sync sync --dry-run --limit 25
```

6. Run the real sync:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ytm-dropbox-dj-sync sync --limit 200
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

- [/Users/harryberg/Documents/Codex/2026-04-24/i-want-to-build-something-in-3/FOR_AGENTS.md](/Users/harryberg/Documents/Codex/2026-04-24/i-want-to-build-something-in-3/FOR_AGENTS.md)

That document explains how to:

- clone or locate the repo
- install the CLI
- copy the `dj-sync` skill into the agent workspace skills directory
- validate with a dry run
- install a recurring daily cron job

## Notes

- Dropbox uses a refresh-token flow, so you should not need to replace expiring access tokens by hand.
- If a file already exists at the target Dropbox path, it is skipped by default.
- If some videos need browser cookies to download, set `YTDLP_COOKIES_FROM_BROWSER` to `chrome`, `brave`, or `safari`.
- Borderline items are excluded unless you pass `--include-borderline`.
- If your Dropbox app is an App Folder app, the configured path may appear under `Apps/...` in Dropbox rather than true root.
