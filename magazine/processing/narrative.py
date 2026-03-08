"""Narrative arc generation for the magazine using OpenAI API."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

import click

from magazine.config import OPENAI_API_KEY, NARRATIVE_CACHE
from magazine.layout.engine import PageSpec
from magazine.processing.vision import PhotoAnalysis
from magazine.services.state import load_json, save_json

logger = logging.getLogger(__name__)

# Maps photo count per page to narrative type
PHOTO_COUNT_TO_TYPE = {
    0: None,
    1: "sentence",
}
# 2+ photos -> heading_word

MOOD_TO_PALETTE = {
    "intimate": "deep_shadow",
    "tender": "warm_gold",
    "joyful": "soft_light",
    "playful": "soft_light",
    "contemplative": "cool_stone",
    "serene": "cool_stone",
    "adventurous": "warm_gold",
    "dramatic": "deep_shadow",
}

MOOD_TO_DESIGN = {
    "intimate": "intimate",
    "tender": "intimate",
    "joyful": "expansive",
    "playful": "expansive",
    "contemplative": "reflective",
    "serene": "reflective",
    "adventurous": "expansive",
    "dramatic": "intimate",
}

# System prompt — sets the role and rules for narrative generation.
NARRATIVE_SYSTEM_PROMPT = """\
You are a literary magazine editor crafting the narrative thread for a personal photo magazine.
You will receive page data with photo analysis. Your task: generate narrative text for each body page
that weaves into a cohesive story arc. The magazine should read like a journey.

Rules:
- For single-photo pages (expected_type = "sentence"): write ONE evocative sentence (8-15 words).
  Not a caption — a literary line that brings the moment to life, like a line from a novel.
  Examples: "The cobblestones remembered every footstep they had ever shared."
  "She turned, and the whole piazza held its breath."
- For multi-photo pages (expected_type = "heading_word"): write ONE evocative word or short heading
  (1-3 words max).
  Examples: "Wanderlust", "Golden Hour", "Belonging", "The In-Between", "Homeward"
- Build a narrative arc: early pages = arrival/discovery, middle = immersion/connection,
  final pages = reflection/gratitude.
- Match the emotional tone of the photos — don't put joyful text on contemplative images.
- Every line should feel distinct — no repetition of words or phrasing across pages.

You MUST respond with a JSON object in this exact format:
{
  "sections": [
    {"page_index": 0, "text": "narrative text here", "type": "sentence"},
    {"page_index": 1, "text": "Wanderlust", "type": "heading_word"}
  ]
}

The "sections" array must have one entry per page provided, in order.
Each entry must have: "page_index" (integer matching the input), "text" (the narrative),
"type" (either "heading_word" or "sentence" matching the expected_type).
"""


@dataclass
class NarrativeSection:
    page_index: int
    text: str
    narrative_type: str  # "heading_word" or "sentence"


def _determine_narrative_type(page: PageSpec) -> str | None:
    n = len(page.photos)
    if n == 0:
        return None
    if n == 1:
        return "sentence"
    return "heading_word"


def _build_page_descriptions(
    pages: list[PageSpec], analyses: dict[str, PhotoAnalysis]
) -> tuple[list[dict], list[int]]:
    """Build a description of each page for the narrative prompt.

    Returns (descriptions, index_map) where index_map[i] gives the
    absolute page index for description i.  Descriptions use sequential
    0-based indices so the LLM returns indices that map cleanly back.
    """
    descs: list[dict] = []
    index_map: list[int] = []

    for abs_idx, page in enumerate(pages):
        if page.template in ("cover", "back_cover", "dedication"):
            continue
        n_type = _determine_narrative_type(page)
        if not n_type:
            continue

        photo_descs = []
        for photo in page.photos:
            pid = photo["id"]
            analysis = analyses.get(pid)
            if analysis:
                photo_descs.append({
                    "setting": analysis.setting,
                    "mood": analysis.mood,
                    "people": analysis.people_description,
                    "elements": analysis.key_elements or [],
                    "emotional_weight": analysis.emotional_weight,
                    "narrative_hint": analysis.narrative_potential,
                })
            else:
                photo_descs.append({"setting": "unknown", "mood": "neutral"})

        seq_idx = len(descs)
        descs.append({
            "page_index": seq_idx,
            "template": page.template,
            "photo_count": len(page.photos),
            "expected_type": n_type,
            "photos": photo_descs,
        })
        index_map.append(abs_idx)

    return descs, index_map


def _call_openai_narrative(client, page_descs: list[dict], title: str, total_pages: int) -> dict:
    """Make the OpenAI API call with retry. Returns parsed JSON dict."""
    user_content = (
        f"Magazine title: {title}\n"
        f"Total pages in magazine: {total_pages}\n"
        f"Pages to narrate ({len(page_descs)} pages):\n"
        f"{json.dumps(page_descs, indent=2)}"
    )

    last_error = None
    for attempt in range(2):
        if attempt > 0:
            click.echo(f"  Retrying narrative generation (attempt {attempt + 1})...")
            time.sleep(2)
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                max_tokens=4096,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": NARRATIVE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
            )
            raw_text = response.choices[0].message.content.strip()
            click.echo(f"  OpenAI response received ({len(raw_text)} chars).")
            parsed = json.loads(raw_text)
            return parsed
        except json.JSONDecodeError as exc:
            click.echo(f"  OpenAI returned invalid JSON: {exc}")
            click.echo(f"  Raw response: {raw_text[:500]}")
            last_error = exc
        except Exception as exc:
            click.echo(f"  OpenAI API error ({type(exc).__name__}): {exc}")
            last_error = exc

    raise last_error


def generate_narrative(
    pages: list[PageSpec],
    analyses: dict[str, PhotoAnalysis],
    title: str = "",
) -> list[NarrativeSection]:
    """Generate narrative text for all body pages via OpenAI GPT-4o.

    Raises an error if the API key is set but the call fails — no silent fallback.
    """
    if not OPENAI_API_KEY:
        click.echo("ERROR: No OPENAI_API_KEY set. Narrative text will be empty.")
        click.echo("  Set OPENAI_API_KEY in your .env file to enable narrative generation.")
        return []

    try:
        from openai import OpenAI
    except ImportError:
        click.echo("ERROR: openai package not installed. Run: pip install openai")
        return []

    page_descs, index_map = _build_page_descriptions(pages, analyses)
    if not page_descs:
        click.echo("No body pages found for narrative generation.")
        return []

    click.echo(f"Generating narrative for {len(page_descs)} pages via OpenAI GPT-4o...")
    click.echo(f"  Photo analyses available: {len(analyses)} photos")

    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        parsed = _call_openai_narrative(client, page_descs, title, len(pages))
    except Exception as exc:
        click.echo(f"NARRATIVE GENERATION FAILED: {type(exc).__name__}: {exc}")
        logger.error("Narrative generation failed after retries: %s", exc, exc_info=True)
        return []

    # Extract sections from the response — supports both {"sections": [...]} and bare [...]
    if isinstance(parsed, dict):
        results = parsed.get("sections", parsed.get("data", []))
        if isinstance(results, dict):
            results = list(results.values())
    elif isinstance(parsed, list):
        results = parsed
    else:
        click.echo(f"Unexpected response structure: {type(parsed)}")
        return []

    if not results:
        click.echo("WARNING: OpenAI returned empty sections array.")
        return []

    sections = []
    for item in results:
        if not isinstance(item, dict):
            continue
        seq_idx = item.get("page_index", 0)
        text = item.get("text", "").strip()
        if not text:
            continue
        if 0 <= seq_idx < len(index_map):
            abs_idx = index_map[seq_idx]
        else:
            abs_idx = seq_idx
        sections.append(NarrativeSection(
            page_index=abs_idx,
            text=text,
            narrative_type=item.get("type", "sentence"),
        ))

    click.echo(f"Narrative generated: {len(sections)} sections from OpenAI.")
    return sections


def assign_narrative_to_pages(
    pages: list[PageSpec],
    analyses: dict[str, PhotoAnalysis],
    title: str = "",
):
    """Generate narrative and assign text + design hints to each PageSpec in-place."""
    click.echo(f"Assigning narrative to {len(pages)} pages ({len(analyses)} photo analyses)...")

    # Assign palette hints from photo mood (even without narrative text)
    palette_count = 0
    for page in pages:
        if page.template in ("cover", "back_cover"):
            continue
        if page.photos:
            pid = page.photos[0]["id"]
            analysis = analyses.get(pid)
            if analysis:
                page.palette_hint = MOOD_TO_PALETTE.get(analysis.mood, "warm_gold")
                page.design_mood = MOOD_TO_DESIGN.get(analysis.mood, "")
                palette_count += 1

    click.echo(f"Palette hints assigned to {palette_count} pages.")

    # Generate narrative text
    sections = generate_narrative(pages, analyses, title=title)

    assigned = 0
    for section in sections:
        if 0 <= section.page_index < len(pages):
            page = pages[section.page_index]
            page.quote = {
                "text": section.text,
                "type": section.narrative_type,
            }
            assigned += 1

    click.echo(f"Narrative text assigned to {assigned}/{len(sections)} pages.")
