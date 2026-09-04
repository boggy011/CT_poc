"""Generate PLACEHOLDER logo assets (no longer used: assets/ now holds the AB InBev logo). Kept for local experiments.

Run: uv run python scripts/make_logo.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path("assets")
COPPER = (180, 102, 31, 255)
COPPER_DARK = (138, 75, 18, 255)
INK = (30, 37, 48, 255)
MUTED = (91, 102, 117, 255)
WHITE = (255, 255, 255, 255)
CLEAR = (0, 0, 0, 0)
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
REGULAR = "/System/Library/Fonts/Supplemental/Arial.ttf"


def font(path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a TrueType font, falling back to Pillow's default."""
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default(size)


def keg_mark(size: int) -> Image.Image:
    """Copper rounded square with a white keg silhouette."""
    img = Image.new("RGBA", (size, size), CLEAR)
    d = ImageDraw.Draw(img)
    r = size * 0.18
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=r, fill=COPPER)
    x0, x1 = size * 0.30, size * 0.70
    y0, y1 = size * 0.20, size * 0.82
    d.rounded_rectangle((x0, y0, x1, y1), radius=size * 0.09, fill=WHITE)
    band = size * 0.035
    for yc in (y0 + (y1 - y0) * 0.30, y0 + (y1 - y0) * 0.70):
        d.rectangle((x0, yc - band / 2, x1, yc + band / 2), fill=COPPER)
    d.rounded_rectangle((size * 0.38, size * 0.14, size * 0.62, size * 0.22), radius=size * 0.03, fill=WHITE)
    d.ellipse((size * 0.46, size * 0.395, size * 0.54, size * 0.475), fill=COPPER_DARK)
    return img


def wordmark(text_color: tuple[int, int, int, int], sub_color: tuple[int, int, int, int]) -> Image.Image:
    """Mark plus the RetPack wordmark and a small sub-line, on a transparent 640x160 canvas."""
    w, h = 640, 160
    img = Image.new("RGBA", (w, h), CLEAR)
    mark = keg_mark(120)
    img.alpha_composite(mark, (10, 20))
    d = ImageDraw.Draw(img)
    d.text((150, 18), "RetPack", font=font(BOLD, 84), fill=text_color)
    x = 154
    small = font(REGULAR, 22)
    for ch in "ABI RETURNABLE PACKAGING":
        d.text((x, 112), ch, font=small, fill=sub_color)
        x += d.textlength(ch, font=small) + 3
    return img


def main() -> None:
    """Write the three placeholder assets."""
    ASSETS.mkdir(exist_ok=True)
    keg_mark(512).save(ASSETS / "logo_icon.png")
    wordmark(INK, MUTED).save(ASSETS / "logo.png")
    wordmark(WHITE, (200, 208, 220, 255)).save(ASSETS / "logo_on_dark.png")
    print("wrote", sorted(p.name for p in ASSETS.glob("*.png")))


if __name__ == "__main__":
    main()
