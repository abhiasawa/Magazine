# Magazine

Magazine is a Google Photos to PDF studio for building editorial-style print magazines with the fewest possible decisions.

## Product Flow

The web app now follows one path only:

1. Connect Google Photos
2. Select the photos in Google Photos
3. Add a cover title
4. Generate the PDF

There is no local upload flow, no manual review grid, and no hero-pin workflow in the product UI.

## Live App

[https://photo-magazine.vercel.app](https://photo-magazine.vercel.app)

## Core Behavior

- Google Photos is the only import source
- Page count is automatic
- Every selected photo is imported and approved for layout
- The PDF is generated directly from the Google selection
- Optional copy is limited to title, subtitle, and one opening line

## Google Photos Setup

Configure a Google Cloud OAuth client for the deployed app:

1. Enable the **Google Photos Picker API**
2. Create an OAuth **Web application**
3. Add JavaScript origin: `https://photo-magazine.vercel.app`
4. Add redirect URI: `https://photo-magazine.vercel.app/oauth/callback`
5. Add these Vercel environment variables:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REDIRECT_URI=https://photo-magazine.vercel.app/oauth/callback`

## Deployment Notes

- The project ships with `api/index.py` and `vercel.json` for Vercel deployment
- Vercel server storage is ephemeral, so generated artifacts are request-scoped unless durable storage is added
- Hosted PDF rendering still depends on available runtime libraries or the Chrome fallback path

## Local Development

```bash
pip install -e .
magazine web
```

## Output

The generated PDF targets print:

- A4 pages
- 3mm bleed
- 300 DPI image pipeline
- editorial layout system with dynamic pagination
