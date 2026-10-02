from __future__ import annotations

from pathlib import Path
import sys

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from piece_editor.domain import DEFAULT_PALETTE, PieceInstance
from piece_editor.io import export_game, save_project
from piece_editor.library import PieceLibrary
from piece_editor.scene import EDITOR_BOUNDS, Scene


LIBRARY_PATH = ROOT / "library"
PROJECT_PATH = ROOT / "maps" / "robot.piece-project.json"
GAME_PATH = ROOT / "maps" / "robot.game.json"
PREVIEW_PATH = ROOT / "maps" / "robot-preview.png"

RED = 8
YELLOW = 11
WHITE = 19
LIGHT_GREY = 20
GREY = 21
BLUE = 17
DARK_BLUE = 16
DARK = 24
BLACK = 25


def build_robot() -> Scene:
    library = PieceLibrary.load(LIBRARY_PATH)
    scene = Scene(library.pieces, EDITOR_BOUNDS)
    sequence = 0

    def add(
        piece_id: str,
        x: int,
        y: int,
        z: int,
        color: int,
        group: str,
        rotation: int = 0,
    ) -> None:
        nonlocal sequence
        sequence += 1
        instance = PieceInstance(
            piece_id=piece_id,
            position=(x, y, z),
            rotation=rotation,
            color_id=color,
            group_id=group,
            instance_id=f"robot_{sequence:03d}",
        )
        scene.validate_reference_bounds(instance)
        scene.add(instance)

    # Feet: deep blue soles, red insteps, and yellow toe armor.
    for x in (-7, -5, -3, 1, 3, 5):
        side = "left" if x < 0 else "right"
        add("blk_008", x, 0, 0, DARK_BLUE, f"{side}_foot")
        add("blk_008", x, 1, 0, BLUE, f"{side}_foot")
    for x in (-6, -4, 2, 4):
        side = "left" if x < 0 else "right"
        add("blk_007", x, 2, 0, RED, f"{side}_ankle")
        add("rmp_002", x, 1, 3, YELLOW, f"{side}_foot_armor")

    # Lower legs: solid 4x8 cores made from 2x2x2 library pieces.
    for x in (-6, -4, 1, 3):
        side = "left" if x < 0 else "right"
        for y in (3, 5, 7, 9):
            color = WHITE if y in (5, 7) else LIGHT_GREY
            add("tal_006", x, y, 0, color, f"{side}_shin")

    # Shin armor, offset one cell in front of the core.
    for x, side in ((-6, "left"), (4, "right")):
        add("tal_001", x, 3, 2, DARK, f"{side}_shin_armor")
        add("tal_001", x, 7, 2, RED, f"{side}_shin_armor")
    for x, side in ((-4, "left"), (2, "right")):
        add("tal_001", x, 4, 2, YELLOW, f"{side}_shin_armor")
        add("tal_001", x, 8, 2, GREY, f"{side}_shin_armor")

    # Thighs and blue front plates.
    for x in (-5, -3, 1, 3):
        side = "left" if x < 0 else "right"
        add("tal_006", x, 11, 0, DARK, f"{side}_thigh")
        add("tal_006", x, 13, 0, GREY, f"{side}_thigh")
    add("arc_001", -5, 12, 2, DARK_BLUE, "left_thigh_armor")
    add("arc_001", 3, 12, 2, DARK_BLUE, "right_thigh_armor", 180)

    # Pelvis and waist bridge the two legs.
    for x in (-5, -3, -1, 1, 3):
        color = WHITE if x != -1 else LIGHT_GREY
        add("tal_006", x, 15, 0, color, "pelvis")
    add("rmp_002", -5, 16, 2, YELLOW, "pelvis_armor")
    add("rmp_002", 3, 16, 2, YELLOW, "pelvis_armor", 180)
    add("arc_001", -1, 15, 2, WHITE, "pelvis_armor")

    # Lower torso.
    for x in (-4, -2, 0, 2):
        color = DARK if x in (-2, 0) else WHITE
        add("tal_006", x, 17, 0, color, "torso")

    # Main chest: red side panels around a dark central column.
    for y in (19, 21):
        for x in (-5, -3, -1, 1, 3):
            color = DARK if x == -1 else RED
            add("tal_006", x, y, 0, color, "chest")
    add("arc_001", -1, 19, 2, YELLOW, "chest_armor")
    add("arc_001", -1, 21, 2, DARK, "chest_armor")

    # Shoulder blocks.
    for x, side in ((-9, "left"), (-7, "left"), (5, "right"), (7, "right")):
        add("tal_006", x, 21, 0, DARK if abs(x) == 7 else WHITE, f"{side}_shoulder")
        add("tal_006", x, 23, 0, WHITE, f"{side}_shoulder")
    add("arc_001", -9, 23, 2, YELLOW, "left_shoulder_armor")
    add("arc_001", 7, 23, 2, YELLOW, "right_shoulder_armor", 180)
    add("tal_001", -7, 21, 2, DARK, "left_shoulder_armor")
    add("tal_001", 6, 21, 2, DARK, "right_shoulder_armor")

    # Upper arms.
    for x, side in ((-10, "left"), (-8, "left"), (6, "right"), (8, "right")):
        add("tal_006", x, 17, 0, RED if abs(x) >= 8 else DARK, f"{side}_upper_arm")
        add("tal_006", x, 19, 0, DARK, f"{side}_upper_arm")
    add("arc_001", -10, 17, 2, RED, "left_elbow")
    add("arc_001", 8, 17, 2, RED, "right_elbow", 180)

    # Forearms and fists.
    for x, side in ((-12, "left"), (-10, "left"), (8, "right"), (10, "right")):
        for y in (11, 13, 15):
            color = WHITE if y == 13 else (RED if y == 15 else DARK)
            add("tal_006", x, y, 0, color, f"{side}_forearm")
        add("tal_006", x, 9, 0, DARK, f"{side}_fist")
    add("tal_001", -12, 12, 2, RED, "left_forearm_armor")
    add("tal_001", -10, 14, 2, GREY, "left_forearm_armor")
    add("tal_001", 11, 12, 2, RED, "right_forearm_armor")
    add("tal_001", 9, 14, 2, GREY, "right_forearm_armor")

    # Neck and helmet core.
    add("tal_006", -2, 23, 0, DARK, "neck")
    add("tal_006", 0, 23, 0, DARK, "neck")
    for x in (-3, -1, 1):
        add("tal_006", x, 25, 0, WHITE, "head")
        add("tal_006", x, 27, 0, LIGHT_GREY, "head")

    # Face, eyes, ears, and red crest sit in the front layer.
    add("arc_002", -2, 25, 2, DARK, "face")
    add("blk_001", -2, 26, 3, YELLOW, "left_eye")
    add("blk_001", 0, 26, 3, YELLOW, "right_eye")
    add("rmp_002", -2, 25, 3, LIGHT_GREY, "mouth")
    add("tal_001", -3, 25, 2, RED, "left_ear")
    add("tal_001", 2, 25, 2, RED, "right_ear")
    add("tal_001", -1, 28, 2, RED, "crest")

    return scene


def render_front_preview(scene: Scene) -> None:
    cell_size = 28
    canvas_size = EDITOR_BOUNDS[0]
    image = Image.new("RGB", (canvas_size * cell_size, canvas_size * cell_size), "#20242B")
    draw = ImageDraw.Draw(image)
    front_cells: dict[tuple[int, int], tuple[int, int]] = {}

    for piece in scene.pieces:
        for x, y, z in scene.cells_for(piece):
            key = (x, y)
            if key not in front_cells or z >= front_cells[key][0]:
                front_cells[key] = (z, piece.color_id)

    for grid in range(canvas_size + 1):
        pixel = grid * cell_size
        draw.line((pixel, 0, pixel, canvas_size * cell_size), fill="#343A44", width=1)
        draw.line((0, pixel, canvas_size * cell_size, pixel), fill="#343A44", width=1)

    min_x = -(canvas_size // 2)
    for (x, y), (_, color_id) in front_cells.items():
        left = (x - min_x) * cell_size
        top = (canvas_size - y - 1) * cell_size
        color = DEFAULT_PALETTE[color_id].rgb
        draw.rectangle(
            (left + 1, top + 1, left + cell_size - 2, top + cell_size - 2),
            fill=color,
            outline="#15181D",
            width=1,
        )

    image.save(PREVIEW_PATH)


def main() -> None:
    scene = build_robot()
    save_project(PROJECT_PATH, scene, DEFAULT_PALETTE, Path("../library"))
    export_game(GAME_PATH, scene.pieces)
    render_front_preview(scene)
    bounds = scene.occupied_bounds
    print(f"Created {len(scene.pieces)} pieces")
    print(f"Occupied bounds: {bounds}")
    print(PROJECT_PATH)
    print(GAME_PATH)
    print(PREVIEW_PATH)


if __name__ == "__main__":
    main()
