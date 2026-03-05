# Photo Magazine Generator

Create beautiful, print-ready photo magazines from your photos. Perfect for gifting — automatically filters couple photos using face detection, lets you curate via a web UI, and generates a stunning warm & romantic PDF magazine with love quotes.

## Features

- **Photo Import**: Local folder or Google Photos Picker API
- **Smart Face Detection**: Automatically finds photos with exactly 2 people using DeepFace
- **Beautiful Review UI**: Web-based photo curation portal with approve/reject controls
- **Romantic Magazine Design**: Warm cream, blush & rose gold palette with elegant typography
- **8 Page Templates**: Cover, dedication, full-bleed, two-photo spread, three-photo grid, quote pages, photo+quote overlay, back cover
- **30+ Love Quotes**: Curated romantic quotes woven throughout the magazine
- **Print-Ready PDF**: A4 size, 300 DPI, 3mm bleed — ready for professional printing

## Quick Start

```bash
# Install
pip install -e .

# Import photos from a local folder
magazine import --source local --path ~/Photos/us

# Detect faces (filters to couple-only photos)
magazine detect

# Review candidates in your browser
magazine review

# Generate the magazine PDF
magazine generate --title "Our Love Story" --dedication "To my beautiful wife..."
```

## One-Command Pipeline

```bash
magazine create --source local --path ~/Photos/us --title "Our Love Story"
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

## Requirements

- Python 3.10+
- System dependencies for WeasyPrint (see [WeasyPrint docs](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html)):
  - **Linux**: `sudo apt install libpango1.0-dev libcairo2-dev libgdk-pixbuf2.0-dev`
  - **macOS**: `brew install pango cairo libffi`

## Output

The generated magazine PDF is saved to `workspace/output/magazine.pdf`. It's print-ready with:
- A4 page size (210mm x 297mm)
- 3mm bleed on all sides
- 300 DPI photo resolution
- High-quality JPEG compression (95%)
