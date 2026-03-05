"""PDF generation using WeasyPrint with Jinja2 templates."""

from pathlib import Path

import click
from jinja2 import Environment, FileSystemLoader
from tqdm import tqdm

from magazine.config import (
    OUTPUT_DIR,
    PRINT_DIR,
    ORIGINALS_DIR,
)
from magazine.layout.engine import PageSpec
from magazine.processing.images import make_print_image


# Paths
PDF_DIR = Path(__file__).parent
TEMPLATES_DIR = PDF_DIR / "templates"
STATIC_DIR = PDF_DIR / "static"
ASSETS_DIR = PDF_DIR / "assets"
CSS_PATH = STATIC_DIR / "magazine.css"
ORNAMENT_DIVIDER = ASSETS_DIR / "ornaments" / "divider.svg"


def prepare_print_images(pages: list[PageSpec]) -> list[PageSpec]:
    """Generate print-quality images for all photos in the layout."""
    # Collect all unique photos
    all_photos = {}
    for page in pages:
        for photo in page.photos:
            pid = photo["id"]
            if pid not in all_photos:
                all_photos[pid] = photo

    click.echo(f"Preparing {len(all_photos)} print-quality images...")

    for pid, photo in tqdm(all_photos.items(), desc="Print images"):
        original = Path(photo["original"])
        if not original.exists():
            # Try in originals dir
            original = ORIGINALS_DIR / f"{pid}.jpg"

        if original.exists():
            print_path = make_print_image(original, PRINT_DIR)
            photo["print_path"] = print_path.as_uri()
        else:
            click.echo(f"Warning: Original not found for {pid}")
            photo["print_path"] = ""

    return pages


def render_html(pages: list[PageSpec]) -> str:
    """Render the magazine HTML from Jinja2 templates."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=False,
    )
    template = env.get_template("magazine.html")

    # Convert PageSpec objects for template context
    page_dicts = []
    for page in pages:
        d = {
            "template": page.template,
            "photos": page.photos,
            "quote": page.quote,
            "title": page.title,
            "subtitle": page.subtitle,
            "dedication": page.dedication,
            "section_title": page.section_title,
            "page_number": page.page_number,
        }
        page_dicts.append(d)

    html = template.render(
        pages=page_dicts,
        css_path=CSS_PATH.as_uri(),
        ornament_divider=ORNAMENT_DIVIDER.as_uri(),
    )
    return html


def generate_pdf(pages: list[PageSpec], output_path: str | None = None) -> Path:
    """Generate the final magazine PDF.

    1. Prepare print-quality images
    2. Render HTML from templates
    3. Convert to PDF with WeasyPrint
    """
    try:
        from weasyprint import HTML
    except ImportError:
        raise click.ClickException(
            "WeasyPrint is required: pip install weasyprint\n"
            "On Linux you may also need: sudo apt install libpango1.0-dev libcairo2-dev"
        )

    # Prepare print images
    pages = prepare_print_images(pages)

    # Render HTML
    click.echo("Rendering magazine layout...")
    html_content = render_html(pages)

    # Save HTML for debugging
    html_path = OUTPUT_DIR / "magazine.html"
    with open(html_path, "w") as f:
        f.write(html_content)

    # Generate PDF
    if output_path is None:
        output_path = OUTPUT_DIR / "magazine.pdf"
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    click.echo("Generating PDF (this may take a few minutes)...")
    html_doc = HTML(string=html_content, base_url=str(TEMPLATES_DIR))
    html_doc.write_pdf(
        str(output_path),
        presentational_hints=True,
    )

    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    click.echo(f"PDF generated: {output_path} ({file_size_mb:.1f} MB)")
    click.echo(f"Pages: {len(pages)}")

    return output_path
