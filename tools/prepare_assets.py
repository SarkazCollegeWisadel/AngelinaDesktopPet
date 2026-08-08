from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageSequence


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "source"
OUTPUT = ROOT / "assets" / "processed"


def remove_green_key(image: Image.Image) -> Image.Image:
    """Remove the deliberately bright chroma-green while preserving painted greens."""
    rgba = np.array(image.convert("RGBA"), dtype=np.uint8, copy=True)
    rgb = rgba[:, :, :3].astype(np.int32)
    key = np.array([0, 255, 0], dtype=np.int32)
    distance = np.sqrt(np.sum((rgb - key) ** 2, axis=2))

    # The source GIFs use a nearly pure #00ff00 rectangle. A soft band keeps
    # antialiased character edges clean without eating muted green props.
    matte = np.clip((distance - 42.0) / (132.0 - 42.0), 0.0, 1.0)
    original_alpha = rgba[:, :, 3].astype(np.float32) / 255.0
    rgba[:, :, 3] = np.rint(original_alpha * matte * 255.0).astype(np.uint8)

    fringe = (matte < 1.0) & (matte > 0.0)
    if np.any(fringe):
        rb_max = np.maximum(rgba[:, :, 0], rgba[:, :, 2])
        rgba[:, :, 1][fringe] = np.minimum(rgba[:, :, 1][fringe], rb_max[fringe] + 12)
    rgba[:, :, :3][rgba[:, :, 3] == 0] = 0
    return Image.fromarray(rgba)


def alpha_bbox(images: list[Image.Image]) -> tuple[int, int, int, int]:
    boxes = [im.getchannel("A").getbbox() for im in images]
    boxes = [box for box in boxes if box]
    if not boxes:
        return (0, 0, images[0].width, images[0].height)
    left = min(box[0] for box in boxes)
    top = min(box[1] for box in boxes)
    right = max(box[2] for box in boxes)
    bottom = max(box[3] for box in boxes)
    pad = max(8, round(max(right - left, bottom - top) * 0.018))
    return (
        max(0, left - pad),
        max(0, top - pad),
        min(images[0].width, right + pad),
        min(images[0].height, bottom + pad),
    )


def save_static(source: Path, name: str) -> dict[str, object]:
    image = Image.open(source).convert("RGBA")
    pixels = np.array(image, dtype=np.uint8, copy=True)
    if name == "办公":
        red = pixels[:, :, 0].astype(np.int16)
        green = pixels[:, :, 1].astype(np.int16)
        blue = pixels[:, :, 2].astype(np.int16)
        alpha = pixels[:, :, 3]
        leftover_key = (alpha < 170) & (green > red + 10) & (green > blue + 20)
        leftover_key |= (
            (alpha < 160)
            & (red > 80)
            & (green > 80)
            & (blue < 90)
            & (np.abs(red - green) < 45)
        )
        leftover_key |= alpha < 16
        pixels[:, :, 3][leftover_key] = 0
    pixels[:, :, :3][pixels[:, :, 3] == 0] = 0
    image = Image.fromarray(pixels)
    box = alpha_bbox([image])
    cropped = image.crop(box)
    target = OUTPUT / "static" / f"{name}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(target, optimize=True)
    return {
        "kind": "static",
        "path": target.relative_to(OUTPUT).as_posix(),
        "width": cropped.width,
        "height": cropped.height,
    }


def save_animation(source: Path, name: str) -> dict[str, object]:
    opened = Image.open(source)
    frames: list[Image.Image] = []
    durations: list[int] = []
    for source_frame in ImageSequence.Iterator(opened):
        frames.append(remove_green_key(source_frame))
        durations.append(max(40, int(source_frame.info.get("duration", opened.info.get("duration", 100)))))
    box = alpha_bbox(frames)
    frame_dir = OUTPUT / "animations" / name
    frame_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for index, frame in enumerate(frames):
        target = frame_dir / f"{index:02d}.png"
        frame.crop(box).save(target, optimize=True)
        paths.append(target.relative_to(OUTPUT).as_posix())
    return {
        "kind": "animation",
        "frames": paths,
        "durations": durations,
        "width": box[2] - box[0],
        "height": box[3] - box[1],
    }


def validate_alpha(path: Path) -> None:
    image = Image.open(path).convert("RGBA")
    alpha = np.asarray(image.getchannel("A"))
    if alpha.min() != 0:
        raise RuntimeError(f"{path.name} 没有透明像素")
    corners = (alpha[0, 0], alpha[0, -1], alpha[-1, 0], alpha[-1, -1])
    if any(int(value) > 8 for value in corners):
        raise RuntimeError(f"{path.name} 的角落不透明: {corners}")


def main() -> None:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
    manifest: dict[str, dict[str, object]] = {}

    for path in sorted((SOURCE / "PNG").glob("*.png")):
        manifest[path.stem] = save_static(path, path.stem)
    for path in sorted((SOURCE / "GIF").glob("*.gif")):
        clip = save_animation(path, path.stem)
        manifest[path.stem]["animation"] = clip

    office = SOURCE / "generated" / "office.png"
    validate_alpha(office)
    manifest["办公"] = save_static(office, "办公")

    icon_source = Image.open(SOURCE / "PNG" / "坐坐.png").convert("RGBA")
    icon_source.thumbnail((256, 256), Image.Resampling.LANCZOS)
    icon_source.save(OUTPUT / "angelina.ico", sizes=[(32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    (OUTPUT / "manifest.json").write_text(
        json.dumps({"version": 1, "scenes": manifest}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Prepared {len(manifest)} scenes in {OUTPUT}")


if __name__ == "__main__":
    main()
