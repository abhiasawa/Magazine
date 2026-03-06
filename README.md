# Maison Folio

Maison Folio turns a Google Photos selection into a polished editorial PDF that feels collectible, not homemade.

It is designed for one outcome: choose your photos, preview the piece in the browser, and export a luxury print-ready volume.

## What It Does

- Connects directly to Google Photos
- Imports the selected images into a single streamlined flow
- Builds a premium editorial layout automatically
- Opens the finished PDF in an in-app preview before download
- Exports a print-ready file with A4 dimensions, bleed, and high-resolution image processing

## Product Experience

Maison Folio is intentionally opinionated.

There is no local upload flow, no manual page-by-page design tool, and no cluttered review workflow. The product is built to remove decisions, preserve taste, and generate something that already feels designed.

## Live App

[https://photo-magazine.vercel.app](https://photo-magazine.vercel.app)

## Why It Feels Different

- Typography-led cover design
- Editorial pacing instead of simple photo dumping
- Image layouts that avoid harsh crops
- Browser preview before download
- Print-first output rather than slideshow-style exports

## Google Photos Setup

Configure a Google Cloud OAuth client for the deployed app:

1. Enable the **Google Photos Picker API**
2. Create an OAuth **Web application**
3. Add JavaScript origin: `https://photo-magazine.vercel.app`
4. Add redirect URI: `https://photo-magazine.vercel.app/oauth/callback`
5. Add these environment variables:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REDIRECT_URI=https://photo-magazine.vercel.app/oauth/callback`

## Local Development

```bash
pip install -e .
magazine web
```

## Output Spec

- A4 PDF
- 3mm bleed
- 300 DPI print pipeline
- Automatic pagination
- Editorial cover and image-led interior spreads

## Deployment Notes

- The app ships with `api/index.py` and `vercel.json` for Vercel deployment
- Vercel storage is ephemeral, so generated files are request-scoped unless durable storage is added
- PDF generation depends on the runtime having the required Python libraries available
