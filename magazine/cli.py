"""CLI entry point for Magazine."""

from __future__ import annotations

import click


@click.group()
def cli():
    """Magazine - Google Photos to print-ready magazine PDFs."""


@cli.command("web")
@click.option("--port", default=5000, help="Port for the web app")
def web_app(port):
    """Launch the Google Photos web workflow."""
    from magazine.review.app import create_app

    app = create_app()
    click.echo(f"Opening Magazine at http://localhost:{port}")
    click.launch(f"http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)


@cli.command("generate")
@click.option("--title", default="Magazine", help="Magazine title")
@click.option("--subtitle", default="", help="Magazine subtitle")
@click.option("--dedication", default="", help="Opening line")
@click.option("--style", default="editorial_luxury", help="Layout style")
@click.option("--pages", default="auto", help="Page count: auto or explicit integer")
@click.option("--min-pages", default=28, type=int, help="Minimum page count for auto mode")
@click.option("--max-pages", default=72, type=int, help="Maximum page count for auto mode")
@click.option("--density", default=1.7, type=float, help="Average photos per page target")
@click.option("--page-step", default=4, type=int, help="Round page count to this step")
@click.option("--output", default=None, help="Output PDF path")
def generate_magazine(
    title,
    subtitle,
    dedication,
    style,
    pages,
    min_pages,
    max_pages,
    density,
    page_step,
    output,
):
    """Generate the magazine PDF from the current imported selection."""
    from magazine.layout.engine import build_layout
    from magazine.pdf.generator import generate_pdf

    pages_spec = build_layout(
        title=title,
        subtitle=subtitle,
        dedication=dedication,
        style=style,
        pages=pages,
        min_pages=min_pages,
        max_pages=max_pages,
        density=density,
        page_step=page_step,
    )
    output_path = generate_pdf(pages_spec, output_path=output, style=style)
    click.echo(f"Magazine saved to: {output_path}")


@cli.command("preflight")
@click.option("--pdf", "pdf_path", default="workspace/output/magazine.pdf", help="PDF path to validate")
@click.option("--expected-pages", type=int, default=None, help="Optional expected page count")
def preflight_pdf(pdf_path, expected_pages):
    """Run preflight checks and render proof images."""
    from magazine.pdf.preflight import run_preflight

    report = run_preflight(pdf_path, expected_pages=expected_pages)
    click.echo(f"Preflight status: {report['status']}")
    for item in report["checks"]:
        click.echo(f"[{item['status']}] {item['name']}: {item['details']}")


if __name__ == "__main__":
    cli()
