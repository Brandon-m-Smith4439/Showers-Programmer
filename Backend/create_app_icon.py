#!/usr/bin/env python3
"""Create the Shower Programmer Windows icon asset."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "Assets"
SOURCE_IMAGE = ROOT / "Shower Programmer Icon.png"
PNG_PATH = ASSETS / "ShowersProgrammer.png"
ICO_PATH = ASSETS / "ShowersProgrammer.ico"


def draw_panel(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], fill: tuple[int, int, int, int]) -> None:
    draw.polygon(points, fill=fill)
    draw.line(points + [points[0]], fill=(185, 221, 255, 230), width=6, joint="curve")


def create_icon() -> Image.Image:
    size = 1024
    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bg = Image.new("RGBA", (size, size), (8, 14, 24, 255))
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((24, 24, 1000, 1000), radius=210, fill=255)
    base.alpha_composite(Image.composite(bg, Image.new("RGBA", (size, size), (0, 0, 0, 0)), mask))

    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_lines = [
        ((360, 710), (650, 882)),
        ((360, 350), (662, 150)),
        ((512, 720), (512, 456)),
        ((612, 520), (790, 632)),
    ]
    for start, end in glow_lines:
        glow_draw.line((start, end), fill=(28, 165, 255, 210), width=16)
    base.alpha_composite(glow.filter(ImageFilter.GaussianBlur(12)))

    panel_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    panel_draw = ImageDraw.Draw(panel_layer)
    left_panel = [(342, 748), (342, 382), (374, 338), (650, 154), (650, 340), (512, 438), (512, 662)]
    right_panel = [(612, 520), (792, 400), (792, 860), (610, 748)]
    center_panel = [(512, 438), (610, 520), (610, 748), (512, 662)]
    draw_panel(panel_draw, left_panel, (92, 126, 160, 112))
    draw_panel(panel_draw, right_panel, (80, 118, 152, 95))
    draw_panel(panel_draw, center_panel, (48, 84, 118, 72))
    base.alpha_composite(panel_layer)

    shine = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shine_draw = ImageDraw.Draw(shine)
    shine_draw.line((368, 346, 650, 158), fill=(88, 192, 255, 255), width=8)
    shine_draw.line((370, 748, 514, 666), fill=(42, 173, 255, 255), width=8)
    shine_draw.line((512, 662, 792, 860), fill=(50, 178, 255, 255), width=8)
    base.alpha_composite(shine.filter(ImageFilter.GaussianBlur(2)))

    return base


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    if SOURCE_IMAGE.exists():
        icon = Image.open(SOURCE_IMAGE).convert("RGBA")
    else:
        icon = create_icon()
    icon.save(PNG_PATH)
    icon.save(ICO_PATH, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)])
    print(f"Wrote {ICO_PATH}")


if __name__ == "__main__":
    main()
