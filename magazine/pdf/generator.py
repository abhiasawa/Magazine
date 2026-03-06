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

    W = 297 * mm
    H = 210 * mm
    MARGIN = 20 * mm

    obsidian = HexColor("#090909")
    coal = HexColor("#171717")
    ivory = HexColor("#f4f1ea")
    parchment = HexColor("#e8e0d1")
    sand = HexColor("#d9d1c1")
    taupe = HexColor("#8b8478")
    gold = HexColor("#c7aa73")
    smoke = HexColor("#efebe4")
    white = Color(1, 1, 1)

    c = canvas.Canvas(str(output_path), pagesize=(W, H))

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

            def _draw_cover_layer(alpha=0.16):
                cover_scale = max(inner_w / iw, inner_h / ih)
                cover_w = iw * cover_scale
                cover_h = ih * cover_scale
                cover_x = inner_x + (inner_w - cover_w) / 2
                cover_y = inner_y + (inner_h - cover_h) / 2
                c.saveState()
                p = c.beginPath()
                p.rect(inner_x, inner_y, inner_w, inner_h)
                c.clipPath(p, stroke=0, fill=0)
                c.drawImage(str(path), cover_x, cover_y, cover_w, cover_h, preserveAspectRatio=False)
                c.setFillColor(Color(smoke.red, smoke.green, smoke.blue, alpha=alpha))
                c.rect(inner_x, inner_y, inner_w, inner_h, fill=1, stroke=0)
                c.restoreState()

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

                if gap_ratio > 0.2 and ratio_delta >= 0.2:
                    _draw_cover_layer(alpha=0.22)

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

    def _draw_text_block(text, x, y, font, size, color, max_width=None, align="left"):
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
        leading = size * 1.3
        for line in lines:
            if align == "center":
                lw = c.stringWidth(line, font, size)
                c.drawString(x + (max_width - lw) / 2, y, line)
            else:
                c.drawString(x, y, line)
            y -= leading
        return y

    def _draw_divider(x1, x2, y, color=None):
        c.setStrokeColor(color or Color(1, 1, 1, alpha=0.18))
        c.setLineWidth(0.3)
        c.line(x1, y, x2, y)

    def _editorial_bg(light=True):
        _fill_page(ivory if light else obsidian)
        c.setFillColor(Color(sand.red, sand.green, sand.blue, alpha=0.18 if light else 0.10))
        c.circle(W * 0.13, H * 0.84, 36 * mm, fill=1, stroke=0)
        c.circle(W * 0.88, H * 0.2, 26 * mm, fill=1, stroke=0)
        c.setFillColor(Color(gold.red, gold.green, gold.blue, alpha=0.12))
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

        c.setFillColor(Color(1, 1, 1, alpha=0.42))
        c.setFont("Helvetica", 8)
        c.drawString(18 * mm, H - 16 * mm, "ESTABLISHED 2026")
        x = 26 * mm
        y = H - 42 * mm
        lines = [
            ("Turn", white),
            ("memories", ivory),
            ("into", white),
            ("something", Color(1, 1, 1, alpha=0.55)),
            ("you hold.", white),
        ]
        for text, color in lines:
            c.setFillColor(color)
            c.setFont("Times-BoldItalic", 34 if text != "memories" else 38)
            c.drawString(x, y, text)
            y -= 14 * mm

        _draw_divider(x, x + 46 * mm, y + 4 * mm, Color(gold.red, gold.green, gold.blue, alpha=0.35))
        y -= 8 * mm
        hero_sub = (
            "Choose moments directly from Google Photos and turn them into "
            "a print-ready editorial volume."
        )
        y = _draw_text_block(hero_sub, x, y, "Helvetica", 10.5, Color(1, 1, 1, alpha=0.72), W * 0.38, "left")
        if page.title and page.title.strip() and page.title.strip().lower() not in {"magazine", "held", "monograph", "maison folio"}:
            c.setFont("Helvetica-Bold", 9)
            c.setFillColor(Color(gold.red, gold.green, gold.blue, alpha=0.82))
            c.drawRightString(W - 20 * mm, 22 * mm, page.title.upper())

    def _back_cover(page):
        _editorial_bg(light=False)
        if page.photos:
            _draw_panel_photo(page.photos[0], 52 * mm, 24 * mm, W - 104 * mm, H - 48 * mm, matte=4 * mm, panel=ivory)

    def _dedication(page):
        _editorial_bg(light=True)

    def _big_polaroid(page):
        _editorial_bg(light=True)
        if page.photos:
            _draw_panel_photo(page.photos[0], 44 * mm, 18 * mm, W - 88 * mm, H - 36 * mm, matte=5 * mm, panel=ivory)

    def _full_bleed(page):
        _editorial_bg(light=False)
        if page.photos:
            _draw_panel_photo(page.photos[0], 18 * mm, 18 * mm, W - 36 * mm, H - 36 * mm, matte=4 * mm, panel=ivory)

    def _two_photos(page):
        _editorial_bg(light=True)
        gap = 8 * mm
        iw = (W - (2 * MARGIN) - gap) / 2
        ih = H - 44 * mm
        for i, photo in enumerate(page.photos[:2]):
            x = MARGIN + i * (iw + gap)
            y = 22 * mm + (4 * mm if i % 2 else 0)
            _draw_panel_photo(photo, x, y, iw, ih - (4 * mm if i % 2 else 0), matte=4 * mm, panel=ivory)

    def _three_photos(page):
        _editorial_bg(light=True)
        gap = 8 * mm
        left_w = W * 0.56
        right_w = W - left_w - 2 * MARGIN - gap
        top_h = H - 44 * mm
        bot_h = (top_h - gap) / 2
        if len(page.photos) >= 1:
            _draw_panel_photo(page.photos[0], MARGIN, 22 * mm, left_w - MARGIN, top_h, matte=4 * mm, panel=ivory)
        for i, photo in enumerate(page.photos[1:3]):
            x = left_w + gap
            y = 22 * mm + (1 - i) * (bot_h + gap)
            _draw_panel_photo(photo, x, y, right_w, bot_h, matte=4 * mm, panel=parchment)

    def _four_photos(page):
        _editorial_bg(light=True)
        gap = 8 * mm
        iw = (W - (2 * MARGIN) - gap) / 2
        ih = (H - 44 * mm - gap) / 2
        positions = [
            (MARGIN, 22 * mm + ih + gap),
            (MARGIN + iw + gap, 22 * mm + ih + gap),
            (MARGIN, 22 * mm),
            (MARGIN + iw + gap, 22 * mm),
        ]
        for i, photo in enumerate(page.photos[:4]):
            x, y = positions[i]
            _draw_panel_photo(photo, x, y, iw, ih, matte=4 * mm, panel=ivory if i % 2 == 0 else parchment)

    def _editorial(page):
        _editorial_bg(light=False)
        img_w = W * 0.58
        if page.photos:
            _draw_panel_photo(page.photos[0], 18 * mm, 18 * mm, img_w, H - 36 * mm, matte=4 * mm, panel=ivory)
        c.setFillColor(Color(1, 1, 1, alpha=0.07))
        c.rect(img_w + 28 * mm, 26 * mm, W - img_w - 50 * mm, H - 52 * mm, fill=1, stroke=0)
        c.setFillColor(Color(gold.red, gold.green, gold.blue, alpha=0.22))
        c.rect(img_w + 28 * mm, 26 * mm, 2 * mm, H - 52 * mm, fill=1, stroke=0)

    def _simple(page):
        """Fallback for unknown templates: place photos in a grid."""
        _editorial_bg(light=True)
        n = len(page.photos)
        if n == 0:
            return
        cols = 2 if n > 1 else 1
        rows = (n + cols - 1) // cols
        gap = 8 * mm
        iw = (W - 2 * MARGIN - (cols - 1) * gap) / cols
        ih = (H - 44 * mm - (rows - 1) * gap) / rows
        for i, photo in enumerate(page.photos):
            col = i % cols
            row = i // cols
            x = MARGIN + col * (iw + gap)
            y = H - 22 * mm - (row + 1) * ih - row * gap
            _draw_panel_photo(photo, x, y, iw, ih, matte=4 * mm, panel=ivory)

    # ── Dispatch ──

    template_map = {
        "cover": _cover,
        "back_cover": _back_cover,
        "dedication": _dedication,
        "full_bleed": _full_bleed,
        "cinematic": _full_bleed,
        "photo_quote_overlay": _full_bleed,
        "big_polaroid": _big_polaroid,
        "collage2": _two_photos,
        "two_photo": _two_photos,
        "collage3": _three_photos,
        "three_photo": _three_photos,
        "collage_stack": _three_photos,
        "collage4": _four_photos,
        "mosaic": _four_photos,
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
