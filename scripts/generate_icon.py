from __future__ import annotations

import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "pdf_manager.ico"


Color = tuple[int, int, int, int]


def _lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def _blend(dst: Color, src: Color) -> Color:
    sr, sg, sb, sa = src
    dr, dg, db, da = dst
    alpha = sa / 255.0
    out_a = int(sa + da * (1.0 - alpha))
    if out_a == 0:
        return (0, 0, 0, 0)
    return (
        int((sr * alpha + dr * (1.0 - alpha))),
        int((sg * alpha + dg * (1.0 - alpha))),
        int((sb * alpha + db * (1.0 - alpha))),
        out_a,
    )


def _rect(img: list[list[Color]], x0: int, y0: int, x1: int, y1: int, color: Color) -> None:
    h = len(img)
    w = len(img[0])
    for y in range(max(0, y0), min(h, y1)):
        for x in range(max(0, x0), min(w, x1)):
            img[y][x] = _blend(img[y][x], color)


def _circle(img: list[list[Color]], cx: float, cy: float, r: float, color: Color) -> None:
    h = len(img)
    w = len(img[0])
    rr = r * r
    for y in range(h):
        for x in range(w):
            if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= rr:
                img[y][x] = _blend(img[y][x], color)


def _line(img: list[list[Color]], x0: int, y0: int, x1: int, y1: int, color: Color, width: int) -> None:
    dx = x1 - x0
    dy = y1 - y0
    steps = max(abs(dx), abs(dy), 1)
    for i in range(steps + 1):
        t = i / steps
        x = int(x0 + dx * t)
        y = int(y0 + dy * t)
        _rect(img, x - width // 2, y - width // 2, x + width // 2 + 1, y + width // 2 + 1, color)


def _make_image(size: int) -> list[list[Color]]:
    img: list[list[Color]] = [[(0, 0, 0, 0) for _ in range(size)] for _ in range(size)]

    for y in range(size):
        t = y / max(size - 1, 1)
        bg = (_lerp(30, 54, t), _lerp(80, 122, t), _lerp(140, 198, t), 255)
        for x in range(size):
            img[y][x] = bg

    _circle(img, size * 0.68, size * 0.27, size * 0.28, (50, 132, 214, 210))
    _circle(img, size * 0.22, size * 0.76, size * 0.22, (39, 174, 96, 180))

    pad = int(size * 0.19)
    doc_x0 = int(size * 0.25)
    doc_y0 = int(size * 0.15)
    doc_x1 = int(size * 0.76)
    doc_y1 = int(size * 0.86)
    _rect(img, doc_x0 + 2, doc_y0 + 3, doc_x1 + 2, doc_y1 + 3, (0, 0, 0, 52))
    _rect(img, doc_x0, doc_y0, doc_x1, doc_y1, (255, 255, 255, 255))

    fold = int(size * 0.16)
    _rect(img, doc_x1 - fold, doc_y0, doc_x1, doc_y0 + fold, (218, 231, 246, 255))
    for i in range(fold):
        x = doc_x1 - fold + i
        y = doc_y0 + i
        _line(img, x, doc_y0, doc_x1, y, (190, 210, 233, 255), max(1, size // 48))

    red = (198, 48, 49, 255)
    band_y0 = int(size * 0.42)
    band_y1 = int(size * 0.62)
    _rect(img, doc_x0 - int(size * 0.06), band_y0, doc_x1 + int(size * 0.04), band_y1, red)

    if size >= 48:
        # Small block-letter PDF mark.
        text_y = band_y0 + int(size * 0.045)
        unit = max(1, size // 32)
        x = doc_x0 + int(size * 0.02)
        for offset, pattern in enumerate(("P", "D", "F")):
            ox = x + offset * int(size * 0.14)
            _rect(img, ox, text_y, ox + unit * 2, text_y + unit * 9, (255, 255, 255, 255))
            if pattern == "P":
                _rect(img, ox, text_y, ox + unit * 6, text_y + unit * 2, (255, 255, 255, 255))
                _rect(img, ox + unit * 5, text_y, ox + unit * 7, text_y + unit * 5, (255, 255, 255, 255))
                _rect(img, ox, text_y + unit * 4, ox + unit * 6, text_y + unit * 6, (255, 255, 255, 255))
            elif pattern == "D":
                _rect(img, ox, text_y, ox + unit * 6, text_y + unit * 2, (255, 255, 255, 255))
                _rect(img, ox + unit * 5, text_y + unit, ox + unit * 7, text_y + unit * 8, (255, 255, 255, 255))
                _rect(img, ox, text_y + unit * 7, ox + unit * 6, text_y + unit * 9, (255, 255, 255, 255))
            else:
                _rect(img, ox, text_y, ox + unit * 7, text_y + unit * 2, (255, 255, 255, 255))
                _rect(img, ox, text_y + unit * 4, ox + unit * 6, text_y + unit * 6, (255, 255, 255, 255))

    line_color = (38, 120, 198, 255)
    for i in range(3):
        y = int(size * (0.68 + i * 0.065))
        _line(img, doc_x0 + pad // 2, y, doc_x1 - pad // 2, y, line_color, max(1, size // 48))

    # Citation brackets.
    bracket_color = (39, 174, 96, 255)
    bx = int(size * 0.14)
    by = int(size * 0.70)
    bw = max(2, size // 18)
    bh = int(size * 0.18)
    _line(img, bx + bw, by, bx, by, bracket_color, max(2, size // 36))
    _line(img, bx, by, bx, by + bh, bracket_color, max(2, size // 36))
    _line(img, bx, by + bh, bx + bw, by + bh, bracket_color, max(2, size // 36))
    _line(img, size - bx - bw, by, size - bx, by, bracket_color, max(2, size // 36))
    _line(img, size - bx, by, size - bx, by + bh, bracket_color, max(2, size // 36))
    _line(img, size - bx - bw, by + bh, size - bx, by + bh, bracket_color, max(2, size // 36))

    return img


def _dib_from_rgba(img: list[list[Color]]) -> bytes:
    size = len(img)
    header = struct.pack(
        "<IIIHHIIIIII",
        40,
        size,
        size * 2,
        1,
        32,
        0,
        size * size * 4,
        0,
        0,
        0,
        0,
    )
    pixels = bytearray()
    for row in reversed(img):
        for r, g, b, a in row:
            pixels.extend((b, g, r, a))
    mask_stride = ((size + 31) // 32) * 4
    mask = bytes(mask_stride * size)
    return header + bytes(pixels) + mask


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [_dib_from_rgba(_make_image(size)) for size in sizes]

    header = struct.pack("<HHH", 0, 1, len(images))
    directory = bytearray()
    offset = 6 + 16 * len(images)
    payload = bytearray()
    for size, data in zip(sizes, images):
        directory.extend(
            struct.pack(
                "<BBBBHHII",
                0 if size == 256 else size,
                0 if size == 256 else size,
                0,
                0,
                1,
                32,
                len(data),
                offset,
            )
        )
        payload.extend(data)
        offset += len(data)
    OUT.write_bytes(header + bytes(directory) + bytes(payload))
    print(f"Generated {OUT}")


if __name__ == "__main__":
    main()
