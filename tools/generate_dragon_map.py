"""Assemble the sitting dragon reference using the existing Racblox library."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from piece_editor.domain import DEFAULT_PALETTE, PieceInstance
from piece_editor.io import export_game, save_project
from piece_editor.library import PieceLibrary
from piece_editor.scene import EDITOR_BOUNDS, Scene


GREEN = 12
GOLD = 9
CREAM = 2
BLACK = 25


def build_dragon() -> Scene:
    """Y is up, +Z is the face, and the center plane is X=0."""
    library = PieceLibrary.load(ROOT / "library")
    if library.warnings:
        raise ValueError("\n".join(library.warnings))
    scene = Scene(library.pieces, EDITOR_BOUNDS)
    cells: dict[tuple[int, int, int], tuple[int, str]] = {}
    slopes: list[tuple[str, tuple[int, int, int], int, int, str]] = []

    def box(x0, x1, y0, y1, z0, z1, color, group):
        # Author one half, then mirror actual pieces to preserve the seams.
        for x in range(x0, x1):
            for y in range(y0, y1):
                for z in range(z0, z1):
                    cells[x, y, z] = (color, group)

    def slope(piece_id, x, y, z, rotation, color, group):
        definition = library.pieces[piece_id]
        _, size = definition.rotated_bounds(rotation)
        for dx in range(size[0]):
            for dy in range(size[1]):
                for dz in range(size[2]):
                    cells.pop((x + dx, y + dy, z + dz), None)
        slopes.append((piece_id, (x, y, z), rotation, color, group))

    # Seated rump, upright chest, and neck.
    box(0, 3, 1, 4, -3, 2, GREEN, "body")
    box(0, 2, 4, 6, -1, 3, GREEN, "neck")
    box(0, 2, 1, 4, 2, 3, GREEN, "chest")
    box(2, 3, 4, 5, -2, 2, GREEN, "shoulder")

    # Thick rear legs, planted feet, and two golden toes on each foot.
    box(2, 4, 0, 3, 0, 4, GREEN, "foot")
    box(2, 4, 2, 4, -2, 0, GREEN, "haunch")
    for x in (2, 3):
        box(x, x + 1, 0, 1, 4, 5, GOLD, f"toe_{x}")
    box(2, 3, 3, 5, 2, 4, GREEN, "arm")
    box(2, 3, 3, 4, 4, 5, GREEN, "hand")

    # A large head with black corner eyes, visible from front and side.
    box(0, 3, 6, 10, 0, 4, GREEN, "head")
    box(2, 3, 8, 9, 3, 4, BLACK, "eye")
    box(0, 2, 6, 8, 4, 6, GREEN, "muzzle")

    # Two swept horns; the ramp rises toward the back of the head.
    box(1, 2, 10, 11, 1, 3, GOLD, "horn")
    box(1, 2, 11, 12, 1, 2, GOLD, "horn")
    slope("rmp_001", 1, 11, 2, 90, GOLD, "horn")
    box(0, 1, 10, 11, 0, 1, GREEN, "head_ridge")
    slope("rmp_001", 0, 10, 1, 90, GREEN, "head_ridge")

    # A green dorsal ridge and a low tapering tail behind the body.
    box(0, 1, 5, 6, -2, 0, GREEN, "ridge")
    box(0, 1, 4, 5, -3, -1, GREEN, "ridge")
    for y in (7, 8):
        box(0, 1, y, y + 1, -1, 0, GOLD, f"back_spine_{y}")
    box(0, 1, 1, 3, -5, -3, GREEN, "tail_base")
    box(0, 1, 1, 2, -7, -5, GREEN, "tail_tip")
    slope("rmp_002", 0, 2, -5, 270, GREEN, "tail_slope")

    # Wings fan outward from the shoulder with a bent upper edge.
    box(3, 4, 4, 6, -2, 0, GOLD, "wing_root")
    slope("rmp_001", 3, 6, -2, 0, GOLD, "wing_root")
    slope("rmp_001", 3, 6, -1, 0, GOLD, "wing_root")
    box(4, 5, 4, 7, -3, -1, GOLD, "wing_finger")
    box(4, 5, 7, 8, -3, -1, GOLD, "wing_elbow")
    box(5, 6, 5, 7, -4, -2, GOLD, "wing_membrane")
    box(6, 7, 5, 6, -5, -3, GOLD, "wing_tip")
    slope("rmp_001", 5, 7, -4, 180, GOLD, "wing_upper")
    slope("rmp_001", 5, 7, -3, 180, GOLD, "wing_upper")
    slope("rmp_001", 6, 6, -5, 180, GOLD, "wing_upper")
    slope("rmp_001", 6, 6, -4, 180, GOLD, "wing_upper")

    def add(piece_id, minimum, rotation, color, group):
        offset, _ = library.pieces[piece_id].rotated_bounds(rotation)
        position = tuple(minimum[i] - offset[i] for i in range(3))
        instance = PieceInstance(
            piece_id=piece_id,
            position=position,
            rotation=rotation,
            color_id=color,
            group_id=group,
            instance_id=f"dragon_{len(scene.pieces) + 1:04d}",
        )
        scene.validate_reference_bounds(instance)
        scene.add(instance)

    def add_pair(piece_id, minimum, rotation, color, group):
        definition = library.pieces[piece_id]
        size = definition.rotated_size(rotation)
        for side, x, angle in (
            ("right", minimum[0], rotation),
            ("left", -minimum[0] - size[0], (180 - rotation) % 360),
        ):
            anchor = (x, minimum[1], minimum[2])
            add(piece_id, anchor, angle, color, f"{side}_{group}")

    for args in slopes:
        add_pair(*args)

    # Use real library blocks, choosing larger pieces before single cubes.
    candidates = []
    for definition in library.pieces.values():
        if definition.category not in {"Blocks", "Tall Blocks"}:
            continue
        for rotation in (0, 90):
            size = definition.rotated_size(rotation)
            candidates.append((definition.volume, definition.id, rotation, size))
    candidates.sort(key=lambda item: (-item[0], item[2], item[1]))

    while cells:
        minimum = min(cells, key=lambda p: (p[1], p[2], p[0]))
        color, group = cells[minimum]
        for _, piece_id, rotation, size in candidates:
            occupied = [
                (minimum[0] + dx, minimum[1] + dy, minimum[2] + dz)
                for dx in range(size[0])
                for dy in range(size[1])
                for dz in range(size[2])
            ]
            if all(cells.get(cell) == (color, group) for cell in occupied):
                add_pair(piece_id, minimum, rotation, color, group)
                for cell in occupied:
                    del cells[cell]
                break
        else:
            raise ValueError(f"Cannot fill {minimum}")

    # Continuous belly plates avoid a distracting vertical center seam.
    for y in range(1, 6):
        add("blk_004", (-2, y, 3), 90, CREAM, f"belly_{y}")

    return scene


def main() -> None:
    scene = build_dragon()
    destination = ROOT / "maps"
    destination.mkdir(exist_ok=True)
    project_path = destination / "dragon.piece-project.json"
    game_path = destination / "dragon.game.json"
    save_project(project_path, scene, DEFAULT_PALETTE, Path("../library"))
    export_game(game_path, scene.pieces)
    print(f"Created {len(scene.pieces)} pieces; bounds: {scene.occupied_bounds}")
    print(f"Colors: {dict(Counter(p.color_id for p in scene.pieces))}")
    print(project_path)
    print(game_path)


if __name__ == "__main__":
    main()
