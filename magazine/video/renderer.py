"""Pure Python frame-by-frame video renderer using PIL.

Replaces Remotion (Node.js) so video generation works on Vercel's Python runtime.
Generates frames as PIL Images; caller encodes them with PyAV.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Generator

import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 1080, 1920

# ---------------------------------------------------------------------------
# Palettes (ported from palette.ts)
# ---------------------------------------------------------------------------
PALETTES = {
    "warm_gold": {"bg": "#0C0A07", "text": "#F0EBE0", "accent": "#C7AA73", "muted": "#8A7D6B"},
    "cool_stone": {"bg": "#0A0B0E", "text": "#E8E6E1", "accent": "#9BA8B8", "muted": "#6B7580"},
    "deep_shadow": {"bg": "#050505", "text": "#D4CFC5", "accent": "#A89070", "muted": "#706050"},
    "soft_light": {"bg": "#F4F1EA", "text": "#1A1814", "accent": "#B8956A", "muted": "#8A7D6B"},
}

# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
_FONT_DIR = Path(__file__).resolve().parent.parent / "pdf" / "assets" / "fonts"
_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    key = (name, size)
    if key not in _font_cache:
        path = _FONT_DIR / name
        try:
            _font_cache[key] = ImageFont.truetype(str(path), size)
        except (OSError, IOError):
            logger.warning("Font %s not found, using default", path)
            _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


TITLE_FONT = "CormorantGaramond-Medium.ttf"
BODY_FONT = "Manrope-Medium.ttf"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_vignette_cache: Image.Image | None = None


def _hex(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


def _rgba(color: str, alpha: int) -> tuple[int, int, int, int]:
    r, g, b = _hex(color)
    return (r, g, b, alpha)


def _ease_in_out(t: float) -> float:
    if t < 0.5:
        return 2 * t * t
    return 1 - (-2 * t + 2) ** 2 / 2


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _get_vignette() -> Image.Image:
    global _vignette_cache
    if _vignette_cache is not None:
        return _vignette_cache
    # Radial gradient from transparent center to semi-opaque black edges
    cx, cy = WIDTH / 2, HEIGHT / 2
    max_dist = math.sqrt(cx * cx + cy * cy)
    arr = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    y_coords = np.arange(HEIGHT).reshape(-1, 1)
    x_coords = np.arange(WIDTH).reshape(1, -1)
    dist = np.sqrt((x_coords - cx) ** 2 + (y_coords - cy) ** 2) / max_dist
    # Ease: transparent inside 40%, then ramp up to 45% opacity
    alpha = np.clip((dist - 0.4) / 0.6, 0, 1) * 115
    arr = alpha.astype(np.uint8)
    vignette = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    vignette.putalpha(Image.fromarray(arr, mode="L"))
    _vignette_cache = vignette
    return _vignette_cache


_photo_cache: dict[str, Image.Image] = {}
MAX_PHOTO_DIM = 2400


def _get_photo(src: str, public_dir: Path) -> Image.Image | None:
    if src in _photo_cache:
        return _photo_cache[src]
    path = public_dir / src
    if not path.exists():
        logger.warning("Photo not found: %s", path)
        return None
    try:
        img = Image.open(path).convert("RGB")
        # Downscale to save memory
        w, h = img.size
        if max(w, h) > MAX_PHOTO_DIM:
            ratio = MAX_PHOTO_DIM / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        _photo_cache[src] = img
        return img
    except Exception as exc:
        logger.warning("Failed to load photo %s: %s", path, exc)
        return None


def _cover_fit(photo: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Crop + resize to fill target dimensions (like CSS object-fit: cover)."""
    pw, ph = photo.size
    scale = max(target_w / pw, target_h / ph)
    new_w, new_h = int(pw * scale), int(ph * scale)
    resized = photo.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    y: int,
    font: ImageFont.FreeTypeFont,
    fill: tuple,
    max_width: int = WIDTH - 120,
):
    """Draw text centered horizontally, wrapping if needed."""
    lines = _wrap_text(text, font, max_width)
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (WIDTH - tw) // 2
        draw.text((x, y), line, font=font, fill=fill)
        th = bbox[3] - bbox[1]
        y += th + 8


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


_scrim_cache: Image.Image | None = None


def _gradient_scrim(img: Image.Image, height_frac: float = 0.35):
    """Apply a bottom gradient scrim for text readability."""
    global _scrim_cache
    if _scrim_cache is None:
        scrim_h = int(HEIGHT * height_frac)
        arr = np.zeros((scrim_h, WIDTH, 4), dtype=np.uint8)
        alphas = np.linspace(0, 180, scrim_h).astype(np.uint8)
        arr[:, :, 3] = alphas[:, np.newaxis]
        _scrim_cache = Image.fromarray(arr, "RGBA")
    scrim_h = _scrim_cache.height
    img.paste(_scrim_cache, (0, HEIGHT - scrim_h), _scrim_cache)


# ---------------------------------------------------------------------------
# Ken Burns effect
# ---------------------------------------------------------------------------
KEN_BURNS_DIRECTIONS = ["zoom_in", "zoom_out", "pan_left", "pan_right"]


def _apply_ken_burns(
    photo: Image.Image,
    frame: int,
    total_frames: int,
    direction: str,
    target_w: int = WIDTH,
    target_h: int = HEIGHT,
) -> Image.Image:
    progress = _clamp(frame / max(total_frames - 1, 1))
    eased = _ease_in_out(progress)
    pw, ph = photo.size

    if direction == "zoom_in":
        scale_start, scale_end = 1.0, 1.12
        scale = scale_start + (scale_end - scale_start) * eased
        crop_w = pw / scale
        crop_h = ph / scale
        cx = pw / 2 + (pw * 0.02) * eased
        cy = ph / 2 + (ph * 0.01) * eased
    elif direction == "zoom_out":
        scale_start, scale_end = 1.12, 1.0
        scale = scale_start + (scale_end - scale_start) * eased
        crop_w = pw / scale
        crop_h = ph / scale
        cx = pw / 2
        cy = ph / 2
    elif direction == "pan_left":
        scale = 1.08
        crop_w = pw / scale
        crop_h = ph / scale
        sweep = (pw - crop_w) * 0.8
        cx = pw / 2 + sweep / 2 - sweep * eased
        cy = ph / 2
    else:  # pan_right
        scale = 1.08
        crop_w = pw / scale
        crop_h = ph / scale
        sweep = (pw - crop_w) * 0.8
        cx = pw / 2 - sweep / 2 + sweep * eased
        cy = ph / 2

    left = max(0, int(cx - crop_w / 2))
    top = max(0, int(cy - crop_h / 2))
    right = min(pw, int(cx + crop_w / 2))
    bottom = min(ph, int(cy + crop_h / 2))

    cropped = photo.crop((left, top, right, bottom))
    return cropped.resize((target_w, target_h), Image.LANCZOS)


# ---------------------------------------------------------------------------
# Scene renderers
# ---------------------------------------------------------------------------

def render_opening_frame(
    frame: int,
    total: int,
    pal: dict,
    title: str,
    subtitle: str,
) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), _hex(pal["bg"]))
    draw = ImageDraw.Draw(img)
    progress = _clamp(frame / max(total - 1, 1))

    # Accent line grows from center (0-40% of animation)
    line_progress = _clamp(progress / 0.4)
    line_w = int(200 * _ease_in_out(line_progress))
    if line_w > 0:
        ly = HEIGHT // 2 - 80
        lx = (WIDTH - line_w) // 2
        draw.rectangle([lx, ly, lx + line_w, ly + 2], fill=_hex(pal["accent"]))

    # Title fades in + slides up (20-70%)
    title_progress = _clamp((progress - 0.2) / 0.5)
    if title_progress > 0:
        alpha = int(255 * _ease_in_out(title_progress))
        slide = int(30 * (1 - _ease_in_out(title_progress)))
        title_font = _font(TITLE_FONT, 72)
        title_color = _rgba(pal["text"], alpha)
        # Use overlay for alpha
        overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        _draw_centered_text(odraw, title, HEIGHT // 2 - 40 + slide, title_font, title_color)
        img = Image.composite(
            Image.new("RGB", (WIDTH, HEIGHT), _hex(pal["text"])),
            img,
            overlay.split()[3],
        )
        # Redraw non-alpha elements
        draw = ImageDraw.Draw(img)
        if line_w > 0:
            ly = HEIGHT // 2 - 80
            lx = (WIDTH - line_w) // 2
            draw.rectangle([lx, ly, lx + line_w, ly + 2], fill=_hex(pal["accent"]))

    # Subtitle fades in (50-90%)
    sub_progress = _clamp((progress - 0.5) / 0.4)
    if sub_progress > 0 and subtitle:
        sub_font = _font(BODY_FONT, 32)
        sub_alpha = int(255 * _ease_in_out(sub_progress))
        sub_color = (*_hex(pal["muted"]), sub_alpha)
        overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        _draw_centered_text(odraw, subtitle, HEIGHT // 2 + 60, sub_font, sub_color)
        img = img.convert("RGBA")
        img = Image.alpha_composite(img, overlay)
        img = img.convert("RGB")

    return img


def render_single_photo_frame(
    frame: int,
    scene: dict,
    scene_index: int,
    public_dir: Path,
) -> Image.Image:
    photo_data = scene["photos"][0]
    pal = PALETTES.get(scene.get("palette", "warm_gold"), PALETTES["warm_gold"])
    duration = scene["durationFrames"]

    photo = _get_photo(photo_data["src"], public_dir)
    if photo is None:
        return Image.new("RGB", (WIDTH, HEIGHT), _hex(pal["bg"]))

    direction = KEN_BURNS_DIRECTIONS[scene_index % 4]
    img = _apply_ken_burns(photo, frame, duration, direction)
    img = img.convert("RGBA")

    # Vignette
    img = Image.alpha_composite(img, _get_vignette())

    # Narrative overlay
    narrative = scene.get("narrative")
    if narrative:
        _draw_narrative_on_image(img, narrative, pal, frame, duration)

    return img.convert("RGB")


def render_multi_photo_frame(
    frame: int,
    scene: dict,
    public_dir: Path,
) -> Image.Image:
    pal = PALETTES.get(scene.get("palette", "warm_gold"), PALETTES["warm_gold"])
    duration = scene["durationFrames"]
    photos = scene["photos"]
    n = len(photos)

    img = Image.new("RGB", (WIDTH, HEIGHT), _hex(pal["bg"]))

    # Grid layout: 2 columns
    gap = 12
    if n <= 2:
        cols, rows_count = 2, 1
    else:
        cols, rows_count = 2, 2

    cell_w = (WIDTH - gap * (cols + 1)) // cols
    cell_h = (HEIGHT - gap * (rows_count + 1)) // rows_count

    for idx, photo_data in enumerate(photos[:4]):
        # Staggered fade-in: 6 frames between each
        stagger_delay = idx * 6
        local_frame = frame - stagger_delay
        if local_frame < 0:
            continue

        fade_progress = _clamp(local_frame / 15)
        scale_val = 0.92 + 0.08 * _ease_in_out(fade_progress)
        alpha_val = _ease_in_out(fade_progress)

        photo = _get_photo(photo_data["src"], public_dir)
        if photo is None:
            continue

        row = idx // cols
        col = idx % cols
        x = gap + col * (cell_w + gap)
        y = gap + row * (cell_h + gap)

        fitted = _cover_fit(photo, cell_w, cell_h)

        # Apply scale
        scaled_w = int(cell_w * scale_val)
        scaled_h = int(cell_h * scale_val)
        scaled = fitted.resize((scaled_w, scaled_h), Image.LANCZOS)

        # Center in cell
        paste_x = x + (cell_w - scaled_w) // 2
        paste_y = y + (cell_h - scaled_h) // 2

        if alpha_val < 1.0:
            alpha_mask = Image.new("L", scaled.size, int(255 * alpha_val))
            img.paste(scaled, (paste_x, paste_y), alpha_mask)
        else:
            img.paste(scaled, (paste_x, paste_y))

    return img


def render_closing_frame(
    frame: int,
    total: int,
    pal: dict,
    title: str,
) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), _hex(pal["bg"]))
    draw = ImageDraw.Draw(img)
    progress = _clamp(frame / max(total - 1, 1))

    # Title fades in (0-50%)
    title_progress = _clamp(progress / 0.5)
    if title_progress > 0:
        title_font = _font(TITLE_FONT, 64)
        alpha = int(255 * _ease_in_out(title_progress))
        title_color = (*_hex(pal["text"]), alpha)
        overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        _draw_centered_text(odraw, title, HEIGHT // 2 - 60, title_font, title_color)
        img = img.convert("RGBA")
        img = Image.alpha_composite(img, overlay)
        img = img.convert("RGB")
        draw = ImageDraw.Draw(img)

    # Accent line (20-60%)
    line_progress = _clamp((progress - 0.2) / 0.4)
    if line_progress > 0:
        line_w = int(120 * _ease_in_out(line_progress))
        ly = HEIGHT // 2 + 10
        lx = (WIDTH - line_w) // 2
        draw.rectangle([lx, ly, lx + line_w, ly + 2], fill=_hex(pal["accent"]))

    # Tagline (40-80%)
    tag_progress = _clamp((progress - 0.4) / 0.4)
    if tag_progress > 0:
        tag_font = _font(BODY_FONT, 24)
        alpha = int(255 * _ease_in_out(tag_progress))
        tag_color = (*_hex(pal["muted"]), alpha)
        overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        _draw_centered_text(odraw, "Made with Maison Folio", HEIGHT // 2 + 50, tag_font, tag_color)
        img = img.convert("RGBA")
        img = Image.alpha_composite(img, overlay)
        img = img.convert("RGB")

    return img


def _draw_narrative_on_image(
    img: Image.Image,
    narrative: dict,
    pal: dict,
    frame: int,
    duration: int,
):
    text = narrative.get("text", "")
    if not text:
        return

    ntype = narrative.get("type", "sentence")
    delay = int(duration * 0.15)
    fade_frames = 12

    local = frame - delay
    if local < 0:
        return

    # Fade in over fade_frames, fade out near end
    remaining = duration - delay
    if local < fade_frames:
        alpha = local / fade_frames
    elif local > remaining - fade_frames:
        alpha = (remaining - local) / fade_frames
    else:
        alpha = 1.0
    alpha = _clamp(alpha)

    slide = int(20 * (1 - _ease_in_out(_clamp(local / fade_frames))))

    if ntype == "heading_word":
        font = _font(TITLE_FONT, 72)
        color = (*_hex(pal["accent"]), int(255 * alpha))
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        _draw_centered_text(odraw, text, HEIGHT // 2 - 40 + slide, font, color)
        composite = Image.alpha_composite(img.convert("RGBA"), overlay)
        img.paste(composite.convert("RGB"))
    else:
        # Sentence mode: bottom-left with gradient scrim
        _gradient_scrim(img)
        font = _font(BODY_FONT, 36)
        color = (*_hex(pal["text"]), int(255 * alpha))
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        lines = _wrap_text(text, font, WIDTH - 120)
        y = HEIGHT - 180 + slide
        for line in lines:
            odraw.text((60, y), line, font=font, fill=color)
            bbox = font.getbbox(line)
            y += (bbox[3] - bbox[1]) + 8
        composite = Image.alpha_composite(img.convert("RGBA"), overlay)
        img.paste(composite.convert("RGB"))


# ---------------------------------------------------------------------------
# Main frame generator
# ---------------------------------------------------------------------------

def generate_frames(
    data: dict,
    public_dir: Path,
    on_progress: callable | None = None,
) -> Generator[tuple[int, Image.Image], None, None]:
    """Yield (frame_index, PIL.Image) tuples for the entire video.

    Sequences: opening -> scenes -> closing.
    """
    fps = data.get("fps", 15)
    scenes = data.get("scenes", [])
    title = data.get("title", "")
    subtitle = data.get("subtitle", "")
    total_frames = data.get("totalDurationFrames", 0)

    opening_frames = data.get("openingFrames", 3 * fps)
    closing_frames = data.get("closingFrames", 4 * fps)

    # Determine dominant palette from scenes
    palette_counts: dict[str, int] = {}
    for scene in scenes:
        p = scene.get("palette", "warm_gold")
        palette_counts[p] = palette_counts.get(p, 0) + 1
    dominant = max(palette_counts, key=palette_counts.get) if palette_counts else "warm_gold"
    pal = PALETTES.get(dominant, PALETTES["warm_gold"])

    frame_idx = 0

    # --- Opening ---
    for f in range(opening_frames):
        yield (frame_idx, render_opening_frame(f, opening_frames, pal, title, subtitle))
        frame_idx += 1
        if on_progress:
            on_progress(frame_idx, total_frames)

    # --- Scenes ---
    for si, scene in enumerate(scenes):
        dur = scene["durationFrames"]
        n_photos = len(scene.get("photos", []))
        for f in range(dur):
            if n_photos == 1:
                yield (frame_idx, render_single_photo_frame(f, scene, si, public_dir))
            else:
                yield (frame_idx, render_multi_photo_frame(f, scene, public_dir))
            frame_idx += 1
            if on_progress:
                on_progress(frame_idx, total_frames)

    # --- Closing ---
    for f in range(closing_frames):
        yield (frame_idx, render_closing_frame(f, closing_frames, pal, title))
        frame_idx += 1
        if on_progress:
            on_progress(frame_idx, total_frames)

    # Clear photo cache to free memory
    _photo_cache.clear()
