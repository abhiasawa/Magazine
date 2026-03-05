"""CLI entry point for the photo magazine generator."""

import click


@click.group()
def cli():
    """Photo Magazine Generator - Create beautiful print-ready photo magazines."""
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


@cli.command("review")
@click.option("--port", default=5000, help="Port for the review web UI")
def review_photos(port):
    """Open web UI to review and approve/reject photo candidates."""
    from magazine.review.app import create_app
    app = create_app()
    click.echo(f"Opening review UI at http://localhost:{port}")
    click.launch(f"http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)


@cli.command("generate")
@click.option("--title", default="Our Love Story", help="Magazine title")
@click.option("--subtitle", default="A Journey Together", help="Magazine subtitle")
@click.option("--dedication", default="For you, with all my love", help="Dedication message")
@click.option("--output", default=None, help="Output PDF path")
def generate_magazine(title, subtitle, dedication, output):
    """Generate the magazine PDF from approved photos."""
    from magazine.layout.engine import build_layout
    from magazine.pdf.generator import generate_pdf

    click.echo("Building magazine layout...")
    pages = build_layout(title=title, subtitle=subtitle, dedication=dedication)
    click.echo(f"Layout: {len(pages)} pages")

    click.echo("Generating PDF...")
    output_path = generate_pdf(pages, output_path=output)
    click.echo(f"Magazine saved to: {output_path}")


@cli.command("create")
@click.option("--source", type=click.Choice(["local", "google"]), required=True, help="Photo source")
@click.option("--path", type=click.Path(exists=True), help="Path to local photo folder")
@click.option("--title", default="Our Love Story", help="Magazine title")
@click.option("--subtitle", default="A Journey Together", help="Magazine subtitle")
@click.option("--dedication", default="For you, with all my love", help="Dedication message")
@click.option("--skip-review", is_flag=True, help="Skip manual review (use all 2-face candidates)")
def create_magazine(source, path, title, subtitle, dedication, skip_review):
    """Full pipeline: import → detect → review → generate."""
    # Step 1: Import
    click.echo("Step 1: Importing photos...")
    if source == "local":
        if not path:
            raise click.UsageError("--path is required for local source")
        from magazine.sources.local import import_local_photos
        import_local_photos(path)
    else:
        from magazine.sources.google_picker import import_google_photos
        import_google_photos()

    # Step 2: Detect faces
    click.echo("\nStep 2: Detecting faces...")
    from magazine.processing.faces import run_face_detection
    run_face_detection()

    # Step 3: Review
    if not skip_review:
        click.echo("\nStep 3: Review photos in browser...")
        from magazine.review.app import create_app
        app = create_app()
        click.launch("http://localhost:5000")
        app.run(host="0.0.0.0", port=5000, debug=False)
        click.echo("Review complete.")
    else:
        click.echo("\nStep 3: Skipping review (using all 2-face candidates)...")
        from magazine.review.app import auto_approve_candidates
        auto_approve_candidates()

    # Step 4: Generate
    click.echo("\nStep 4: Generating magazine...")
    from magazine.layout.engine import build_layout
    from magazine.pdf.generator import generate_pdf

    pages = build_layout(title=title, subtitle=subtitle, dedication=dedication)
    output_path = generate_pdf(pages)
    click.echo(f"\nMagazine saved to: {output_path}")


if __name__ == "__main__":
    cli()
