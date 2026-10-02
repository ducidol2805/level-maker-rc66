"""Render a saved project with the same meshes and PBR shader as the editor."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import moderngl
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from piece_editor.domain import PaletteColor, PieceInstance
from piece_editor.io import load_project_data
from piece_editor.library import PieceLibrary
from piece_editor.renderer3d import ModernGLSceneRenderer
from piece_editor.scene import Scene


def render_preview(project_path: Path, output_path: Path) -> None:
    data = load_project_data(project_path)
    library_path = project_path.parent / str(data["library"])
    library = PieceLibrary.load(library_path)
    scene = Scene(
        library.pieces,
        tuple(data["bounds"]),
        [PieceInstance.from_dict(item) for item in data["pieces"]],
    )
    palette = tuple(PaletteColor.from_dict(item) for item in data["palette"])
    if scene.occupied_bounds is None:
        raise ValueError("Cannot preview an empty map")

    context = moderngl.create_standalone_context(require=330)
    renderer = ModernGLSceneRenderer()
    # Keep the preview clean; map geometry and shading are unchanged.
    renderer._ensure_grid = lambda _scene: None
    renderer.projection_mode = "orthographic"
    size = 1000
    framebuffer = context.simple_framebuffer((size, size))
    renderer.resize(size, size)
    low, high = (np.asarray(v, dtype=np.float32) for v in scene.occupied_bounds)
    center = (low + high) * 0.5
    distance = float(max(high - low) * 1.28)
    panels = []

    for label, yaw, pitch in (
        ("TOP", 0, 89.99),
        ("FRONT", 0, 0),
        ("SIDE", 90, 0),
        ("PERSPECTIVE", 42, 24),
    ):
        renderer.camera.target = center.copy()
        renderer.camera.yaw = yaw
        renderer.camera.pitch = pitch
        renderer.projection_mode = "perspective" if label == "PERSPECTIVE" else "orthographic"
        renderer.camera.distance = distance * (1.40 if label == "PERSPECTIVE" else 1.0)
        renderer.render(scene, palette, set(), framebuffer.glo)
        pixels = framebuffer.read(components=3, alignment=1)
        panel = Image.frombytes("RGB", (size, size), pixels).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        panel = panel.resize((700, 700), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(panel)
        try:
            font = ImageFont.truetype("segoeui.ttf", 19)
        except OSError:
            font = ImageFont.load_default()
        draw.text((24, 20), label, font=font, fill="#B4C0CE")
        panels.append(panel)

    sheet = Image.new("RGB", (1402, 1402), "#414956")
    for panel, position in zip(panels, ((0, 0), (702, 0), (0, 702), (702, 702))):
        sheet.paste(panel, position)
    sheet.save(output_path)
    print(f"Preview: {output_path}")
    print(f"Rendered {len(scene.pieces)} pieces with {renderer.stats.cached_objects} mesh batches")
    framebuffer.release()
    context.release()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.project.with_name(args.project.name.replace(".piece-project.json", "-preview.png"))
    render_preview(args.project.resolve(), output.resolve())


if __name__ == "__main__":
    main()
