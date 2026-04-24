# DJ Sync

Use this skill when the task is to run or maintain the YouTube-to-Dropbox DJ sync job.

## Purpose

This workflow syncs liked YouTube items into a flat MP3 library in Dropbox for DJ deck use.

The sync CLI lives in the `DJ-Sync` repository and should be treated as the source of truth. Do not reimplement the sync logic in the agent.

## What This Skill Should Do

1. Go to the local `DJ-Sync` checkout.
2. Ensure dependencies are installed.
3. Confirm required config and auth files exist.
4. Run the CLI sync command.
5. Report success, skips, and failures clearly.
6. If asked to automate, install a recurring daily cron job that runs the same sync command.

## Expected Repo Layout

The repo should contain:

- `pyproject.toml`
- `.env`
- `.secrets/`
- `.data/`
- `library/`

Important files:

- `.env`: Google and Dropbox app credentials plus runtime config
- `.secrets/ytmusic-oauth.json`: Google OAuth token
- `.secrets/dropbox-oauth.json`: Dropbox OAuth token
- `.data/sync-state.json`: processed/skipped/failed history

## Setup

From the repo root:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv sync
```

If `.env` is missing, stop and report that setup is incomplete.

If either OAuth file is missing, do not invent a workaround. Report that one-time auth is required unless the user explicitly asks you to perform it.

## Primary Command

Run the real sync with:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ytm-dropbox-dj-sync sync --limit 200
```

Useful alternatives:

Dry run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ytm-dropbox-dj-sync sync --dry-run --limit 50
```

Retry previously failed items:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ytm-dropbox-dj-sync sync --limit 200 --retry-failed
```

Include borderline items:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ytm-dropbox-dj-sync sync --limit 200 --include-borderline
```

## Success Criteria

A healthy run should:

- complete without a shell error
- print a summary with uploaded, skipped, and failed counts
- keep files flat rather than nested in artist folders
- write files into Dropbox under the configured `DROPBOX_ROOT`

## Guardrails

- Do not delete existing files unless the user explicitly asks.
- Do not re-run interactive auth flows unless credentials are actually missing or broken.
- Do not rewrite the sync tool when the task is just to run it.
- Prefer the existing CLI over ad hoc scripts.
- Keep the Dropbox library flat. Do not create artist subfolders.

## Daily Automation

If the user asks for recurring automation, set up a daily cron job that runs the primary command from the repo root.

The cron job should:

- `cd` into the repo root first
- use `UV_CACHE_DIR=/tmp/uv-cache`
- append stdout and stderr to a log file
- run once daily

Example command payload:

```bash
cd /path/to/DJ-Sync && UV_CACHE_DIR=/tmp/uv-cache uv run ytm-dropbox-dj-sync sync --limit 200 >> .data/cron.log 2>&1
```

Use the actual repo path on the machine instead of the placeholder path above.

## Troubleshooting

- If the CLI reports auth problems, check `.env` and `.secrets/`.
- If the sync runs but uploads nothing, inspect `.data/sync-state.json` and the summary output.
- If `yt-dlp` needs browser cookies, check whether `YTDLP_COOKIES_FROM_BROWSER` is set in `.env`.
- If Dropbox paths look wrong, inspect `DROPBOX_ROOT` in `.env`.

## Response Style

When reporting back:

- say whether the run succeeded
- include the summary counts
- mention any failures plainly
- mention whether automation was installed or updated
