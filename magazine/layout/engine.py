"""Layout engine: distributes approved photos across magazine page templates."""

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from magazine.config import PHOTOS_MANIFEST, REVIEW_STATE
from magazine.layout.quotes import get_quotes


@dataclass
class PageSpec:
    """Specification for a single magazine page."""
    template: str
    photos: list[dict] = field(default_factory=list)
    quote: dict | None = None
    title: str = ""
    subtitle: str = ""
    dedication: str = ""
    section_title: str = ""
    page_number: int = 0


def load_approved_photos() -> list[dict]:
    """Load approved photos from review state, sorted by date."""
    if not PHOTOS_MANIFEST.exists() or not REVIEW_STATE.exists():
        return []

    with open(PHOTOS_MANIFEST) as f:
        photos = json.load(f)

    with open(REVIEW_STATE) as f:
        review_state = json.load(f)

    approved = []
    for p in photos:
        if review_state.get(p["id"]) == "approved":
            approved.append(p)

    approved.sort(key=lambda p: p.get("date_taken") or "9999")
    return approved


def pick_best_photo(photos: list[dict]) -> dict:
    """Pick the highest resolution photo (best for cover/full-bleed)."""
    if not photos:
        return None
    return max(photos, key=lambda p: p.get("width", 0) * p.get("height", 0))


# Layout sequences — varied page patterns to avoid repetition
LAYOUT_SEQUENCES = [
    # Sequence A: dramatic opener, grid, overlay
    ["full_bleed", "two_photo", "three_photo", "photo_quote_overlay"],
    # Sequence B: cinematic, editorial, grid
    ["cinematic", "editorial", "three_photo", "two_photo"],
    # Sequence C: full bleed, mosaic, overlay
    ["full_bleed", "mosaic", "photo_quote_overlay", "two_photo"],
    # Sequence D: editorial, cinematic, grid
    ["editorial", "full_bleed", "two_photo", "cinematic"],
]


def build_layout(title: str = "Our Love Story", subtitle: str = "A Journey Together",
                 dedication: str = "For you, with all my love") -> list[PageSpec]:
    """Build the complete magazine layout from approved photos.

    Returns an ordered list of PageSpec objects defining each page.
    """
    photos = load_approved_photos()

    if not photos:
        raise ValueError("No approved photos found. Run 'magazine review' first.")

    num_quotes = max(6, len(photos) // 5)
    quotes = get_quotes(num_quotes)

    pages: list[PageSpec] = []
    page_num = 1

    # --- Cover ---
    cover_photo = pick_best_photo(photos)
    remaining = [p for p in photos if p["id"] != cover_photo["id"]]

    pages.append(PageSpec(
        template="cover",
        photos=[cover_photo],
        title=title,
        subtitle=subtitle,
        page_number=page_num,
    ))
    page_num += 1

    # --- Dedication ---
    pages.append(PageSpec(
        template="dedication",
        dedication=dedication,
        page_number=page_num,
    ))
    page_num += 1

    # --- Content Pages ---
    num_sections = max(2, min(5, len(remaining) // 6))
    section_size = len(remaining) // num_sections
    sections = []
    for i in range(num_sections):
        start = i * section_size
        end = start + section_size if i < num_sections - 1 else len(remaining)
        sections.append(remaining[start:end])

    section_titles = [
        "The Beginning",
        "Growing Together",
        "Beautiful Moments",
        "Adventures & Joy",
        "Always & Forever",
    ]

    quote_idx = 0

    for sec_i, section_photos in enumerate(sections):
        sec_title = section_titles[sec_i] if sec_i < len(section_titles) else f"Chapter {sec_i + 1}"

        # Quote page as section divider (except before first section)
        if sec_i > 0 and quote_idx < len(quotes):
            pages.append(PageSpec(
                template="quote_page",
                quote=quotes[quote_idx],
                section_title=sec_title,
                page_number=page_num,
            ))
            page_num += 1
            quote_idx += 1

        # Pick a layout sequence for this section
        sequence = LAYOUT_SEQUENCES[sec_i % len(LAYOUT_SEQUENCES)]
        idx = 0
        step = 0

        while idx < len(section_photos):
            left = len(section_photos) - idx
            template = sequence[step % len(sequence)]

            if template == "full_bleed" and left >= 1:
                best = pick_best_photo(section_photos[idx:idx + 3])
                pages.append(PageSpec(
                    template="full_bleed",
                    photos=[best],
                    section_title=sec_title if idx == 0 else "",
                    page_number=page_num,
                ))
                idx += 1
                page_num += 1

            elif template == "cinematic" and left >= 1:
                pages.append(PageSpec(
                    template="cinematic",
                    photos=[section_photos[idx]],
                    section_title=sec_title if idx == 0 else "",
                    page_number=page_num,
                ))
                idx += 1
                page_num += 1

            elif template == "two_photo" and left >= 2:
                pages.append(PageSpec(
                    template="two_photo",
                    photos=section_photos[idx:idx + 2],
                    page_number=page_num,
                ))
                idx += 2
                page_num += 1

            elif template == "three_photo" and left >= 3:
                pages.append(PageSpec(
                    template="three_photo",
                    photos=section_photos[idx:idx + 3],
                    page_number=page_num,
                ))
                idx += 3
                page_num += 1

            elif template == "mosaic" and left >= 3:
                count = min(4, left)
                pages.append(PageSpec(
                    template="mosaic",
                    photos=section_photos[idx:idx + count],
                    page_number=page_num,
                ))
                idx += count
                page_num += 1

            elif template == "editorial" and left >= 1 and quote_idx < len(quotes):
                pages.append(PageSpec(
                    template="editorial",
                    photos=[section_photos[idx]],
                    quote=quotes[quote_idx],
                    page_number=page_num,
                ))
                idx += 1
                quote_idx += 1
                page_num += 1

            elif template == "photo_quote_overlay" and left >= 1 and quote_idx < len(quotes):
                pages.append(PageSpec(
                    template="photo_quote_overlay",
                    photos=[section_photos[idx]],
                    quote=quotes[quote_idx],
                    page_number=page_num,
                ))
                idx += 1
                quote_idx += 1
                page_num += 1

            else:
                # Fallback: use whatever fits
                if left >= 1:
                    pages.append(PageSpec(
                        template="full_bleed",
                        photos=[section_photos[idx]],
                        page_number=page_num,
                    ))
                    idx += 1
                    page_num += 1
                else:
                    break

            step += 1

    # --- Closing quote ---
    if quote_idx < len(quotes):
        pages.append(PageSpec(
            template="quote_page",
            quote=quotes[quote_idx],
            page_number=page_num,
        ))
        page_num += 1

    # --- Back Cover ---
    back_photo = photos[-1] if photos else None
    pages.append(PageSpec(
        template="back_cover",
        photos=[back_photo] if back_photo else [],
        title=title,
        page_number=page_num,
    ))

    return pages
