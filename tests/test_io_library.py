from __future__ import annotations

import json

from PIL import Image

from piece_editor.domain import (
    DEFAULT_PALETTE,
    PieceDef,
    PieceInstance,
    load_palette_image,
    load_palette_order,
    reorder_palette,
)
from piece_editor.io import export_game, load_project_data, save_project
from piece_editor.library import PieceLibrary
from piece_editor.scene import Scene


def test_library_scans_nested_piece_definitions(tmp_path) -> None:
    folder = tmp_path / "bars" / "long"
    folder.mkdir(parents=True)
    (folder / "piece.json").write_text(
        json.dumps({"id": "bar", "size": [2, 1, 1], "allowed_rotations": [0, 90]}),
        encoding="utf-8",
    )

    library = PieceLibrary.load(tmp_path)

    assert library.pieces["bar"].size == (2, 1, 1)
    assert not library.warnings


def test_bundled_library_pivots_follow_grid_box_rule() -> None:
    library = PieceLibrary.load("library")

    assert not library.warnings
    for piece in library.pieces.values():
        expected = tuple(value / 2.0 if value % 2 else 0.5 for value in piece.size)
        if piece.category == "Ramps":
            expected = (piece.size[0] - 0.5, expected[1], expected[2])
        assert piece.pivot == expected


def test_project_round_trip_and_minimal_game_export(tmp_path) -> None:
    definition = PieceDef("cube", (1, 1, 1))
    piece = PieceInstance("cube", (2, 3, 0), 90, 4, "head", rotation_x=45)
    scene = Scene({"cube": definition}, pieces=[piece])
    project_path = tmp_path / "model.piece-project.json"
    game_path = tmp_path / "model.json"

    save_project(project_path, scene, DEFAULT_PALETTE, tmp_path / "library")
    export_game(game_path, scene.pieces)

    project = load_project_data(project_path)
    game = json.loads(game_path.read_text(encoding="utf-8"))
    assert project["pieces"][0]["group_id"] == "head"
    assert project["pieces"][0]["rotation_x"] == 45
    assert game == {
        "pieces": [{"id": "cube", "pos": [2, 3, 0], "rot": 90, "rot_x": 45, "color": 4}]
    }
    assert PieceInstance.from_dict(game["pieces"][0]).rotation_x == 45


def test_legacy_piece_data_defaults_x_rotation_to_zero() -> None:
    project_piece = PieceInstance.from_dict(
        {"piece_id": "cube", "position": [0, 0, 0], "rotation": 90, "color_id": 1}
    )
    game_piece = PieceInstance.from_dict({"id": "cube", "pos": [0, 0, 0], "rot": 90, "color": 1})

    assert project_piece.rotation_x == 0
    assert game_piece.rotation_x == 0


def test_palette_image_preserves_pixel_order_and_skips_duplicates(tmp_path) -> None:
    image = Image.new("RGBA", (4, 1))
    image.putdata([(1, 2, 3, 255), (9, 8, 7, 0), (4, 5, 6, 255), (1, 2, 3, 255)])
    path = tmp_path / "Palette.png"
    image.save(path)

    palette = load_palette_image(path)

    assert [(color.id, color.rgb) for color in palette] == [(0, "#010203"), (1, "#040506")]


def test_text_file_controls_palette_order(tmp_path) -> None:
    image = Image.new("RGBA", (3, 1))
    image.putdata([(1, 2, 3, 255), (4, 5, 6, 255), (7, 8, 9, 255)])
    image_path = tmp_path / "Palette.png"
    order_path = tmp_path / "palette.txt"
    image.save(image_path)
    order_path.write_text("070809, #010203\n040506", encoding="utf-8")

    palette = reorder_palette(load_palette_image(image_path), load_palette_order(order_path))

    assert [(color.id, color.rgb) for color in palette] == [
        (0, "#070809"),
        (1, "#010203"),
        (2, "#040506"),
    ]

