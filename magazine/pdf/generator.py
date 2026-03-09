"""PDF generation using reportlab (pure Python, no system deps)."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse, unquote

import click
from tqdm import tqdm

from magazine.config import (
    OUTPUT_DIR,
    PRINT_DIR,
    ORIGINALS_DIR,
    DEFAULT_STYLE,
)
from magazine.layout.engine import PageSpec
from magazine.processing.images import make_print_image

logger = logging.getLogger(__name__)

# Paths
PDF_DIR = Path(__file__).parent
TEMPLATES_DIR = PDF_DIR / "templates"
STATIC_DIR = PDF_DIR / "static"
ASSETS_DIR = PDF_DIR / "assets"

# Approximate target slot sizes by template and index.
_SLOT_TARGETS = {
    "cover": {0: (2300, 1900)},
    "back_cover": {0: (1200, 1200)},
    "full_bleed": {0: (2551, 3579)},
    "cinematic": {0: (2551, 1450)},
    "editorial": {0: (1800, 2600)},
    "big_polaroid": {0: (2100, 2600)},
    "photo_quote_overlay": {0: (2551, 3579)},
    "collage2": {0: (1700, 1700), 1: (1700, 1700)},
    "two_photo": {0: (1800, 2200), 1: (1800, 2200)},
    "collage3": {0: (1800, 1350), 1: (1600, 1200), 2: (1800, 1400)},
    "three_photo": {0: (2200, 1700), 1: (1400, 1200), 2: (1400, 1200)},
    "collage4": {0: (1500, 1100), 1: (1500, 1100), 2: (1500, 1100), 3: (1500, 1100)},
    "mosaic": {0: (1300, 900), 1: (1300, 900), 2: (1300, 900), 3: (1300, 900)},
    "collage_stack": {0: (1900, 1400), 1: (1900, 1400), 2: (1900, 1400)},
}


def _slot_size(template: str, idx: int) -> tuple[int, int]:
    slots = _SLOT_TARGETS.get(template, {})
    if idx in slots:
        return slots[idx]
    return 2551, 3579


def _focal_point(photo: dict) -> tuple[float, float] | None:
    faces = photo.get("faces")
    width = photo.get("width")
    height = photo.get("height")
    if not isinstance(faces, list) or not faces or not width or not height:
        return None

    centers_x = []
    centers_y = []
    for face in faces:
        x = float(face.get("x", 0))
        y = float(face.get("y", 0))
        w = float(face.get("w", 0))
        h = float(face.get("h", 0))
        centers_x.append(x + w / 2)
        centers_y.append(y + h / 2)

    if not centers_x or not centers_y:
        return None

    return (sum(centers_x) / len(centers_x) / float(width), sum(centers_y) / len(centers_y) / float(height))


def prepare_print_images(pages: list[PageSpec]) -> list[PageSpec]:
    """Generate print-quality images for all photo slots in the layout."""
    jobs = []
    for page in pages:
        for idx, photo in enumerate(page.photos):
            jobs.append((page, idx, photo))

    click.echo(f"Preparing {len(jobs)} print image slots...")

    for page, idx, photo in tqdm(jobs, desc="Print images"):
        pid = photo["id"]
        original = Path(photo["original"])
        if not original.exists():
            original = ORIGINALS_DIR / f"{pid}.jpg"

        if not original.exists():
            click.echo(f"Warning: Original not found for {pid}")
            photo["print_path"] = ""
            continue

        width, height = _slot_size(page.template, idx)
        focus = _focal_point(photo)
        filename = f"{pid}_{page.template}_{idx}_{width}x{height}"
        print_path = make_print_image(
            original,
            PRINT_DIR,
            target_width=width,
            target_height=height,
            focal_point=focus,
            filename=filename,
        )
        photo["print_path"] = print_path.as_uri()

    return pages


# ── Image / text helpers ──────────────────────────────────────────────────


def _uri_to_path(uri: str) -> Path | None:
    """Convert a file:// URI back to a filesystem path."""
    if not uri:
        return None
    if uri.startswith("file://"):
        return Path(unquote(urlparse(uri).path))
    return Path(uri)


def _photo_path(photo: dict) -> Path | None:
    """Resolve the best available image path for a photo."""
    for key in ("print_path", "original"):
        val = photo.get(key, "")
        if val:
            p = _uri_to_path(val)
            if p and p.exists():
                return p
    pid = photo.get("id", "")
    if pid:
        fallback = ORIGINALS_DIR / f"{pid}.jpg"
        if fallback.exists():
            return fallback
    return None


# ── Reportlab renderer ────────────────────────────────────────────────────


def _render_pdf(pages: list[PageSpec], output_path: Path):
    """Render magazine pages to PDF using reportlab."""
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import Color, HexColor
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    W = 297 * mm
    H = 210 * mm
    MARGIN = 20 * mm

    # ── Legacy color aliases (used by cover + back_cover which keep their bespoke look) ──
    obsidian = HexColor("#090909")
    coal = HexColor("#171717")
    ivory = HexColor("#f4f1ea")
    parchment = HexColor("#e8e0d1")
    sand = HexColor("#d9d1c1")
    taupe = HexColor("#8b8478")
    gold = HexColor("#c7aa73")
    smoke = HexColor("#efebe4")
    white = Color(1, 1, 1)

    # ── Mood-driven palette system ──
    # Each palette is a dict of semantic color roles keyed by palette_hint.
    PALETTES = {
        "warm_gold": {
            "bg": HexColor("#0C0A07"),
            "surface": HexColor("#1A1610"),
            "text": HexColor("#F0EBE0"),
            "accent": HexColor("#C7AA73"),
            "muted": HexColor("#8B7D6B"),
            "panel": HexColor("#f4f1ea"),
            "smoke": HexColor("#efebe4"),
        },
        "cool_stone": {
            "bg": HexColor("#0A0B0E"),
            "surface": HexColor("#14161C"),
            "text": HexColor("#E8E6E1"),
            "accent": HexColor("#9BA8B8"),
            "muted": HexColor("#6B7280"),
            "panel": HexColor("#E8E6E1"),
            "smoke": HexColor("#DDD9D2"),
        },
        "deep_shadow": {
            "bg": HexColor("#050505"),
            "surface": HexColor("#0F0F0F"),
            "text": HexColor("#D4CFC5"),
            "accent": HexColor("#A89070"),
            "muted": HexColor("#5C5549"),
            "panel": HexColor("#D4CFC5"),
            "smoke": HexColor("#C8C1B6"),
        },
        "soft_light": {
            "bg": HexColor("#F4F1EA"),
            "surface": HexColor("#EDE8DD"),
            "text": HexColor("#1A1814"),
            "accent": HexColor("#B8956A"),
            "muted": HexColor("#9B8E7E"),
            "panel": HexColor("#f4f1ea"),
            "smoke": HexColor("#efebe4"),
        },
    }
    DEFAULT_PALETTE = PALETTES["warm_gold"]

    def _pal(page):
        """Resolve palette for a page, defaulting to warm_gold."""
        return PALETTES.get(page.palette_hint, DEFAULT_PALETTE)

    def _page_accent(page):
        """Return the accent color for a page's palette."""
        pal = _pal(page)
        return pal["accent"]

    # ── Fonts ──
    display_font = "Times-BoldItalic"
    serif_font = "Times-Roman"
    sans_font = "Helvetica"

    font_defs = [
        ("MaisonDisplay", ASSETS_DIR / "fonts" / "CormorantGaramond-BoldItalic.ttf"),
        ("MaisonSerif", ASSETS_DIR / "fonts" / "CormorantGaramond-Medium.ttf"),
        ("MaisonSans", ASSETS_DIR / "fonts" / "Manrope-Medium.ttf"),
    ]
    for font_name, font_path in font_defs:
        if font_path.exists():
            try:
                pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
            except Exception:
                continue

    if (ASSETS_DIR / "fonts" / "CormorantGaramond-BoldItalic.ttf").exists():
        display_font = "MaisonDisplay"
    if (ASSETS_DIR / "fonts" / "CormorantGaramond-Medium.ttf").exists():
        serif_font = "MaisonSerif"
    if (ASSETS_DIR / "fonts" / "Manrope-Medium.ttf").exists():
        sans_font = "MaisonSans"

    c = canvas.Canvas(str(output_path), pagesize=(W, H))

    # ── Core drawing primitives ──

    def _fill_page(color):
        c.setFillColor(color)
        c.rect(0, 0, W, H, fill=1, stroke=0)

    def _draw_image_contain(
        photo,
        x,
        y,
        w,
        h,
        pad=0,
        bg=None,
        valign=0.5,
        crop_tolerance=0.12,
        adaptive_zoom=True,
    ):
        """Draw a photo with a fit-first strategy and optional gentle zoom."""
        path = _photo_path(photo)
        if not path:
            return
        try:
            from PIL import Image as PILImage

            with PILImage.open(path) as img:
                iw, ih = img.size

            if bg:
                c.setFillColor(bg)
                c.rect(x, y, w, h, fill=1, stroke=0)

            inner_x = x + pad
            inner_y = y + pad
            inner_w = max(1, w - pad * 2)
            inner_h = max(1, h - pad * 2)

            contain_scale = min(inner_w / iw, inner_h / ih)
            scale = contain_scale
            image_ratio = iw / ih
            frame_ratio = inner_w / inner_h
            ratio_delta = abs(image_ratio - frame_ratio) / max(frame_ratio, 0.01)

            if adaptive_zoom:
                draw_w = iw * contain_scale
                draw_h = ih * contain_scale
                gap_ratio = max(1 - (draw_w / inner_w), 1 - (draw_h / inner_h))
                if gap_ratio > 0.12:
                    if ratio_delta < 0.12:
                        tuned_crop_tolerance = max(crop_tolerance, 0.18)
                    elif ratio_delta < 0.24:
                        tuned_crop_tolerance = max(crop_tolerance * 0.9, 0.12)
                    else:
                        tuned_crop_tolerance = 0.0

                    max_scale_w = inner_w / max(1, iw * (1 - tuned_crop_tolerance))
                    max_scale_h = inner_h / max(1, ih * (1 - tuned_crop_tolerance))
                    allowed_scale = min(max_scale_w, max_scale_h)
                    if allowed_scale > contain_scale:
                        zoom_strength = min(1.0, (gap_ratio - 0.12) / 0.26)
                        scale = contain_scale + ((allowed_scale - contain_scale) * zoom_strength)

            draw_w = iw * scale
            draw_h = ih * scale

            focus = _focal_point(photo)
            if focus:
                fx, fy = focus
            else:
                fx, fy = 0.5, valign

            if draw_w > inner_w:
                overflow_x = draw_w - inner_w
                offset_x = inner_x - (overflow_x * fx)
            else:
                offset_x = inner_x + (inner_w - draw_w) / 2

            if draw_h > inner_h:
                overflow_y = draw_h - inner_h
                offset_y = inner_y - (overflow_y * fy)
            else:
                offset_y = inner_y + (inner_h - draw_h) * valign

            c.saveState()
            p = c.beginPath()
            p.rect(inner_x, inner_y, inner_w, inner_h)
            c.clipPath(p, stroke=0, fill=0)
            c.drawImage(str(path), offset_x, offset_y, draw_w, draw_h, preserveAspectRatio=False)
            c.restoreState()
        except Exception:
            try:
                c.drawImage(str(path), x, y, w, h, preserveAspectRatio=True)
            except Exception:
                pass

    def _draw_panel_photo(photo, x, y, w, h, matte=5 * mm, panel=ivory, crop_tolerance=0.12):
        shadow = 2.5 * mm
        c.setFillColor(Color(0, 0, 0, alpha=0.12))
        c.rect(x + shadow, y - shadow, w, h, fill=1, stroke=0)
        c.setFillColor(panel)
        c.rect(x, y, w, h, fill=1, stroke=0)
        c.setStrokeColor(Color(0, 0, 0, alpha=0.08))
        c.setLineWidth(0.5)
        c.rect(x, y, w, h, fill=0, stroke=1)
        _draw_image_contain(
            photo,
            x + matte,
            y + matte,
            w - 2 * matte,
            h - 2 * matte,
            bg=smoke,
            crop_tolerance=crop_tolerance,
            adaptive_zoom=True,
        )

    def _draw_bleed_photo(photo, x, y, w, h, crop_tolerance=0.18, bg=None):
        _draw_image_contain(
            photo,
            x,
            y,
            w,
            h,
            pad=0,
            bg=bg,
            crop_tolerance=crop_tolerance,
            adaptive_zoom=True,
        )

    def _draw_gutter(x, y, w, h, fill=None):
        c.setFillColor(fill or ivory)
        c.rect(x, y, w, h, fill=1, stroke=0)

    def _draw_polygon_photo(photo, points, crop_tolerance=0.18, bg=None):
        path = _photo_path(photo)
        if not path:
            return
        xs = [pt[0] for pt in points]
        ys = [pt[1] for pt in points]
        x = min(xs)
        y = min(ys)
        w = max(xs) - x
        h = max(ys) - y
        if bg:
            c.setFillColor(bg)
            c.rect(x, y, w, h, fill=1, stroke=0)
        c.saveState()
        p = c.beginPath()
        first_x, first_y = points[0]
        p.moveTo(first_x, first_y)
        for px, py in points[1:]:
            p.lineTo(px, py)
        p.close()
        c.clipPath(p, stroke=0, fill=0)
        _draw_bleed_photo(photo, x, y, w, h, crop_tolerance=crop_tolerance, bg=bg)
        c.restoreState()

    def _draw_shadowed_frame(photo, x, y, w, h, matte=3 * mm, shadow=3 * mm, panel=ivory, crop_tolerance=0.15):
        c.setFillColor(Color(0, 0, 0, alpha=0.16))
        c.roundRect(x + shadow, y - shadow, w, h, 2 * mm, fill=1, stroke=0)
        c.setFillColor(panel)
        c.roundRect(x, y, w, h, 1.5 * mm, fill=1, stroke=0)
        c.setStrokeColor(Color(0, 0, 0, alpha=0.06))
        c.setLineWidth(0.5)
        c.roundRect(x, y, w, h, 1.5 * mm, fill=0, stroke=1)
        _draw_image_contain(
            photo,
            x + matte,
            y + matte,
            w - 2 * matte,
            h - 2 * matte,
            bg=smoke,
            crop_tolerance=crop_tolerance,
            adaptive_zoom=True,
        )

    def _draw_split_separator(x, y, w, h, fill=ivory):
        c.setFillColor(fill)
        c.saveState()
        p = c.beginPath()
        p.moveTo(x, y)
        p.lineTo(x + w * 0.72, y)
        p.lineTo(x + w, y + h * 0.5)
        p.lineTo(x + w * 0.72, y + h)
        p.lineTo(x, y + h)
        p.lineTo(x + w * 0.28, y + h * 0.5)
        p.close()
        c.drawPath(p, fill=1, stroke=0)
        c.restoreState()

    def _draw_accent_rule(x, y, length, horizontal=True, alpha=0.28, color=None):
        ac = color or gold
        c.setStrokeColor(Color(ac.red, ac.green, ac.blue, alpha=alpha))
        c.setLineWidth(0.9)
        if horizontal:
            c.line(x, y, x + length, y)
        else:
            c.line(x, y, x, y + length)

    def _draw_corner_bracket(x, y, size=12 * mm, color=None):
        c.setStrokeColor(color or Color(1, 1, 1, alpha=0.18))
        c.setLineWidth(0.7)
        c.line(x, y, x + size, y)
        c.line(x, y, x, y - size)

    def _draw_text_block(text, x, y, font, size, color, max_width=None, align="left", leading_mult=1.3):
        """Draw wrapped text and return the final y position."""
        c.setFont(font, size)
        c.setFillColor(color)
        if not max_width:
            max_width = W - 2 * MARGIN
        words = text.split()
        lines = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            if c.stringWidth(test, font, size) <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        leading = size * leading_mult
        for line in lines:
            if align == "center":
                lw = c.stringWidth(line, font, size)
                c.drawString(x + (max_width - lw) / 2, y, line)
            elif align == "right":
                lw = c.stringWidth(line, font, size)
                c.drawString(x + max_width - lw, y, line)
            else:
                c.drawString(x, y, line)
            y -= leading
        return y

    def _draw_divider(x1, x2, y, color=None):
        c.setStrokeColor(color or Color(1, 1, 1, alpha=0.18))
        c.setLineWidth(0.3)
        c.line(x1, y, x2, y)

    # ── Narrative text helpers ──

    # Consistent text strip dimensions (used by every single-photo template)
    TEXT_STRIP_H = 26 * mm   # height of bottom text zone
    TEXT_STRIP_X = 24 * mm   # left margin for sentence text
    TEXT_STRIP_Y = 14 * mm   # baseline of first text line (from page bottom)
    TEXT_STRIP_W = W * 0.52  # reading width (~155mm, left-aligned)

    def _draw_gradient_scrim(x, y, w, h, steps=12):
        """Draw a bottom-to-top gradient scrim for text legibility over photos."""
        step_h = h / steps
        for i in range(steps):
            alpha = 0.52 * (1 - i / steps) ** 1.8
            c.setFillColor(Color(0, 0, 0, alpha=alpha))
            c.rect(x, y + i * step_h, w, step_h + 0.5, fill=1, stroke=0)

    def _draw_text_strip(page, has_photo_behind=False):
        """Render narrative sentence in a consistent bottom-left strip.

        Every single-photo template calls this so the reader always
        finds text in the same place: bottom-left of the page.

        When has_photo_behind=True, a gradient scrim is drawn first
        and text is rendered in white. Otherwise text uses the palette
        text color on the existing background.
        """
        if not page.quote or page.quote.get("type") != "sentence":
            return
        text = page.quote.get("text", "")
        if not text:
            return
        pal = _pal(page)

        if has_photo_behind:
            # Gradient scrim across bottom for legibility over photos
            _draw_gradient_scrim(0, 0, W * 0.60, TEXT_STRIP_H + 10 * mm)
            text_color = Color(1, 1, 1, alpha=0.92)
        else:
            text_color = Color(
                pal["text"].red, pal["text"].green, pal["text"].blue, alpha=0.88,
            )

        _draw_text_block(
            text, TEXT_STRIP_X, TEXT_STRIP_Y,
            font=serif_font, size=13,
            color=text_color,
            max_width=TEXT_STRIP_W,
            leading_mult=1.7,
        )

    def _draw_narrative_sentence(page, x, y, max_width):
        """Render a narrative sentence on a page if present.

        DEPRECATED — kept for any templates that need custom placement.
        Prefer _draw_text_strip() for consistent bottom-left positioning.
        """
        if not page.quote or page.quote.get("type") != "sentence":
            return
        text = page.quote.get("text", "")
        if not text:
            return
        pal = _pal(page)
        _draw_text_block(
            text, x, y,
            font=serif_font, size=14,
            color=Color(pal["text"].red, pal["text"].green, pal["text"].blue, alpha=0.88),
            max_width=max_width,
            leading_mult=1.7,
        )

    def _draw_heading_word(page, x, y, max_width, size=36, align="center"):
        """Render an evocative heading word on a multi-photo page."""
        if not page.quote or page.quote.get("type") != "heading_word":
            return
        text = page.quote.get("text", "")
        if not text:
            return
        pal = _pal(page)
        # Wide letter-spacing via manual character placement for display font
        c.setFont(display_font, size)
        accent = pal["accent"]
        c.setFillColor(Color(accent.red, accent.green, accent.blue, alpha=0.82))
        text_w = c.stringWidth(text, display_font, size)
        if align == "center":
            tx = x + (max_width - text_w) / 2
        elif align == "right":
            tx = x + max_width - text_w
        else:
            tx = x
        c.drawString(tx, y, text)

    def _draw_vertical_heading(page, x, y, height):
        """Render heading word vertically (rotated 90deg) in a gutter."""
        if not page.quote or page.quote.get("type") != "heading_word":
            return
        text = page.quote.get("text", "").upper()
        if not text:
            return
        pal = _pal(page)
        c.saveState()
        c.translate(x, y)
        c.rotate(90)
        c.setFont(sans_font, 8)
        c.setFillColor(Color(pal["muted"].red, pal["muted"].green, pal["muted"].blue, alpha=0.62))
        # Draw with wide letter-spacing
        char_x = 0
        for ch in text:
            c.drawString(char_x, 0, ch)
            char_x += c.stringWidth(ch, sans_font, 8) + 2.5
        c.restoreState()

    def _draw_pull_quote_mark(x, y, pal):
        """Large decorative opening quote mark behind editorial text."""
        accent = pal["accent"]
        c.setFillColor(Color(accent.red, accent.green, accent.blue, alpha=0.08))
        c.setFont(display_font, 96)
        c.drawString(x, y, "\u201C")

    # ── Background helpers ──

    def _editorial_bg(light=True, page=None):
        pal = _pal(page) if page else DEFAULT_PALETTE
        if light:
            _fill_page(pal.get("panel", ivory))
        else:
            _fill_page(pal["bg"])
        accent = pal["accent"]
        muted = pal["muted"]
        mood = page.design_mood if page else ""
        if mood == "intimate":
            c.setFillColor(Color(muted.red, muted.green, muted.blue, alpha=0.10))
            c.circle(W * 0.15, H * 0.28, 44 * mm, fill=1, stroke=0)
        elif mood == "expansive":
            c.setFillColor(Color(accent.red, accent.green, accent.blue, alpha=0.08))
            c.rect(W * 0.06, H * 0.48, W * 0.88, 1.5 * mm, fill=1, stroke=0)
        elif mood == "reflective":
            c.setFillColor(Color(muted.red, muted.green, muted.blue, alpha=0.08))
            c.circle(W * 0.82, H * 0.72, 32 * mm, fill=1, stroke=0)
            c.circle(W * 0.74, H * 0.62, 18 * mm, fill=1, stroke=0)
        else:
            base = sand if light else muted
            c.setFillColor(Color(base.red, base.green, base.blue, alpha=0.18 if light else 0.10))
            c.circle(W * 0.13, H * 0.84, 36 * mm, fill=1, stroke=0)
            c.circle(W * 0.88, H * 0.2, 26 * mm, fill=1, stroke=0)
            c.setFillColor(Color(accent.red, accent.green, accent.blue, alpha=0.12))
            c.rect(W * 0.68, H * 0.64, 52 * mm, 2 * mm, fill=1, stroke=0)
            c.rect(W * 0.08, H * 0.14, 34 * mm, 2 * mm, fill=1, stroke=0)

    # ── Template renderers ──

    def _cover(page):
        _fill_page(obsidian)
        c.setFillColor(Color(1, 1, 1, alpha=0.05))
        c.circle(W * 0.86, H * 0.83, 42 * mm, fill=1, stroke=0)
        c.circle(W * 0.77, H * 0.2, 22 * mm, fill=1, stroke=0)
        c.setFillColor(Color(gold.red, gold.green, gold.blue, alpha=0.18))
        c.rect(18 * mm, 24 * mm, 62 * mm, 1.2 * mm, fill=1, stroke=0)
        c.rect(W - 78 * mm, H - 28 * mm, 60 * mm, 1.2 * mm, fill=1, stroke=0)

        c.setStrokeColor(Color(1, 1, 1, alpha=0.12))
        c.setLineWidth(0.5)
        c.rect(14 * mm, 14 * mm, W - 28 * mm, H - 28 * mm, fill=0, stroke=1)

        c.setFillColor(Color(1, 1, 1, alpha=0.04))
        c.rect(W * 0.58, 26 * mm, 78 * mm, H - 52 * mm, fill=1, stroke=0)
        c.setFillColor(Color(gold.red, gold.green, gold.blue, alpha=0.16))
        c.rect(W * 0.58, 26 * mm, 2 * mm, H - 52 * mm, fill=1, stroke=0)
        c.setStrokeColor(Color(1, 1, 1, alpha=0.08))
        c.setLineWidth(0.4)
        c.rect(W * 0.62, 34 * mm, 60 * mm, 44 * mm, fill=0, stroke=1)
        c.rect(W * 0.67, 86 * mm, 42 * mm, 30 * mm, fill=0, stroke=1)
        c.rect(W * 0.61, H - 66 * mm, 54 * mm, 18 * mm, fill=0, stroke=1)

        c.setFillColor(Color(1, 1, 1, alpha=0.05))
        c.circle(W * 0.74, H * 0.52, 16 * mm, fill=1, stroke=0)
        c.circle(W * 0.84, H * 0.44, 8 * mm, fill=1, stroke=0)
        c.circle(W * 0.69, H * 0.31, 6 * mm, fill=1, stroke=0)

        c.setFillColor(Color(1, 1, 1, alpha=0.42))
        c.setFont(sans_font, 8)
        c.drawString(18 * mm, H - 16 * mm, "MAISON FOLIO")

        c.setFillColor(Color(gold.red, gold.green, gold.blue, alpha=0.82))
        c.setFont(sans_font, 8.5)
        c.drawString(26 * mm, H - 42 * mm, "PRIVATE EDITION")

        c.setFillColor(ivory)
        c.setFont(display_font, 56)
        c.drawString(24 * mm, H * 0.56, "Memories")

        c.setFillColor(Color(1, 1, 1, alpha=0.34))
        c.setFont(serif_font, 24)
        c.drawString(28 * mm, H * 0.43, "worth keeping")

        _draw_divider(26 * mm, 76 * mm, H * 0.37, Color(gold.red, gold.green, gold.blue, alpha=0.35))

        c.setStrokeColor(Color(gold.red, gold.green, gold.blue, alpha=0.24))
        c.setLineWidth(0.6)
        c.line(24 * mm, H * 0.62, 24 * mm, H * 0.34)
        c.line(82 * mm, H * 0.62, 82 * mm, H * 0.48)

        c.setFillColor(Color(1, 1, 1, alpha=0.24))
        c.setFont(display_font, 26)
        c.drawRightString(W - 22 * mm, 24 * mm, "Vol. I")

    def _back_cover(page):
        _fill_page(obsidian)
        if page.photos:
            _draw_bleed_photo(page.photos[0], 0, 0, W, H, crop_tolerance=0.2, bg=coal)
            c.setFillColor(Color(0, 0, 0, alpha=0.24))
            c.rect(W - 30 * mm, 0, 30 * mm, H, fill=1, stroke=0)
            _draw_corner_bracket(W - 18 * mm, H - 18 * mm, size=10 * mm, color=Color(1, 1, 1, alpha=0.16))

    def _dedication(page):
        _editorial_bg(light=True, page=page)

    def _big_polaroid(page):
        _editorial_bg(light=True, page=page)
        if page.photos:
            pal = _pal(page)
            _draw_panel_photo(page.photos[0], 44 * mm, TEXT_STRIP_H + 4 * mm, W - 88 * mm, H - TEXT_STRIP_H - 28 * mm, matte=5 * mm, panel=pal["panel"])
        # Consistent bottom-left text strip
        _draw_text_strip(page, has_photo_behind=False)

    def _full_bleed(page):
        pal = _pal(page)
        _fill_page(pal["bg"])
        if page.photos:
            _draw_bleed_photo(page.photos[0], 0, 0, W, H, crop_tolerance=0.22, bg=pal["surface"])
            # Subtle left edge darkening
            c.setFillColor(Color(0, 0, 0, alpha=0.14))
            c.rect(0, 0, 14 * mm, H, fill=1, stroke=0)
            accent = pal["accent"]
            _draw_accent_rule(10 * mm, H - 18 * mm, 42 * mm, horizontal=False, alpha=0.30, color=accent)
            _draw_accent_rule(W - 52 * mm, 16 * mm, 34 * mm, horizontal=True, alpha=0.30, color=accent)
        # Consistent bottom-left text strip (with scrim over photo)
        _draw_text_strip(page, has_photo_behind=True)

    def _cinematic(page):
        pal = _pal(page)
        _fill_page(pal["bg"])
        if page.photos:
            _draw_polygon_photo(
                page.photos[0],
                [
                    (0, TEXT_STRIP_H),
                    (W * 0.78, TEXT_STRIP_H),
                    (W, H * 0.36),
                    (W, H),
                    (W * 0.18, H),
                    (0, H * 0.72),
                ],
                crop_tolerance=0.2,
                bg=pal["surface"],
            )
            accent = pal["accent"]
            _draw_split_separator(W * 0.74, H * 0.16, 18 * mm, 48 * mm, fill=pal["panel"])
        # Consistent bottom-left text strip (below the polygon photo)
        _draw_text_strip(page, has_photo_behind=False)

    def _two_photos(page):
        pal = _pal(page)
        _fill_page(pal["bg"])
        gap = 4 * mm
        left_w = W * 0.7
        right_w = W - left_w - gap
        if len(page.photos) >= 1:
            _draw_bleed_photo(page.photos[0], 0, 0, left_w, H, crop_tolerance=0.18, bg=pal["surface"])
        if len(page.photos) >= 2:
            _draw_shadowed_frame(
                page.photos[1],
                left_w - 12 * mm,
                16 * mm,
                right_w + 4 * mm,
                H - 32 * mm,
                matte=2.5 * mm,
                shadow=4 * mm,
                panel=pal["panel"],
                crop_tolerance=0.14,
            )
        accent = pal["accent"]
        _draw_accent_rule(left_w + gap + 12 * mm, H - 20 * mm, 22 * mm, horizontal=True, alpha=0.34, color=accent)
        # Heading word at top center
        _draw_heading_word(page, 0, H - 18 * mm, max_width=left_w, size=32, align="center")

    def _three_photos(page):
        pal = _pal(page)
        _fill_page(pal.get("panel", ivory))
        gap = 4 * mm
        left_w = W * 0.6
        right_w = W - left_w - gap
        # Photo 0: large left panel (full height)
        if len(page.photos) >= 1:
            _draw_bleed_photo(page.photos[0], 0, 0, left_w, H, crop_tolerance=0.18, bg=pal["smoke"])
        # Photos 1 & 2: right column, split vertically
        for i, photo in enumerate(page.photos[1:3]):
            x = left_w + gap
            y = H - (i + 1) * ((H - gap) / 2)
            _draw_bleed_photo(photo, x, y, right_w, (H - gap) / 2, crop_tolerance=0.16, bg=pal["smoke"])
        _draw_gutter(left_w, 0, gap, H, fill=pal.get("panel", ivory))
        _draw_gutter(left_w + gap, H / 2 - gap / 2, right_w, gap, fill=pal.get("panel", ivory))
        # Vertical heading in the gutter
        _draw_vertical_heading(page, left_w + gap / 2 - 1, H * 0.35, H * 0.3)

    def _four_photos(page):
        pal = _pal(page)
        _fill_page(pal.get("panel", parchment))
        gap = 4 * mm
        left_w = W * 0.54
        right_w = W - left_w - gap
        top_h = H * 0.54
        bot_h = H - top_h - gap
        positions = [
            (0, H - top_h),
            (left_w + gap, H - top_h),
            (left_w + gap, 0),
            (left_w + gap + (right_w - gap) / 2, 0),
        ]
        sizes = [
            (left_w, top_h),
            (right_w, top_h),
            ((right_w - gap) / 2, bot_h),
            ((right_w - gap) / 2, bot_h),
        ]
        if len(page.photos) >= 1:
            _draw_bleed_photo(page.photos[0], 0, 0, left_w, H, crop_tolerance=0.18, bg=pal["smoke"])
        for i, photo in enumerate(page.photos[1:4], start=1):
            x, y = positions[i]
            w_slot, h_slot = sizes[i]
            if i == 1:
                _draw_shadowed_frame(photo, x + 6 * mm, y + 8 * mm, w_slot - 12 * mm, h_slot - 14 * mm, matte=2.5 * mm, panel=pal["panel"], crop_tolerance=0.12)
            else:
                _draw_bleed_photo(photo, x, y, w_slot, h_slot, crop_tolerance=0.14, bg=pal["smoke"])
        _draw_gutter(left_w, 0, gap, H, fill=pal.get("panel", parchment))
        _draw_gutter(left_w + gap, bot_h, right_w, gap, fill=pal.get("panel", parchment))
        _draw_gutter(left_w + gap + (right_w - gap) / 2, 0, gap, bot_h, fill=pal.get("panel", parchment))
        # Heading word at bottom center
        accent = pal["accent"]
        _draw_accent_rule(W * 0.35, 12 * mm, W * 0.3, horizontal=True, alpha=0.20, color=accent)
        _draw_heading_word(page, 0, 18 * mm, max_width=W, size=28, align="center")

    def _editorial(page):
        _editorial_bg(light=False, page=page)
        pal = _pal(page)
        img_w = W * 0.68
        if page.photos:
            _draw_polygon_photo(
                page.photos[0],
                [
                    (0, TEXT_STRIP_H),
                    (img_w, TEXT_STRIP_H),
                    (img_w - 18 * mm, H),
                    (0, H),
                ],
                crop_tolerance=0.2,
                bg=pal["surface"],
            )
        # Right sidebar — decorative accent only (text moved to bottom strip)
        sidebar_x = img_w + 8 * mm
        c.setFillColor(Color(1, 1, 1, alpha=0.04))
        c.rect(img_w + 6 * mm, TEXT_STRIP_H, W - img_w - 6 * mm, H - TEXT_STRIP_H, fill=1, stroke=0)
        accent = pal["accent"]
        c.setFillColor(Color(accent.red, accent.green, accent.blue, alpha=0.22))
        c.rect(img_w + 6 * mm, TEXT_STRIP_H, 2 * mm, H - TEXT_STRIP_H, fill=1, stroke=0)
        # Pull-quote mark as decorative element in sidebar
        if page.quote and page.quote.get("type") == "sentence":
            _draw_pull_quote_mark(sidebar_x + 2 * mm, H * 0.58, pal)
            _draw_accent_rule(sidebar_x + 6 * mm, H * 0.44, 28 * mm, horizontal=True, alpha=0.24, color=accent)
        else:
            _draw_accent_rule(sidebar_x + 6 * mm, H - 34 * mm, 28 * mm, horizontal=False, alpha=0.24, color=accent)
        # Consistent bottom-left text strip
        _draw_text_strip(page, has_photo_behind=False)

    def _mosaic(page):
        pal = _pal(page)
        _fill_page(pal.get("panel", ivory))
        gap = 4 * mm
        left_w = W * 0.58
        right_w = W - left_w - gap
        top_h = H * 0.6
        bottom_h = H - top_h - gap
        if len(page.photos) >= 1:
            _draw_bleed_photo(page.photos[0], 0, H - top_h, left_w, top_h, crop_tolerance=0.18, bg=pal["smoke"])
        if len(page.photos) >= 2:
            _draw_bleed_photo(page.photos[1], left_w + gap, H - top_h, right_w, top_h, crop_tolerance=0.18, bg=pal["smoke"])
        if len(page.photos) >= 3:
            _draw_bleed_photo(page.photos[2], 0, 0, W * 0.4, bottom_h, crop_tolerance=0.12, bg=pal["smoke"])
        if len(page.photos) >= 4:
            _draw_shadowed_frame(
                page.photos[3],
                W * 0.43,
                8 * mm,
                W * 0.3,
                bottom_h - 16 * mm,
                matte=2.8 * mm,
                panel=pal["panel"],
                crop_tolerance=0.12,
            )
        _draw_gutter(0, bottom_h, W, gap, fill=pal.get("panel", ivory))
        _draw_gutter(left_w, H - top_h, gap, top_h, fill=pal.get("panel", ivory))
        # Heading word bottom-right
        accent = pal["accent"]
        _draw_accent_rule(W * 0.55, 14 * mm, W * 0.25, horizontal=True, alpha=0.20, color=accent)
        _draw_heading_word(page, W * 0.45, 20 * mm, max_width=W * 0.5, size=26, align="center")

    def _simple(page):
        """Fallback for unknown templates: place photos in a grid."""
        _fill_page(ivory)
        n = len(page.photos)
        if n == 0:
            return
        cols = 2 if n > 1 else 1
        rows = (n + cols - 1) // cols
        gap = 4 * mm
        iw = (W - (cols - 1) * gap) / cols
        ih = (H - (rows - 1) * gap) / rows
        for i, photo in enumerate(page.photos):
            col = i % cols
            row = i // cols
            x = col * (iw + gap)
            y = H - (row + 1) * ih - row * gap
            _draw_bleed_photo(photo, x, y, iw, ih, crop_tolerance=0.16, bg=smoke)
        for col in range(cols - 1):
            _draw_gutter((col + 1) * iw + col * gap, 0, gap, H, fill=ivory)
        for row in range(rows - 1):
            _draw_gutter(0, H - (row + 1) * ih - (row + 1) * gap, W, gap, fill=ivory)

    # ── Dispatch ──

    template_map = {
        "cover": _cover,
        "back_cover": _back_cover,
        "dedication": _dedication,
        "full_bleed": _full_bleed,
        "cinematic": _cinematic,
        "photo_quote_overlay": _full_bleed,
        "big_polaroid": _big_polaroid,
        "collage2": _two_photos,
        "two_photo": _two_photos,
        "collage3": _three_photos,
        "three_photo": _three_photos,
        "collage_stack": _three_photos,
        "collage4": _four_photos,
        "mosaic": _mosaic,
        "editorial": _editorial,
    }

    for page in pages:
        renderer = template_map.get(page.template, _simple)
        renderer(page)
        c.showPage()

    c.save()


# ── Main entry point ──────────────────────────────────────────────────────


def generate_pdf(
    pages: list[PageSpec],
    output_path: str | None = None,
    style: str = DEFAULT_STYLE,
) -> Path:
    """Generate the final magazine PDF using reportlab."""
    pages = prepare_print_images(pages)

    if output_path is None:
        output_path = OUTPUT_DIR / "magazine.pdf"
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    click.echo("Generating PDF...")
    _render_pdf(pages, output_path)

    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    click.echo(f"PDF generated: {output_path} ({file_size_mb:.1f} MB)")
    click.echo(f"Pages: {len(pages)}")

    return output_path
