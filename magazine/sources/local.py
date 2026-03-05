"""Import photos from a local folder."""

import json
import shutil
from pathlib import Path

import click
from tqdm import tqdm

from magazine.config import (
    SUPPORTED_EXTENSIONS,
    ORIGINALS_DIR,
    THUMBNAILS_DIR,
    PHOTOS_MANIFEST,
)
from magazine.processing.images import (
    convert_to_jpeg,
    make_thumbnail,
    get_exif_date,
    get_image_dimensions,
)


def scan_folder(folder: str | Path) -> list[Path]:
    """Recursively find all supported image files in a folder."""
    folder = Path(folder)
    files = []
    for f in sorted(folder.rglob("*")):
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(f)
    return files


def import_local_photos(folder: str | Path) -> list[dict]:
    """Import photos from a local folder into the workspace.

    1. Scan for supported image files
    2. Copy/convert to workspace/originals/ as JPEG
    3. Generate thumbnails in workspace/thumbnails/
    4. Save manifest with metadata
    """
    folder = Path(folder)
    click.echo(f"Scanning {folder}...")
    files = scan_folder(folder)
    click.echo(f"Found {len(files)} photos")

    if not files:
        click.echo("No photos found. Check the path and supported formats.")
        return []

    photos = []

    for i, src in enumerate(tqdm(files, desc="Importing")):
        # Unique name to avoid collisions
        stem = f"{i:04d}_{src.stem}"
        dest_original = ORIGINALS_DIR / f"{stem}.jpg"

        # Convert to JPEG (handles HEIC, PNG, etc.)
        needs_conversion = src.suffix.lower() not in (".jpg", ".jpeg")
        if needs_conversion:
            convert_to_jpeg(src, dest_original)
        else:
            # Copy and fix rotation
            shutil.copy2(src, dest_original)

        # Generate thumbnail
        thumb_path = make_thumbnail(dest_original, THUMBNAILS_DIR)

        # Extract metadata
        date_taken = get_exif_date(src)
        width, height = get_image_dimensions(dest_original)

        photos.append({
            "id": stem,
            "original": str(dest_original),
            "thumbnail": str(thumb_path),
            "source_path": str(src),
            "date_taken": date_taken,
            "width": width,
            "height": height,
        })

    # Save manifest
    with open(PHOTOS_MANIFEST, "w") as f:
        json.dump(photos, f, indent=2)

    click.echo(f"Imported {len(photos)} photos to workspace")
    return photos
