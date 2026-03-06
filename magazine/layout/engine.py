"""Layout engine for dynamic editorial magazine generation."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from magazine.config import PHOTOS_MANIFEST, FACE_RESULTS
from magazine.layout.quotes import get_quotes
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
    """Load approved photos from review state, sorted by date."""
    if not PHOTOS_MANIFEST.exists():
        return []

    photos = load_json(PHOTOS_MANIFEST, [])
    review_state = load_review_state()
    face_results = load_json(FACE_RESULTS, {})

    approved = []
    for p in photos:
        pid = p["id"]
        entry = review_state.get(pid, {"status": "pending", "hero_pin": False, "caption": ""})
        if _review_status(entry) == "approved":
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


def estimate_page_count(
    photo_count: int,
    density: float = 1.7,
    fixed_pages: int = 8,
    min_pages: int = 28,
    max_pages: int = 72,
    page_step: int = 4,
) -> int:
    """Estimate dynamic page count from selected photos.

    Formula:
      raw_pages = ceil(photo_count / density) + fixed_pages
      clamp to [min_pages, max_pages]
      round up to signature step
    """
    if density <= 0:
        density = 1.7
    if page_step <= 0:
        page_step = 4

    raw_pages = math.ceil(max(photo_count, 0) / density) + fixed_pages
    clamped = min(max(raw_pages, min_pages), max_pages)
    rounded = int(math.ceil(clamped / page_step) * page_step)
    return min(rounded, max_pages)


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
    min_pages: int = 28,
    max_pages: int = 72,
    density: float = 1.7,
    page_step: int = 4,
    fixed_pages: int = 8,
) -> list[PageSpec]:
    """Build dynamic editorial layout from approved photos."""
    photos = load_approved_photos()

    if not photos:
        raise ValueError("No approved photos found. Review and approve photos first.")

    if pages == "auto":
        target_pages = estimate_page_count(
            photo_count=len(photos),
            density=density,
            fixed_pages=fixed_pages,
            min_pages=min_pages,
            max_pages=max_pages,
            page_step=page_step,
        )
    else:
        try:
            target_pages = int(pages)
        except Exception as exc:
            raise ValueError(f"Invalid pages value: {pages}") from exc
        target_pages = max(min_pages, min(target_pages, max_pages))
        target_pages = int(math.ceil(target_pages / page_step) * page_step)

    _overflow_guard(photo_count=len(photos), target_pages=target_pages)

    quotes = get_quotes(max(10, target_pages // 3))
    quote_idx = 0

    cover_photo = pick_best_photo(photos)
    remaining = [clone_photo(p) for p in photos if p["id"] != cover_photo["id"]]
    heroes = [p for p in remaining if p.get("hero_pin")]
    regular = [p for p in remaining if not p.get("hero_pin")]
    reuse_pool = remaining[:] if remaining else [clone_photo(cover_photo)]
    reuse_idx = [0]

    pages_out: list[PageSpec] = []
    page_num = 1

    # Fixed opening pages
    pages_out.append(
        PageSpec(
            template="cover",
            photos=[clone_photo(cover_photo)],
            title=title,
            subtitle=subtitle,
            page_number=page_num,
        )
    )
    page_num += 1

    pages_out.append(
        PageSpec(
            template="dedication",
            dedication=dedication,
            page_number=page_num,
        )
    )
    page_num += 1

    pages_out.append(
        PageSpec(
            template="quote_page",
            quote=quotes[quote_idx] if quote_idx < len(quotes) else None,
            section_title="The Beginning",
            page_number=page_num,
        )
    )
    quote_idx += 1
    page_num += 1

    pages_out.append(
        PageSpec(
            template="editorial",
            photos=_take_n(1, regular, heroes, reuse_pool, reuse_idx, prefer_hero_first=True),
            quote=quotes[quote_idx] if quote_idx < len(quotes) else None,
            page_number=page_num,
        )
    )
    quote_idx += 1
    page_num += 1

    # Dynamic body pages
    body_pages = max(0, target_pages - 8)

    template_cycle = [
        "full_bleed",
        "collage3",
        "collage2",
        "mosaic",
        "collage4",
        "two_photo",
        "three_photo",
        "big_polaroid",
        "collage_stack",
        "photo_quote_overlay",
        "cinematic",
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

    premium_templates = {"full_bleed", "cinematic", "big_polaroid", "editorial"}

    chapter_titles = [
        "The Beginning",
        "Growing Together",
        "Beautiful Moments",
        "Always & Forever",
    ]

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

        quote = None
        if template in {"big_polaroid", "photo_quote_overlay", "collage_stack", "editorial"}:
            quote = quotes[quote_idx] if quote_idx < len(quotes) else None
            quote_idx += 1

        section_title = ""
        if template in {"full_bleed", "cinematic"} and idx % 6 == 0:
            section_title = chapter_titles[(idx // 6) % len(chapter_titles)]

        pages_out.append(
            PageSpec(
                template=template,
                photos=page_photos,
                quote=quote,
                section_title=section_title,
                page_number=page_num,
            )
        )
        page_num += 1

    # Fixed closing pages
    pages_out.append(
        PageSpec(
            template="quote_page",
            quote=quotes[quote_idx] if quote_idx < len(quotes) else None,
            section_title="Forever",
            page_number=page_num,
        )
    )
    quote_idx += 1
    page_num += 1

    pages_out.append(
        PageSpec(
            template="cinematic",
            photos=_take_n(1, regular, heroes, reuse_pool, reuse_idx, prefer_hero_first=True),
            section_title="Forever & Always",
            page_number=page_num,
        )
    )
    page_num += 1

    pages_out.append(
        PageSpec(
            template="quote_page",
            quote=quotes[quote_idx] if quote_idx < len(quotes) else None,
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
