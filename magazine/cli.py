"""CLI entry point for Magazine."""

from __future__ import annotations

import click


@click.group()
def cli():
    """Magazine - Create beautiful print-ready magazines."""
    pass


@cli.command("import")
@click.option("--source", type=click.Choice(["local", "google"]), required=True, help="Photo source")
@click.option("--path", type=click.Path(exists=True), help="Path to local photo folder (required for local source)")
def import_photos(source, path):
    """Import photos from a local folder or Google Photos."""
    if source == "local":
        if not path:
            raise click.UsageError("--path is required for local source")
        from magazine.sources.local import import_local_photos

        import_local_photos(path)
    elif source == "google":
        from magazine.sources.google_picker import import_google_photos

        import_google_photos()


@cli.command("detect")
def detect_faces():
    """Detect faces in imported photos and filter candidates."""
    from magazine.processing.faces import run_face_detection

    run_face_detection()


@cli.command("web")
@click.option("--port", default=5000, help="Port for the web app")
def web_app(port):
    """Launch the unified web workflow (import, review, story, generate)."""
    from magazine.review.app import create_app

    app = create_app()
    click.echo(f"Opening web app at http://localhost:{port}")
    click.launch(f"http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)


@cli.command("review")
@click.option("--port", default=5000, help="Port for the review web UI")
def review_photos(port):
    """Backward-compatible alias for launching the web app."""
    from magazine.review.app import create_app

    app = create_app()
    click.echo(f"Opening review UI at http://localhost:{port}")
    click.launch(f"http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)


@cli.command("generate")
@click.option("--title", default="Our Love Story", help="Magazine title")
@click.option("--subtitle", default="A Journey Together", help="Magazine subtitle")
@click.option("--dedication", default="For you, with all my love", help="Dedication message")
@click.option("--style", default="editorial_luxury", help="Layout style (e.g. editorial_luxury)")
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
    """Generate the magazine PDF from approved photos."""
    from magazine.layout.engine import build_layout
    from magazine.pdf.generator import generate_pdf

    click.echo("Building magazine layout...")
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
    click.echo(f"Layout: {len(pages_spec)} pages")

    click.echo("Generating PDF...")
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


@cli.command("create")
@click.option("--source", type=click.Choice(["local", "google"]), required=True, help="Photo source")
@click.option("--path", type=click.Path(exists=True), help="Path to local photo folder")
@click.option("--title", default="Our Love Story", help="Magazine title")
@click.option("--subtitle", default="A Journey Together", help="Magazine subtitle")
@click.option("--dedication", default="For you, with all my love", help="Dedication message")
@click.option("--style", default="editorial_luxury", help="Layout style")
@click.option("--pages", default="auto", help="Page count: auto or integer")
@click.option("--min-pages", default=28, type=int)
@click.option("--max-pages", default=72, type=int)
@click.option("--density", default=1.7, type=float)
@click.option("--page-step", default=4, type=int)
@click.option("--skip-review", is_flag=True, help="Skip manual review (use all imported photos)")
def create_magazine(
    source,
    path,
    title,
    subtitle,
    dedication,
    style,
    pages,
    min_pages,
    max_pages,
    density,
    page_step,
    skip_review,
):
    """Full pipeline: import -> detect -> review -> generate."""
    click.echo("Step 1: Importing photos...")
    if source == "local":
        if not path:
            raise click.UsageError("--path is required for local source")
        from magazine.sources.local import import_local_photos

        import_local_photos(path)
    else:
        from magazine.sources.google_picker import import_google_photos

        import_google_photos()

    click.echo("\nStep 2: Detecting faces...")
    from magazine.processing.faces import run_face_detection

    run_face_detection()

    if not skip_review:
        click.echo("\nStep 3: Review photos in browser...")
        from magazine.review.app import create_app

        app = create_app()
        click.launch("http://localhost:5000")
        app.run(host="0.0.0.0", port=5000, debug=False)
        click.echo("Review complete.")
    else:
        click.echo("\nStep 3: Skipping review (marking all photos approved)...")
        from magazine.services.state import load_photos_manifest, load_review_state, save_review_state

        review_state = load_review_state()
        for photo in load_photos_manifest():
            entry = review_state.get(photo["id"], {"status": "pending", "hero_pin": False, "caption": ""})
            entry["status"] = "approved"
            review_state[photo["id"]] = entry
        save_review_state(review_state)

    click.echo("\nStep 4: Generating magazine...")
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
    output_path = generate_pdf(pages_spec, style=style)
    click.echo(f"\nMagazine saved to: {output_path}")


if __name__ == "__main__":
    cli()
