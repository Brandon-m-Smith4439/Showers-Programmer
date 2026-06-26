#!/usr/bin/env python3
"""Create crisp Shower Programmer PNG/ICO assets.

The ICO is written with hand-rendered frames for each Windows icon size. That
keeps the taskbar icon readable instead of letting Windows shrink a detailed
1024px image into a blurry 16px/32px symbol.
"""

from __future__ import annotations

import io
import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "Assets"
PNG_PATH = ASSETS / "ShowersProgrammer.png"
ICO_PATH = ASSETS / "ShowersProgrammer.ico"
ICO_SIZES = (256, 128, 64, 48, 32, 24, 16)


def rounded_radius(size: int) -> int:
    return max(4, round(size * 0.20))


def scaled_points(points: list[tuple[float, float]], size: int) -> list[tuple[int, int]]:
    return [(round(x * size), round(y * size)) for x, y in points]


def draw_background(size: int, scale: int) -> Image.Image:
    canvas = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas, "RGBA")
    radius = rounded_radius(size) * scale
    inset = max(1, round(size * 0.045)) * scale
    rect = (inset, inset, size * scale - inset, size * scale - inset)

    top = (31, 126, 214, 255)
    bottom = (16, 74, 146, 255)
    for y in range(rect[1], rect[3]):
        t = (y - rect[1]) / max(1, rect[3] - rect[1])
        color = tuple(round(top[i] * (1 - t) + bottom[i] * t) for i in range(3)) + (255,)
        draw.line((rect[0], y, rect[2], y), fill=color)

    mask = Image.new("L", canvas.size, 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(rect, radius=radius, fill=255)
    shaped = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shaped.alpha_composite(canvas)
    shaped.putalpha(mask)

    border = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    border_draw = ImageDraw.Draw(border, "RGBA")
    border_draw.rounded_rectangle(rect, radius=radius, outline=(166, 218, 255, 210), width=max(1, round(size * 0.025)) * scale)
    shaped.alpha_composite(border)
    return shaped


def draw_glass_mark(size: int, scale: int) -> Image.Image:
    art = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(art, "RGBA")

    if size <= 32:
        outer = max(2, round(size * 0.13)) * scale
        inner = max(1, round(size * 0.055)) * scale
        pane = [
            (0.30, 0.70),
            (0.30, 0.38),
            (0.43, 0.27),
            (0.68, 0.22),
            (0.68, 0.36),
            (0.56, 0.45),
            (0.56, 0.70),
            (0.42, 0.78),
        ]
        pts = scaled_points(pane, size * scale)
        draw.line(pts + [pts[0]], fill=(0, 174, 255, 255), width=outer, joint="curve")
        draw.line(pts + [pts[0]], fill=(237, 252, 255, 255), width=inner, joint="curve")
        if size >= 24:
            right = [
                (0.52, 0.45),
                (0.75, 0.34),
                (0.75, 0.72),
                (0.52, 0.64),
            ]
            rpts = scaled_points(right, size * scale)
            draw.line(rpts + [rpts[0]], fill=(0, 174, 255, 255), width=outer, joint="curve")
            draw.line(rpts + [rpts[0]], fill=(237, 252, 255, 255), width=inner, joint="curve")
        if size >= 32:
            cut_pts = scaled_points([(0.58, 0.24), (0.69, 0.21), (0.69, 0.32), (0.65, 0.34)], size * scale)
            draw.line(cut_pts, fill=(237, 252, 255, 255), width=inner, joint="curve")
        return art

    # Simple, high-contrast panes. These proportions are intentionally bolder
    # than the full-size art so the taskbar icon reads as glass at 16-32px.
    left = [
        (0.25, 0.72),
        (0.25, 0.34),
        (0.35, 0.25),
        (0.69, 0.17),
        (0.69, 0.38),
        (0.54, 0.47),
        (0.54, 0.72),
        (0.39, 0.82),
    ]
    right = [
        (0.50, 0.45),
        (0.78, 0.31),
        (0.78, 0.77),
        (0.50, 0.68),
    ]
    center = [
        (0.46, 0.49),
        (0.54, 0.47),
        (0.54, 0.72),
        (0.46, 0.68),
    ]
    cut = [
        (0.58, 0.22),
        (0.70, 0.19),
        (0.70, 0.32),
        (0.66, 0.34),
        (0.66, 0.25),
        (0.60, 0.27),
    ]

    line_outer = max(2, round(size * 0.060)) * scale
    line_inner = max(1, round(size * 0.028)) * scale
    line_highlight = max(1, round(size * 0.014)) * scale

    if size >= 48:
        glow = Image.new("RGBA", art.size, (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow, "RGBA")
        for pane in (left, right, center):
            pts = scaled_points(pane, size * scale)
            glow_draw.line(pts + [pts[0]], fill=(19, 193, 255, 175), width=line_outer * 2, joint="curve")
        art.alpha_composite(glow.filter(ImageFilter.GaussianBlur(max(1, round(size * 0.025)) * scale)))

    for pane, fill in (
        (left, (156, 215, 255, 72)),
        (right, (156, 215, 255, 64)),
        (center, (86, 190, 255, 86)),
    ):
        pts = scaled_points(pane, size * scale)
        draw.polygon(pts, fill=fill)
        draw.line(pts + [pts[0]], fill=(0, 149, 255, 245), width=line_outer, joint="curve")
        draw.line(pts + [pts[0]], fill=(231, 250, 255, 245), width=line_inner, joint="curve")

    # A single bright diagonal/meeting-point line prevents the small icon from
    # becoming just a pale square.
    draw.line(
        scaled_points([(0.35, 0.25), (0.69, 0.17), (0.69, 0.38), (0.54, 0.47)], size * scale),
        fill=(255, 255, 255, 245),
        width=line_highlight,
        joint="curve",
    )
    draw.line(
        scaled_points([(0.39, 0.82), (0.54, 0.72), (0.50, 0.68), (0.78, 0.77)], size * scale),
        fill=(90, 226, 255, 245),
        width=max(1, round(size * 0.022)) * scale,
        joint="curve",
    )

    if size >= 32:
        cut_width = max(1, round(size * 0.036)) * scale
        cut_pts = scaled_points(cut, size * scale)
        draw.line(cut_pts, fill=(0, 177, 255, 245), width=cut_width * 2, joint="curve")
        draw.line(cut_pts, fill=(232, 252, 255, 245), width=cut_width, joint="curve")

    return art


def create_icon_frame(size: int) -> Image.Image:
    # Larger master frames get supersampled. Tiny frames are drawn directly with
    # simpler geometry to preserve sharp edges.
    scale = 4 if size >= 48 else 1
    frame = draw_background(size, scale)
    frame.alpha_composite(draw_glass_mark(size, scale))
    return frame.resize((size, size), Image.Resampling.LANCZOS)


def create_png_master() -> Image.Image:
    master = create_icon_frame(1024)
    return master


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def write_ico(path: Path, frames: dict[int, Image.Image]) -> None:
    entries: list[tuple[int, bytes]] = [(size, png_bytes(frames[size])) for size in ICO_SIZES]
    header_size = 6 + 16 * len(entries)
    offset = header_size
    directory = bytearray()
    chunks: list[bytes] = []

    for size, data in entries:
        width_byte = 0 if size >= 256 else size
        height_byte = 0 if size >= 256 else size
        directory.extend(
            struct.pack(
                "<BBBBHHII",
                width_byte,
                height_byte,
                0,
                0,
                1,
                32,
                len(data),
                offset,
            )
        )
        chunks.append(data)
        offset += len(data)

    with path.open("wb") as handle:
        handle.write(struct.pack("<HHH", 0, 1, len(entries)))
        handle.write(directory)
        for chunk in chunks:
            handle.write(chunk)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    PNG_PATH.write_bytes(png_bytes(create_png_master()))
    frames = {size: create_icon_frame(size) for size in ICO_SIZES}
    write_ico(ICO_PATH, frames)
    print(f"Wrote {PNG_PATH}")
    print(f"Wrote {ICO_PATH}")


if __name__ == "__main__":
    main()
