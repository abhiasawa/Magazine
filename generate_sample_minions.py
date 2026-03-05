"""Generate 40 fun minion-style sample images for testing the magazine pipeline."""

import random
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = Path("sample_photos")
OUTPUT_DIR.mkdir(exist_ok=True)

# Minion color palette
MINION_YELLOW = (255, 217, 15)
MINION_YELLOW_DARK = (230, 190, 10)
MINION_BLUE = (45, 85, 160)
MINION_BLUE_DARK = (35, 65, 130)
MINION_BROWN = (100, 70, 40)
MINION_BLACK = (30, 30, 30)
MINION_WHITE = (255, 255, 255)
MINION_GRAY = (180, 180, 180)
MINION_EYE_BROWN = (120, 80, 30)

BACKGROUNDS = [
    (255, 240, 200),  # warm cream
    (200, 230, 255),  # sky blue
    (220, 255, 220),  # mint green
    (255, 220, 220),  # soft pink
    (240, 230, 255),  # lavender
    (255, 250, 230),  # warm white
    (200, 220, 200),  # sage
    (255, 235, 210),  # peach
]


def draw_minion(draw, cx, cy, scale=1.0, mood="happy", looking="center"):
    """Draw a cute minion character at the given center position."""
    s = scale

    # Body (rounded rectangle via ellipse)
    body_w, body_h = int(120 * s), int(180 * s)
    body_top = cy - int(50 * s)
    body_left = cx - body_w // 2

    # Body shape
    draw.rounded_rectangle(
        [body_left, body_top, body_left + body_w, body_top + body_h],
        radius=int(55 * s),
        fill=MINION_YELLOW,
        outline=MINION_YELLOW_DARK,
        width=max(1, int(2 * s)),
    )

    # Overalls
    overall_top = body_top + int(100 * s)
    draw.rounded_rectangle(
        [body_left + int(5 * s), overall_top, body_left + body_w - int(5 * s), body_top + body_h - int(5 * s)],
        radius=int(20 * s),
        fill=MINION_BLUE,
        outline=MINION_BLUE_DARK,
        width=max(1, int(2 * s)),
    )

    # Overall pocket
    pocket_size = int(20 * s)
    pocket_x = cx - pocket_size // 2
    pocket_y = overall_top + int(15 * s)
    draw.rounded_rectangle(
        [pocket_x, pocket_y, pocket_x + pocket_size, pocket_y + pocket_size],
        radius=int(4 * s),
        fill=MINION_BLUE_DARK,
    )

    # Overall straps
    strap_w = int(8 * s)
    draw.rectangle(
        [body_left + int(20 * s), overall_top - int(15 * s),
         body_left + int(20 * s) + strap_w, overall_top + int(5 * s)],
        fill=MINION_BLUE,
    )
    draw.rectangle(
        [body_left + body_w - int(20 * s) - strap_w, overall_top - int(15 * s),
         body_left + body_w - int(20 * s), overall_top + int(5 * s)],
        fill=MINION_BLUE,
    )

    # Goggle strap
    goggle_y = body_top + int(40 * s)
    draw.rectangle(
        [body_left, goggle_y - int(8 * s), body_left + body_w, goggle_y + int(8 * s)],
        fill=MINION_GRAY,
    )

    # Eye(s) - goggle
    eye_r = int(28 * s)
    eye_offset = int(2 * s) if looking == "center" else (int(5 * s) if looking == "right" else int(-5 * s))

    # Goggle rim
    draw.ellipse(
        [cx - eye_r - int(5*s), goggle_y - eye_r - int(5*s),
         cx + eye_r + int(5*s), goggle_y + eye_r + int(5*s)],
        fill=MINION_GRAY,
        outline=(120, 120, 120),
        width=max(1, int(3 * s)),
    )

    # Eye white
    draw.ellipse(
        [cx - eye_r, goggle_y - eye_r, cx + eye_r, goggle_y + eye_r],
        fill=MINION_WHITE,
    )

    # Iris
    iris_r = int(14 * s)
    draw.ellipse(
        [cx + eye_offset - iris_r, goggle_y - iris_r,
         cx + eye_offset + iris_r, goggle_y + iris_r],
        fill=MINION_EYE_BROWN,
    )

    # Pupil
    pupil_r = int(7 * s)
    draw.ellipse(
        [cx + eye_offset - pupil_r, goggle_y - pupil_r,
         cx + eye_offset + pupil_r, goggle_y + pupil_r],
        fill=MINION_BLACK,
    )

    # Eye shine
    shine_r = int(3 * s)
    draw.ellipse(
        [cx + eye_offset - int(4*s) - shine_r, goggle_y - int(5*s) - shine_r,
         cx + eye_offset - int(4*s) + shine_r, goggle_y - int(5*s) + shine_r],
        fill=MINION_WHITE,
    )

    # Mouth
    mouth_y = body_top + int(70 * s)
    if mood == "happy":
        draw.arc(
            [cx - int(20*s), mouth_y - int(8*s), cx + int(20*s), mouth_y + int(15*s)],
            start=0, end=180,
            fill=MINION_BLACK,
            width=max(1, int(3 * s)),
        )
    elif mood == "excited":
        draw.ellipse(
            [cx - int(15*s), mouth_y - int(3*s), cx + int(15*s), mouth_y + int(18*s)],
            fill=MINION_BLACK,
        )
        # Teeth
        draw.rectangle(
            [cx - int(8*s), mouth_y - int(3*s), cx + int(8*s), mouth_y + int(3*s)],
            fill=MINION_WHITE,
        )
    elif mood == "silly":
        # Tongue out
        draw.arc(
            [cx - int(20*s), mouth_y - int(5*s), cx + int(20*s), mouth_y + int(15*s)],
            start=0, end=180,
            fill=MINION_BLACK,
            width=max(1, int(3 * s)),
        )
        draw.ellipse(
            [cx - int(5*s), mouth_y + int(8*s), cx + int(5*s), mouth_y + int(18*s)],
            fill=(220, 100, 100),
        )
    else:  # neutral
        draw.line(
            [cx - int(15*s), mouth_y + int(5*s), cx + int(15*s), mouth_y + int(5*s)],
            fill=MINION_BLACK,
            width=max(1, int(2 * s)),
        )

    # Hair (a few sprigs on top)
    hair_base_y = body_top + int(5 * s)
    for i in range(random.randint(2, 5)):
        hx = cx + random.randint(int(-25*s), int(25*s))
        length = random.randint(int(15*s), int(30*s))
        curve = random.randint(int(-10*s), int(10*s))
        draw.line(
            [hx, hair_base_y, hx + curve, hair_base_y - length],
            fill=MINION_BLACK,
            width=max(1, int(2 * s)),
        )

    # Arms (simple)
    arm_y = body_top + int(95 * s)
    # Left arm
    draw.line(
        [body_left, arm_y, body_left - int(20*s), arm_y + int(25*s)],
        fill=MINION_YELLOW_DARK,
        width=max(1, int(8 * s)),
    )
    # Right arm
    draw.line(
        [body_left + body_w, arm_y, body_left + body_w + int(20*s), arm_y + int(25*s)],
        fill=MINION_YELLOW_DARK,
        width=max(1, int(8 * s)),
    )

    # Feet
    foot_y = body_top + body_h - int(5 * s)
    draw.ellipse(
        [cx - int(35*s), foot_y - int(5*s), cx - int(8*s), foot_y + int(12*s)],
        fill=MINION_BLACK,
    )
    draw.ellipse(
        [cx + int(8*s), foot_y - int(5*s), cx + int(35*s), foot_y + int(12*s)],
        fill=MINION_BLACK,
    )


def add_scene_elements(draw, w, h, scene_type):
    """Add background scene elements."""
    if scene_type == "stars":
        for _ in range(30):
            x, y = random.randint(0, w), random.randint(0, h // 2)
            r = random.randint(1, 3)
            draw.ellipse([x-r, y-r, x+r, y+r], fill=(255, 255, 200))

    elif scene_type == "hearts":
        for _ in range(8):
            x, y = random.randint(50, w-50), random.randint(50, h-50)
            size = random.randint(10, 25)
            color = random.choice([(255, 150, 150), (255, 180, 200), (255, 120, 120)])
            # Simple heart shape with two circles and a triangle
            draw.ellipse([x - size, y - size, x, y], fill=color)
            draw.ellipse([x, y - size, x + size, y], fill=color)
            draw.polygon([(x - size, y - size//3), (x + size, y - size//3), (x, y + size)], fill=color)

    elif scene_type == "grass":
        for x in range(0, w, 8):
            gh = random.randint(20, 60)
            green = random.randint(80, 160)
            draw.line([x, h, x + random.randint(-5, 5), h - gh],
                     fill=(40, green, 30), width=2)

    elif scene_type == "confetti":
        for _ in range(40):
            x, y = random.randint(0, w), random.randint(0, h)
            size = random.randint(3, 8)
            color = random.choice([
                (255, 100, 100), (100, 200, 255), (255, 255, 100),
                (200, 100, 255), (100, 255, 150), (255, 180, 100),
            ])
            draw.rectangle([x, y, x + size, y + size * 2], fill=color)


def generate_image(idx):
    """Generate a single minion image."""
    # Random size (simulating different camera photos)
    w = random.choice([1200, 1400, 1600, 1800, 2000])
    h = random.choice([1200, 1400, 1600, 1800, 2000])

    bg_color = random.choice(BACKGROUNDS)
    img = Image.new("RGB", (w, h), bg_color)
    draw = ImageDraw.Draw(img)

    # Add scene elements
    scene = random.choice(["stars", "hearts", "grass", "confetti", "none", "none"])
    if scene != "none":
        add_scene_elements(draw, w, h, scene)

    # Draw 2 minions (to simulate couple photos with 2 "faces")
    num_minions = 2  # Always 2 for our couple filter
    moods = ["happy", "excited", "silly", "neutral"]

    if num_minions == 2:
        scale = random.uniform(0.9, 1.4)
        gap = int(random.uniform(120, 200) * scale)

        # Two minions side by side
        m1_x = w // 2 - gap // 2
        m2_x = w // 2 + gap // 2
        m_y = h // 2 + int(30 * scale)

        draw_minion(draw, m1_x, m_y, scale=scale,
                   mood=random.choice(moods), looking="right")
        draw_minion(draw, m2_x, m_y, scale=scale,
                   mood=random.choice(moods), looking="left")

    # Add a fun label at the bottom
    labels = [
        "Banana!", "BELLO!", "We're the best!", "Together forever!",
        "Minion Love", "Partners in crime", "Best friends", "La Boda!",
        "Papaya!", "Gelato!", "Adventure time!", "BFF",
        "Bee-do Bee-do!", "Le buddies", "Kompai!", "Poopaye!",
        "Muak muak!", "Tank yu!", "Me want banana!", "Bottom!",
    ]

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", int(28 * scale))
    except Exception:
        font = ImageFont.load_default()

    label = random.choice(labels)
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]

    # Label background
    label_y = h - int(80 * scale)
    draw.rounded_rectangle(
        [w//2 - tw//2 - 20, label_y - 10, w//2 + tw//2 + 20, label_y + bbox[3] - bbox[1] + 10],
        radius=15,
        fill=(255, 255, 255, 200),
        outline=MINION_YELLOW,
        width=2,
    )
    draw.text((w//2 - tw//2, label_y), label, fill=MINION_BLACK, font=font)

    # Save
    filename = OUTPUT_DIR / f"minion_{idx:03d}.jpg"
    img.save(filename, "JPEG", quality=92)
    return filename


if __name__ == "__main__":
    print("Generating 40 minion sample images...")
    for i in range(40):
        path = generate_image(i)
        print(f"  Created: {path}")
    print(f"\nDone! 40 images saved to {OUTPUT_DIR}/")
