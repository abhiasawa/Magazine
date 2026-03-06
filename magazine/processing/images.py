"""Image processing utilities: HEIC conversion, EXIF rotation, thumbnails, print resize."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ExifTags
from PIL import ImageEnhance

from magazine.config import (
    THUMBNAIL_SIZE,
    PRINT_DPI,
    JPEG_QUALITY,
    FULL_BLEED_WIDTH_PX,
    FULL_BLEED_HEIGHT_PX,
)


def fix_exif_rotation(img: Image.Image) -> Image.Image:
    """Apply EXIF orientation tag and return correctly rotated image."""
    try:
        exif = img.getexif()
        orientation_key = None
        for k, v in ExifTags.TAGS.items():
            if v == "Orientation":
                orientation_key = k
                break

        if orientation_key and orientation_key in exif:
            orientation = exif[orientation_key]
            rotations = {
                3: 180,
                6: 270,
                8: 90,
            }
            if orientation in rotations:
                img = img.rotate(rotations[orientation], expand=True)
            elif orientation == 2:
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            elif orientation == 4:
                img = img.transpose(Image.FLIP_TOP_BOTTOM)
            elif orientation == 5:
                img = img.transpose(Image.FLIP_LEFT_RIGHT).rotate(270, expand=True)
            elif orientation == 7:
                img = img.transpose(Image.FLIP_LEFT_RIGHT).rotate(90, expand=True)
    except Exception:
        pass
    return img


def convert_to_jpeg(src: Path, dest: Path) -> Path:
    """Convert any supported image (including HEIC) to JPEG."""
    suffix = src.suffix.lower()

    if suffix in (".heic", ".heif"):
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except ImportError:
            raise RuntimeError("pillow-heif required for HEIC support: pip install pillow-heif")

    img = Image.open(src)
    img = fix_exif_rotation(img)

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    dest = dest.with_suffix(".jpg")
    img.save(dest, "JPEG", quality=JPEG_QUALITY)
    return dest


def make_thumbnail(src: Path, dest_dir: Path) -> Path:
    """Create a thumbnail (longest side = THUMBNAIL_SIZE px)."""
    img = Image.open(src)
    img = fix_exif_rotation(img)

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    img.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE), Image.LANCZOS)

    dest = dest_dir / (src.stem + ".jpg")
    img.save(dest, "JPEG", quality=85)
    return dest


def _apply_gentle_grade(img: Image.Image) -> Image.Image:
    """Apply subtle editorial color treatment for cross-spread consistency."""
    img = ImageEnhance.Color(img).enhance(1.04)
    img = ImageEnhance.Contrast(img).enhance(1.03)
    img = ImageEnhance.Brightness(img).enhance(1.01)
    return img


def make_print_image(
    src: Path,
    dest_dir: Path,
    target_width: int = None,
    target_height: int = None,
    focal_point: tuple[float, float] | None = None,
    filename: str | None = None,
) -> Path:
    """Resize image for print at 300 DPI, preserving the full frame."""
    if target_width is None:
        target_width = FULL_BLEED_WIDTH_PX
    if target_height is None:
        target_height = FULL_BLEED_HEIGHT_PX

    img = Image.open(src)
    img = fix_exif_rotation(img)

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img = _apply_gentle_grade(img)

    scale = min(target_width / img.width, target_height / img.height)
    scale = min(scale, 1.0)
    new_width = max(1, int(img.width * scale))
    new_height = max(1, int(img.height * scale))
    img = img.resize((new_width, new_height), Image.LANCZOS)

    name = filename or src.stem
    dest = dest_dir / f"{name}.jpg"
    img.save(dest, "JPEG", quality=JPEG_QUALITY, dpi=(PRINT_DPI, PRINT_DPI))
    return dest


def get_exif_date(src: Path) -> str | None:
    """Extract date taken from EXIF data."""
    try:
        img = Image.open(src)
        exif = img.getexif()
        # DateTimeOriginal
        for tag_id, tag_name in ExifTags.TAGS.items():
            if tag_name == "DateTimeOriginal":
                if tag_id in exif:
                    return exif[tag_id]
        # Fallback to DateTime
        for tag_id, tag_name in ExifTags.TAGS.items():
            if tag_name == "DateTime":
                if tag_id in exif:
                    return exif[tag_id]
    except Exception:
        pass
    return None


def get_image_dimensions(src: Path) -> tuple[int, int]:
    """Get image dimensions (width, height)."""
    with Image.open(src) as img:
        img = fix_exif_rotation(img)
        return img.size
