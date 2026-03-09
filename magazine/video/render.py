"""Render the magazine video using pure Python (PIL + PyAV).

Replaces the previous Remotion/Node.js subprocess so video generation
works on Vercel's Python serverless runtime.
"""

from __future__ import annotations

import json
import logging
import random
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse, unquote

import click

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

FPS = 15
SCENE_DURATION_SECONDS = 3
MULTI_SCENE_SECONDS = 4
VIDEO_SCENE_SECONDS = 5
OPENING_SECONDS = 3
CLOSING_SECONDS = 4
MAX_SCENES = 12

# ---------------------------------------------------------------------------
# Music selection (ported from music.ts)
# ---------------------------------------------------------------------------
TRACKS = [
    {"file": "warm-piano-01.mp3", "mood": "warm_romantic"},
    {"file": "warm-piano-02.mp3", "mood": "warm_romantic"},
    {"file": "warm-piano-03.mp3", "mood": "warm_romantic"},
    {"file": "warm-piano-04.mp3", "mood": "warm_romantic"},
    {"file": "gentle-acoustic-01.mp3", "mood": "gentle_acoustic"},
    {"file": "gentle-acoustic-02.mp3", "mood": "gentle_acoustic"},
    {"file": "gentle-acoustic-03.mp3", "mood": "gentle_acoustic"},
    {"file": "gentle-acoustic-04.mp3", "mood": "gentle_acoustic"},
    {"file": "ambient-cinematic-01.mp3", "mood": "ambient_cinematic"},
    {"file": "ambient-cinematic-02.mp3", "mood": "ambient_cinematic"},
    {"file": "ambient-cinematic-03.mp3", "mood": "ambient_cinematic"},
    {"file": "ambient-cinematic-04.mp3", "mood": "ambient_cinematic"},
    {"file": "upbeat-joyful-01.mp3", "mood": "upbeat_joyful"},
    {"file": "upbeat-joyful-02.mp3", "mood": "upbeat_joyful"},
    {"file": "upbeat-joyful-03.mp3", "mood": "upbeat_joyful"},
    {"file": "upbeat-joyful-04.mp3", "mood": "upbeat_joyful"},
    {"file": "emotional-cinematic-01.mp3", "mood": "emotional_cinematic"},
    {"file": "emotional-cinematic-02.mp3", "mood": "emotional_cinematic"},
    {"file": "emotional-cinematic-03.mp3", "mood": "emotional_cinematic"},
    {"file": "emotional-cinematic-04.mp3", "mood": "emotional_cinematic"},
]

PALETTE_TO_MOOD = {
    "warm_gold": ["warm_romantic", "emotional_cinematic"],
    "cool_stone": ["gentle_acoustic", "ambient_cinematic"],
    "deep_shadow": ["ambient_cinematic", "emotional_cinematic"],
    "soft_light": ["upbeat_joyful", "gentle_acoustic"],
}


def _select_music_track(scenes: list[dict]) -> Path | None:
    """Select the best music track based on scene palette distribution."""
    votes: dict[str, int] = {
        "warm_romantic": 0, "gentle_acoustic": 0,
        "ambient_cinematic": 0, "upbeat_joyful": 0,
        "emotional_cinematic": 0,
    }
    for scene in scenes:
        palette = scene.get("palette", "warm_gold")
        prefs = PALETTE_TO_MOOD.get(palette, PALETTE_TO_MOOD["warm_gold"])
        for mood in prefs:
            votes[mood] = votes.get(mood, 0) + 1

    best_mood = max(votes, key=votes.get)
    candidates = [t for t in TRACKS if t["mood"] == best_mood]
    if not candidates:
        candidates = TRACKS

    chosen = random.choice(candidates)
    track_path = MUSIC_DIR / chosen["file"]
    if track_path.exists():
        click.echo(f"Video: selected music track — {chosen['file']} ({best_mood})")
        return track_path

    # Fallback: any available track
    for t in TRACKS:
        p = MUSIC_DIR / t["file"]
        if p.exists():
            click.echo(f"Video: fallback music track — {t['file']}")
            return p

    click.echo("Video: no music tracks found")
    return None


# ---------------------------------------------------------------------------
# Audio muxing
# ---------------------------------------------------------------------------

def _mux_audio(video_path: Path, audio_path: Path, output_path: Path, duration_s: float) -> bool:
    """Combine silent video + music track using ffmpeg."""
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, Exception):
        ffmpeg = shutil.which("ffmpeg")

    if not ffmpeg:
        click.echo("Video: ffmpeg not available — video will have no music")
        return False

    fade_in = 2.0
    fade_out = 3.0
    fade_out_start = max(0, duration_s - fade_out)

    try:
        subprocess.run(
            [
                ffmpeg, "-y",
                "-i", str(video_path),
                "-i", str(audio_path),
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "128k",
                "-af", f"volume=0.6,afade=t=in:d={fade_in},afade=t=out:st={fade_out_start}:d={fade_out}",
                "-t", str(duration_s),
                "-shortest",
                str(output_path),
            ],
            capture_output=True,
            timeout=30,
        )
        return output_path.exists()
    except Exception as exc:
        logger.warning("Audio mux failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Path utilities
# ---------------------------------------------------------------------------

def _resolve_path(val: str) -> Path | None:
    """Convert a plain path or file:// URI to a Path."""
    if not val:
        return None
    if val.startswith("file://"):
        return Path(unquote(urlparse(val).path))
    return Path(val)


# ---------------------------------------------------------------------------
# Scene selection & data building (unchanged from original)
# ---------------------------------------------------------------------------

def _select_best_photos(
    pages: list[PageSpec],
    analyses: dict[str, PhotoAnalysis],
) -> list[PageSpec]:
    """Select the most emotionally impactful pages for the video."""
    body_pages = [
        p for p in pages
        if p.template not in ("cover", "back_cover", "dedication") and p.photos
    ]

    def page_score(page: PageSpec) -> float:
        weights = []
        for photo in page.photos:
            a = analyses.get(photo["id"])
            if a:
                weights.append(a.emotional_weight)
            else:
                weights.append(3)
        return sum(weights) / len(weights) if weights else 0

    scored = [(i, p, page_score(p)) for i, p in enumerate(body_pages)]
    scored.sort(key=lambda x: x[2], reverse=True)
    selected = scored[:MAX_SCENES]
    selected.sort(key=lambda x: x[0])
    click.echo(f"Video: selected {len(selected)} scenes from {len(body_pages)} body pages.")
    return [s[1] for s in selected]


def _copy_photo_to_public(photo: dict) -> str | None:
    """Copy a photo to the public dir, return the relative src path."""
    pid = photo["id"]
    for key in ("print_path", "original", "thumbnail"):
        val = photo.get(key, "")
        if not val:
            continue
        src_path = _resolve_path(val)
        if src_path and src_path.exists():
            dest = PHOTOS_DIR / f"{pid}{src_path.suffix}"
            shutil.copy2(src_path, dest)
            return f"photos/{pid}{src_path.suffix}"

    for ext in (".jpg", ".jpeg", ".png"):
        fallback = ORIGINALS_DIR / f"{pid}{ext}"
        if fallback.exists():
            dest = PHOTOS_DIR / f"{pid}{ext}"
            shutil.copy2(fallback, dest)
            return f"photos/{pid}{ext}"

    click.echo(f"Video: could not find photo file for {pid} (keys: {list(photo.keys())})")
    return None


def _copy_video_to_public(photo: dict) -> str | None:
    """Copy a video file to the public dir if available."""
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
    """Build the data structure consumed by the frame renderer."""
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

    selected_pages = _select_best_photos(pages, analyses)
    click.echo(f"Video: building data for {len(selected_pages)} pages ({len(pages)} total).")
    scenes = []
    copied_count = 0
    failed_count = 0

    for page in selected_pages:
        photos_data = []
        for photo in page.photos:
            src = _copy_photo_to_public(photo)
            if not src:
                failed_count += 1
                continue
            copied_count += 1
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

    click.echo(f"Video: {copied_count} photos copied, {failed_count} failed, {len(scenes)} scenes built.")

    opening_frames = OPENING_SECONDS * FPS
    closing_frames = CLOSING_SECONDS * FPS
    scenes_duration = sum(s["durationFrames"] for s in scenes)
    total = opening_frames + scenes_duration + closing_frames

    return {
        "title": title,
        "subtitle": subtitle,
        "fps": FPS,
        "totalDurationFrames": total,
        "openingFrames": opening_frames,
        "closingFrames": closing_frames,
        "scenes": scenes,
    }


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render_video(
    pages: list[PageSpec],
    analyses: dict[str, PhotoAnalysis],
    title: str = "Maison Folio",
    subtitle: str = "",
    output_path: Path | None = None,
) -> Path | None:
    """Render the magazine video using PIL + PyAV.

    Returns the output MP4 path, or None if rendering fails.
    """
    if output_path is None:
        output_path = OUTPUT_DIR / "magazine.mp4"

    click.echo("Video: starting render pipeline...")

    # Build data
    data = _build_video_data(pages, analyses, title, subtitle)
    if not data["scenes"]:
        click.echo("Video: no scenes built — skipping render.")
        save_json(VIDEO_STATUS, {"status": "failed", "error": "No photo files found for video scenes"})
        return None

    total_frames = data["totalDurationFrames"]
    DATA_JSON.parent.mkdir(parents=True, exist_ok=True)
    DATA_JSON.write_text(json.dumps(data, indent=2))
    click.echo(f"Video: {len(data['scenes'])} scenes, {total_frames} frames at {FPS}fps.")

    start = time.monotonic()

    save_json(VIDEO_STATUS, {
        "status": "rendering",
        "progress": 0,
        "totalFrames": total_frames,
    })

    # Encode frames with PyAV
    try:
        import av
        import numpy as np
        from magazine.video.renderer import generate_frames
    except ImportError as exc:
        error = f"Missing dependency: {exc}. Install av and numpy."
        click.echo(f"Video: {error}")
        save_json(VIDEO_STATUS, {"status": "failed", "error": error})
        return None

    silent_path = output_path.with_suffix(".silent.mp4")
    try:
        container = av.open(str(silent_path), mode="w")
        stream = container.add_stream("libx264", rate=FPS)
        stream.width = 1080
        stream.height = 1920
        stream.pix_fmt = "yuv420p"
        stream.options = {"crf": "23", "preset": "fast"}

        last_status_update = 0

        def _on_progress(current: int, total: int):
            nonlocal last_status_update
            now = time.monotonic()
            if now - last_status_update < 1.0:
                return
            last_status_update = now
            elapsed = int(now - start)
            pct = int(current / max(total, 1) * 90)  # Reserve 10% for audio mux
            speed = current / max(elapsed, 1)
            remaining = int((total - current) / max(speed, 1))
            save_json(VIDEO_STATUS, {
                "status": "rendering",
                "progress": min(pct, 89),
                "elapsed": elapsed,
                "remaining": remaining,
                "totalFrames": total,
            })

        for frame_idx, pil_img in generate_frames(data, PUBLIC_DIR, on_progress=_on_progress):
            arr = np.array(pil_img)
            video_frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
            for packet in stream.encode(video_frame):
                container.mux(packet)

        # Flush encoder
        for packet in stream.encode():
            container.mux(packet)
        container.close()

        elapsed = int(time.monotonic() - start)
        click.echo(f"Video: frames encoded in {elapsed}s")

    except Exception as exc:
        logger.exception("Video frame encoding failed")
        click.echo(f"Video: encoding failed — {exc}")
        save_json(VIDEO_STATUS, {"status": "failed", "error": str(exc)})
        if silent_path.exists():
            silent_path.unlink()
        return None

    # Mux audio
    save_json(VIDEO_STATUS, {"status": "rendering", "progress": 90})
    duration_s = total_frames / FPS
    audio_track = _select_music_track(data["scenes"])

    if audio_track:
        success = _mux_audio(silent_path, audio_track, output_path, duration_s)
        if success:
            silent_path.unlink(missing_ok=True)
        else:
            # Fall back to silent video
            shutil.move(str(silent_path), str(output_path))
    else:
        shutil.move(str(silent_path), str(output_path))

    if output_path.exists():
        size_mb = output_path.stat().st_size / (1024 * 1024)
        total_time = int(time.monotonic() - start)
        click.echo(f"Video: rendered successfully — {size_mb:.1f} MB in {total_time}s")
        save_json(VIDEO_STATUS, {"status": "ready", "progress": 100})
        return output_path

    click.echo("Video: encoding completed but output file not found.")
    save_json(VIDEO_STATUS, {"status": "failed", "error": "Output file not found after encoding"})
    return None
