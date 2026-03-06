"""Unified photo import service for local folders, uploads, and provider downloads."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Iterable, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from werkzeug.datastructures import FileStorage
else:
    FileStorage = Any

from magazine.config import (
    SUPPORTED_EXTENSIONS,
    ORIGINALS_DIR,
    THUMBNAILS_DIR,
    PHOTO_HASHES,
    FACE_RESULTS,
)
from magazine.processing.images import (
    convert_to_jpeg,
    make_thumbnail,
    get_exif_date,
    get_image_dimensions,
)
from magazine.services.state import (
    load_json,
    save_json,
    load_photos_manifest,
    save_photos_manifest,
    load_review_state,
    save_review_state,
    normalize_review_entry,
    merge_photos,
)


def scan_folder(folder: str | Path) -> list[Path]:
    folder = Path(folder)
    files = []
    for f in sorted(folder.rglob("*")):
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(f)
    return files


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_jpeg(src: Path, dest: Path) -> Path:
    if src.suffix.lower() in (".jpg", ".jpeg"):
        shutil.copy2(src, dest)
        return dest
    return convert_to_jpeg(src, dest)


def _new_photo_id(src_name: str, content_hash: str, existing_ids: set[str]) -> str:
    base = Path(src_name).stem.lower().replace(" ", "-")
    base = "".join(ch for ch in base if ch.isalnum() or ch in {"-", "_"})[:32] or "photo"
    token = content_hash[:10]
    candidate = f"{base}_{token}"
    idx = 1
    while candidate in existing_ids:
        candidate = f"{base}_{token}_{idx}"
        idx += 1
    return candidate


def _build_photo_record(pid: str, original_path: Path, source_path: str, content_hash: str) -> dict:
    thumb_path = make_thumbnail(original_path, THUMBNAILS_DIR)
    width, height = get_image_dimensions(original_path)
    date_taken = get_exif_date(original_path)
    return {
        "id": pid,
        "original": str(original_path),
        "thumbnail": str(thumb_path),
        "source_path": source_path,
        "date_taken": date_taken,
        "width": width,
        "height": height,
        "hash": content_hash,
    }


def _persist_imported(imported: list[dict]):
    if not imported:
        return 0

    existing = load_photos_manifest()
    merged, added = merge_photos(existing, imported)
    save_photos_manifest(merged)

    review_state = load_review_state()
    for photo in imported:
        pid = photo["id"]
        review_state.setdefault(pid, normalize_review_entry("pending"))
    save_review_state(review_state)

    face_results = load_json(FACE_RESULTS, {})
    if not isinstance(face_results, dict):
        face_results = {}
    for photo in imported:
        face_results.setdefault(photo["id"], {"face_count": -1, "faces": []})
    save_json(FACE_RESULTS, face_results)

    return added


def import_local_folder(folder: str | Path) -> dict:
    files = scan_folder(folder)
    return import_existing_paths(files, source_prefix="local")


def import_existing_paths(paths: Iterable[Path], source_prefix: str) -> dict:
    paths = [Path(p) for p in paths]
    hash_map = load_json(PHOTO_HASHES, {})
    if not isinstance(hash_map, dict):
        hash_map = {}

    existing_ids = {p["id"] for p in load_photos_manifest()}
    imported: list[dict] = []
    skipped = 0

    for src in paths:
        if not src.exists() or src.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        # Hash original bytes to dedupe across imports/sources.
        content_hash = sha256_file(src)
        if content_hash in hash_map:
            skipped += 1
            continue

        pid = _new_photo_id(src.name, content_hash, existing_ids)
        existing_ids.add(pid)

        dest = ORIGINALS_DIR / f"{pid}.jpg"
        final_path = _ensure_jpeg(src, dest)
        rec = _build_photo_record(pid, final_path, f"{source_prefix}:{src}", content_hash)
        imported.append(rec)
        hash_map[content_hash] = pid

    save_json(PHOTO_HASHES, hash_map)
    added = _persist_imported(imported)
    return {
        "total": len(paths),
        "imported": added,
        "skipped": skipped,
        "photos": imported,
    }


def import_uploaded_files(files: list[FileStorage]) -> dict:
    hash_map = load_json(PHOTO_HASHES, {})
    if not isinstance(hash_map, dict):
        hash_map = {}

    existing_ids = {p["id"] for p in load_photos_manifest()}
    imported: list[dict] = []
    skipped = 0

    with tempfile.TemporaryDirectory(prefix="magazine-upload-") as tmp_dir:
        tmp = Path(tmp_dir)
        for storage in files:
            filename = storage.filename or "upload.jpg"
            suffix = Path(filename).suffix.lower()
            if suffix not in SUPPORTED_EXTENSIONS:
                continue

            temp_src = tmp / f"{len(imported) + skipped}_{Path(filename).name}"
            storage.save(temp_src)

            content_hash = sha256_file(temp_src)
            if content_hash in hash_map:
                skipped += 1
                continue

            pid = _new_photo_id(filename, content_hash, existing_ids)
            existing_ids.add(pid)
            dest = ORIGINALS_DIR / f"{pid}.jpg"
            final_path = _ensure_jpeg(temp_src, dest)
            rec = _build_photo_record(pid, final_path, f"upload:{filename}", content_hash)
            imported.append(rec)
            hash_map[content_hash] = pid

    save_json(PHOTO_HASHES, hash_map)
    added = _persist_imported(imported)
    return {
        "total": len(files),
        "imported": added,
        "skipped": skipped,
        "photos": imported,
    }
