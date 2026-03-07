"""Narrative arc generation for the magazine using OpenAI API."""

from __future__ import annotations

import json
import logging
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

NARRATIVE_PROMPT = """\
You are a literary magazine editor crafting the narrative thread for a personal photo magazine.
You are given a sequence of magazine pages, each with photo analysis data.

Your task is to generate narrative text for EACH body page (not cover or back_cover) that weaves
into a cohesive story arc. The magazine should read as a journey.

Rules:
- For single-photo pages: write ONE evocative sentence (8-15 words). Not a caption —
  a literary line that brings the moment to life. It should feel like a line from a novel.
  Examples: "The cobblestones remembered every footstep they had ever shared."
  "She turned, and the whole piazza held its breath."
- For multi-photo pages (2+ photos): write ONE evocative word or short heading (1-3 words max).
  Examples: "Wanderlust", "Golden Hour", "Belonging", "The In-Between", "Homeward"
- Build a narrative arc: early pages = arrival/discovery, middle = immersion/connection,
  final pages = reflection/gratitude
- Match the emotional tone of the photos — don't put joyful text on contemplative images
- Every line should feel distinct — no repetition of words or phrasing across pages

Return a JSON array with one object per page (in order). Each object:
- "page_index": integer (0-based index in the pages list provided)
- "text": the narrative text (word or sentence)
- "type": "heading_word" or "sentence"

Return ONLY the JSON array, no markdown fences.
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


def _build_page_descriptions(pages: list[PageSpec], analyses: dict[str, PhotoAnalysis]) -> list[dict]:
    """Build a description of each page for the narrative prompt."""
    descs = []
    for i, page in enumerate(pages):
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

        descs.append({
            "page_index": i,
            "template": page.template,
            "photo_count": len(page.photos),
            "expected_type": n_type,
            "photos": photo_descs,
        })
    return descs


def generate_narrative(
    pages: list[PageSpec],
    analyses: dict[str, PhotoAnalysis],
    title: str = "",
) -> list[NarrativeSection]:
    """Generate narrative text for all body pages.

    Returns list of NarrativeSection objects. Gracefully returns empty list
    if AI is unavailable.
    """
    if not OPENAI_API_KEY:
        return []

    try:
        from openai import OpenAI
    except ImportError:
        return []

    page_descs = _build_page_descriptions(pages, analyses)
    if not page_descs:
        return []

    prompt_data = json.dumps(page_descs, indent=2)
    context = f"Magazine title: {title}\nTotal pages: {len(pages)}\n\nPages to narrate:\n{prompt_data}"

    click.echo(f"Generating narrative for {len(page_descs)} pages...")

    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=4096,
            messages=[
                {"role": "user", "content": f"{context}\n\n{NARRATIVE_PROMPT}"},
            ],
        )
        raw_text = response.choices[0].message.content.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]

        results = json.loads(raw_text)
    except Exception as exc:
        logger.warning("Narrative generation failed: %s", exc)
        return []

    sections = []
    for item in results:
        sections.append(NarrativeSection(
            page_index=item.get("page_index", 0),
            text=item.get("text", ""),
            narrative_type=item.get("type", "sentence"),
        ))
    return sections


def assign_narrative_to_pages(
    pages: list[PageSpec],
    analyses: dict[str, PhotoAnalysis],
    title: str = "",
):
    """Generate narrative and assign text + design hints to each PageSpec in-place."""
    # Assign palette hints from photo mood (even without narrative text)
    for page in pages:
        if page.template in ("cover", "back_cover"):
            continue
        if page.photos:
            # Use the first photo's mood to drive design
            pid = page.photos[0]["id"]
            analysis = analyses.get(pid)
            if analysis:
                page.palette_hint = MOOD_TO_PALETTE.get(analysis.mood, "warm_gold")
                page.design_mood = MOOD_TO_DESIGN.get(analysis.mood, "")

    # Generate narrative text
    sections = generate_narrative(pages, analyses, title=title)
    for section in sections:
        if 0 <= section.page_index < len(pages):
            page = pages[section.page_index]
            page.quote = {
                "text": section.text,
                "type": section.narrative_type,
            }
