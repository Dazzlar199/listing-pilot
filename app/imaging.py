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


def fill_enclosed_holes(photo: Image.Image, mask: np.ndarray, see_through_dist: float = 90.0) -> tuple[np.ndarray, dict]:
    """SAM often leaves enclosed parts out (a label, the wax in a jar, coffee in a cup).

    Fill every hole fully enclosed by the mask, except holes whose colour matches the
    background just outside the product: those are real openings (a mug handle).
    """
    from scipy import ndimage

    m = mask.astype(bool)
    # SAM may leave out a part that reaches the product's edge (a wrap-around label), so the gap is
    # not enclosed. Seal narrow gaps with a closing first; whatever that adds is judged like any hole.
    bb = mask_bbox(mask)
    r = max(3, int(0.03 * max(bb[2] - bb[0], bb[3] - bb[1]))) if bb else 3
    padded = np.pad(m, r)
    sealed = ndimage.binary_closing(padded, iterations=r)[r:-r, r:-r] | m
    holes = ndimage.binary_fill_holes(sealed) & ~m
    labels, n = ndimage.label(holes)
    if n == 0:
        return mask, {"filled": 0, "kept_open": 0}
    a = np.asarray(load_rgb(photo), dtype=np.float32)
    outside = ~ndimage.binary_dilation(m, iterations=6)
    H, W = m.shape
    out = m.copy()
    filled = kept = 0
    min_px = max(50, m.sum() // 2000)
    for i in range(1, n + 1):
        region = labels == i
        if region.sum() < min_px:          # pin-holes: always fill
            out |= region
            continue
        # Compare with the background right next to this hole (a window twice its size).
        ys, xs = np.nonzero(region)
        hy, hx = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
        win = np.zeros_like(m)
        win[max(0, ys.min() - hy):min(H, ys.max() + hy), max(0, xs.min() - hx):min(W, xs.max() + hx)] = True
        near = a[win & outside]
        if len(near) < 30:
            out |= region
            filled += 1
            continue
        hole = np.median(a[region], axis=0)
        dist = float(np.linalg.norm(hole - np.median(near, axis=0)))
        # A real opening looks like the background, and more like it than like the product around it.
        # On plain studio backgrounds a white label or pale wax is also close to the background colour,
        # but it matches the product ring around it better, so it is filled.
        ring = ndimage.binary_dilation(region, iterations=5) & m
        ring_dist = float(np.linalg.norm(hole - np.median(a[ring], axis=0))) if ring.sum() >= 30 else 1e9
        if dist < see_through_dist and dist + 25 < ring_dist:
            kept += 1
        else:
            out |= region
            filled += 1
    return out.astype(np.uint8), {"filled": filled, "kept_open": kept}


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
