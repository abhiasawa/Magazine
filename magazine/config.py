"""Configuration and constants for Magazine."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Base paths
PROJECT_ROOT = Path(__file__).parent.parent


def _workspace_root() -> Path:
    override = os.getenv("MAGAZINE_WORKSPACE", "").strip()
    if override:
        return Path(override).expanduser()
    if os.getenv("VERCEL") or os.getenv("VERCEL_ENV"):
        return Path("/tmp/magazine-workspace")
    return PROJECT_ROOT / "workspace"


WORKSPACE = _workspace_root()
ORIGINALS_DIR = WORKSPACE / "originals"
THUMBNAILS_DIR = WORKSPACE / "thumbnails"
PRINT_DIR = WORKSPACE / "print"
OUTPUT_DIR = WORKSPACE / "output"

# Ensure workspace dirs exist
for d in [ORIGINALS_DIR, THUMBNAILS_DIR, PRINT_DIR, OUTPUT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Manifest files
PHOTOS_MANIFEST = WORKSPACE / "photos.json"
FACE_RESULTS = WORKSPACE / "face_results.json"
REVIEW_STATE = WORKSPACE / "review_state.json"
STORY_CONFIG = WORKSPACE / "story_config.json"
PHOTO_HASHES = WORKSPACE / "photo_hashes.json"

# Image settings
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tiff", ".tif"}
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
SUPPORTED_MEDIA_EXTENSIONS = SUPPORTED_EXTENSIONS | SUPPORTED_VIDEO_EXTENSIONS
THUMBNAIL_SIZE = 400  # px, longest side
PRINT_DPI = 300
JPEG_QUALITY = 95

# Page dimensions (A4 with 3mm bleed)
PAGE_WIDTH_MM = 210
PAGE_HEIGHT_MM = 297
BLEED_MM = 3
TRIM_WIDTH_MM = PAGE_WIDTH_MM  # 210mm
TRIM_HEIGHT_MM = PAGE_HEIGHT_MM  # 297mm
MEDIA_WIDTH_MM = PAGE_WIDTH_MM + 2 * BLEED_MM  # 216mm
MEDIA_HEIGHT_MM = PAGE_HEIGHT_MM + 2 * BLEED_MM  # 303mm
SAFE_MARGIN_MM = 15  # from trim edge

# Full-bleed image size at 300 DPI
FULL_BLEED_WIDTH_PX = int(MEDIA_WIDTH_MM / 25.4 * PRINT_DPI)  # ~2551px
FULL_BLEED_HEIGHT_PX = int(MEDIA_HEIGHT_MM / 25.4 * PRINT_DPI)  # ~3579px

# Google OAuth
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "")
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/photospicker.mediaitems.readonly"]
PICKER_API_BASE = "https://photospicker.googleapis.com/v1"

# Magazine design
COLORS = {
    "cream": "#FFF8F0",
    "blush": "#FDE8E0",
    "rose_gold": "#B76E79",
    "gold": "#C9A96E",
    "chocolate": "#3C2415",
    "warm_gray": "#7A6B63",
}

# AI / Vision analysis
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
VISION_ANALYSIS = WORKSPACE / "vision_analysis.json"
NARRATIVE_CACHE = WORKSPACE / "narrative_cache.json"

# Face detection
FACE_DETECTOR_BACKEND = "retinaface"
TARGET_FACE_COUNT = 2

# Dynamic pagination defaults
DEFAULT_STYLE = "editorial_luxury"
DEFAULT_PAGINATION = {
    "mode": "auto",
    "density": 1.7,
    "fixed_pages": 3,
}
