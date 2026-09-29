from __future__ import annotations

import pytest

from piece_editor.domain import PieceDef, PieceInstance
from piece_editor.scene import EDITOR_BOUNDS, PlacementError, Scene, SceneHistory


def definitions() -> dict[str, PieceDef]:
    return {
        "bar": PieceDef("bar", (2, 1, 1)),
        "cube": PieceDef("cube", (1, 1, 1)),
    }


def test_default_canvas_is_fixed_to_thirty_by_thirty() -> None:
    scene = Scene(definitions())

    assert scene.bounds == EDITOR_BOUNDS == (30, 30, 30)
    assert (scene.min_x, scene.max_x) == (-15, 15)
    assert (scene.min_z, scene.max_z) == (-15, 15)


def test_default_canvas_accepts_exactly_thirty_depth_layers() -> None:
    scene = Scene(definitions())
    lower = PieceInstance("cube", (0, 0, -15), 0, 0)
    upper = PieceInstance("cube", (1, 0, 14), 0, 0)

    scene.add_many((lower, upper))

    assert len(range(scene.min_z, scene.max_z)) == 30
    with pytest.raises(PlacementError, match="outside scene bounds"):
        scene.add(PieceInstance("cube", (2, 0, -16), 0, 0))
    with pytest.raises(PlacementError, match="outside scene bounds"):
        scene.add(PieceInstance("cube", (2, 0, 15), 0, 0))


def test_rotated_footprint_and_overlap() -> None:
    scene = Scene(definitions(), bounds=(8, 8, 2))
    bar = PieceInstance("bar", (2, 2, 0), 90, 0)
    scene.add(bar)

    assert set(scene.cells_for(bar)) == {(2, 2, -1), (2, 2, 0)}
    assert scene.piece_at((2, 2, -1)) is bar
    with pytest.raises(PlacementError, match="already occupied"):
        scene.add(PieceInstance("cube", (2, 2, -1), 0, 1))


def test_default_grid_pivot_uses_corner_box_for_even_axes_and_center_box_for_odd_axes() -> None:
    assert PieceDef("unit", (1, 1, 1)).pivot == (0.5, 0.5, 0.5)
    assert PieceDef("mixed", (4, 3, 6)).pivot == (0.5, 1.5, 0.5)
    assert PieceDef("odd", (3, 5, 3)).pivot == (1.5, 2.5, 1.5)


def test_negative_x_is_valid_inside_centered_bounds() -> None:
    scene = Scene(definitions(), bounds=(8, 8, 2))
    piece = PieceInstance("cube", (-4, 0, 0), 0, 0)

    scene.add(piece)

    assert scene.piece_at((-4, 0, 0)) is piece
    with pytest.raises(PlacementError, match="outside scene bounds"):
        scene.add(PieceInstance("cube", (-5, 0, 0), 0, 0))


def test_negative_z_is_valid_without_breaking_existing_positive_depth() -> None:
    scene = Scene(definitions(), bounds=(8, 8, 3))
    negative = PieceInstance("cube", (0, 0, -1), 0, 0)
    positive = PieceInstance("cube", (0, 0, 1), 0, 0)

    scene.add_many((negative, positive))

    assert scene.piece_at((0, 0, -1)) is negative
    assert scene.piece_at((0, 0, 1)) is positive
    with pytest.raises(PlacementError, match="outside scene bounds"):
        scene.add(PieceInstance("cube", (0, 0, -2), 0, 0))
    with pytest.raises(PlacementError, match="outside scene bounds"):
        scene.add(PieceInstance("cube", (0, 0, 2), 0, 0))


def test_replace_is_atomic_when_move_is_invalid() -> None:
    scene = Scene(definitions(), bounds=(4, 4, 1))
    cube = PieceInstance("cube", (0, 0, 0), 0, 0)
    scene.add(cube)
    invalid = PieceInstance("cube", (4, 0, 0), 0, 0, instance_id=cube.instance_id)

    with pytest.raises(PlacementError):
        scene.replace_many({cube.instance_id: invalid})

    assert scene.piece_at((0, 0, 0)) is cube


def test_history_round_trip() -> None:
    scene = Scene(definitions())
    history = SceneHistory(scene)
    history.checkpoint()
    scene.add(PieceInstance("cube", (1, 1, 0), 0, 2))

    assert history.undo()
    assert scene.pieces == []
    assert history.redo()
    assert len(scene.pieces) == 1
    assert scene.pieces[0].color_id == 2

