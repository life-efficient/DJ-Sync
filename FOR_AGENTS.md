# For Agents

This file explains how to set up and automate the DJ sync tool from a shell inside a container or VM.

## Goal

Set up the DJ Sync CLI, install the `dj-sync` skill into the agent's workspace skills directory, and configure a recurring daily cron job that runs the sync automatically.

## Repository

The sync tool lives in the `DJ-Sync` repository.

If the user provides a git URL, clone from that URL.

If the repo is already present on disk, reuse the existing checkout instead of cloning again.

If neither a repo path nor a git URL is available, stop and ask for the canonical repo location.

## Setup Workflow

1. Clone or locate the `DJ-Sync` repository.
2. Go to the repo root.
3. Install dependencies with:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv sync
```

4. Confirm these exist before attempting unattended sync:

- `.env`
- `.secrets/ytmusic-oauth.json`
- `.secrets/dropbox-oauth.json`

5. If they are missing, report that one-time setup or auth is still required.

## Skill Installation

Copy this skill:

- `skills/dj-sync/SKILL.md`

into the workspace skills directory used by the agent environment.

The installed skill should remain named `dj-sync`.

Do not paraphrase it into some other document if the system expects actual skill files. Copy the file into the proper skills directory so the agent can use it later.

## Validation

Before scheduling automation, validate the CLI with a dry run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ytm-dropbox-dj-sync sync --dry-run --limit 25
```

If that succeeds, run the real sync:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ytm-dropbox-dj-sync sync --limit 200
```

## Daily Cron Job

Install a recurring daily cron job that runs the DJ sync from the repo root.

The cron entry should:

- `cd` into the repo root
- use `UV_CACHE_DIR=/tmp/uv-cache`
- run `uv run ytm-dropbox-dj-sync sync --limit 200`
- append logs to `.data/cron.log`

Example payload:

```bash
cd /path/to/DJ-Sync && UV_CACHE_DIR=/tmp/uv-cache uv run ytm-dropbox-dj-sync sync --limit 200 >> .data/cron.log 2>&1
```

Choose a daily schedule unless the user asks for a different cadence.

## Update Policy

Prefer predictable updates.

- If the repo is pinned to a tag or commit, preserve that pin unless the user asks to upgrade.
- If the repo tracks a branch, pull the latest version before reinstalling dependencies.
- After updates, rerun the dry run before re-enabling or trusting automation.

## Operating Rules

- Use the CLI; do not rebuild its logic in shell scripts.
- Do not delete the auth files or sync state.
- Do not trigger fresh OAuth unless credentials are missing or broken.
- Keep the library flat; nested artist folders are not desired.
- Report clearly if the environment is missing `uv`, network access, repo access, or credentials.

## What To Tell The User

When you finish, report:

- where the repo lives
- where the skill was installed
- whether the dry run succeeded
- whether the real sync succeeded
- whether the daily cron job was installed
- any blockers that still need human action
