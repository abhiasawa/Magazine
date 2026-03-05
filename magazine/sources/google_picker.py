"""Google Photos Picker API integration for selecting and downloading photos."""

import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import click
import requests
from google_auth_oauthlib.flow import Flow

from magazine.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    GOOGLE_SCOPES,
    PICKER_API_BASE,
    ORIGINALS_DIR,
    THUMBNAILS_DIR,
    PHOTOS_MANIFEST,
)
from magazine.processing.images import (
    make_thumbnail,
    get_exif_date,
    get_image_dimensions,
    fix_exif_rotation,
)


class GooglePhotoPicker:
    """Manages the Google Photos Picker API flow."""

    def __init__(self):
        self.credentials = None
        self.session_id = None
        self.picker_uri = None

    def get_auth_url(self) -> str:
        """Generate OAuth authorization URL."""
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            raise click.ClickException(
                "Google OAuth credentials not configured.\n"
                "1. Create a project at https://console.cloud.google.com\n"
                "2. Enable the Google Photos Picker API\n"
                "3. Create OAuth 2.0 credentials\n"
                "4. Copy .env.example to .env and fill in your credentials"
            )

        client_config = {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [GOOGLE_REDIRECT_URI],
            }
        }

        self.flow = Flow.from_client_config(client_config, scopes=GOOGLE_SCOPES)
        self.flow.redirect_uri = GOOGLE_REDIRECT_URI

        auth_url, _ = self.flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return auth_url

    def handle_callback(self, authorization_response: str):
        """Exchange authorization code for credentials."""
        self.flow.fetch_token(authorization_response=authorization_response)
        self.credentials = self.flow.credentials

    def create_session(self) -> str:
        """Create a Picker API session, returns pickerUri."""
        resp = requests.post(
            f"{PICKER_API_BASE}/sessions",
            headers={
                "Authorization": f"Bearer {self.credentials.token}",
                "Content-Type": "application/json",
            },
            json={},
        )
        resp.raise_for_status()
        data = resp.json()
        self.session_id = data["id"]
        self.picker_uri = data["pickerUri"]
        return self.picker_uri

    def poll_session(self, timeout: int = 600) -> bool:
        """Poll session until user finishes selecting photos.

        Returns True if media items were set, False on timeout.
        """
        start = time.time()
        while time.time() - start < timeout:
            resp = requests.get(
                f"{PICKER_API_BASE}/sessions/{self.session_id}",
                headers={"Authorization": f"Bearer {self.credentials.token}"},
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("mediaItemsSet"):
                return True

            poll_interval = int(data.get("pollInterval", "5").rstrip("s"))
            time.sleep(poll_interval)

        return False

    def get_media_items(self) -> list[dict]:
        """Retrieve all selected media items (paginated)."""
        items = []
        page_token = None

        while True:
            params = {"sessionId": self.session_id, "pageSize": 100}
            if page_token:
                params["pageToken"] = page_token

            resp = requests.get(
                f"{PICKER_API_BASE}/mediaItems",
                headers={"Authorization": f"Bearer {self.credentials.token}"},
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

            items.extend(data.get("mediaItems", []))

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return items

    def download_photo(self, item: dict, dest_dir: Path) -> Path | None:
        """Download a single photo from its baseUrl."""
        try:
            media_file = item.get("mediaFile", {})
            base_url = media_file.get("baseUrl", "")
            if not base_url:
                return None

            # Request full resolution
            width = media_file.get("mediaFileMetadata", {}).get("width", 4000)
            height = media_file.get("mediaFileMetadata", {}).get("height", 3000)
            download_url = f"{base_url}=w{width}-h{height}"

            resp = requests.get(download_url, timeout=60)
            resp.raise_for_status()

            item_id = item.get("id", "unknown")
            filename = f"google_{item_id}.jpg"
            dest = dest_dir / filename

            with open(dest, "wb") as f:
                f.write(resp.content)

            return dest
        except Exception as e:
            click.echo(f"Failed to download {item.get('id', '?')}: {e}")
            return None

    def download_all(self, items: list[dict]) -> list[Path]:
        """Download all media items in parallel."""
        paths = []

        def _download(item):
            return self.download_photo(item, ORIGINALS_DIR)

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(_download, items))

        return [p for p in results if p is not None]


def import_google_photos():
    """Run the Google Photos import flow using Flask for OAuth callback."""
    from flask import Flask, request, redirect

    picker = GooglePhotoPicker()
    app = Flask(__name__)
    server_thread = None

    @app.route("/")
    def index():
        auth_url = picker.get_auth_url()
        return redirect(auth_url)

    @app.route("/oauth/callback")
    def oauth_callback():
        picker.handle_callback(request.url)
        picker_uri = picker.create_session()
        return (
            f'<h2>Authorization successful!</h2>'
            f'<p>Now select your photos in Google Photos:</p>'
            f'<p><a href="{picker_uri}" target="_blank">Open Google Photos Picker</a></p>'
            f'<p>After selecting photos, come back here and '
            f'<a href="/wait">click here to download</a>.</p>'
        )

    @app.route("/wait")
    def wait_for_selection():
        click.echo("Waiting for photo selection...")
        success = picker.poll_session(timeout=600)
        if not success:
            return "<h2>Timeout waiting for photo selection.</h2>"

        items = picker.get_media_items()
        click.echo(f"Found {len(items)} selected photos. Downloading...")
        paths = picker.download_all(items)
        click.echo(f"Downloaded {len(paths)} photos.")

        # Process downloaded photos (thumbnails + manifest)
        from tqdm import tqdm
        photos = []
        for i, photo_path in enumerate(tqdm(paths, desc="Processing")):
            stem = photo_path.stem
            thumb = make_thumbnail(photo_path, THUMBNAILS_DIR)
            date_taken = get_exif_date(photo_path)
            width, height = get_image_dimensions(photo_path)

            photos.append({
                "id": stem,
                "original": str(photo_path),
                "thumbnail": str(thumb),
                "source_path": f"google_photos:{stem}",
                "date_taken": date_taken,
                "width": width,
                "height": height,
            })

        # Merge with existing manifest if any
        existing = []
        if PHOTOS_MANIFEST.exists():
            with open(PHOTOS_MANIFEST) as f:
                existing = json.load(f)

        existing.extend(photos)
        with open(PHOTOS_MANIFEST, "w") as f:
            json.dump(existing, f, indent=2)

        # Shutdown the server
        func = request.environ.get("werkzeug.server.shutdown")
        if func:
            func()

        return (
            f"<h2>Done!</h2>"
            f"<p>Downloaded and processed {len(paths)} photos.</p>"
            f"<p>You can close this window and return to the terminal.</p>"
        )

    click.echo("Opening browser for Google Photos authorization...")
    click.launch("http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
