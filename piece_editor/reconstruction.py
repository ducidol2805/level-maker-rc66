from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .domain import PaletteColor
from .solver import EMPTY


@dataclass(frozen=True, slots=True)
class ReconstructionSettings:
    target_width: int = 20
    max_height: int = 50
    depth: int = 1
    sample_mode: str = "nearest"
    simplification: int = 35
    palette_size: int | None = None
    preserve_silhouette: bool = True
    preserve_major_colors: bool = True


@dataclass(slots=True)
class ReconstructionResult:
    source: Image.Image
    normalized: Image.Image
    mask: np.ndarray

    def preview(self, palette: tuple[PaletteColor, ...], cell_size: int = 16) -> Image.Image:
        height, width = self.mask.shape
        pixels = np.zeros((height, width, 4), dtype=np.uint8)
        lookup = {color.id: _hex_to_rgb(color.rgb) for color in palette}
        for color_id, rgb in lookup.items():
            selected = self.mask == color_id
            pixels[selected, :3] = rgb
            pixels[selected, 3] = 255
        image = Image.fromarray(pixels, "RGBA")
        return image.resize((width * cell_size, height * cell_size), Image.Resampling.NEAREST)


def reconstruct_image(
    image_or_path: str | Path | Image.Image,
    palette: tuple[PaletteColor, ...],
    settings: ReconstructionSettings,
) -> ReconstructionResult:
    if settings.target_width <= 0 or settings.max_height <= 0:
        raise ValueError("Target dimensions must be positive")
    if not palette:
        raise ValueError("Palette cannot be empty")

    if isinstance(image_or_path, Image.Image):
        source = image_or_path.convert("RGBA")
    else:
        with Image.open(image_or_path) as opened:
            source = opened.convert("RGBA")

    rgba = np.asarray(source, dtype=np.uint8).copy()
    foreground = _foreground_mask(rgba, settings.simplification)
    if not np.any(foreground):
        raise ValueError("No foreground object could be separated from the image")

    rows, cols = np.where(foreground)
    top, bottom = int(rows.min()), int(rows.max()) + 1
    left, right = int(cols.min()), int(cols.max()) + 1
    cropped = rgba[top:bottom, left:right]
    cropped_foreground = foreground[top:bottom, left:right]

    output_width = settings.target_width
    output_height = max(1, round(cropped.shape[0] * output_width / cropped.shape[1]))
    if output_height > settings.max_height:
        scale = settings.max_height / output_height
        output_height = settings.max_height
        output_width = max(1, round(output_width * scale))

    resampling = _resampling_filter(settings.sample_mode)
    color_image = Image.fromarray(cropped, "RGBA").resize((output_width, output_height), resampling)
    alpha_image = Image.fromarray(cropped_foreground.astype(np.uint8) * 255, "L").resize(
        (output_width, output_height), resampling
    )
    resized_rgba = np.asarray(color_image, dtype=np.uint8).copy()
    resized_foreground = np.asarray(alpha_image, dtype=np.uint8) >= 128
    resized_rgba[..., 3] = np.where(resized_foreground, 255, 0)

    active_palette = _select_palette(resized_rgba, resized_foreground, palette, settings.palette_size)
    result_mask = _map_to_palette(resized_rgba[..., :3], resized_foreground, active_palette)
    result_mask = _simplify_mask(result_mask, settings)
    normalized = Image.fromarray(resized_rgba, "RGBA")
    return ReconstructionResult(source, normalized, result_mask)


def _foreground_mask(rgba: np.ndarray, simplification: int) -> np.ndarray:
    alpha = rgba[..., 3]
    if np.any(alpha < 250):
        return alpha >= max(24, min(224, 48 + simplification))

    rgb = rgba[..., :3].astype(np.float32)
    corners = np.array((rgb[0, 0], rgb[0, -1], rgb[-1, 0], rgb[-1, -1]))
    background = np.median(corners, axis=0)
    distance = np.sqrt(np.sum((rgb - background) ** 2, axis=2))
    tolerance = 18 + max(0, min(100, simplification)) * 0.7
    candidate_background = distance <= tolerance

    # Only erase background-colored pixels connected to an edge. This preserves
    # similarly colored details enclosed by the foreground object.
    height, width = candidate_background.shape
    outside = np.zeros_like(candidate_background)
    stack: list[tuple[int, int]] = []
    for x in range(width):
        stack.extend(((0, x), (height - 1, x)))
    for y in range(height):
        stack.extend(((y, 0), (y, width - 1)))
    while stack:
        row, col = stack.pop()
        if not (0 <= row < height and 0 <= col < width):
            continue
        if outside[row, col] or not candidate_background[row, col]:
            continue
        outside[row, col] = True
        stack.extend(((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)))
    return ~outside


def _map_to_palette(rgb: np.ndarray, foreground: np.ndarray, palette: tuple[PaletteColor, ...]) -> np.ndarray:
    mask = np.full(foreground.shape, EMPTY, dtype=np.int16)
    if not np.any(foreground):
        return mask
    source_lab = _rgb_to_lab(rgb[foreground].astype(np.float64) / 255.0)
    palette_rgb = np.array([_hex_to_rgb(color.rgb) for color in palette], dtype=np.float64) / 255.0
    palette_lab = _rgb_to_lab(palette_rgb)
    distances = np.sum((source_lab[:, None, :] - palette_lab[None, :, :]) ** 2, axis=2)
    nearest = np.argmin(distances, axis=1)
    ids = np.array([color.id for color in palette], dtype=np.int16)
    mask[foreground] = ids[nearest]
    return mask


def _select_palette(
    rgba: np.ndarray,
    foreground: np.ndarray,
    palette: tuple[PaletteColor, ...],
    palette_size: int | None,
) -> tuple[PaletteColor, ...]:
    if palette_size is None or palette_size >= len(palette):
        return palette
    size = max(1, palette_size)
    provisional = _map_to_palette(rgba[..., :3], foreground, palette)
    counts = [(int(np.sum(provisional == color.id)), color) for color in palette]
    counts.sort(key=lambda item: (-item[0], item[1].id))
    return tuple(color for _, color in counts[:size])


def _simplify_mask(mask: np.ndarray, settings: ReconstructionSettings) -> np.ndarray:
    strength = max(0, min(100, settings.simplification))
    if strength < 20:
        return mask
    result = mask.copy()
    passes = 1 if strength < 70 else 2
    for _ in range(passes):
        source = result.copy()
        for row in range(mask.shape[0]):
            for col in range(mask.shape[1]):
                value = int(source[row, col])
                neighbors = [
                    int(source[rr, cc])
                    for rr, cc in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1))
                    if 0 <= rr < mask.shape[0] and 0 <= cc < mask.shape[1]
                ]
                if value == EMPTY:
                    continue
                same = neighbors.count(value)
                occupied = [candidate for candidate in neighbors if candidate != EMPTY]
                if not settings.preserve_major_colors and same == 0 and occupied:
                    result[row, col] = max(set(occupied), key=occupied.count)
                if not settings.preserve_silhouette and strength >= 70 and not occupied:
                    result[row, col] = EMPTY
    return result


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _resampling_filter(sample_mode: str) -> Image.Resampling:
    filters = {
        "nearest": Image.Resampling.NEAREST,
        "bilinear": Image.Resampling.BILINEAR,
        "bicubic": Image.Resampling.BICUBIC,
        "lanczos": Image.Resampling.LANCZOS,
    }
    try:
        return filters[sample_mode.lower()]
    except KeyError as exc:
        raise ValueError(f"Unsupported sample mode: {sample_mode}") from exc


def _rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    xyz = linear @ np.array(
        [
            [0.4124564, 0.2126729, 0.0193339],
            [0.3575761, 0.7151522, 0.1191920],
            [0.1804375, 0.0721750, 0.9503041],
        ]
    )
    xyz = xyz / np.array([0.95047, 1.0, 1.08883])
    delta = 6 / 29
    f = np.where(xyz > delta**3, np.cbrt(xyz), xyz / (3 * delta**2) + 4 / 29)
    return np.stack((116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])), axis=-1)

