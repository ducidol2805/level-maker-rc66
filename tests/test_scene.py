from __future__ import annotations

import pytest

from piece_editor.domain import PieceDef, PieceInstance
from piece_editor.scene import EDITOR_BOUNDS, PlacementError, Scene, SceneHistory


def definitions() -> dict[str, PieceDef]:
    return {
        "bar": PieceDef("bar", (2, 1, 1)),
        "cube": PieceDef("cube", (1, 1, 1)),
    }


def test_default_canvas_is_fixed_to_fifty_by_fifty() -> None:
    scene = Scene(definitions())

    assert scene.bounds == EDITOR_BOUNDS == (50, 50, 50)
    assert (scene.min_x, scene.max_x) == (-25, 25)
    assert (scene.min_z, scene.max_z) == (-25, 25)


def test_fifty_cell_bounds_include_both_edge_cells() -> None:
    scene = Scene(definitions())
    lower = PieceInstance("cube", (0, 0, -25), 0, 0)
    upper = PieceInstance("cube", (1, 0, 24), 0, 0)

    scene.add_many((lower, upper))

    assert len(range(scene.min_z, scene.max_z)) == 50
    assert len(scene.pieces) == 2


@pytest.mark.parametrize("position", [(-26, 0, 0), (25, 0, 0), (0, -1, 0), (0, 50, 0), (0, 0, -26), (0, 0, 25)])
def test_all_six_scene_boundaries_reject_outside_cells(position) -> None:
    scene = Scene(definitions())
    with pytest.raises(PlacementError, match="outside scene bounds"):
        scene.add(PieceInstance("cube", position, 0, 0))
    assert scene.pieces == []
    assert scene.occupied_bounds is None


@pytest.mark.parametrize("position,rotation", [((24, 0, 0), 0), ((0, 0, -25), 90), ((24, 0, 24), 45)])
def test_full_rotated_piece_must_fit_even_when_anchor_is_inside(position, rotation) -> None:
    scene = Scene(definitions())
    assert scene.contains_cell(position)
    with pytest.raises(PlacementError, match="outside scene bounds"):
        scene.add(PieceInstance("bar", position, rotation, 0))


def test_loading_out_of_bounds_piece_is_rejected() -> None:
    with pytest.raises(PlacementError, match="outside scene bounds"):
        Scene(definitions(), pieces=[PieceInstance("cube", (80, 0, -70), 0, 0)])


def test_rotated_footprint_and_overlap() -> None:
    scene = Scene(definitions(), bounds=(8, 8, 2))
    bar = PieceInstance("bar", (2, 2, 0), 90, 0)
    scene.add(bar)

    assert set(scene.cells_for(bar)) == {(2, 2, -1), (2, 2, 0)}
    assert scene.piece_at((2, 2, -1)) is bar
    cube = PieceInstance("cube", (2, 2, -1), 0, 1)
    scene.add(cube)
    assert scene.pieces == [bar, cube]
    assert scene.piece_at((2, 2, -1)) is cube
    scene.remove_many((cube.instance_id,))
    assert scene.piece_at((2, 2, -1)) is bar


def test_x_rotated_footprint_swaps_height_and_depth() -> None:
    definition = PieceDef("tall", (1, 2, 1))
    piece = PieceInstance("tall", (0, 2, 0), 0, 0, rotation_x=90)
    scene = Scene({"tall": definition}, pieces=[piece])

    assert set(scene.cells_for(piece)) == {(0, 2, 0), (0, 2, 1)}


def test_default_grid_pivot_uses_corner_box_for_even_axes_and_center_box_for_odd_axes() -> None:
    assert PieceDef("unit", (1, 1, 1)).pivot == (0.5, 0.5, 0.5)
    assert PieceDef("mixed", (4, 3, 6)).pivot == (0.5, 1.5, 0.5)
    assert PieceDef("odd", (3, 5, 3)).pivot == (1.5, 2.5, 1.5)


def test_x_bounds_and_reference_check_are_enforced() -> None:
    scene = Scene(definitions(), bounds=(8, 8, 2))
    piece = PieceInstance("cube", (-4, 0, 0), 0, 0)

    scene.add(piece)

    assert scene.piece_at((-4, 0, 0)) is piece
    outside = PieceInstance("cube", (-50, 0, 0), 0, 0)
    with pytest.raises(PlacementError, match="outside scene bounds"):
        scene.add(outside)
    with pytest.raises(PlacementError, match="outside the 8x2 Front canvas"):
        scene.validate_reference_bounds(outside)


def test_custom_odd_depth_and_height_bounds_are_enforced() -> None:
    scene = Scene(definitions(), bounds=(8, 8, 3))
    negative = PieceInstance("cube", (0, 0, -1), 0, 0)
    positive = PieceInstance("cube", (0, 0, 1), 0, 0)

    scene.add_many((negative, positive))

    assert scene.piece_at((0, 0, -1)) is negative
    assert scene.piece_at((0, 0, 1)) is positive
    for position in ((0, 0, -2), (0, 0, 2), (0, 8, 0)):
        with pytest.raises(PlacementError, match="outside scene bounds"):
            scene.add(PieceInstance("cube", position, 0, 0))


@pytest.mark.parametrize("position", [(0, 4, 0), (-3, 0, 0), (2, 0, 0), (0, 0, -1), (0, 0, 1)])
def test_replace_is_atomic_when_move_is_invalid(position) -> None:
    scene = Scene(definitions(), bounds=(4, 4, 1))
    cube = PieceInstance("cube", (0, 0, 0), 0, 0)
    scene.add(cube)
    invalid = PieceInstance("cube", position, 0, 0, instance_id=cube.instance_id)

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

