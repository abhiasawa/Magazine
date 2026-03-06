"""PDF generation using WeasyPrint with Jinja2 templates."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import click
from jinja2 import Environment, FileSystemLoader
from tqdm import tqdm

from magazine.config import (
    OUTPUT_DIR,
    PRINT_DIR,
    ORIGINALS_DIR,
    DEFAULT_STYLE,
)
from magazine.layout.engine import PageSpec
from magazine.processing.images import make_print_image


# Paths
PDF_DIR = Path(__file__).parent
TEMPLATES_DIR = PDF_DIR / "templates"
STATIC_DIR = PDF_DIR / "static"
ASSETS_DIR = PDF_DIR / "assets"
DEFAULT_CSS_PATH = STATIC_DIR / "magazine.css"
EDITORIAL_CSS_PATH = STATIC_DIR / "editorial_luxury.css"
ORNAMENT_DIVIDER = ASSETS_DIR / "ornaments" / "divider.svg"


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


def _css_path_for_style(style: str) -> Path:
    if style == "editorial_luxury" and EDITORIAL_CSS_PATH.exists():
        return EDITORIAL_CSS_PATH
    return DEFAULT_CSS_PATH


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


def render_html(pages: list[PageSpec], style: str = DEFAULT_STYLE) -> str:
    """Render the magazine HTML from Jinja2 templates."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=False,
    )
    template = env.get_template("magazine.html")

    page_dicts = []
    for page in pages:
        page_dicts.append(
            {
                "template": page.template,
                "photos": page.photos,
                "quote": page.quote,
                "title": page.title,
                "subtitle": page.subtitle,
                "dedication": page.dedication,
                "section_title": page.section_title,
                "page_number": page.page_number,
            }
        )

    css_path = _css_path_for_style(style)
    html = template.render(
        pages=page_dicts,
        css_path=css_path.as_uri(),
        ornament_divider=ORNAMENT_DIVIDER.as_uri(),
    )
    return html


def _find_chrome_binary() -> str | None:
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _write_pdf_with_chrome(html_path: Path, output_path: Path):
    chrome = _find_chrome_binary()
    if not chrome:
        raise click.ClickException(
            "WeasyPrint is unavailable and no Chrome-compatible browser was found for PDF fallback."
        )

    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        "--allow-file-access-from-files",
        f"--print-to-pdf={output_path}",
        html_path.as_uri(),
    ]
    subprocess.run(cmd, check=True)


def generate_pdf(
    pages: list[PageSpec],
    output_path: str | None = None,
    style: str = DEFAULT_STYLE,
) -> Path:
    """Generate the final magazine PDF."""
    pages = prepare_print_images(pages)

    click.echo("Rendering magazine layout...")
    html_content = render_html(pages, style=style)

    html_path = OUTPUT_DIR / "magazine.html"
    with open(html_path, "w") as f:
        f.write(html_content)

    if output_path is None:
        output_path = OUTPUT_DIR / "magazine.pdf"
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    click.echo("Generating PDF (this may take a few minutes)...")
    try:
        from weasyprint import HTML

        html_doc = HTML(string=html_content, base_url=str(TEMPLATES_DIR))
        html_doc.write_pdf(
            str(output_path),
            presentational_hints=True,
        )
    except Exception as exc:
        click.echo(f"WeasyPrint unavailable, falling back to headless Chrome: {exc}")
        _write_pdf_with_chrome(html_path, output_path)

    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    click.echo(f"PDF generated: {output_path} ({file_size_mb:.1f} MB)")
    click.echo(f"Pages: {len(pages)}")

    return output_path
