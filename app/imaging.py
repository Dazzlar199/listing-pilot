"""Deterministic image work: cut-out compositing and pixel-level image checks.

The models decide *what* the product is and where it is (SAM 3.1 mask).
This module guarantees the main image is measurably compliant: pure white
background, product fill ratio, size. Nothing here calls an API.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageFilter

WHITE = (255, 255, 255)


def load_rgb(path_or_img) -> Image.Image:
    img = path_or_img if isinstance(path_or_img, Image.Image) else Image.open(path_or_img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, WHITE)
        bg.paste(img, mask=img.split()[-1])
        return bg
    return img.convert("RGB")


def mask_bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def compose_on_white(photo: Image.Image, mask: np.ndarray, size: int = 2000, fill: float = 0.87,
                     feather: float = 1.2) -> Image.Image:
    """Cut the product out with its mask and place it centred on a pure-white square.

    `fill` is the share of the longer side the product occupies (Amazon asks for >= 85%).
    """
    photo = load_rgb(photo)
    bbox = mask_bbox(mask)
    if bbox is None:
        raise ValueError("empty mask: segmentation found no product")
    alpha = Image.fromarray((mask > 0).astype(np.uint8) * 255, "L")
    if feather:
        alpha = alpha.filter(ImageFilter.GaussianBlur(feather))
    rgba = photo.copy()
    rgba.putalpha(alpha)
    rgba = rgba.crop(bbox)

    w, h = rgba.size
    scale = (size * fill) / max(w, h)
    rgba = rgba.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    canvas = Image.new("RGB", (size, size), WHITE)
    x = (size - rgba.width) // 2
    y = (size - rgba.height) // 2
    canvas.paste(rgba, (x, y), rgba)
    return canvas


@dataclass
class ImageCheck:
    rule: str
    ok: bool
    detail: str
    value: float | int | str | None = None


@dataclass
class ImageReport:
    checks: list[ImageCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def failed(self) -> list[ImageCheck]:
        return [c for c in self.checks if not c.ok]


def foreground(img: Image.Image, tol: int = 8) -> np.ndarray:
    """Pixels that are not (near-)pure white."""
    a = np.asarray(load_rgb(img), dtype=np.int16)
    return (np.abs(a - 255) > tol).any(axis=2)


def check_main_image(img: Image.Image, rules: dict) -> ImageReport:
    img = load_rgb(img)
    a = np.asarray(img, dtype=np.uint8)
    r = ImageReport()
    w, h = img.size
    longest = max(w, h)

    r.checks.append(ImageCheck(
        "image.min_side", longest >= rules["min_longest_side_px"],
        f"longest side {longest}px (need >= {rules['min_longest_side_px']}px for zoom)", longest))
    r.checks.append(ImageCheck(
        "image.max_side", longest <= rules["max_longest_side_px"],
        f"longest side {longest}px (max {rules['max_longest_side_px']}px)", longest))

    # Background: the outer frame must be exactly RGB 255,255,255.
    band = max(4, longest // 100)
    frame = np.concatenate([a[:band].reshape(-1, 3), a[-band:].reshape(-1, 3),
                            a[:, :band].reshape(-1, 3), a[:, -band:].reshape(-1, 3)])
    pure = float((frame == 255).all(axis=1).mean())
    r.checks.append(ImageCheck(
        "image.white_background", pure >= rules["white_frame_share"],
        f"{pure:.1%} of the border is pure white RGB 255,255,255", round(pure, 4)))

    fg = foreground(img)
    bbox = mask_bbox(fg)
    if bbox is None:
        r.checks.append(ImageCheck("image.product_present", False, "no product pixels found", 0))
        return r
    bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    fill = max(bw / w, bh / h)
    r.checks.append(ImageCheck(
        "image.fill_ratio", fill >= rules["min_fill_ratio"],
        f"product spans {fill:.0%} of the frame (need >= {rules['min_fill_ratio']:.0%})", round(fill, 3)))
    touches = bbox[0] == 0 or bbox[1] == 0 or bbox[2] == w or bbox[3] == h
    r.checks.append(ImageCheck(
        "image.not_cropped", not touches,
        "product touches the edge (looks cropped)" if touches else "product fully in frame", None))
    return r
