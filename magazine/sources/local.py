"""Import photos from a local folder."""

from pathlib import Path

import click

from magazine.services.importer import import_local_folder


def import_local_photos(folder: str | Path) -> list[dict]:
    """Import photos from a local folder into the workspace."""
    folder = Path(folder)
    click.echo(f"Scanning {folder}...")
    result = import_local_folder(folder)
    click.echo(
        f"Imported {result['imported']} photos"
        f" ({result['skipped']} duplicates skipped from {result['total']} files)"
    )
    return result["photos"]
