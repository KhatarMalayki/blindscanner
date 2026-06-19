from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def generate_icon(size: int = 256) -> Image.Image:
    image = Image.new("RGBA", (size, size), (15, 23, 42, 255))
    draw = ImageDraw.Draw(image)

    pad = int(size * 0.1)
    body = [pad, pad, size - pad, size - pad]
    draw.rounded_rectangle(body, radius=int(size * 0.18), fill=(17, 24, 39, 255), outline=(56, 189, 248, 255), width=max(4, size // 64))

    glass_w = int(size * 0.42)
    glass_h = int(size * 0.32)
    glass_x = (size - glass_w) // 2
    glass_y = int(size * 0.2)
    draw.rounded_rectangle(
        [glass_x, glass_y, glass_x + glass_w, glass_y + glass_h],
        radius=int(size * 0.05),
        fill=(56, 189, 248, 220),
    )

    base_y = glass_y + glass_h + int(size * 0.08)
    draw.rectangle(
        [int(size * 0.22), base_y, int(size * 0.78), base_y + int(size * 0.12)],
        fill=(148, 163, 184, 255),
    )
    draw.rectangle(
        [int(size * 0.28), base_y + int(size * 0.14), int(size * 0.72), base_y + int(size * 0.36)],
        fill=(229, 231, 235, 255),
    )
    draw.rectangle(
        [int(size * 0.32), base_y + int(size * 0.22), int(size * 0.68), base_y + int(size * 0.26)],
        fill=(56, 189, 248, 255),
    )

    return image


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    assets_dir = root / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    image = generate_icon()
    png_path = assets_dir / "blindscanner.png"
    ico_path = assets_dir / "blindscanner.ico"
    image.save(png_path, format="PNG")
    image.save(ico_path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    main()
