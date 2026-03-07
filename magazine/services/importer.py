"""Photo import service for provider-downloaded image files."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Iterable

from magazine.config import (
    SUPPORTED_EXTENSIONS,
    SUPPORTED_VIDEO_EXTENSIONS,
    SUPPORTED_MEDIA_EXTENSIONS,
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
import logging
import subprocess

logger = logging.getLogger(__name__)


def _extract_video_frame(video_path: Path, dest_jpeg: Path, seek_seconds: float = 2.0) -> Path | None:
    """Extract a representative still frame from a video using FFmpeg."""
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-ss", str(seek_seconds),
                "-i", str(video_path),
                "-frames:v", "1",
                "-q:v", "2",
                str(dest_jpeg),
            ],
            capture_output=True,
            timeout=30,
        )
        if dest_jpeg.exists() and dest_jpeg.stat().st_size > 0:
            return dest_jpeg
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.warning("FFmpeg not available or timed out for %s", video_path.name)
    return None


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
def import_existing_paths(paths: Iterable[Path], source_prefix: str) -> dict:
    paths = [Path(p) for p in paths]
    hash_map = load_json(PHOTO_HASHES, {})
    if not isinstance(hash_map, dict):
        hash_map = {}

    existing_ids = {p["id"] for p in load_photos_manifest()}
    imported: list[dict] = []
    skipped = 0

    for src in paths:
        if not src.exists():
            continue
        ext = src.suffix.lower()
        is_video = ext in SUPPORTED_VIDEO_EXTENSIONS
        if ext not in SUPPORTED_MEDIA_EXTENSIONS:
            continue

        # Hash original bytes to dedupe across imports/sources.
        content_hash = sha256_file(src)
        if content_hash in hash_map:
            skipped += 1
            continue

        pid = _new_photo_id(src.name, content_hash, existing_ids)
        existing_ids.add(pid)

        if is_video:
            # Store original video and extract a representative frame
            video_dest = ORIGINALS_DIR / f"{pid}{ext}"
            shutil.copy2(src, video_dest)
            frame_dest = ORIGINALS_DIR / f"{pid}.jpg"
            extracted = _extract_video_frame(src, frame_dest)
            if not extracted:
                # Fall back to first frame
                extracted = _extract_video_frame(src, frame_dest, seek_seconds=0.0)
            if not extracted:
                logger.warning("Could not extract frame from %s, skipping", src.name)
                continue
            rec = _build_photo_record(pid, frame_dest, f"{source_prefix}:{src}", content_hash)
            rec["media_type"] = "video"
            rec["video_path"] = str(video_dest)
        else:
            dest = ORIGINALS_DIR / f"{pid}.jpg"
            final_path = _ensure_jpeg(src, dest)
            rec = _build_photo_record(pid, final_path, f"{source_prefix}:{src}", content_hash)
            rec["media_type"] = "photo"

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
