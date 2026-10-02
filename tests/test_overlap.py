from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from piece_editor.brush3d import BrushStroke3D
from piece_editor.document import EditorTool
from piece_editor.domain import DEFAULT_PALETTE, PieceDef, PieceInstance
from piece_editor.io import export_game, import_game_data, load_project_data, save_project
from piece_editor.scene import Scene
from piece_editor.viewport import EditorViewport


def test_overlapping_pieces_survive_project_and_game_round_trip(tmp_path) -> None:
    definition = PieceDef("bar", (3, 2, 2))
    originals = [PieceInstance("bar", (0, 1, 0), rotation, 1) for rotation in (0, 45, 90)]
    scene = Scene({"bar": definition}, pieces=originals)
    project_path = tmp_path / "overlap.piece-project.json"
    save_project(project_path, scene, DEFAULT_PALETTE, "library")
    project_data = load_project_data(project_path)
    loaded = Scene(scene.piece_defs, pieces=[PieceInstance.from_dict(item) for item in project_data["pieces"]])
    assert loaded.snapshot() == scene.snapshot()
    game_path = tmp_path / "overlap.game.json"
    export_game(game_path, loaded.pieces)
    imported = Scene(scene.piece_defs, pieces=import_game_data(game_path))
    assert [piece.to_game_dict() for piece in imported.pieces] == [piece.to_game_dict() for piece in originals]
    loaded.remove_many((loaded.pieces[-1].instance_id,))
    assert len(loaded.pieces) == 2
    for piece in loaded.pieces:
        assert loaded.piece_by_id(piece.instance_id) is piece
        assert all(loaded.instance_id_at(cell) is not None for cell in loaded.cells_for(piece))


def test_overlapping_front_and_3d_strokes_erase_and_undo() -> None:
    app = QApplication.instance() or QApplication([])
    original = PieceInstance("cube", (0, 0, 0), 0, 0)
    scene = Scene({"cube": PieceDef("cube", (1, 1, 1))}, pieces=[original])
    viewport = EditorViewport(scene, DEFAULT_PALETTE)
    viewport._place((0, 0))
    assert len(scene.pieces) == 2
    viewport.document.begin_stroke()
    viewport.brush_stroke3d = BrushStroke3D(EditorTool.PLACE, (0, 1, 0), 0.0)
    viewport._apply_3d_cells(((0, 0, 0),))
    viewport._apply_3d_cells(((0, 0, 0),))
    viewport.document.end_stroke()
    assert len(scene.pieces) == 3
    top_id = scene.instance_id_at((0, 0, 0))
    viewport.document.begin_stroke()
    viewport.brush_stroke3d = BrushStroke3D(EditorTool.ERASE, (0, 1, 0), 1.0)
    viewport._apply_3d_cells(((0, 0, 0),))
    viewport.document.end_stroke()
    assert len(scene.pieces) == 2
    assert scene.instance_id_at((0, 0, 0)) != top_id
    assert viewport.document.undo()
    assert len(scene.pieces) == 3
    assert scene.instance_id_at((0, 0, 0)) == top_id
    assert viewport.document.undo()
    assert len(scene.pieces) == 2
    assert viewport.document.redo()
    assert len(scene.pieces) == 3
    assert scene.instance_id_at((0, 0, 0)) == top_id
    viewport.deleteLater()
    app.processEvents()
