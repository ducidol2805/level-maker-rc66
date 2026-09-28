from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from piece_editor.domain import DEFAULT_PALETTE
from piece_editor.reconstruction import ReconstructionSettings, reconstruct_image
from piece_editor.solver import EMPTY


def test_reconstruction_crops_background_and_uses_palette() -> None:
    image = Image.new("RGB", (40, 30), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 5, 29, 24), fill="#E84A45")
    settings = ReconstructionSettings(target_width=10, max_height=20, simplification=20)

    result = reconstruct_image(image, DEFAULT_PALETTE, settings)

    assert result.mask.shape == (10, 10)
    assert np.all(result.mask != EMPTY)
    assert set(np.unique(result.mask)) == {8}


def test_transparent_image_keeps_only_opaque_shape() -> None:
    pixels = np.zeros((8, 8, 4), dtype=np.uint8)
    pixels[2:6, 1:7] = (52, 136, 217, 255)
    image = Image.fromarray(pixels, "RGBA")

    result = reconstruct_image(image, DEFAULT_PALETTE, ReconstructionSettings(target_width=6, max_height=10))

    assert result.mask.shape == (4, 6)
    assert np.all(result.mask == 17)


def test_nearest_neighbor_is_the_default_sample_mode() -> None:
    pixels = np.zeros((3, 4, 4), dtype=np.uint8)
    pixels[1, 1] = (228, 59, 68, 255)
    pixels[1, 2] = (0, 153, 219, 255)
    image = Image.fromarray(pixels, "RGBA")
    settings = ReconstructionSettings(target_width=4, max_height=4, simplification=0)

    result = reconstruct_image(image, DEFAULT_PALETTE, settings)

    normalized = np.asarray(result.normalized)
    assert settings.sample_mode == "nearest"
    assert result.mask.shape == (2, 4)
    assert np.all(normalized[:, :2, :3] == (228, 59, 68))
    assert np.all(normalized[:, 2:, :3] == (0, 153, 219))

