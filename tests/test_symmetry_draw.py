from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from piece_editor.brush3d import BrushStroke3D, mirrored_piece_yz
from piece_editor.document import EditorTool
from piece_editor.domain import DEFAULT_PALETTE, PieceDef, PieceInstance
from piece_editor.renderer3d import RayHit
from piece_editor.scene import Scene
from piece_editor.viewport import EditorViewport, ViewMode


@pytest.mark.parametrize("rotation", range(0, 360, 45))
@pytest.mark.parametrize("rotation_x", (0, 45, 90, 270))
def test_mirror_reflects_full_rotated_footprint(rotation, rotation_x) -> None:
    definition = PieceDef("bar", (2, 3, 4), pivot=(0.5, 1.5, 0.5))
    scene = Scene({definition.id: definition})
    original = PieceInstance("bar", (7, 10, 3), rotation, 2, rotation_x=rotation_x)
    mirrored = mirrored_piece_yz(definition, original)
    assert set(scene.cells_for(mirrored)) == {(-x - 1, y, z) for x, y, z in scene.cells_for(original)}
    assert mirrored.rotation == rotation
    assert mirrored.rotation_x == rotation_x
    assert mirrored.color_id == original.color_id
    assert mirrored.instance_id != original.instance_id


@pytest.fixture
def viewport():
    app = QApplication.instance() or QApplication([])
    view = EditorViewport(Scene({"cube": PieceDef("cube", (1, 1, 1))}), DEFAULT_PALETTE)
    view.set_view_mode(ViewMode.PERSPECTIVE)
    yield view
    view.deleteLater()
    app.processEvents()


def test_toggle_stroke_dedup_bounds_and_single_undo(viewport) -> None:
    button = viewport.renderer_panel.symmetry_button
    assert not button.isChecked()
    button.click()
    assert viewport.symmetry_draw
    viewport.document.begin_stroke()
    viewport.brush_stroke3d = BrushStroke3D(EditorTool.PLACE, (0, 1, 0), 0.0)
    viewport._apply_3d_cells(((0, 0, 2), (-1, 0, 2), (24, 0, 2)))
    viewport._apply_3d_cells(((0, 0, 2),))
    viewport.document.end_stroke()
    assert {piece.position for piece in viewport.scene.pieces} == {
        (0, 0, 2), (-1, 0, 2), (24, 0, 2), (-25, 0, 2),
    }
    assert viewport.document.undo()
    assert viewport.scene.pieces == []
    assert not viewport.document.undo()
    assert viewport.document.redo()
    assert len(viewport.scene.pieces) == 4
    button.click()
    assert not viewport.symmetry_draw
    viewport.brush_stroke3d = BrushStroke3D(EditorTool.PLACE, (0, 1, 0), 0.0)
    viewport._apply_3d_cells(((3, 0, 2),))
    assert viewport.scene.piece_at((3, 0, 2)) is not None
    assert viewport.scene.piece_at((-4, 0, 2)) is None


def test_symmetry_preview_and_placement_allow_occupied_mirror(viewport) -> None:
    viewport.scene.add(PieceInstance("cube", (-4, 0, 2), 0, 0))
    viewport.set_symmetry_draw(True)
    hit = RayHit(None, (3, 0, 2), (0, 1, 0), (3.5, 0.0, 2.5), 1.0, True)
    preview = viewport._preview_for_hit(hit, EditorTool.PLACE)
    assert preview is not None
    assert preview.instance.position == (3, 0, 2)
    assert len(preview.companions) == 1
    assert preview.companions[0].instance.position == (-4, 0, 2)
    assert preview.companions[0].color == preview.color
    viewport.brush_stroke3d = BrushStroke3D(EditorTool.PLACE, (0, 1, 0), 0.0)
    viewport._apply_3d_cells((hit.cell,))
    assert len(viewport.scene.pieces) == 3


def test_centered_multi_cell_piece_is_not_duplicated(viewport) -> None:
    viewport.scene.piece_defs["bar"] = PieceDef("bar", (2, 1, 1))
    viewport.active_piece_id = "bar"
    viewport.set_symmetry_draw(True)
    viewport.brush_stroke3d = BrushStroke3D(EditorTool.PLACE, (0, 1, 0), 0.0)
    viewport._apply_3d_cells(((-1, 0, 0),))
    assert len(viewport.scene.pieces) == 1
    assert set(viewport.scene.cells_for(viewport.scene.pieces[0])) == {(-1, 0, 0), (0, 0, 0)}


def test_symmetry_paint_and_erase_share_undo(viewport) -> None:
    for x in (3, -4):
        viewport.scene.add(PieceInstance("cube", (x, 0, 2), 0, 0))
    viewport.set_symmetry_draw(True)
    viewport.active_color_id = 1
    for mode in (EditorTool.PAINT, EditorTool.ERASE):
        viewport.document.begin_stroke()
        viewport.brush_stroke3d = BrushStroke3D(mode, (0, 1, 0), 1.0)
        viewport._apply_3d_cells(((3, 0, 2), (-4, 0, 2)))
        viewport.document.end_stroke()
        if mode == EditorTool.PAINT:
            assert [piece.color_id for piece in viewport.scene.pieces] == [1, 1]
        else:
            assert viewport.scene.pieces == []
        assert viewport.document.undo()
        assert len(viewport.scene.pieces) == 2
        assert [piece.color_id for piece in viewport.scene.pieces] == [0, 0]
