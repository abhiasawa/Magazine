# Magazine

Create beautiful print magazines from your photos. Import from your browser or Google Photos, curate in a premium web UI, and generate dynamic-page editorial layouts ready for print export.

## Features

- **Unified Web Workflow**: `Import -> Review -> Story -> Generate -> Preflight`
- **Dual Import Sources**: Upload from local machine or sync from Google Photos Picker API
- **Dynamic Pagination**: Auto page count based on approved photos (defaults: 28-72 pages, rounded to print signatures)
- **Hero Pinning**: Mark must-have photos for premium spread placement
- **Editorial Luxury Mode**: Soft luxury print layout with multiple spread templates
- **Manual Curation First**: Face detection is optional; you can simply approve the right photos yourself
- **Preflight Checks**: Generate `preflight_report.json` and optional proof PNG renders
- **Print-Ready PDF**: A4 size, 300 DPI, 3mm bleed output

## Hosted Workflow

Use the public deployment:

[https://photo-magazine.vercel.app](https://photo-magazine.vercel.app)

The hosted flow is:
1. Import photos from your browser or Google Photos
2. Review and approve the keepers
3. Generate the magazine

## Google Photos Setup

1. Create a project at [Google Cloud Console](https://console.cloud.google.com)
2. Enable the **Google Photos Picker API**
3. Create **OAuth 2.0 credentials** (Web application type)
4. Add authorized JavaScript origin: `https://photo-magazine.vercel.app`
5. Add authorized redirect URI: `https://photo-magazine.vercel.app/oauth/callback`
6. Add the credentials in Vercel project environment variables:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REDIRECT_URI=https://photo-magazine.vercel.app/oauth/callback`

## Vercel Deployment

The repository includes a Vercel Flask entrypoint at `api/index.py` and `vercel.json`, so it can be deployed directly on Vercel.

Important constraints:
- Vercel uses ephemeral server storage, so imported photos and generated artifacts are not durable across deploys or cold starts.
- Google Photos requires production OAuth credentials and the deployed callback URL to be added in Google Cloud.
- PDF export is still limited by hosted rendering constraints unless you add a dedicated rendering/storage service.

## Requirements

- Python 3.10+
- Optional system dependencies for WeasyPrint (see [WeasyPrint docs](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html)):
  - **Linux**: `sudo apt install libpango1.0-dev libcairo2-dev libgdk-pixbuf2.0-dev`
  - **macOS**: `brew install pango cairo libffi`

## Output

The generated magazine PDF is designed for print with:
- A4 page size (210mm x 297mm)
- 3mm bleed on all sides
- 300 DPI photo resolution
- High-quality JPEG compression (95%)
