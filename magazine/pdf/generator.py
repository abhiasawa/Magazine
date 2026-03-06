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
    from reportlab.lib.colors import Color

    W = 210 * mm
    H = 297 * mm
    MARGIN = 15 * mm

    bg_dark = Color(0.047, 0.043, 0.039)       # #0c0b0a
    bg_cream = Color(0.957, 0.933, 0.902)       # #f4eee6
    ink = Color(0.094, 0.075, 0.063)            # #181310
    muted = Color(0.494, 0.42, 0.376)           # #7e6b60
    white = Color(1, 0.98, 0.957)               # #fffaf4

    c = canvas.Canvas(str(output_path), pagesize=(W, H))

    def _fill_page(color):
        c.setFillColor(color)
        c.rect(0, 0, W, H, fill=1, stroke=0)

    def _draw_image_fill(photo, x, y, w, h):
        """Draw full photo scaled to fit inside the box (contain-fit, no cropping)."""
        path = _photo_path(photo)
        if not path:
            return
        try:
            from PIL import Image as PILImage
            with PILImage.open(path) as img:
                iw, ih = img.size
            scale = min(w / iw, h / ih)
            draw_w = iw * scale
            draw_h = ih * scale
            offset_x = x + (w - draw_w) / 2
            offset_y = y + (h - draw_h) / 2
            c.drawImage(str(path), offset_x, offset_y, draw_w, draw_h,
                        preserveAspectRatio=False)
        except Exception:
            try:
                c.drawImage(str(path), x, y, w, h, preserveAspectRatio=True)
            except Exception:
                pass

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

    def _page_number(num):
        if num:
            c.setFont("Times-Roman", 8)
            c.setFillColor(muted)
            c.drawCentredString(W / 2, 10 * mm, str(num))

    # ── Template renderers ──

    def _cover(page):
        _fill_page(bg_dark)
        if page.photos:
            _draw_image_fill(page.photos[0], 0, 0, W, H)
            c.setFillColor(Color(0, 0, 0, alpha=0.4))
            c.rect(0, 0, W, H * 0.45, fill=1, stroke=0)
        y = H * 0.3
        if page.title:
            _draw_text_block(page.title, MARGIN, y, "Times-Bold", 48, white,
                             W - 2 * MARGIN, "left")
        if page.subtitle:
            c.setFont("Times-Roman", 16)
            c.setFillColor(Color(1, 1, 1, alpha=0.7))
            c.drawString(MARGIN, y - 60, page.subtitle)

    def _back_cover(page):
        _fill_page(bg_dark)
        if page.photos:
            _draw_image_fill(page.photos[0], MARGIN, H * 0.35, W - 2 * MARGIN, H * 0.55)
        if page.title:
            c.setFont("Times-Bold", 28)
            c.setFillColor(white)
            c.drawCentredString(W / 2, H * 0.2, page.title)
        if page.subtitle:
            c.setFont("Times-Roman", 12)
            c.setFillColor(Color(1, 1, 1, alpha=0.6))
            c.drawCentredString(W / 2, H * 0.15, page.subtitle)

    def _dedication(page):
        _fill_page(bg_cream)
        if page.dedication:
            _draw_text_block(page.dedication, MARGIN * 2, H * 0.55, "Times-Italic", 18,
                             muted, W - 4 * MARGIN, "center")
        _page_number(page.page_number)

    def _full_bleed(page):
        _fill_page(bg_dark)
        if page.photos:
            _draw_image_fill(page.photos[0], 0, 0, W, H)
        if page.section_title:
            c.setFillColor(Color(0, 0, 0, alpha=0.5))
            c.rect(0, 0, W, 30 * mm, fill=1, stroke=0)
            c.setFont("Times-Roman", 10)
            c.setFillColor(white)
            c.drawString(MARGIN, 12 * mm, page.section_title.upper())
        _page_number(page.page_number)

    def _quote(page):
        _fill_page(bg_cream)
        y = H * 0.6
        if page.quote:
            text = page.quote.get("text", "")
            author = page.quote.get("author", "")
            if text:
                y = _draw_text_block(f"\u201c{text}\u201d", MARGIN * 2, y,
                                     "Times-Italic", 22, ink, W - 4 * MARGIN, "center")
            if author:
                c.setFont("Times-Roman", 11)
                c.setFillColor(muted)
                c.drawCentredString(W / 2, y - 20, f"\u2014 {author}")
        _page_number(page.page_number)

    def _big_polaroid(page):
        _fill_page(bg_cream)
        pad = 20 * mm
        img_w = W - 2 * pad
        img_h = H * 0.65
        img_y = H - pad - img_h
        c.setFillColor(Color(1, 1, 1))
        c.roundRect(pad - 4 * mm, img_y - 18 * mm, img_w + 8 * mm,
                    img_h + 22 * mm, 3 * mm, fill=1, stroke=0)
        c.setStrokeColor(Color(0, 0, 0, alpha=0.08))
        c.roundRect(pad - 4 * mm, img_y - 18 * mm, img_w + 8 * mm,
                    img_h + 22 * mm, 3 * mm, fill=0, stroke=1)
        if page.photos:
            _draw_image_fill(page.photos[0], pad, img_y, img_w, img_h)
        if page.quote:
            text = page.quote.get("text", "")
            if text:
                _draw_text_block(text, pad, img_y - 28 * mm, "Times-Italic", 13,
                                 muted, img_w, "center")
        _page_number(page.page_number)

    def _two_photos(page):
        _fill_page(bg_cream)
        gap = 4 * mm
        iw = (W - 2 * MARGIN - gap) / 2
        ih = H - 2 * MARGIN
        for i, photo in enumerate(page.photos[:2]):
            x = MARGIN + i * (iw + gap)
            _draw_image_fill(photo, x, MARGIN, iw, ih)
        _page_number(page.page_number)

    def _three_photos(page):
        _fill_page(bg_cream)
        gap = 4 * mm
        top_h = (H - 2 * MARGIN - gap) * 0.6
        bot_h = (H - 2 * MARGIN - gap) * 0.4
        if len(page.photos) >= 1:
            _draw_image_fill(page.photos[0], MARGIN, MARGIN + bot_h + gap,
                             W - 2 * MARGIN, top_h)
        bot_w = (W - 2 * MARGIN - gap) / 2
        for i, photo in enumerate(page.photos[1:3]):
            x = MARGIN + i * (bot_w + gap)
            _draw_image_fill(photo, x, MARGIN, bot_w, bot_h)
        _page_number(page.page_number)

    def _four_photos(page):
        _fill_page(bg_cream)
        gap = 4 * mm
        iw = (W - 2 * MARGIN - gap) / 2
        ih = (H - 2 * MARGIN - gap) / 2
        positions = [
            (MARGIN, MARGIN + ih + gap),
            (MARGIN + iw + gap, MARGIN + ih + gap),
            (MARGIN, MARGIN),
            (MARGIN + iw + gap, MARGIN),
        ]
        for i, photo in enumerate(page.photos[:4]):
            x, y = positions[i]
            _draw_image_fill(photo, x, y, iw, ih)
        _page_number(page.page_number)

    def _editorial(page):
        _fill_page(bg_cream)
        img_w = W * 0.48
        if page.photos:
            _draw_image_fill(page.photos[0], MARGIN, MARGIN, img_w, H - 2 * MARGIN)
        text_x = MARGIN + img_w + 8 * mm
        text_w = W - text_x - MARGIN
        if page.section_title:
            c.setFont("Times-Roman", 9)
            c.setFillColor(muted)
            c.drawString(text_x, H - MARGIN - 10, page.section_title.upper())
        if page.quote:
            text = page.quote.get("text", "")
            if text:
                _draw_text_block(text, text_x, H - MARGIN - 30, "Times-Italic", 14,
                                 ink, text_w)
        _page_number(page.page_number)

    def _simple(page):
        """Fallback for unknown templates: place photos in a grid."""
        _fill_page(bg_cream)
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
        "quote_page": _quote,
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
