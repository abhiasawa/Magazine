"""Face detection pipeline using DeepFace."""

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import click
from tqdm import tqdm

from magazine.config import (
    PHOTOS_MANIFEST,
    FACE_RESULTS,
    REVIEW_STATE,
    FACE_DETECTOR_BACKEND,
    TARGET_FACE_COUNT,
)


def count_faces_in_photo(photo_path: str) -> int:
    """Detect and count faces in a single photo.

    Uses DeepFace with configurable backend.
    Returns number of faces detected.
    """
    try:
        from deepface import DeepFace

        faces = DeepFace.extract_faces(
            img_path=photo_path,
            detector_backend=FACE_DETECTOR_BACKEND,
            enforce_detection=False,
        )
        # Filter out low-confidence detections
        confident_faces = [f for f in faces if f.get("confidence", 0) > 0.5]
        return len(confident_faces)
    except Exception:
        return -1  # Error indicator


def _process_single(args: tuple) -> tuple[str, int]:
    """Worker function for parallel processing."""
    photo_id, photo_path = args
    count = count_faces_in_photo(photo_path)
    return photo_id, count


def run_face_detection():
    """Run face detection on all imported photos.

    Produces:
    - face_results.json: face count per photo
    - review_state.json: initial review state (2-face = pre-approved)
    """
    if not PHOTOS_MANIFEST.exists():
        raise click.ClickException("No photos imported yet. Run 'magazine import' first.")

    with open(PHOTOS_MANIFEST) as f:
        photos = json.load(f)

    click.echo(f"Detecting faces in {len(photos)} photos...")

    # Prepare work items
    work = [(p["id"], p["original"]) for p in photos]
    results = {}

    # Process with progress bar (sequential to avoid DeepFace model loading issues)
    for item in tqdm(work, desc="Face detection"):
        photo_id, count = _process_single(item)
        results[photo_id] = count

    # Save face results
    with open(FACE_RESULTS, "w") as f:
        json.dump(results, f, indent=2)

    # Create initial review state
    candidates = 0
    others = 0
    review_state = {}
    for photo_id, face_count in results.items():
        if face_count == TARGET_FACE_COUNT:
            review_state[photo_id] = "approved"
            candidates += 1
        elif face_count < 0:
            review_state[photo_id] = "error"
        else:
            review_state[photo_id] = "rejected"
            others += 1

    with open(REVIEW_STATE, "w") as f:
        json.dump(review_state, f, indent=2)

    click.echo(f"\nResults:")
    click.echo(f"  Candidates (2 faces, pre-approved): {candidates}")
    click.echo(f"  Others (different face count): {others}")
    click.echo(f"  Errors: {sum(1 for v in results.values() if v < 0)}")
    click.echo(f"\nRun 'magazine review' to review and adjust selections.")
