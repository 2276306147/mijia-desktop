"""生成应用图标（app.ico / app.png）。只需在改动设计时手动运行一次。

    python tools/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app" / "resources"

SCALE = 4  # 先画大图再缩放，边缘更干净
BASE = 256 * SCALE


def _gradient(size: int) -> Image.Image:
    top = (255, 138, 61)
    bottom = (255, 90, 0)
    image = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(image)
    for y in range(size):
        ratio = y / max(1, size - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
        draw.line([(0, y), (size, y)], fill=color)
    return image


def build() -> Image.Image:
    canvas = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    mask = Image.new("L", (BASE, BASE), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, BASE - 1, BASE - 1], radius=int(BASE * 0.22), fill=255)
    canvas.paste(_gradient(BASE), (0, 0), mask)

    draw = ImageDraw.Draw(canvas)
    white = (255, 255, 255, 255)

    # 屋顶
    draw.polygon(
        [(BASE * 0.5, BASE * 0.17), (BASE * 0.845, BASE * 0.47), (BASE * 0.155, BASE * 0.47)],
        fill=white,
    )
    # 房体
    draw.rounded_rectangle(
        [BASE * 0.245, BASE * 0.44, BASE * 0.755, BASE * 0.80],
        radius=int(BASE * 0.045),
        fill=white,
    )
    # 门（用橙色挖空）
    door_color = (255, 96, 0, 255)
    draw.rounded_rectangle(
        [BASE * 0.425, BASE * 0.56, BASE * 0.575, BASE * 0.80],
        radius=int(BASE * 0.02),
        fill=door_color,
    )
    # 门把手
    draw.ellipse(
        [BASE * 0.545, BASE * 0.665, BASE * 0.567, BASE * 0.687],
        fill=white,
    )
    return canvas


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    art = build()
    art.resize((512, 512), Image.LANCZOS).save(OUT / "app.png")
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    art.resize((256, 256), Image.LANCZOS).save(OUT / "app.ico", sizes=sizes)
    print("written:", OUT / "app.ico", OUT / "app.png")


if __name__ == "__main__":
    main()
