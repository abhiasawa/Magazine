"""Shared state helpers for manifests, review state, and story config."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from magazine.config import (
    PHOTOS_MANIFEST,
    REVIEW_STATE,
    STORY_CONFIG,
    DEFAULT_PAGINATION,
)


def load_json(path: Path, default: Any):
    if not path.exists():
        return default
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def normalize_review_entry(value: Any) -> dict:
    """Normalize old/new review entry into object format.

    Old format: "approved" | "rejected" | ...
    New format: {"status": "approved", "hero_pin": bool, "caption": str}
    """
    if isinstance(value, dict):
        return {
            "status": value.get("status", "pending"),
            "hero_pin": bool(value.get("hero_pin", False)),
            "caption": (value.get("caption") or "").strip(),
        }

    status = str(value or "pending")
    return {
        "status": status,
        "hero_pin": False,
        "caption": "",
    }


def normalize_review_state(raw: Any) -> dict[str, dict]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): normalize_review_entry(v) for k, v in raw.items()}


def load_review_state() -> dict[str, dict]:
    return normalize_review_state(load_json(REVIEW_STATE, {}))


def save_review_state(state: dict[str, dict]):
    save_json(REVIEW_STATE, state)


def ensure_review_entries(photo_ids: list[str]) -> dict[str, dict]:
    state = load_review_state()
    changed = False
    for pid in photo_ids:
        if pid not in state:
            state[pid] = normalize_review_entry("pending")
            changed = True
    if changed:
        save_review_state(state)
    return state


def load_photos_manifest() -> list[dict]:
    photos = load_json(PHOTOS_MANIFEST, [])
    if isinstance(photos, list):
        return photos
    return []


def save_photos_manifest(photos: list[dict]):
    save_json(PHOTOS_MANIFEST, photos)


def load_story_config() -> dict:
    data = load_json(STORY_CONFIG, {})
    if not isinstance(data, dict):
        data = {}

    pagination = data.get("pagination") if isinstance(data.get("pagination"), dict) else {}
    normalized = {
        "style": data.get("style", "editorial_luxury"),
        "title": data.get("title", "Our Love Story"),
        "subtitle": data.get("subtitle", "A Journey Together"),
        "dedication": data.get("dedication", "For you, with all my love"),
        "flow": data.get("flow", "chronological"),
        "heroes": data.get("heroes", []),
        "pagination": {
            "mode": pagination.get("mode", DEFAULT_PAGINATION["mode"]),
            "min_pages": int(pagination.get("min_pages", DEFAULT_PAGINATION["min_pages"])),
            "max_pages": int(pagination.get("max_pages", DEFAULT_PAGINATION["max_pages"])),
            "density": float(pagination.get("density", DEFAULT_PAGINATION["density"])),
            "fixed_pages": int(pagination.get("fixed_pages", DEFAULT_PAGINATION["fixed_pages"])),
            "page_step": int(pagination.get("page_step", DEFAULT_PAGINATION["page_step"])),
        },
    }
    return normalized


def save_story_config(config: dict):
    save_json(STORY_CONFIG, config)


def merge_photos(existing: list[dict], new_photos: list[dict]) -> tuple[list[dict], int]:
    """Merge photos by id while preserving existing rows."""
    by_id = {p["id"]: p for p in existing}
    added = 0
    for p in new_photos:
        pid = p["id"]
        if pid not in by_id:
            by_id[pid] = p
            added += 1
        else:
            # Keep any new metadata fields if missing
            merged = by_id[pid]
            for key, value in p.items():
                if key not in merged or merged.get(key) in (None, ""):
                    merged[key] = value
    merged_list = list(by_id.values())
    merged_list.sort(key=lambda p: p.get("date_taken") or "9999")
    return merged_list, added
