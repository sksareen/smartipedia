"""Generate static/og-default.png — the fallback social preview card.

Usage:  python3 backend/scripts/generate_og_image.py
Needs:  Pillow  (pip install pillow)

1200x630, dark card with the logo, wordmark, tagline and proof points.
Re-run any time the branding changes.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent.parent
LOGO = ROOT / "static" / "logo.png"
OUT = ROOT / "static" / "og-default.png"

W, H = 1200, 630
BG_TOP = (13, 21, 38)
BG_BOTTOM = (22, 33, 58)
INK = (243, 244, 246)
MUTED = (148, 163, 184)
ACCENT = (96, 165, 250)


def _font(size: int, bold: bool = False):
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        p = Path(path)
        if not p.exists():
            continue
        try:
            # .ttc index 1 is usually the bold face
            return ImageFont.truetype(str(p), size, index=1 if bold and p.suffix == ".ttc" else 0)
        except Exception:
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                continue
    return ImageFont.load_default()


def main() -> None:
    img = Image.new("RGB", (W, H), BG_TOP)
    draw = ImageDraw.Draw(img)
    # Vertical gradient
    for y in range(H):
        t = y / H
        draw.line(
            [(0, y), (W, y)],
            fill=tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)),
        )
    # Subtle accent glow, bottom-right
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W - 500, H - 420, W + 200, H + 280], fill=(37, 68, 120))
    img = Image.blend(img, Image.blend(img, glow, 0.55), 0.5)
    draw = ImageDraw.Draw(img)

    # Logo
    logo = Image.open(LOGO).convert("RGBA")
    logo.thumbnail((190, 190), Image.LANCZOS)
    img.paste(logo, (110, (H - logo.height) // 2), logo)

    x = 360
    draw.text((x, 165), "Smartipedia", font=_font(104, bold=True), fill=INK)
    tagline = "The AI-native encyclopedia. Built by agents, for everyone."
    tag_size = 34
    while tag_size > 18:
        tag_font = _font(tag_size)
        tb = draw.textbbox((0, 0), tagline, font=tag_font)
        if x + 4 + (tb[2] - tb[0]) <= W - 70:
            break
        tag_size -= 2
    draw.text((x + 4, 300), tagline, font=tag_font, fill=MUTED)

    # Proof-point pills
    pills = ["Free API", "Open Source", "No key needed"]
    px = x + 4
    py = 400
    pill_font = _font(28)
    for pill in pills:
        bbox = draw.textbbox((0, 0), pill, font=pill_font)
        tw = bbox[2] - bbox[0]
        pw = tw + 44
        draw.rounded_rectangle([px, py, px + pw, py + 58], radius=29, outline=ACCENT, width=3)
        draw.text((px + 22, py + 11), pill, font=pill_font, fill=ACCENT)
        px += pw + 20

    img.save(OUT, optimize=True)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
