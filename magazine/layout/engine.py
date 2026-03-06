"""Layout engine for dynamic editorial magazine generation."""

from __future__ import annotations

import math
from datetime import datetime
from dataclasses import dataclass, field

from magazine.config import PHOTOS_MANIFEST, FACE_RESULTS
from magazine.services.state import load_json, load_review_state


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


def _review_status(entry) -> str:
    if isinstance(entry, dict):
        return str(entry.get("status", "pending"))
    return str(entry or "pending")


def _hero_pin(entry) -> bool:
    if isinstance(entry, dict):
        return bool(entry.get("hero_pin", False))
    return False


def _caption(entry) -> str:
    if isinstance(entry, dict):
        return (entry.get("caption") or "").strip()
    return ""


def _face_payload(entry) -> tuple[int, list[dict]]:
    if isinstance(entry, dict):
        return int(entry.get("face_count", -1)), list(entry.get("faces", []))
    try:
        return int(entry), []
    except Exception:
        return -1, []


def clone_photo(photo: dict) -> dict:
    cloned = dict(photo)
    faces = cloned.get("faces")
    if isinstance(faces, list):
        cloned["faces"] = [dict(face) for face in faces]
    return cloned


def load_approved_photos() -> list[dict]:
    """Load selected photos for layout, excluding only explicit rejects."""
    if not PHOTOS_MANIFEST.exists():
        return []

    photos = load_json(PHOTOS_MANIFEST, [])
    review_state = load_review_state()
    face_results = load_json(FACE_RESULTS, {})

    approved = []
    for p in photos:
        pid = p["id"]
        entry = review_state.get(pid, {"status": "pending", "hero_pin": False, "caption": ""})
        if _review_status(entry) == "rejected":
            continue

        face_count, faces = _face_payload(face_results.get(pid, {}))
        row = clone_photo(p)
        row["hero_pin"] = _hero_pin(entry)
        row["caption"] = _caption(entry)
        row["face_count"] = face_count
        row["faces"] = faces
        approved.append(row)

    approved.sort(key=lambda p: p.get("date_taken") or "9999")
    return approved


def pick_best_photo(photos: list[dict]) -> dict | None:
    """Pick the highest resolution photo (best for cover/full-bleed)."""
    if not photos:
        return None
    return max(photos, key=lambda p: p.get("width", 0) * p.get("height", 0))


def _parse_taken_date(photo: dict) -> datetime | None:
    raw = str(photo.get("date_taken") or "").strip()
    if not raw:
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _format_cover_date_range(photos: list[dict]) -> str:
    dates = [dt for photo in photos if (dt := _parse_taken_date(photo))]
    if not dates:
        return "Assembled from your selected photographs"

    start = min(dates)
    end = max(dates)
    if start.year == end.year and start.month == end.month:
        return start.strftime("%B %Y")
    if start.year == end.year:
        return f"{start.strftime('%B')} - {end.strftime('%B %Y')}"
    return f"{start.strftime('%b %Y')} - {end.strftime('%b %Y')}"


def _cover_storyline(photos: list[dict]) -> tuple[str, str]:
    count = len(photos)
    if count >= 80:
        return "An expansive private volume", f"Edited from {count} selected photographs"
    if count >= 40:
        return "A private edition of remembered days", f"Edited from {count} selected photographs"
    if count >= 20:
        return "A collected volume of moments worth keeping", f"Edited from {count} selected photographs"
    return "A small private edition of what mattered most", f"Edited from {count} selected photographs"


def estimate_page_count(
    photo_count: int,
    density: float = 1.7,
    fixed_pages: int = 3,
    **_kwargs,
) -> int:
    """Estimate page count from selected photos.

    Formula: ceil(photo_count / density) + fixed_pages
    Purely dynamic — no min/max clamping.
    """
    if density <= 0:
        density = 1.7
    return math.ceil(max(photo_count, 0) / density) + fixed_pages


def _select_photo(
    regular: list[dict],
    heroes: list[dict],
    reuse_pool: list[dict],
    reuse_idx: list[int],
    prefer_hero: bool = False,
) -> dict:
    if prefer_hero and heroes:
        return clone_photo(heroes.pop(0))

    if regular:
        return clone_photo(regular.pop(0))

    if heroes:
        return clone_photo(heroes.pop(0))

    # Reuse pass for low-photo/high-page scenarios.
    if not reuse_pool:
        raise ValueError("No photos available to place in layout")
    picked = clone_photo(reuse_pool[reuse_idx[0] % len(reuse_pool)])
    reuse_idx[0] += 1
    return picked


def _take_n(
    n: int,
    regular: list[dict],
    heroes: list[dict],
    reuse_pool: list[dict],
    reuse_idx: list[int],
    prefer_hero_first: bool = False,
) -> list[dict]:
    photos = []
    for idx in range(n):
        photos.append(
            _select_photo(
                regular=regular,
                heroes=heroes,
                reuse_pool=reuse_pool,
                reuse_idx=reuse_idx,
                prefer_hero=prefer_hero_first and idx == 0,
            )
        )
    return photos


def _overflow_guard(photo_count: int, target_pages: int, compact_density: float = 2.1):
    capacity = int(target_pages * compact_density)
    if photo_count > capacity:
        overflow = photo_count - capacity
        raise ValueError(
            f"Selected {photo_count} photos, but estimated safe capacity for {target_pages} pages is {capacity}. "
            f"Reduce selection by ~{overflow} photos or increase max pages."
        )


def build_layout(
    title: str = "Our Love Story",
    subtitle: str = "A Journey Together",
    dedication: str = "For you, with all my love",
    style: str = "editorial_luxury",
    pages: str | int = "auto",
    density: float = 1.7,
    fixed_pages: int = 3,
    **_kwargs,
) -> list[PageSpec]:
    """Build dynamic editorial layout from the selected photo set."""
    photos = load_approved_photos()

    if not photos:
        raise ValueError("No imported photos found. Select photos in Google Photos first.")

    if pages == "auto":
        target_pages = estimate_page_count(
            photo_count=len(photos),
            density=density,
            fixed_pages=fixed_pages,
        )
    else:
        try:
            target_pages = int(pages)
        except Exception as exc:
            raise ValueError(f"Invalid pages value: {pages}") from exc

    _overflow_guard(photo_count=len(photos), target_pages=target_pages)

    remaining = [clone_photo(p) for p in photos]
    heroes = [p for p in remaining if p.get("hero_pin")]
    regular = [p for p in remaining if not p.get("hero_pin")]
    reuse_pool = remaining[:] if remaining else []
    reuse_idx = [0]

    pages_out: list[PageSpec] = []
    page_num = 1
    cover_line, cover_meta = _cover_storyline(photos)
    cover_date_range = _format_cover_date_range(photos)

    # Fixed opening pages
    pages_out.append(
        PageSpec(
            template="cover",
            photos=[],
            title=cover_line,
            subtitle=cover_meta,
            section_title=cover_date_range,
            page_number=page_num,
        )
    )
    page_num += 1

    # Dynamic body pages
    body_pages = max(0, target_pages - 3)

    template_cycle = [
        "cinematic",
        "editorial",
        "two_photo",
        "three_photo",
        "mosaic",
        "collage2",
        "collage3",
        "collage4",
        "full_bleed",
    ]

    photo_requirements = {
        "full_bleed": 1,
        "collage2": 2,
        "collage3": 3,
        "collage4": 4,
        "mosaic": 4,
        "two_photo": 2,
        "three_photo": 3,
        "big_polaroid": 1,
        "collage_stack": 3,
        "photo_quote_overlay": 1,
        "cinematic": 1,
        "editorial": 1,
    }

    premium_templates = {"full_bleed", "cinematic", "editorial"}

    for idx in range(body_pages):
        template = template_cycle[idx % len(template_cycle)]
        # Inject hero pages periodically until pinned heroes are exhausted.
        if heroes and idx % 5 == 0:
            template = "full_bleed"

        need = photo_requirements[template]
        page_photos = _take_n(
            need,
            regular,
            heroes,
            reuse_pool,
            reuse_idx,
            prefer_hero_first=template in premium_templates,
        )

        pages_out.append(
            PageSpec(
                template=template,
                photos=page_photos,
                page_number=page_num,
            )
        )
        page_num += 1

    # Fixed closing pages
    pages_out.append(
        PageSpec(
            template="cinematic",
            photos=_take_n(1, regular, heroes, reuse_pool, reuse_idx, prefer_hero_first=True),
            page_number=page_num,
        )
    )
    page_num += 1

    back_photo = _select_photo(regular, heroes, reuse_pool, reuse_idx, prefer_hero=False)
    pages_out.append(
        PageSpec(
            template="back_cover",
            photos=[back_photo],
            title=title,
            page_number=page_num,
        )
    )

    return pages_out
