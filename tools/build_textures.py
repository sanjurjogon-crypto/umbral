from __future__ import annotations

import math
import random
import zlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "umbral" / "assets"
SCENES = ASSETS / "scenes"
OUT = ASSETS / "themes"

WIDTH, HEIGHT = 1920, 1080

TINTS = {
    "souls": (201, 164, 95),
    "zelda": (127, 210, 166),
    "elden": (227, 193, 101),
    "metro": (201, 180, 88),
    "layton": (47, 93, 138),
    "tlou": (168, 176, 106),
    "mario": (224, 69, 47),
    "halo": (121, 194, 216),
    "doom": (224, 81, 42),
    "hollow": (207, 227, 242),
}


def style_seed(style: str) -> int:
    return zlib.crc32(style.encode("utf-8"))


def source_for(style: str) -> Path | None:
    single = SCENES / f"{style}.jpg"
    if single.exists():
        return single
    nested = SCENES / style / "library_hero.jpg"
    if nested.exists():
        return nested
    return None


def logo_for(style: str) -> Path | None:
    nested = SCENES / style / "logo_2x.png"
    return nested if nested.exists() else None


def cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(image, size, method=Image.LANCZOS, centering=(0.5, 0.45))


def grain(size: tuple[int, int], seed: int) -> Image.Image:
    rng = random.Random(seed)
    small = Image.new("L", (max(1, size[0] // 3), max(1, size[1] // 3)))
    small.putdata([rng.randint(0, 255) for _ in range(small.width * small.height)])
    small = small.resize(size, Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.1))
    layer = Image.new("RGBA", size, (255, 255, 255, 0))
    layer.putalpha(small.point(lambda value: int(abs(value - 128) * 0.35)))
    return layer


def vignette(size: tuple[int, int], strength: int) -> Image.Image:
    width, height = size
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    steps = 60
    for step in range(steps):
        ratio = step / steps
        inset_x = int(width * 0.5 * ratio)
        inset_y = int(height * 0.5 * ratio)
        alpha = int(strength * (ratio ** 2))
        draw.rectangle(
            [inset_x, inset_y, width - inset_x, height - inset_y],
            outline=alpha,
            width=max(2, width // (steps * 2)),
        )
    mask = mask.filter(ImageFilter.GaussianBlur(width // 30))
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    layer.putalpha(mask)
    return layer


def texture(style: str, size: tuple[int, int]) -> Image.Image:
    width, height = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    tint = TINTS[style]
    rng = random.Random(style_seed(style))

    if style in {"souls", "elden"}:
        for _ in range(260):
            x = rng.randint(0, width)
            y = rng.randint(0, height)
            length = rng.randint(40, 260)
            alpha = rng.randint(10, 30)
            draw.line([(x, y), (x + rng.randint(-8, 8), y + length)], fill=(*tint, alpha), width=1)
    elif style == "metro":
        for x in range(0, width, 48):
            draw.line([(x, 0), (x, height)], fill=(*tint, 9), width=1)
        for y in range(0, height, 48):
            draw.line([(0, y), (width, y)], fill=(*tint, 7), width=1)
    elif style == "halo":
        for y in range(0, height, 6):
            draw.line([(0, y), (width, y)], fill=(*tint, 12), width=1)
    elif style == "mario":
        for row, y in enumerate(range(0, height, 80)):
            for x in range(-80, width, 160):
                offset = 80 if row % 2 else 0
                draw.rectangle(
                    [x + offset + 4, y + 4, x + offset + 76, y + 76],
                    outline=(*tint, 20),
                    width=3,
                )
    elif style == "layton":
        for y in range(0, height, 56):
            draw.line([(0, y), (width, y)], fill=(*tint, 14), width=2)
        for x in range(0, width, 56):
            draw.line([(x, 0), (x, height)], fill=(*tint, 9), width=1)
    elif style == "doom":
        for _ in range(140):
            x = rng.randint(0, width)
            y = rng.randint(0, height)
            radius = rng.randint(24, 110)
            draw.arc(
                [x - radius, y - radius, x + radius, y + radius],
                0,
                360,
                fill=(*tint, 16),
                width=2,
            )
    elif style == "hollow":
        for _ in range(240):
            x = rng.randint(0, width)
            y = rng.randint(0, height)
            radius = rng.randint(2, 7)
            draw.ellipse([x, y, x + radius, y + radius], fill=(*tint, rng.randint(14, 40)))
    elif style == "zelda":
        for _ in range(30):
            x = rng.randint(0, width)
            y = rng.randint(0, height)
            radius = rng.randint(140, 360)
            draw.arc(
                [x - radius, y - radius, x + radius, y + radius],
                rng.randint(0, 180),
                rng.randint(180, 360),
                fill=(*tint, 14),
                width=2,
            )
    elif style == "tlou":
        for _ in range(420):
            x = rng.randint(0, width)
            y = rng.randint(0, height)
            length = rng.randint(8, 28)
            angle = rng.uniform(-0.6, 0.6)
            draw.line(
                [(x, y), (x + math.cos(angle) * length, y + math.sin(angle) * length)],
                fill=(*tint, rng.randint(8, 26)),
                width=1,
            )
    return layer


def build(style: str) -> bool:
    source_path = source_for(style)
    if source_path is None:
        return False
    source = Image.open(source_path).convert("RGB")
    base = cover(source, (WIDTH, HEIGHT))

    gray = base.convert("L")
    mean = sum(gray.getdata()) / (gray.width * gray.height)
    if mean < 105:
        boost = min(1.9, 1.0 + (105 - mean) / 105)
        base = ImageEnhance.Brightness(base).enhance(boost)
        base = ImageEnhance.Contrast(base).enhance(0.96)
    print("  luminance", round(mean, 1), "boost", round(boost if mean < 105 else 1.0, 2))

    far = base.filter(ImageFilter.GaussianBlur(16))
    far = far.resize((WIDTH // 4, HEIGHT // 4), Image.BILINEAR).resize((WIDTH, HEIGHT), Image.BILINEAR)
    far = Image.blend(base, far, 0.5)

    tint = Image.new("RGB", (WIDTH, HEIGHT), tuple(int(channel * 0.16) for channel in TINTS[style]))
    far = Image.blend(far, tint, 0.4)

    canvas = far.convert("RGBA")
    canvas = Image.alpha_composite(canvas, texture(style, (WIDTH, HEIGHT)))
    canvas = Image.alpha_composite(canvas, grain((WIDTH, HEIGHT), style_seed(style)))
    canvas = Image.alpha_composite(canvas, vignette((WIDTH, HEIGHT), 170))

    frame = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(frame)
    draw.rectangle([10, 10, WIDTH - 11, HEIGHT - 11], outline=(*TINTS[style], 70), width=3)
    draw.rectangle([26, 26, WIDTH - 27, HEIGHT - 27], outline=(*TINTS[style], 26), width=1)
    canvas = Image.alpha_composite(canvas, frame)

    logo_path = logo_for(style)
    if logo_path is not None:
        logo = Image.open(logo_path).convert("RGBA")
        ratio = 520 / logo.width
        logo = logo.resize((520, max(1, int(logo.height * ratio))), Image.LANCZOS)
        alpha = logo.split()[3].point(lambda value: int(value * 0.5))
        logo.putalpha(alpha)
        canvas.alpha_composite(logo, (WIDTH - logo.width - 70, 70))

    OUT.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(OUT / f"{style}.jpg", quality=90, optimize=True)
    return True


def main() -> None:
    for style in TINTS:
        built = build(style)
        print("built" if built else "missing", style)


if __name__ == "__main__":
    main()
