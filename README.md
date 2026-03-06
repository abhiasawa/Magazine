# Photo Magazine Generator

Create beautiful photo magazines from your photos. Import from local or Google Photos, curate in a premium web UI, and generate dynamic-page editorial layouts ready for print export.

## Features

- **Unified Web Workflow**: `Import -> Review -> Story -> Generate -> Preflight`
- **Dual Import Sources**: Upload from local machine or sync from Google Photos Picker API
- **Dynamic Pagination**: Auto page count based on approved photos (defaults: 28-72 pages, rounded to print signatures)
- **Hero Pinning**: Mark must-have photos for premium spread placement
- **Editorial Luxury Mode**: Soft luxury print layout with multiple spread templates
- **Manual Curation First**: Face detection is optional; you can simply approve the right photos yourself
- **Preflight Checks**: Generate `preflight_report.json` and optional proof PNG renders
- **Print-Ready PDF**: A4 size, 300 DPI, 3mm bleed output

## Quick Start

```bash
# Install the hosted/manual-review workflow
pip install -e .

# Optional: add local-only PDF and face-detection dependencies
pip install -r requirements-local.txt

# Launch the web app (recommended)
magazine web

# Optional CLI workflow
magazine import --source local --path ~/Photos/us
magazine detect
magazine generate --style editorial_luxury --pages auto --min-pages 28 --max-pages 72
magazine preflight --pdf workspace/output/magazine.pdf
```

## One-Command Pipeline

```bash
magazine create --source local --path ~/Photos/us --style editorial_luxury --pages auto
```

## Google Photos Setup

1. Create a project at [Google Cloud Console](https://console.cloud.google.com)
2. Enable the **Google Photos Picker API**
3. Create **OAuth 2.0 credentials** (Web application type)
4. Set redirect URI to `http://localhost:5000/oauth/callback`
5. Copy `.env.example` to `.env` and fill in your credentials

```bash
magazine import --source google
```

Or use the web UI import screen, which supports both local upload and Google sync.

## Vercel Deployment

The repository includes a root `app.py` Flask entrypoint and `vercel.json`, so it can be deployed directly on Vercel.

Important constraints:
- Vercel uses ephemeral server storage, so imported photos and generated artifacts are not durable across deploys or cold starts.
- Google Photos requires production OAuth credentials and the deployed callback URL to be added in Google Cloud.
- PDF export and face detection are better treated as local features unless you add hosted rendering/storage services.

## Requirements

- Python 3.10+
- Optional system dependencies for WeasyPrint (see [WeasyPrint docs](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html)):
  - **Linux**: `sudo apt install libpango1.0-dev libcairo2-dev libgdk-pixbuf2.0-dev`
  - **macOS**: `brew install pango cairo libffi`

## Output

The generated magazine PDF is saved to `workspace/output/magazine.pdf`. It's print-ready with:
- A4 page size (210mm x 297mm)
- 3mm bleed on all sides
- 300 DPI photo resolution
- High-quality JPEG compression (95%)
