from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QSizePolicy

from piece_editor.domain import DEFAULT_PALETTE, PieceDef, PieceInstance
from piece_editor.renderer3d import RenderStats
from piece_editor.scene import Scene
from piece_editor.viewport import EditorViewport, ViewMode


def test_h_key_centers_view_on_origin() -> None:
    app = QApplication.instance() or QApplication([])
    viewport = EditorViewport(Scene({"cube": PieceDef("cube", (1, 1, 1))}), DEFAULT_PALETTE)
    viewport.resize(600, 400)
    viewport.offset.setX(12)
    viewport.offset.setY(34)

    viewport.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_H, Qt.KeyboardModifier.NoModifier))

    assert viewport.offset.x() == viewport.width() / 2
    assert viewport.offset.y() == viewport.height() / 2
    viewport.deleteLater()
    app.processEvents()


def test_3d_shader_mode_can_switch_between_pbr_and_simple() -> None:
    app = QApplication.instance() or QApplication([])
    viewport = EditorViewport(Scene({"cube": PieceDef("cube", (1, 1, 1))}), DEFAULT_PALETTE)

    assert viewport.shading_mode == "pbr"
    viewport.set_shading_mode("simple")
    assert viewport.shading_mode == "simple"
    assert viewport.renderer_panel.shader_buttons["simple"].isChecked()
    viewport.set_shading_mode("pbr")
    assert viewport.shading_mode == "pbr"
    assert viewport.renderer_panel.shader_buttons["pbr"].isChecked()
    viewport.deleteLater()
    app.processEvents()


def test_floating_renderer_panel_contains_stats_shader_and_projection_switch() -> None:
    app = QApplication.instance() or QApplication([])
    viewport = EditorViewport(Scene({"cube": PieceDef("cube", (1, 1, 1))}), DEFAULT_PALETTE)

    assert viewport.renderer_panel.isHidden()
    assert viewport.renderer_panel.width() == 282
    viewport.set_view_mode(ViewMode.PERSPECTIVE)
    assert not viewport.renderer_panel.isHidden()
    viewport.renderer_panel.update_stats(RenderStats(256, 1, 48128, 188, 3))
    assert "OBJ 256 → 1 cached" in viewport.renderer_panel.stats_label.text()
    assert "Tris 48,128" in viewport.renderer_panel.stats_label.text()
    assert viewport.projection_mode == "perspective"
    assert [button.text() for button in viewport.renderer_panel.shader_buttons.values()] == ["High", "Low"]
    assert [button.text() for button in viewport.renderer_panel.projection_buttons.values()] == [
        "Perspective",
        "Ortho",
        "Iso",
    ]
    viewport.renderer_panel.projection_buttons["orthographic"].click()
    assert viewport.projection_mode == "orthographic"
    assert viewport.renderer_panel.projection_buttons["orthographic"].isChecked()
    viewport.renderer_panel.projection_buttons["iso"].click()
    assert viewport.projection_mode == "iso"
    assert viewport.renderer_panel.projection_buttons["iso"].isChecked()
    viewport.set_view_mode(ViewMode.FRONT)
    assert viewport.renderer_panel.isHidden()
    viewport.deleteLater()
    app.processEvents()


def test_palette_uses_eight_columns_and_four_rows() -> None:
    from piece_editor.ui import PalettePanel

    app = QApplication.instance() or QApplication([])
    panel = PalettePanel(DEFAULT_PALETTE)

    assert panel.grid.count() == 32
    positions = [panel.grid.getItemPosition(index)[:2] for index in range(panel.grid.count())]
    assert positions == [(index // 8, index % 8) for index in range(32)]
    assert max(row for row, _ in positions) == 3
    assert max(column for _, column in positions) == 7
    assert all(
        button.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
        and button.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Expanding
        for button in panel.buttons.values()
    )
    panel.deleteLater()
    app.processEvents()


def test_palette_and_library_use_resizable_vertical_splitter() -> None:
    from piece_editor.ui import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow("library")

    assert window.left_splitter.orientation() == Qt.Orientation.Vertical
    assert window.left_splitter.widget(0) is window.palette_panel
    assert window.left_splitter.widget(1) is window.library_panel
    assert not window.left_splitter.childrenCollapsible()
    window.close()
    window.deleteLater()
    app.processEvents()


def test_ai_controls_cannot_exceed_canvas_size_and_scale_sets_width(tmp_path) -> None:
    from piece_editor.ui import AIBuildPanel
    from PIL import Image

    app = QApplication.instance() or QApplication([])
    panel = AIBuildPanel()
    image_path = tmp_path / "reference.png"
    Image.new("RGB", (96, 40), "red").save(image_path)
    panel.drop.set_path(str(image_path))

    assert panel.width.maximum() == 30
    assert panel.height.maximum() == 30
    assert panel.scale.value() == 4
    assert panel.width.value() == 24
    panel.scale.setValue(8)
    assert panel.width.value() == 12
    assert panel.sample_mode.currentData() == "nearest"
    assert panel.palette_size.value() == 32
    panel.deleteLater()
    app.processEvents()


def test_paint_and_erase_strokes_are_continuous_unselected_and_single_undo() -> None:
    app = QApplication.instance() or QApplication([])
    scene = Scene({"cube": PieceDef("cube", (1, 1, 1))})
    viewport = EditorViewport(scene, DEFAULT_PALETTE)

    viewport._begin_paint_stroke(Qt.MouseButton.LeftButton, (-1, 0))
    viewport._continue_paint_stroke((2, 0))
    viewport._end_paint_stroke()

    assert [piece.position for piece in scene.pieces] == [(-1, 0, 0), (0, 0, 0), (1, 0, 0), (2, 0, 0)]
    assert viewport.selection == set()
    viewport.undo()
    assert scene.pieces == []
    viewport.redo()
    assert len(scene.pieces) == 4

    viewport._begin_paint_stroke(Qt.MouseButton.RightButton, (0, 0))
    viewport._continue_paint_stroke((2, 0))
    viewport._end_paint_stroke()

    assert [piece.position for piece in scene.pieces] == [(-1, 0, 0)]
    viewport.undo()
    assert len(scene.pieces) == 4
    viewport.deleteLater()
    app.processEvents()


def test_replace_all_does_not_select_every_generated_piece() -> None:
    app = QApplication.instance() or QApplication([])
    scene = Scene({"cube": PieceDef("cube", (1, 1, 1))})
    viewport = EditorViewport(scene, DEFAULT_PALETTE)
    pieces = [PieceInstance("cube", (x, 0, 0), 0, 0) for x in range(-2, 3)]

    assert viewport.replace_all(pieces)
    assert len(scene.pieces) == 5
    assert viewport.selection == set()
    viewport.deleteLater()
    app.processEvents()
