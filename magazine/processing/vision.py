"""AI vision analysis of photos using Claude API."""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

import click
from tqdm import tqdm

from magazine.config import (
    ANTHROPIC_API_KEY,
    VISION_ANALYSIS,
    THUMBNAILS_DIR,
)
from magazine.services.state import load_json, save_json

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """\
You are a magazine art director studying photographs for an editorial spread.
Analyze each photo and return a JSON array with one object per photo (in the same order).

Each object must have these fields:
- "photo_id": string (the id provided)
- "scene_type": one of "landscape", "portrait", "candid", "detail", "group", "architecture", "food", "nature", "cityscape", "interior"
- "setting": short description of the location/environment (e.g. "outdoor cafe", "beach at sunset")
- "time_of_day": one of "golden_hour", "midday", "afternoon", "evening", "night", "dawn", "overcast"
- "mood": one of "intimate", "joyful", "contemplative", "adventurous", "serene", "playful", "dramatic", "tender"
- "color_temperature": one of "warm", "cool", "neutral"
- "dominant_colors": array of 3 hex color strings from the image
- "people_description": what people are doing (empty string if no people)
- "key_elements": array of 3-5 notable visual elements
- "emotional_weight": integer 1-5, how emotionally significant this moment feels
- "narrative_potential": one sentence about what makes this photo meaningful

Return ONLY the JSON array, no markdown fences or extra text.
"""


@dataclass
class PhotoAnalysis:
    photo_id: str
    scene_type: str = ""
    setting: str = ""
    time_of_day: str = ""
    mood: str = ""
    color_temperature: str = ""
    dominant_colors: list[str] | None = None
    people_description: str = ""
    key_elements: list[str] | None = None
    emotional_weight: int = 3
    narrative_potential: str = ""


def _load_cache() -> dict[str, dict]:
    raw = load_json(VISION_ANALYSIS, {})
    return raw if isinstance(raw, dict) else {}


def _save_cache(cache: dict[str, dict]):
    save_json(VISION_ANALYSIS, cache)


def _photo_to_base64(photo: dict) -> str | None:
    """Get a reasonably-sized image for vision analysis."""
    # Prefer thumbnail (already ~400px) to save tokens
    for key in ("thumbnail", "original"):
        val = photo.get(key, "")
        if val:
            p = Path(val)
            if p.exists():
                return base64.standard_b64encode(p.read_bytes()).decode("ascii")
    return None


def _analyze_batch(client, photos: list[dict]) -> list[PhotoAnalysis]:
    """Send a batch of photos to Claude for vision analysis."""
    content = []
    photo_ids = []
    for photo in photos:
        b64 = _photo_to_base64(photo)
        if not b64:
            continue
        pid = photo["id"]
        photo_ids.append(pid)
        content.append({
            "type": "text",
            "text": f"Photo ID: {pid} (#{len(photo_ids)} of batch)",
        })
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": b64,
            },
        })

    if not content:
        return []

    content.append({"type": "text", "text": ANALYSIS_PROMPT})

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": content}],
    )

    raw_text = response.content[0].text.strip()
    # Strip markdown fences if present
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]

    try:
        results = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse vision analysis response")
        return []

    analyses = []
    for item in results:
        analyses.append(PhotoAnalysis(
            photo_id=item.get("photo_id", ""),
            scene_type=item.get("scene_type", ""),
            setting=item.get("setting", ""),
            time_of_day=item.get("time_of_day", ""),
            mood=item.get("mood", ""),
            color_temperature=item.get("color_temperature", ""),
            dominant_colors=item.get("dominant_colors", []),
            people_description=item.get("people_description", ""),
            key_elements=item.get("key_elements", []),
            emotional_weight=int(item.get("emotional_weight", 3)),
            narrative_potential=item.get("narrative_potential", ""),
        ))
    return analyses


def analyze_photos(photos: list[dict], batch_size: int = 5) -> dict[str, PhotoAnalysis]:
    """Analyze all photos using Claude vision API. Returns dict keyed by photo_id.

    Results are cached — photos already analyzed are skipped.
    Gracefully returns empty dict if API key is missing or calls fail.
    """
    if not ANTHROPIC_API_KEY:
        click.echo("No ANTHROPIC_API_KEY set — skipping AI vision analysis.")
        return {}

    try:
        import anthropic
    except ImportError:
        click.echo("anthropic package not installed — skipping vision analysis.")
        return {}

    cache = _load_cache()
    uncached = [p for p in photos if p["id"] not in cache]

    if not uncached:
        click.echo(f"Vision analysis cached for all {len(photos)} photos.")
        return {pid: PhotoAnalysis(**data) for pid, data in cache.items() if pid in {p["id"] for p in photos}}

    click.echo(f"Analyzing {len(uncached)} photos with Claude vision ({len(photos) - len(uncached)} cached)...")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    batches = [uncached[i:i + batch_size] for i in range(0, len(uncached), batch_size)]
    all_analyses: list[PhotoAnalysis] = []

    for batch in tqdm(batches, desc="Vision analysis"):
        try:
            results = _analyze_batch(client, batch)
            all_analyses.extend(results)
        except Exception as exc:
            logger.warning("Vision analysis batch failed: %s", exc)
            continue

    # Update cache
    for analysis in all_analyses:
        cache[analysis.photo_id] = asdict(analysis)
    _save_cache(cache)

    # Build result dict for all requested photos
    result = {}
    for photo in photos:
        pid = photo["id"]
        if pid in cache:
            result[pid] = PhotoAnalysis(**cache[pid])
    return result
