from __future__ import annotations

import json
import plistlib
import re
import shutil
import subprocess
import webbrowser
from dataclasses import asdict, dataclass, field
from hashlib import sha1
from pathlib import Path
from typing import Any

import dropbox
import typer
from dotenv import load_dotenv
from dropbox import files
from dropbox.oauth import DropboxOAuth2FlowNoRedirect
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC, ID3NoHeaderError
from ytmusicapi import setup_oauth

app = typer.Typer(add_completion=False, no_args_is_help=True)

DROPBOX_APP_SCOPES = [
    "account_info.read",
    "files.metadata.read",
    "files.metadata.write",
    "files.content.read",
    "files.content.write",
]

NEGATIVE_PATTERNS = [
    r"\bpodcast\b",
    r"\bepisode\b",
    r"\bshorts?\b",
    r"\binterview\b",
    r"\breaction\b",
    r"\breview\b",
    r"\btutorial\b",
    r"\bcommentary\b",
    r"\bhighlights?\b",
    r"\btrailer\b",
    r"\bvlog\b",
    r"\bnews\b",
    r"\baudiobook\b",
    r"\bsermon\b",
    r"\blecture\b",
]

POSITIVE_PATTERNS = [
    r"\bremix\b",
    r"\bmix\b",
    r"\bedit\b",
    r"\bbootleg\b",
    r"\bvip\b",
    r"\bextended\b",
    r"\blive set\b",
    r"\bdj set\b",
    r"\boriginal mix\b",
    r"\bofficial audio\b",
]


@dataclass
class Config:
    project_root: Path
    local_library_dir: Path
    data_dir: Path
    temp_dir: Path
    secrets_dir: Path
    ytmusic_oauth_path: Path
    dropbox_oauth_path: Path
    state_path: Path
    dropbox_root: str
    google_client_id: str
    google_client_secret: str
    dropbox_app_key: str | None
    dropbox_app_secret: str | None
    cookies_from_browser: str | None

    @classmethod
    def load(cls) -> "Config":
        project_root = Path.cwd()
        load_dotenv(project_root / ".env")

        google_client_id = env("GOOGLE_CLIENT_ID")
        google_client_secret = env("GOOGLE_CLIENT_SECRET")

        data_dir = project_root / ".data"
        secrets_dir = project_root / ".secrets"
        temp_dir = project_root / ".tmp"
        local_library_dir = project_root / "library"

        return cls(
            project_root=project_root,
            local_library_dir=local_library_dir,
            data_dir=data_dir,
            temp_dir=temp_dir,
            secrets_dir=secrets_dir,
            ytmusic_oauth_path=secrets_dir / "ytmusic-oauth.json",
            dropbox_oauth_path=secrets_dir / "dropbox-oauth.json",
            state_path=data_dir / "sync-state.json",
            dropbox_root=normalize_dropbox_path(env("DROPBOX_ROOT", "/Apps/YTM DJ Sync")),
            google_client_id=google_client_id,
            google_client_secret=google_client_secret,
            dropbox_app_key=env("DROPBOX_APP_KEY"),
            dropbox_app_secret=env("DROPBOX_APP_SECRET"),
            cookies_from_browser=env("YTDLP_COOKIES_FROM_BROWSER"),
        )

    def ensure_dirs(self) -> None:
        self.local_library_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.secrets_dir.mkdir(parents=True, exist_ok=True)


@dataclass
class Track:
    video_id: str
    title: str
    artists: list[str]
    album: str | None
    duration_seconds: int | None
    video_type: str | None
    is_available: bool
    is_explicit: bool
    playlist_index: int
    thumbnail_url: str | None
    description: str | None = None


@dataclass
class Classification:
    label: str
    score: int
    reasons: list[str] = field(default_factory=list)


@dataclass
class SyncRecord:
    video_id: str
    title: str
    artists: list[str]
    album: str | None
    local_path: str
    dropbox_path: str
    file_size_bytes: int
    sha1: str
    classification: dict[str, Any]


@app.command("auth-youtube")
def auth_youtube(open_browser: bool = typer.Option(True, help="Open the browser automatically.")) -> None:
    """Connect this project to your YouTube Music account."""
    config = Config.load()
    config.ensure_dirs()
    if not config.google_client_id or not config.google_client_secret:
        raise typer.BadParameter("Missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET in .env")

    typer.echo(f"Writing OAuth token to {config.ytmusic_oauth_path}")
    setup_oauth(
        client_id=config.google_client_id,
        client_secret=config.google_client_secret,
        filepath=str(config.ytmusic_oauth_path),
        open_browser=open_browser,
    )
    typer.echo("YouTube Music is connected.")


@app.command("auth-dropbox")
def auth_dropbox(open_browser: bool = typer.Option(True, help="Open the browser automatically.")) -> None:
    """Connect this project to Dropbox with a refreshable token."""
    config = Config.load()
    config.ensure_dirs()

    if not config.dropbox_app_key:
        raise typer.BadParameter("Missing DROPBOX_APP_KEY in .env")
    if not config.dropbox_app_secret:
        typer.echo("DROPBOX_APP_SECRET is empty; using PKCE flow with app key only.")

    flow = DropboxOAuth2FlowNoRedirect(
        consumer_key=config.dropbox_app_key,
        consumer_secret=config.dropbox_app_secret,
        token_access_type="offline",
        scope=DROPBOX_APP_SCOPES,
        use_pkce=config.dropbox_app_secret is None,
    )
    authorize_url = flow.start()

    typer.echo("\nOpen this Dropbox URL and approve access:\n")
    typer.echo(authorize_url)
    typer.echo("")
    if open_browser:
        webbrowser.open(authorize_url)

    code = typer.prompt("Paste the Dropbox authorization code")
    result = flow.finish(code.strip())
    payload = {
        "app_key": config.dropbox_app_key,
        "app_secret": config.dropbox_app_secret,
        "refresh_token": result.refresh_token,
        "access_token": result.access_token,
        "account_id": result.account_id,
        "scopes": result.scope,
    }
    config.dropbox_oauth_path.write_text(json.dumps(payload, indent=2) + "\n")
    typer.echo(f"Dropbox token saved to {config.dropbox_oauth_path}")


@app.command()
def setup(open_browser: bool = typer.Option(True, help="Open browser windows during auth.")) -> None:
    """Run the one-time auth setup for both services."""
    auth_youtube(open_browser=open_browser)
    auth_dropbox(open_browser=open_browser)
    typer.echo("Setup complete.")


@app.command()
def sync(
    limit: int = typer.Option(200, min=1, help="How many liked items to inspect."),
    dry_run: bool = typer.Option(False, help="Show decisions without downloading or uploading."),
    include_borderline: bool = typer.Option(
        False,
        help="Include items that look maybe-musical instead of clearly musical.",
    ),
    retry_failed: bool = typer.Option(False, help="Retry items that failed previously."),
    overwrite_dropbox: bool = typer.Option(False, help="Overwrite files that already exist in Dropbox."),
) -> None:
    """Sync liked YouTube Music tracks into the local library and Dropbox."""
    config = Config.load()
    config.ensure_dirs()
    youtube = build_youtube_client(config)
    dbx = build_dropbox_client(config)
    state = load_state(config.state_path)

    tracks = get_liked_tracks(youtube, limit)

    typer.echo(f"Loaded {len(tracks)} liked items from YouTube.")

    uploaded_count = 0
    skipped_count = 0
    failed_count = 0

    for track in tracks:
        if track.video_id in state["processed"]:
            typer.echo(f"Skipping already-synced item: {track.title}")
            skipped_count += 1
            continue
        if track.video_id in state["failed"] and not retry_failed:
            typer.echo(f"Skipping previously failed item: {track.title}")
            skipped_count += 1
            continue

        classification = classify_track(track)
        typer.echo(
            f"\n[{track.playlist_index}] {display_artist(track)} - {track.title} "
            f"=> {classification.label} ({classification.score})"
        )

        if classification.label == "skip" or (
            classification.label == "borderline" and not include_borderline
        ):
            skipped_count += 1
            state["processed"][track.video_id] = {
                "video_id": track.video_id,
                "title": track.title,
                "artists": track.artists,
                "album": track.album,
                "classification": asdict(classification),
                "status": "skipped",
            }
            save_state(config.state_path, state)
            continue

        local_path = choose_local_path(config.local_library_dir, track)
        dropbox_path = normalize_dropbox_path(
            f"{config.dropbox_root}/{local_path.relative_to(config.local_library_dir).as_posix()}"
        )

        if dry_run:
            typer.echo(f"Would save to {local_path}")
            typer.echo(f"Would upload to {dropbox_path}")
            skipped_count += 1
            continue

        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            final_path = download_audio(track, local_path, config)
            retag_file(final_path, track)
            upload_file(dbx, final_path, dropbox_path, overwrite=overwrite_dropbox)
            record = SyncRecord(
                video_id=track.video_id,
                title=track.title,
                artists=track.artists,
                album=track.album,
                local_path=str(final_path),
                dropbox_path=dropbox_path,
                file_size_bytes=final_path.stat().st_size,
                sha1=file_sha1(final_path),
                classification=asdict(classification),
            )
            state["processed"][track.video_id] = asdict(record)
            state["failed"].pop(track.video_id, None)
            save_state(config.state_path, state)
            uploaded_count += 1
            typer.echo(f"Synced {final_path.name}")
        except Exception as exc:  # noqa: BLE001
            state["failed"][track.video_id] = {
                "video_id": track.video_id,
                "title": track.title,
                "artists": track.artists,
                "error": str(exc),
            }
            save_state(config.state_path, state)
            failed_count += 1
            typer.echo(f"Failed: {exc}", err=True)

    typer.echo("\nSummary")
    typer.echo(f"Uploaded: {uploaded_count}")
    typer.echo(f"Skipped: {skipped_count}")
    typer.echo(f"Failed: {failed_count}")


@app.command("install-launch-agent")
def install_launch_agent(
    interval_minutes: int = typer.Option(30, min=5, help="How often the sync should run."),
    limit: int = typer.Option(200, min=1, help="How many likes to inspect per run."),
    include_borderline: bool = typer.Option(False, help="Include borderline items automatically."),
) -> None:
    """Install a macOS LaunchAgent so the sync runs on its own."""
    config = Config.load()
    config.ensure_dirs()

    launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
    launch_agents_dir.mkdir(parents=True, exist_ok=True)

    plist_path = launch_agents_dir / "com.harryberg.ytm-dropbox-dj-sync.plist"
    stdout_path = config.data_dir / "launchd.stdout.log"
    stderr_path = config.data_dir / "launchd.stderr.log"
    uv_executable = shutil.which("uv")
    if not uv_executable:
        raise typer.BadParameter("Could not find `uv` on PATH.")

    program_arguments = [
        uv_executable,
        "run",
        "ytm-dropbox-dj-sync",
        "sync",
        "--limit",
        str(limit),
    ]
    if include_borderline:
        program_arguments.append("--include-borderline")

    plist = {
        "Label": "com.harryberg.ytm-dropbox-dj-sync",
        "ProgramArguments": program_arguments,
        "WorkingDirectory": str(config.project_root),
        "EnvironmentVariables": {
            "PATH": env("PATH", "") or "",
            "UV_CACHE_DIR": "/tmp/uv-cache",
        },
        "StartInterval": interval_minutes * 60,
        "RunAtLoad": True,
        "StandardOutPath": str(stdout_path),
        "StandardErrorPath": str(stderr_path),
    }

    plist_path.write_bytes(plistlib.dumps(plist))
    subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)
    typer.echo(f"Installed LaunchAgent at {plist_path}")
    typer.echo(f"Logs will be written to {stdout_path} and {stderr_path}")


@app.command()
def status() -> None:
    """Show whether the project is fully set up for unattended sync."""
    config = Config.load()
    lines = [
        f"YouTube auth: {'ready' if config.ytmusic_oauth_path.exists() else 'missing'}",
        f"Dropbox auth: {'ready' if config.dropbox_oauth_path.exists() else 'missing'}",
        f"State file: {'ready' if config.state_path.exists() else 'not created yet'}",
        f"Library dir: {config.local_library_dir}",
    ]
    for line in lines:
        typer.echo(line)


def main() -> None:
    app()


def env(name: str, default: str | None = None) -> str | None:
    return __import__("os").environ.get(name, default)


def read_required_env(name: str) -> str:
    value = env(name)
    if not value:
        raise typer.BadParameter(f"Missing required environment variable: {name}")
    return value


def build_youtube_client(config: Config):
    if not config.google_client_id or not config.google_client_secret:
        raise typer.BadParameter(
            "Missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET in .env"
        )
    if not config.ytmusic_oauth_path.exists():
        raise typer.BadParameter(
            f"Missing {config.ytmusic_oauth_path}. Run `uv run ytm-dropbox-dj-sync auth-youtube` first."
        )

    auth_payload = json.loads(config.ytmusic_oauth_path.read_text())
    scopes = auth_payload.get("scope")
    if isinstance(scopes, str):
        scopes = scopes.split()

    credentials = Credentials(
        token=auth_payload.get("access_token"),
        refresh_token=auth_payload.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.google_client_id,
        client_secret=config.google_client_secret,
        scopes=scopes,
    )
    credentials.refresh(Request())
    auth_payload["access_token"] = credentials.token
    if credentials.expiry:
        auth_payload["expires_at"] = int(credentials.expiry.timestamp())
    config.ytmusic_oauth_path.write_text(json.dumps(auth_payload, indent=2) + "\n")
    return build("youtube", "v3", credentials=credentials)


def build_dropbox_client(config: Config) -> dropbox.Dropbox:
    if config.dropbox_oauth_path.exists():
        auth_payload = json.loads(config.dropbox_oauth_path.read_text())
        return dropbox.Dropbox(
            oauth2_access_token=auth_payload.get("access_token"),
            oauth2_refresh_token=auth_payload["refresh_token"],
            app_key=auth_payload["app_key"],
            app_secret=auth_payload.get("app_secret"),
        )

    legacy_access_token = env("DROPBOX_ACCESS_TOKEN")
    if legacy_access_token:
        return dropbox.Dropbox(legacy_access_token)

    raise typer.BadParameter(
        f"Missing {config.dropbox_oauth_path}. Run `uv run ytm-dropbox-dj-sync auth-dropbox` first."
    )


def get_liked_tracks(youtube, limit: int) -> list[Track]:
    tracks: list[Track] = []
    page_token = None

    while len(tracks) < limit:
        response = youtube.videos().list(
            part="snippet,contentDetails,status",
            myRating="like",
            maxResults=min(50, limit - len(tracks)),
            pageToken=page_token,
        ).execute()

        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            thumbnails = snippet.get("thumbnails", {})
            thumbnail_url = None
            for key in ["maxres", "standard", "high", "medium", "default"]:
                if key in thumbnails:
                    thumbnail_url = thumbnails[key].get("url")
                    break

            tracks.append(
                Track(
                    video_id=item["id"],
                    title=snippet.get("title", "Untitled"),
                    artists=[snippet.get("channelTitle", "Unknown Artist")],
                    album=None,
                    duration_seconds=parse_iso_duration(item.get("contentDetails", {}).get("duration", "PT0S")),
                    video_type=item.get("kind"),
                    is_available=item.get("status", {}).get("privacyStatus") != "private",
                    is_explicit=False,
                    playlist_index=len(tracks) + 1,
                    thumbnail_url=thumbnail_url,
                    description=snippet.get("description"),
                )
            )

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return tracks


def classify_track(track: Track) -> Classification:
    score = 0
    reasons: list[str] = []
    haystack = " ".join(
        [track.title, " ".join(track.artists), track.album or "", track.description or ""]
    ).lower()

    if not track.is_available:
        return Classification(label="skip", score=-10, reasons=["unavailable"])

    if track.video_type and "youtube#video" in track.video_type:
        score += 1
        reasons.append(f"video_type:{track.video_type}")

    if any("topic" in artist.lower() for artist in track.artists):
        score += 3
        reasons.append("artist-topic-channel")

    if track.album:
        score += 2
        reasons.append("album")

    if track.artists:
        score += 2
        reasons.append("artists")
    else:
        score -= 3
        reasons.append("missing-artists")

    duration = track.duration_seconds or 0
    if 60 <= duration <= 5400:
        score += 2
        reasons.append("duration-normal")
    elif 5400 < duration <= 14400:
        score += 1
        reasons.append("duration-long")
    elif duration and duration < 60:
        score -= 5
        reasons.append("duration-short")
    elif duration > 14400:
        score -= 3
        reasons.append("duration-very-long")

    for pattern in POSITIVE_PATTERNS:
        if re.search(pattern, haystack, re.IGNORECASE):
            score += 1
            reasons.append(f"positive:{pattern}")

    for pattern in NEGATIVE_PATTERNS:
        if re.search(pattern, haystack, re.IGNORECASE):
            score -= 6
            reasons.append(f"negative:{pattern}")

    hard_skip_patterns = [r"\bpodcast\b", r"\bepisode\b", r"\bshorts?\b"]
    if any(re.search(pattern, haystack, re.IGNORECASE) for pattern in hard_skip_patterns):
        return Classification(label="skip", score=score, reasons=reasons)

    if score >= 6:
        return Classification(label="music", score=score, reasons=reasons)
    if score >= 2:
        return Classification(label="borderline", score=score, reasons=reasons)
    return Classification(label="skip", score=score, reasons=reasons)


def choose_local_path(local_library_dir: Path, track: Track) -> Path:
    artist = sanitize_path_component(primary_artist_name(track))
    title = sanitize_path_component(track.title)
    base = local_library_dir / f"{artist} - {title}.mp3"
    if not base.exists():
        return base
    return local_library_dir / f"{artist} - {title} [{track.video_id}].mp3"


def download_audio(track: Track, destination: Path, config: Config) -> Path:
    if destination.exists():
        return destination

    temp_template = config.temp_dir / f"{track.video_id}.%(ext)s"
    command = [
        "yt-dlp",
        f"https://music.youtube.com/watch?v={track.video_id}",
        "--no-playlist",
        "--extract-audio",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "--embed-thumbnail",
        "--add-metadata",
        "--output",
        str(temp_template),
    ]
    if config.cookies_from_browser:
        command.extend(["--cookies-from-browser", config.cookies_from_browser])

    subprocess.run(command, check=True)

    temp_file = config.temp_dir / f"{track.video_id}.mp3"
    if not temp_file.exists():
        raise FileNotFoundError(f"yt-dlp did not create {temp_file}")

    shutil.move(str(temp_file), str(destination))
    return destination


def retag_file(file_path: Path, track: Track) -> None:
    try:
        tags = EasyID3(str(file_path))
    except ID3NoHeaderError:
        tags = EasyID3()
        tags.save(str(file_path))
        tags = EasyID3(str(file_path))

    tags["title"] = [track.title]
    tags["artist"] = normalized_artist_names(track) or ["Unknown Artist"]
    if track.album:
        tags["album"] = [track.album]
    tags.save()

    if track.thumbnail_url:
        try:
            import requests

            response = requests.get(track.thumbnail_url, timeout=30)
            response.raise_for_status()
            artwork = ID3(str(file_path))
            artwork.delall("APIC")
            artwork.add(
                APIC(
                    encoding=3,
                    mime=response.headers.get("Content-Type", "image/jpeg"),
                    type=3,
                    desc="Cover",
                    data=response.content,
                )
            )
            artwork.save(v2_version=3)
        except Exception:
            pass


def upload_file(dbx: dropbox.Dropbox, local_path: Path, dropbox_path: str, overwrite: bool) -> None:
    if not overwrite and dropbox_exists(dbx, dropbox_path):
        return

    ensure_dropbox_folders(dbx, dropbox_path.rsplit("/", 1)[0])
    with local_path.open("rb") as handle:
        payload = handle.read()

    if len(payload) <= 150 * 1024 * 1024:
        dbx.files_upload(
            payload,
            dropbox_path,
            mode=files.WriteMode.overwrite if overwrite else files.WriteMode.add,
            mute=True,
        )
        return

    upload_large_file(dbx, local_path, dropbox_path, overwrite)


def upload_large_file(
    dbx: dropbox.Dropbox,
    local_path: Path,
    dropbox_path: str,
    overwrite: bool,
    chunk_size: int = 8 * 1024 * 1024,
) -> None:
    size = local_path.stat().st_size
    with local_path.open("rb") as handle:
        session = dbx.files_upload_session_start(handle.read(chunk_size))
        cursor = files.UploadSessionCursor(session_id=session.session_id, offset=handle.tell())
        commit = files.CommitInfo(
            path=dropbox_path,
            mode=files.WriteMode.overwrite if overwrite else files.WriteMode.add,
            mute=True,
        )
        while handle.tell() < size:
            remaining = size - handle.tell()
            if remaining <= chunk_size:
                dbx.files_upload_session_finish(handle.read(chunk_size), cursor, commit)
            else:
                dbx.files_upload_session_append_v2(handle.read(chunk_size), cursor)
                cursor.offset = handle.tell()


def dropbox_exists(dbx: dropbox.Dropbox, dropbox_path: str) -> bool:
    try:
        dbx.files_get_metadata(dropbox_path)
        return True
    except dropbox.exceptions.ApiError as exc:
        if exc.error.is_path() and exc.error.get_path().is_not_found():
            return False
        raise


def ensure_dropbox_folders(dbx: dropbox.Dropbox, folder_path: str) -> None:
    if not folder_path or folder_path == "/":
        return

    current = ""
    for part in folder_path.split("/"):
        if not part:
            continue
        current = f"{current}/{part}"
        try:
            dbx.files_create_folder_v2(current)
        except dropbox.exceptions.ApiError as exc:
            if not (exc.error.is_path() and exc.error.get_path().is_conflict()):
                raise


def file_sha1(file_path: Path) -> str:
    digest = sha1()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def display_artist(track: Track) -> str:
    artists = normalized_artist_names(track)
    return ", ".join(artists) if artists else "Unknown Artist"


def normalized_artist_names(track: Track) -> list[str]:
    artists = [normalize_artist_name(artist) for artist in track.artists]
    return [artist for artist in artists if artist] or ["Unknown Artist"]


def primary_artist_name(track: Track) -> str:
    return normalized_artist_names(track)[0]


def normalize_artist_name(value: str) -> str:
    cleaned = re.sub(r"\s+-\s+topic\s*$", "", value, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
    return cleaned or value


def sanitize_path_component(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:120] or "Untitled"


def normalize_dropbox_path(value: str) -> str:
    cleaned = re.sub(r"/{2,}", "/", value.replace("\\", "/"))
    return cleaned if cleaned.startswith("/") else f"/{cleaned}"


def parse_iso_duration(value: str) -> int:
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value or "")
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def load_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {"processed": {}, "failed": {}}
    return json.loads(state_path.read_text())


def save_state(state_path: Path, state: dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2) + "\n")
