"""Layout engine: distributes approved photos across collage-style magazine pages."""

import json
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


# Collage layout sequences — varied patterns per section
LAYOUT_SEQUENCES = [
    ["full_bleed", "collage3", "big_polaroid", "collage2"],
    ["big_polaroid", "collage4", "photo_quote_overlay", "collage3"],
    ["full_bleed", "collage_stack", "collage2", "collage4"],
    ["collage3", "big_polaroid", "collage4", "photo_quote_overlay"],
    ["big_polaroid", "collage2", "collage_stack", "collage3"],
]


def build_layout(title: str = "Our Love Story", subtitle: str = "A Journey Together",
                 dedication: str = "For you, with all my love") -> list[PageSpec]:
    """Build collage-style magazine layout from approved photos."""
    photos = load_approved_photos()

    if not photos:
        raise ValueError("No approved photos found. Run 'magazine review' first.")

    num_quotes = max(6, len(photos) // 4)
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

        # Quote page as section divider
        if sec_i > 0 and quote_idx < len(quotes):
            pages.append(PageSpec(
                template="quote_page",
                quote=quotes[quote_idx],
                section_title=sec_title,
                page_number=page_num,
            ))
            page_num += 1
            quote_idx += 1

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

            elif template == "collage3" and left >= 3:
                pages.append(PageSpec(
                    template="collage3",
                    photos=section_photos[idx:idx + 3],
                    section_title=sec_title if idx == 0 else "",
                    page_number=page_num,
                ))
                idx += 3
                page_num += 1

            elif template == "collage2" and left >= 2:
                pages.append(PageSpec(
                    template="collage2",
                    photos=section_photos[idx:idx + 2],
                    page_number=page_num,
                ))
                idx += 2
                page_num += 1

            elif template == "collage4" and left >= 3:
                count = min(4, left)
                pages.append(PageSpec(
                    template="collage4",
                    photos=section_photos[idx:idx + count],
                    page_number=page_num,
                ))
                idx += count
                page_num += 1

            elif template == "big_polaroid" and left >= 1:
                q = quotes[quote_idx] if quote_idx < len(quotes) else None
                pages.append(PageSpec(
                    template="big_polaroid",
                    photos=[section_photos[idx]],
                    quote=q,
                    page_number=page_num,
                ))
                if q:
                    quote_idx += 1
                idx += 1
                page_num += 1

            elif template == "collage_stack" and left >= 3 and quote_idx < len(quotes):
                pages.append(PageSpec(
                    template="collage_stack",
                    photos=section_photos[idx:idx + 3],
                    quote=quotes[quote_idx],
                    page_number=page_num,
                ))
                idx += 3
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
                # Fallback
                if left >= 2:
                    pages.append(PageSpec(
                        template="collage2",
                        photos=section_photos[idx:idx + 2],
                        page_number=page_num,
                    ))
                    idx += 2
                    page_num += 1
                elif left >= 1:
                    pages.append(PageSpec(
                        template="big_polaroid",
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
