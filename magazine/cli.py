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
@click.option("--density", default=1.7, type=float, help="Average photos per page target")
@click.option("--output", default=None, help="Output PDF path")
def generate_magazine(
    title,
    subtitle,
    dedication,
    style,
    pages,
    density,
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
        density=density,
    )
    output_path = generate_pdf(pages_spec, output_path=output, style=style)
    click.echo(f"Magazine saved to: {output_path}")


if __name__ == "__main__":
    cli()
