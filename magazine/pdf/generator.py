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
    import random

    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import Color

    W = 297 * mm
    H = 210 * mm
    MARGIN = 20 * mm

    # Core palette — clean neutrals
    bg_dark = Color(0.047, 0.047, 0.047)         # #0c0c0c
    bg_cream = Color(0.945, 0.937, 0.922)         # #f1eeeb
    ink = Color(0.067, 0.067, 0.067)              # #111111
    muted = Color(0.45, 0.45, 0.45)               # #737373
    white = Color(1, 1, 1)                         # #ffffff

    # Extended palette — neutral, desaturated
    stone = Color(0.910, 0.894, 0.878)             # #e8e4e0
    pearl = Color(0.941, 0.929, 0.910)             # #f0ede8
    charcoal = Color(0.102, 0.102, 0.102)          # #1a1a1a
    rose_gold = Color(0.788, 0.663, 0.431)         # #c9a96e

    # Background per template type
    _bg = {
        "cover": bg_dark, "back_cover": bg_dark,
        "dedication": bg_cream, "editorial": bg_cream,
        "full_bleed": bg_dark, "cinematic": bg_dark, "photo_quote_overlay": bg_dark,
        "big_polaroid": pearl,
        "collage2": bg_cream, "two_photo": pearl,
        "collage3": stone, "three_photo": bg_cream,
        "collage4": stone, "mosaic": pearl,
        "collage_stack": stone,
    }

    c = canvas.Canvas(str(output_path), pagesize=(W, H))

    def _fill_page(color):
        c.setFillColor(color)
        c.rect(0, 0, W, H, fill=1, stroke=0)

    def _page_bg(template):
        _fill_page(_bg.get(template, bg_cream))

    def _draw_image_cover(photo, x, y, w, h, anchor_y=0.5):
        """Draw a photo cropped to fill the box."""
        path = _photo_path(photo)
        if not path:
            return
        try:
            from PIL import Image as PILImage
            with PILImage.open(path) as img:
                iw, ih = img.size
            scale = max(w / iw, h / ih)
            draw_w = iw * scale
            draw_h = ih * scale
            offset_x = x + (w - draw_w) / 2
            offset_y = y + (h - draw_h) * anchor_y
            c.saveState()
            p = c.beginPath()
            p.rect(x, y, w, h)
            c.clipPath(p, stroke=0, fill=0)
            c.drawImage(str(path), offset_x, offset_y, draw_w, draw_h, preserveAspectRatio=False)
            c.restoreState()
        except Exception:
            try:
                c.drawImage(str(path), x, y, w, h, preserveAspectRatio=True)
            except Exception:
                pass

    def _draw_image_fill(photo, x, y, w, h):
        """Backwards-compatible alias used by older renderers."""
        _draw_image_cover(photo, x, y, w, h)

    def _draw_framed_photo(photo, x, y, w, h, border=2 * mm, shadow=True):
        """Draw a photo with white border and subtle drop shadow."""
        fx = x - border
        fy = y - border
        fw = w + 2 * border
        fh = h + 2 * border
        if shadow:
            so = 2 * mm
            c.setFillColor(Color(0, 0, 0, alpha=0.08))
            c.rect(fx + so, fy - so, fw, fh, fill=1, stroke=0)
        c.setFillColor(Color(1, 1, 1))
        c.rect(fx, fy, fw, fh, fill=1, stroke=0)
        c.setStrokeColor(Color(0, 0, 0, alpha=0.04))
        c.setLineWidth(0.3)
        c.rect(fx, fy, fw, fh, fill=0, stroke=1)
        _draw_image_cover(photo, x, y, w, h)

    def _draw_rotated_framed_photo(photo, x, y, w, h, border=2 * mm, angle=0):
        """Draw a framed photo with rotation around its center."""
        cx = x + w / 2
        cy = y + h / 2
        c.saveState()
        c.translate(cx, cy)
        c.rotate(angle)
        c.translate(-cx, -cy)
        _draw_framed_photo(photo, x, y, w, h, border=border, shadow=True)
        c.restoreState()

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

    def _draw_divider(y, color=None):
        """Draw a thin decorative centered horizontal rule."""
        c.setStrokeColor(color or Color(0, 0, 0, alpha=0.10))
        c.setLineWidth(0.3)
        c.line(W * 0.25, y, W * 0.75, y)

    def _draw_corner_ornament(x, y, size=15 * mm, rotation=0):
        """Draw a decorative corner flourish in rose gold."""
        c.saveState()
        c.translate(x, y)
        c.rotate(rotation)
        c.setStrokeColor(Color(rose_gold.red, rose_gold.green, rose_gold.blue, alpha=0.6))
        c.setLineWidth(0.6)
        p = c.beginPath()
        p.moveTo(0, size * 0.5)
        p.curveTo(0, size * 0.1, size * 0.1, 0, size * 0.5, 0)
        c.drawPath(p, stroke=1, fill=0)
        p2 = c.beginPath()
        p2.moveTo(size * 0.08, size * 0.5)
        p2.curveTo(size * 0.08, size * 0.18, size * 0.18, size * 0.08, size * 0.5, size * 0.08)
        c.drawPath(p2, stroke=1, fill=0)
        c.setFillColor(Color(rose_gold.red, rose_gold.green, rose_gold.blue, alpha=0.6))
        c.circle(size * 0.04, size * 0.5, 1, fill=1, stroke=0)
        c.circle(size * 0.5, size * 0.04, 1, fill=1, stroke=0)
        c.restoreState()

    def _page_number(num):
        if num:
            c.setFont("Helvetica", 6)
            c.setFillColor(Color(1, 1, 1, alpha=0.62))
            c.drawCentredString(W / 2, 9 * mm, f"PAGE {num}")

    def _bottom_fade(height=42 * mm, darkness=0.82):
        steps = 28
        for i in range(steps):
            frac = i / steps
            alpha = darkness * (1 - frac)
            c.setFillColor(Color(0, 0, 0, alpha=alpha))
            c.rect(0, frac * height, W, height / steps + 1, fill=1, stroke=0)

    def _soft_panel(x, y, w, h, alpha=0.18):
        c.setFillColor(Color(1, 1, 1, alpha=alpha))
        c.rect(x, y, w, h, fill=1, stroke=0)

    # ── Template renderers ──

    def _cover(page):
        _fill_page(bg_dark)
        if page.photos:
            _draw_image_cover(page.photos[0], 0, 0, W, H)
        _bottom_fade(height=H * 0.42, darkness=0.92)
        c.setFillColor(Color(1, 1, 1, alpha=0.42))
        c.setFont("Helvetica", 8)
        c.drawString(18 * mm, H - 16 * mm, "ESTABLISHED 2024")
        y = H * 0.23
        if page.title:
            _draw_text_block(page.title, 18 * mm, y, "Times-BoldItalic", 44, white, W * 0.55, "left")
        if page.subtitle:
            c.setFont("Helvetica", 10)
            c.setFillColor(Color(1, 1, 1, alpha=0.6))
            sub = page.subtitle.upper()
            c.drawString(18 * mm, y - 38, sub)

    def _back_cover(page):
        _fill_page(bg_dark)
        if page.photos:
            _draw_image_cover(page.photos[0], 0, 0, W, H)
        c.setFillColor(Color(0, 0, 0, alpha=0.74))
        c.rect(0, 0, W, 52 * mm, fill=1, stroke=0)
        if page.title:
            c.setFont("Helvetica", 8)
            c.setFillColor(Color(1, 1, 1, alpha=0.7))
            title_text = page.title.upper()
            c.drawString(18 * mm, 22 * mm, title_text)
            c.setFont("Times-BoldItalic", 22)
            c.setFillColor(white)
            c.drawString(18 * mm, 32 * mm, "Forever, in print.")

    def _dedication(page):
        _fill_page(bg_dark)
        c.setFillColor(Color(1, 1, 1, alpha=0.04))
        c.rect(16 * mm, 16 * mm, W - 32 * mm, H - 32 * mm, fill=1, stroke=0)
        if page.dedication:
            c.setFont("Helvetica", 8)
            c.setFillColor(Color(1, 1, 1, alpha=0.46))
            c.drawCentredString(W / 2, H * 0.66, "DEDICATION")
            y = _draw_text_block(page.dedication, 30 * mm, H * 0.56, "Times-Italic", 19, white, W - 60 * mm, "center")
            c.setStrokeColor(Color(1, 1, 1, alpha=0.14))
            c.line(W * 0.38, y - 8 * mm, W * 0.62, y - 8 * mm)
        _page_number(page.page_number)

    def _full_bleed(page):
        _fill_page(bg_dark)
        if page.photos:
            _draw_image_cover(page.photos[0], 0, 0, W, H)
        if page.template in ("cinematic", "photo_quote_overlay", "full_bleed"):
            _bottom_fade(height=52 * mm, darkness=0.9)
        if page.template in ("cinematic", "photo_quote_overlay"):
            c.setFillColor(Color(0, 0, 0, alpha=0.65))
            c.rect(0, H - 14 * mm, W, 14 * mm, fill=1, stroke=0)
            c.rect(0, 0, W, 14 * mm, fill=1, stroke=0)
        if page.section_title:
            c.setFillColor(Color(1, 1, 1, alpha=0.8))
            c.setFont("Helvetica", 8)
            c.drawString(18 * mm, 16 * mm, page.section_title.upper())
        if page.quote and page.template == "photo_quote_overlay":
            _soft_panel(18 * mm, 22 * mm, W * 0.42, 42 * mm, alpha=0.12)
            c.setFont("Times-BoldItalic", 20)
            c.setFillColor(white)
            quote_text = f'"{page.quote.get("text", "")}"'
            y = _draw_text_block(quote_text, 24 * mm, 52 * mm, "Times-BoldItalic", 20, white, W * 0.35, "left")
            c.setFont("Helvetica", 8)
            c.setFillColor(Color(1, 1, 1, alpha=0.74))
            c.drawString(24 * mm, y - 3 * mm, f"— {page.quote.get('author', '')}")
        _page_number(page.page_number)

    def _big_polaroid(page):
        _fill_page(bg_dark)
        if page.photos:
            _draw_image_cover(page.photos[0], 0, 0, W, H)
        c.setFillColor(Color(0, 0, 0, alpha=0.72))
        c.rect(0, 0, W * 0.42, H, fill=1, stroke=0)
        c.setFillColor(Color(1, 1, 1, alpha=0.4))
        c.setFont("Helvetica", 8)
        c.drawString(18 * mm, H - 26 * mm, "FEATURE")
        if page.quote:
            y = _draw_text_block(f'"{page.quote.get("text", "")}"', 18 * mm, H - 42 * mm, "Times-BoldItalic", 24, white, W * 0.28, "left")
            c.setFont("Helvetica", 8)
            c.setFillColor(Color(1, 1, 1, alpha=0.72))
            c.drawString(18 * mm, y - 5 * mm, f"— {page.quote.get('author', '')}")
        _page_number(page.page_number)

    def _two_photos(page):
        _fill_page(bg_dark)
        gap = 4 * mm
        iw = (W - gap) / 2
        ih = H
        for i, photo in enumerate(page.photos[:2]):
            x = i * (iw + gap)
            _draw_image_cover(photo, x, 0, iw, ih)
        c.setFillColor(Color(0, 0, 0, alpha=0.42))
        c.rect(iw - 8 * mm, 0, 16 * mm, H, fill=1, stroke=0)
        _page_number(page.page_number)

    def _three_photos(page):
        _fill_page(bg_dark)
        gap = 4 * mm
        top_h = H * 0.58
        bot_h = H - top_h - gap
        if len(page.photos) >= 1:
            _draw_image_cover(page.photos[0], 0, H - top_h, W, top_h)
        bot_w = (W - gap) / 2
        for i, photo in enumerate(page.photos[1:3]):
            x = i * (bot_w + gap)
            _draw_image_cover(photo, x, 0, bot_w, bot_h)
        _page_number(page.page_number)

    def _four_photos(page):
        _fill_page(bg_dark)
        gap = 4 * mm
        iw = (W - gap) / 2
        ih = (H - gap) / 2
        positions = [
            (0, ih + gap),
            (iw + gap, ih + gap),
            (0, 0),
            (iw + gap, 0),
        ]
        for i, photo in enumerate(page.photos[:4]):
            x, y = positions[i]
            _draw_image_cover(photo, x, y, iw, ih)
        _page_number(page.page_number)

    def _editorial(page):
        _fill_page(bg_dark)
        img_w = W * 0.62
        if page.photos:
            _draw_image_cover(page.photos[0], 0, 0, img_w, H)
        c.setFillColor(Color(0, 0, 0, alpha=0.75))
        c.rect(img_w, 0, W - img_w, H, fill=1, stroke=0)
        text_x = img_w + 14 * mm
        if page.section_title:
            c.setFont("Helvetica", 8)
            c.setFillColor(Color(1, 1, 1, alpha=0.45))
            c.drawString(text_x, H - 28 * mm, page.section_title.upper())
            c.setFont("Times-BoldItalic", 28)
            c.setFillColor(white)
            _draw_text_block(page.section_title, text_x, H - 42 * mm, "Times-BoldItalic", 28, white, W - text_x - 18 * mm, "left")
        _page_number(page.page_number)

    def _simple(page):
        """Fallback for unknown templates: place photos in a grid."""
        _page_bg(page.template)
        n = len(page.photos)
        if n == 0:
            _page_number(page.page_number)
            return
        cols = 2 if n > 1 else 1
        rows = (n + cols - 1) // cols
        gap = 4 * mm
        iw = (W - 2 * MARGIN - (cols - 1) * gap) / cols
        ih = (H - 2 * MARGIN - (rows - 1) * gap) / rows
        for i, photo in enumerate(page.photos):
            col = i % cols
            row = i // cols
            x = MARGIN + col * (iw + gap)
            y = H - MARGIN - (row + 1) * ih - row * gap
            _draw_image_fill(photo, x, y, iw, ih)
        _page_number(page.page_number)

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
