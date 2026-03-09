"""Narrative arc generation for the magazine using OpenAI API."""

from __future__ import annotations

import json
import logging
import random
import time
import traceback
from dataclasses import dataclass
from datetime import datetime

import click

from magazine.config import OPENAI_API_KEY, NARRATIVE_CACHE, WORKSPACE
from magazine.layout.engine import PageSpec
from magazine.processing.vision import PhotoAnalysis
from magazine.services.state import load_json, save_json

logger = logging.getLogger(__name__)

# Persistent log file for API diagnostics — survives across requests.
_API_LOG = WORKSPACE / "api_debug.log"


def _log_api_event(stage: str, detail: str):
    """Append a timestamped line to the API debug log file."""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(_API_LOG, "a") as f:
            f.write(f"[{ts}] [{stage}] {detail}\n")
    except Exception:
        pass

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
  Prefer metaphor over description. Don't say what's in the photo — say what the photo FEELS like.
  Bad: "The sunset painted the sky in orange." Good: "The day exhaled, and everything turned to honey."
  Bad: "Color filled the room." Good: "The walls hummed with a warmth no one could name."
  Write as if for a Conde Nast Traveler feature or a published memoir.
- For multi-photo pages (expected_type = "heading_word"): write ONE evocative word or short heading
  (1-3 words max). Avoid overused words (Beautiful, Amazing, Wonderful, Golden Hour, Wanderlust).
  Prefer evocative, unusual words: "Heirloom", "Liminal", "Unmoored", "Gilded", "Aftermath"
- NEVER use generic words: "color", "texture", "beauty", "moment", "memory", "journey".
  Every word must be specific and surprising.
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


# ── Fallback narrative text (used when API is unavailable) ──────────────────

# Sentences for single-photo pages, grouped by arc position
_FALLBACK_SENTENCES = {
    "early": [
        "And so the story began, quietly, without ceremony.",
        "Some journeys start not with a step but with a glance.",
        "The light that morning carried a promise no one spoke aloud.",
        "There are places that wait for you before you know they exist.",
        "Every beginning holds a world not yet imagined.",
        "The first breath of a new place always tastes like possibility.",
        "Something shifted in the air, and the day opened wide.",
    ],
    "middle": [
        "The hours dissolved like sugar in warm rain.",
        "They moved through the day as though time had forgotten them.",
        "In the middle of everything, a perfect stillness.",
        "Some moments refuse to be hurried.",
        "The world grew smaller until only this remained.",
        "Laughter echoed where silence had lived before.",
        "Between one heartbeat and the next, everything changed.",
        "The afternoon unfolded like a letter written long ago.",
        "Here was the proof that ordinary days hold extraordinary light.",
    ],
    "late": [
        "And like all beautiful things, it asked for nothing in return.",
        "The last light lingered, reluctant to leave.",
        "Some endings are just the quiet side of gratitude.",
        "What remained was not the place but the feeling.",
        "They carried this moment home like a stone from the sea.",
        "The distance between then and now is only a photograph.",
        "Everything worth remembering happened in the spaces between.",
    ],
}

_FALLBACK_HEADINGS = [
    "Heirloom", "Liminal", "Gilded", "Tidewater",
    "Unwritten", "Sanctuary", "Reverie", "Half-Light",
    "Tender", "Passage", "Interlude", "Aftermath",
    "Meridian", "Driftwood", "Flourish", "Quietude",
    "Daybreak", "Together", "Vivid", "Belonging",
]


def _generate_fallback_narrative(
    pages: list[PageSpec],
    analyses: dict[str, PhotoAnalysis],
) -> list[NarrativeSection]:
    """Generate narrative text locally without an API call.

    Produces evocative literary text based on the page position in the
    magazine arc (early / middle / late) and the photo mood.
    """
    body_pages = []
    for abs_idx, page in enumerate(pages):
        if page.template in ("cover", "back_cover", "dedication"):
            continue
        n_type = _determine_narrative_type(page)
        if not n_type:
            continue
        body_pages.append((abs_idx, page, n_type))

    if not body_pages:
        return []

    total = len(body_pages)
    sections = []
    used_sentences: set[str] = set()
    heading_pool = list(_FALLBACK_HEADINGS)
    random.shuffle(heading_pool)
    heading_idx = 0

    for i, (abs_idx, page, n_type) in enumerate(body_pages):
        position = i / max(total - 1, 1)

        if n_type == "heading_word":
            text = heading_pool[heading_idx % len(heading_pool)]
            heading_idx += 1
        else:
            # Pick arc bucket
            if position < 0.25:
                pool = _FALLBACK_SENTENCES["early"]
            elif position > 0.75:
                pool = _FALLBACK_SENTENCES["late"]
            else:
                pool = _FALLBACK_SENTENCES["middle"]
            # Pick unused sentence
            available = [s for s in pool if s not in used_sentences]
            if not available:
                available = pool
            text = random.choice(available)
            used_sentences.add(text)

        sections.append(NarrativeSection(
            page_index=abs_idx,
            text=text,
            narrative_type=n_type,
        ))

    return sections


# ── Core types and helpers ──────────────────────────────────────────────────


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

    _log_api_event("NARRATIVE_REQUEST", f"model=gpt-5.4 pages={len(page_descs)} title={title!r}")

    last_error = None
    for attempt in range(3):
        if attempt > 0:
            click.echo(f"  Retrying narrative generation (attempt {attempt + 1})...")
            _log_api_event("NARRATIVE_RETRY", f"attempt={attempt + 1}")
            time.sleep(2)
        try:
            response = client.chat.completions.create(
                model="gpt-5.4",
                max_completion_tokens=4096,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": NARRATIVE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
            )
            raw_text = response.choices[0].message.content.strip()
            click.echo(f"  OpenAI response received ({len(raw_text)} chars).")
            _log_api_event("NARRATIVE_RESPONSE", f"chars={len(raw_text)} preview={raw_text[:200]!r}")
            parsed = json.loads(raw_text)
            _log_api_event("NARRATIVE_PARSED", f"keys={list(parsed.keys()) if isinstance(parsed, dict) else type(parsed).__name__}")
            return parsed
        except json.JSONDecodeError as exc:
            click.echo(f"  OpenAI returned invalid JSON: {exc}")
            _log_api_event("NARRATIVE_JSON_ERROR", f"error={exc} raw={raw_text[:500]!r}")
            last_error = exc
        except Exception as exc:
            click.echo(f"  OpenAI API error ({type(exc).__name__}): {exc}")
            _log_api_event("NARRATIVE_API_ERROR", f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            last_error = exc

    raise last_error


def generate_narrative(
    pages: list[PageSpec],
    analyses: dict[str, PhotoAnalysis],
    title: str = "",
) -> list[NarrativeSection]:
    """Generate narrative text for all body pages via OpenAI.

    Falls back to curated local text if the API is unavailable or fails.
    """
    _log_api_event("NARRATIVE_START", f"pages={len(pages)} analyses={len(analyses)} api_key_set={bool(OPENAI_API_KEY)}")

    if not OPENAI_API_KEY:
        click.echo("No OPENAI_API_KEY — using local narrative fallback.")
        _log_api_event("NARRATIVE_SKIP", "No OPENAI_API_KEY set")
        return _generate_fallback_narrative(pages, analyses)

    try:
        from openai import OpenAI
    except ImportError:
        click.echo("openai package not installed — using local narrative fallback.")
        _log_api_event("NARRATIVE_SKIP", "openai package not installed")
        return _generate_fallback_narrative(pages, analyses)

    page_descs, index_map = _build_page_descriptions(pages, analyses)
    if not page_descs:
        click.echo("No body pages found for narrative generation.")
        _log_api_event("NARRATIVE_SKIP", "No body pages to narrate")
        return []

    click.echo(f"Generating narrative for {len(page_descs)} pages via OpenAI gpt-5.4...")
    click.echo(f"  Photo analyses available: {len(analyses)} photos")

    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        parsed = _call_openai_narrative(client, page_descs, title, len(pages))
    except Exception as exc:
        click.echo(f"NARRATIVE API FAILED ({type(exc).__name__}: {exc}) — using local fallback.")
        _log_api_event("NARRATIVE_FAILED", f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
        return _generate_fallback_narrative(pages, analyses)

    # Extract sections from the response — supports both {"sections": [...]} and bare [...]
    if isinstance(parsed, dict):
        results = parsed.get("sections", parsed.get("data", []))
        if isinstance(results, dict):
            results = list(results.values())
    elif isinstance(parsed, list):
        results = parsed
    else:
        click.echo(f"Unexpected response structure: {type(parsed)} — using local fallback.")
        return _generate_fallback_narrative(pages, analyses)

    if not results:
        click.echo("OpenAI returned empty sections — using local fallback.")
        return _generate_fallback_narrative(pages, analyses)

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

    if not sections:
        click.echo("OpenAI returned no usable sections — using local fallback.")
        return _generate_fallback_narrative(pages, analyses)

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

    # Generate narrative text (API with local fallback — always produces text)
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

    # Safety: if no text was assigned at all, something is fundamentally wrong
    if assigned == 0 and len(pages) > 3:
        click.echo("WARNING: Zero narrative text assigned. Check API key and logs.")
        logger.error("No narrative text was assigned to any page")
