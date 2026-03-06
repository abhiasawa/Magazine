"""Face detection pipeline using DeepFace."""

import json

import click
from tqdm import tqdm

from magazine.config import (
    PHOTOS_MANIFEST,
    FACE_RESULTS,
    REVIEW_STATE,
    FACE_DETECTOR_BACKEND,
    TARGET_FACE_COUNT,
)
from magazine.services.state import load_review_state, save_review_state, normalize_review_entry


def detect_faces_in_photo(photo_path: str) -> dict:
    """Detect faces in a single photo.

    Returns:
      {
        "face_count": int,
        "faces": [{"x": int, "y": int, "w": int, "h": int, "confidence": float}],
      }
    """
    try:
        from deepface import DeepFace

        faces = DeepFace.extract_faces(
            img_path=photo_path,
            detector_backend=FACE_DETECTOR_BACKEND,
            enforce_detection=False,
        )

        extracted = []
        for face in faces:
            confidence = float(face.get("confidence", 0.0))
            area = face.get("facial_area") or {}
            extracted.append(
                {
                    "x": int(area.get("x", 0)),
                    "y": int(area.get("y", 0)),
                    "w": int(area.get("w", 0)),
                    "h": int(area.get("h", 0)),
                    "confidence": confidence,
                }
            )

        confident_faces = [f for f in extracted if f["confidence"] > 0.5]
        return {
            "face_count": len(confident_faces),
            "faces": confident_faces,
        }
    except Exception:
        return {"face_count": -1, "faces": []}


def _face_count(value) -> int:
    if isinstance(value, dict):
        return int(value.get("face_count", -1))
    try:
        return int(value)
    except Exception:
        return -1


def run_face_detection():
    """Run face detection on all imported photos.

    Produces:
    - face_results.json: face count + face boxes per photo
    - review_state.json: initial review state (2-face = pre-approved)
    """
    if not PHOTOS_MANIFEST.exists():
        raise click.ClickException("No photos imported yet. Run 'magazine import' first.")

    with open(PHOTOS_MANIFEST) as f:
        photos = json.load(f)

    click.echo(f"Detecting faces in {len(photos)} photos...")

    results = {}
    for photo in tqdm(photos, desc="Face detection"):
        results[photo["id"]] = detect_faces_in_photo(photo["original"])

    with open(FACE_RESULTS, "w") as f:
        json.dump(results, f, indent=2)

    review_state = load_review_state()
    candidates = 0
    others = 0
    errors = 0
    for photo_id, payload in results.items():
        face_count = _face_count(payload)
        entry = review_state.get(photo_id, normalize_review_entry("pending"))
        if face_count == TARGET_FACE_COUNT:
            entry["status"] = "approved"
            candidates += 1
        elif face_count < 0:
            entry["status"] = "error"
            errors += 1
        else:
            entry["status"] = "rejected"
            others += 1
        review_state[photo_id] = entry

    save_review_state(review_state)

    click.echo("\nResults:")
    click.echo(f"  Candidates (2 faces, pre-approved): {candidates}")
    click.echo(f"  Others (different face count): {others}")
    click.echo(f"  Errors: {errors}")
    click.echo("\nRun 'magazine review' to review and adjust selections.")
