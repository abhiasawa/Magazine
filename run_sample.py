"""Run the sample magazine pipeline: import photos, skip face detection, auto-approve all, generate PDF."""

import json
import sys
from pathlib import Path

# Ensure we can import magazine
sys.path.insert(0, str(Path(__file__).parent))

from magazine.config import (
    ORIGINALS_DIR, THUMBNAILS_DIR, PRINT_DIR, OUTPUT_DIR,
    PHOTOS_MANIFEST, FACE_RESULTS, REVIEW_STATE,
)
from magazine.processing.images import make_thumbnail, get_image_dimensions, convert_to_jpeg
from magazine.layout.engine import build_layout
from magazine.pdf.generator import generate_pdf

import shutil
from tqdm import tqdm


def main():
    sample_dir = Path("sample_photos")
    photos_files = sorted(sample_dir.glob("*.jpg"))
    print(f"Found {len(photos_files)} sample photos")

    # Step 1: Import photos
    print("\n--- Step 1: Importing photos ---")
    photos = []
    for i, src in enumerate(tqdm(photos_files, desc="Importing")):
        stem = f"{i:04d}_{src.stem}"
        dest = ORIGINALS_DIR / f"{stem}.jpg"
        shutil.copy2(src, dest)

        thumb = make_thumbnail(dest, THUMBNAILS_DIR)
        w, h = get_image_dimensions(dest)

        photos.append({
            "id": stem,
            "original": str(dest),
            "thumbnail": str(thumb),
            "source_path": str(src),
            "date_taken": f"2025:0{(i % 9) + 1}:{(i % 28) + 1:02d} 12:00:00",
            "width": w,
            "height": h,
        })

    with open(PHOTOS_MANIFEST, "w") as f:
        json.dump(photos, f, indent=2)
    print(f"Imported {len(photos)} photos")

    # Step 2: Skip face detection, auto-approve all
    print("\n--- Step 2: Auto-approving all photos (skipping face detection) ---")
    face_results = {p["id"]: 2 for p in photos}  # Pretend all have 2 faces
    review_state = {p["id"]: "approved" for p in photos}

    with open(FACE_RESULTS, "w") as f:
        json.dump(face_results, f, indent=2)
    with open(REVIEW_STATE, "w") as f:
        json.dump(review_state, f, indent=2)
    print(f"Approved all {len(photos)} photos")

    # Step 3: Build layout
    print("\n--- Step 3: Building magazine layout ---")
    pages = build_layout(
        title="Minion Love Story",
        subtitle="A Banana-Filled Adventure",
        dedication="To our favorite little yellow friends,\nwho remind us that love is best shared\nwith a banana and a smile.",
    )
    print(f"Layout: {len(pages)} pages")

    # Step 4: Generate PDF
    print("\n--- Step 4: Generating PDF ---")
    output_path = generate_pdf(pages)
    print(f"\nDone! Magazine saved to: {output_path}")


if __name__ == "__main__":
    main()
