"""Python wrapper to render the Remotion video from magazine data."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import time
from pathlib import Path

from magazine.config import OUTPUT_DIR, ORIGINALS_DIR, THUMBNAILS_DIR, VIDEO_STATUS
from magazine.layout.engine import PageSpec
from magazine.processing.vision import PhotoAnalysis
from magazine.services.state import save_json

logger = logging.getLogger(__name__)

VIDEO_DIR = Path(__file__).parent
PUBLIC_DIR = VIDEO_DIR / "public"
PHOTOS_DIR = PUBLIC_DIR / "photos"
MUSIC_DIR = VIDEO_DIR / "music" / "tracks"
DATA_JSON = PUBLIC_DIR / "data.json"

FPS = 30
SCENE_DURATION_SECONDS = 3  # per single photo
MULTI_SCENE_SECONDS = 4  # per multi-photo scene
VIDEO_SCENE_SECONDS = 5  # per video clip
OPENING_SECONDS = 3
CLOSING_SECONDS = 4
MAX_SCENES = 15


def _select_best_photos(
    pages: list[PageSpec],
    analyses: dict[str, PhotoAnalysis],
) -> list[PageSpec]:
    """Select the most emotionally impactful pages for the video."""
    body_pages = [
        p for p in pages
        if p.template not in ("cover", "back_cover", "dedication") and p.photos
    ]

    # Score each page by its photos' emotional weight
    def page_score(page: PageSpec) -> float:
        weights = []
        for photo in page.photos:
            a = analyses.get(photo["id"])
            if a:
                weights.append(a.emotional_weight)
            else:
                weights.append(3)
        return sum(weights) / len(weights) if weights else 0

    # Sort by score but preserve rough chronological order by using a weighted sort
    scored = [(i, p, page_score(p)) for i, p in enumerate(body_pages)]
    # Take top MAX_SCENES by score, then re-sort by original order
    scored.sort(key=lambda x: x[2], reverse=True)
    selected = scored[:MAX_SCENES]
    selected.sort(key=lambda x: x[0])
    return [s[1] for s in selected]


def _copy_photo_to_public(photo: dict) -> str | None:
    """Copy a photo to the Remotion public dir, return the relative src path."""
    pid = photo["id"]
    # Prefer print-ready, then original, then thumbnail
    for key in ("print_ready", "original", "thumbnail"):
        val = photo.get(key, "")
        if val:
            src_path = Path(val)
            if src_path.exists():
                dest = PHOTOS_DIR / f"{pid}{src_path.suffix}"
                shutil.copy2(src_path, dest)
                return f"photos/{pid}{src_path.suffix}"
    return None


def _copy_video_to_public(photo: dict) -> str | None:
    """Copy a video file to the Remotion public dir if available."""
    video_path = photo.get("video_path", "")
    if not video_path:
        return None
    src = Path(video_path)
    if not src.exists():
        return None
    pid = photo["id"]
    dest = PHOTOS_DIR / f"{pid}{src.suffix}"
    shutil.copy2(src, dest)
    return f"photos/{pid}{src.suffix}"


def _build_video_data(
    pages: list[PageSpec],
    analyses: dict[str, PhotoAnalysis],
    title: str,
    subtitle: str,
) -> dict:
    """Build the data.json structure for Remotion."""
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

    selected_pages = _select_best_photos(pages, analyses)
    scenes = []

    for page in selected_pages:
        photos_data = []
        for photo in page.photos:
            src = _copy_photo_to_public(photo)
            if not src:
                continue
            media_type = photo.get("media_type", "photo")
            pd = {
                "id": photo["id"],
                "src": src,
                "width": photo.get("width", 1080),
                "height": photo.get("height", 1920),
                "mediaType": media_type,
            }
            if media_type == "video":
                video_src = _copy_video_to_public(photo)
                if video_src:
                    pd["videoSrc"] = video_src
            photos_data.append(pd)

        if not photos_data:
            continue

        # Determine duration
        is_video = any(p.get("mediaType") == "video" and p.get("videoSrc") for p in photos_data)
        if is_video:
            duration_s = VIDEO_SCENE_SECONDS
        elif len(photos_data) > 1:
            duration_s = MULTI_SCENE_SECONDS
        else:
            duration_s = SCENE_DURATION_SECONDS

        scene = {
            "photos": photos_data,
            "palette": page.palette_hint or "warm_gold",
            "durationFrames": duration_s * FPS,
        }

        if page.quote:
            scene["narrative"] = {
                "text": page.quote.get("text", ""),
                "type": page.quote.get("type", "sentence"),
            }

        scenes.append(scene)

    # Verify music tracks exist — copy to public if needed
    music_public = PUBLIC_DIR / "music" / "tracks"
    music_public.mkdir(parents=True, exist_ok=True)
    if MUSIC_DIR.exists():
        for mp3 in MUSIC_DIR.glob("*.mp3"):
            dest = music_public / mp3.name
            if not dest.exists():
                shutil.copy2(mp3, dest)

    # Calculate total duration
    scenes_duration = sum(s["durationFrames"] for s in scenes)
    total = OPENING_SECONDS * FPS + scenes_duration + CLOSING_SECONDS * FPS

    return {
        "title": title,
        "subtitle": subtitle,
        "fps": FPS,
        "totalDurationFrames": total,
        "scenes": scenes,
    }


def render_video(
    pages: list[PageSpec],
    analyses: dict[str, PhotoAnalysis],
    title: str = "Maison Folio",
    subtitle: str = "",
    output_path: Path | None = None,
) -> Path | None:
    """Render the magazine video using Remotion.

    Returns the output MP4 path, or None if rendering fails.
    """
    if output_path is None:
        output_path = OUTPUT_DIR / "magazine.mp4"

    # Check if npx is available
    npx = shutil.which("npx")
    if not npx:
        logger.warning("npx not found — cannot render video")
        return None

    # Build data JSON
    data = _build_video_data(pages, analyses, title, subtitle)
    if not data["scenes"]:
        logger.warning("No scenes to render — skipping video")
        return None

    total_frames = data["totalDurationFrames"]
    DATA_JSON.write_text(json.dumps(data, indent=2))
    logger.info("Video data written: %d scenes, %d total frames", len(data["scenes"]), total_frames)

    # Estimate render time: ~3 frames/sec on average hardware
    estimated_seconds = max(10, int(total_frames / 3))

    def _update_progress(progress: int, elapsed: int):
        remaining = max(0, estimated_seconds - elapsed)
        save_json(VIDEO_STATUS, {
            "status": "rendering",
            "progress": min(progress, 99),
            "elapsed": elapsed,
            "remaining": remaining,
            "totalFrames": total_frames,
        })

    _update_progress(0, 0)

    # Render with Remotion using Popen for progress tracking
    try:
        proc = subprocess.Popen(
            [
                npx, "remotion", "render",
                "src/index.ts", "Magazine",
                f"--output={output_path}",
                "--codec=h264",
                "--log=verbose",
            ],
            cwd=str(VIDEO_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        start = time.monotonic()
        frame_re = re.compile(r"(\d+)\s*/\s*(\d+)")
        last_parsed_pct = 0

        while proc.poll() is None:
            # Read stderr non-blocking (readline blocks until \n)
            line = proc.stderr.readline()
            elapsed = int(time.monotonic() - start)

            # Try to parse actual frame progress from Remotion output
            if line:
                m = frame_re.search(line)
                if m:
                    rendered = int(m.group(1))
                    total = int(m.group(2))
                    if total > 0:
                        last_parsed_pct = int(rendered / total * 100)
                        # Recalibrate estimate based on actual speed
                        if rendered > 5:
                            speed = rendered / max(elapsed, 1)
                            estimated_seconds = int(total / max(speed, 0.5))

            # Use parsed progress if available, else time-based estimate
            if last_parsed_pct > 0:
                progress = last_parsed_pct
            else:
                progress = min(95, int(elapsed / max(estimated_seconds, 1) * 100))

            _update_progress(progress, elapsed)

        # Drain remaining output
        _, stderr_tail = proc.communicate(timeout=10)

        if proc.returncode != 0:
            full_stderr = stderr_tail or ""
            logger.error("Remotion render failed (exit %d):\n%s", proc.returncode, full_stderr[-2000:])
            return None

        if output_path.exists():
            logger.info("Video rendered: %s", output_path)
            return output_path

    except subprocess.TimeoutExpired:
        logger.error("Remotion render timed out (5 min)")
        try:
            proc.kill()
        except Exception:
            pass
    except FileNotFoundError:
        logger.error("npx/remotion not found")

    return None
