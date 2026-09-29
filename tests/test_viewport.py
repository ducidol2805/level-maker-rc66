from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QSettings, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QSizePolicy

from piece_editor.domain import DEFAULT_PALETTE, PieceDef, PieceInstance
from piece_editor.renderer3d import RenderStats
from piece_editor.scene import Scene
from piece_editor.viewport import EditorTool, EditorViewport, ViewMode


def test_h_key_centers_front_origin_near_bottom() -> None:
    app = QApplication.instance() or QApplication([])
    viewport = EditorViewport(Scene({"cube": PieceDef("cube", (1, 1, 1))}), DEFAULT_PALETTE)
    viewport.resize(600, 400)
    viewport.offset.setX(12)
    viewport.offset.setY(34)

    viewport.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_H, Qt.KeyboardModifier.NoModifier))

    assert viewport.offset.x() == viewport.width() / 2
    assert viewport.offset.y() == viewport.height() - 54
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
    assert viewport.renderer_panel.width() == 210
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
    expected_grid_positions = {
        viewport.renderer_panel.shader_buttons["pbr"]: (1, 0, 1, 3),
        viewport.renderer_panel.shader_buttons["simple"]: (1, 3, 1, 3),
        viewport.renderer_panel.projection_buttons["perspective"]: (3, 0, 1, 2),
        viewport.renderer_panel.projection_buttons["orthographic"]: (3, 2, 1, 2),
        viewport.renderer_panel.projection_buttons["iso"]: (3, 4, 1, 2),
    }
    for button, expected in expected_grid_positions.items():
        index = viewport.renderer_panel.controls_grid.indexOf(button)
        assert viewport.renderer_panel.controls_grid.getItemPosition(index) == expected
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


def test_toolbox_palette_and_library_use_resizable_vertical_splitter() -> None:
    from piece_editor.ui import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow("library", persist_ui_state=False)

    assert window.left_splitter.orientation() == Qt.Orientation.Vertical
    assert window.left_splitter.widget(0) is window.toolbox_panel
    assert window.left_splitter.widget(1) is window.palette_panel
    assert window.left_splitter.widget(2) is window.library_panel
    assert not window.left_splitter.childrenCollapsible()
    window.close()
    window.deleteLater()
    app.processEvents()


def test_toolbox_buttons_fit_panel_in_requested_rows() -> None:
    from piece_editor.ui import MainWindow
    from PIL import Image

    app = QApplication.instance() or QApplication([])
    window = MainWindow("library", persist_ui_state=False)

    assert set(window.toolbox_panel.buttons) == {
        "place",
        "erase",
        "paint",
        "select",
        "move",
        "box",
        "duplicate",
        "mirror",
    }
    expected_positions = {
        "place": (0, 0),
        "erase": (0, 1),
        "move": (0, 2),
        "duplicate": (0, 3),
        "select": (1, 0),
        "box": (1, 1),
        "mirror": (1, 2),
        "paint": (1, 3),
    }
    for key, position in expected_positions.items():
        index = window.toolbox_panel.grid.indexOf(window.toolbox_panel.buttons[key])
        assert window.toolbox_panel.grid.getItemPosition(index)[:2] == position
    assert window.toolbox_panel.grid.count() == 8
    for button in window.toolbox_panel.buttons.values():
        assert button.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
        assert button.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Expanding
        assert button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextUnderIcon
        assert not button.icon().isNull()
    expected_icons = {
        "place": "tool_brush.png",
        "erase": "tool_eraser.png",
        "paint": "tool_paint.png",
        "move": "tool_move.png",
        "duplicate": "tool_dup.png",
        "select": "tool_select.png",
        "box": "tool_box.png",
        "mirror": "tool_flip_H.png",
    }
    for key, filename in expected_icons.items():
        assert window.toolbox_icon_paths[key].name == filename
        assert window.toolbox_icon_paths[key].is_file()
        assert window.toolbox_panel.buttons[key].icon().cacheKey() == window.toolbox_icons[key].cacheKey()
    with Image.open(window.toolbox_icon_paths["paint"]) as paint_icon:
        assert paint_icon.size == (256, 256)
        assert paint_icon.mode == "RGBA"
    window.close()
    window.deleteLater()
    app.processEvents()


def test_front_and_3d_are_separate_hideable_center_panels() -> None:
    from piece_editor.ui import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow("library", persist_ui_state=False)

    assert window.view_splitter.widget(0) is window.front_panel
    assert window.view_splitter.widget(1) is window.view3d_panel
    assert window.front_viewport is not window.view3d
    assert window.front_viewport.scene is window.view3d.scene
    assert window.front_viewport.document is window.view3d.document
    assert window.front_viewport.view_mode == ViewMode.FRONT
    assert window.view3d.view_mode == ViewMode.PERSPECTIVE
    assert not window.front_viewport.allow_3d
    assert not window.view3d.read_only

    window._set_view_panel_visible("3d", False)
    assert window.view3d_panel.isHidden()
    assert not window.view3d_panel_action.isChecked()
    window._set_view_panel_visible("3d", True)
    assert not window.view3d_panel.isHidden()
    assert window.view3d_panel_action.isChecked()
    window.close()
    window.deleteLater()
    app.processEvents()


def test_window_geometry_splitters_and_panel_visibility_persist(tmp_path) -> None:
    from piece_editor.ui import MainWindow

    app = QApplication.instance() or QApplication([])
    settings_path = tmp_path / "ui-state.ini"
    settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
    first = MainWindow("library", settings=settings)
    first.resize(1234, 777)
    first.show()
    app.processEvents()
    first.main_splitter.setSizes([210, 760, 240])
    first.workspace_splitter.setSizes([500, 240])
    first.left_splitter.setSizes([180, 110, 230])
    first.view_splitter.setSizes([430, 330])
    first._set_view_panel_visible("front", True)
    first._set_view_panel_visible("3d", False)
    app.processEvents()
    expected_size = first.size()
    expected_geometry = first.saveGeometry()
    expected_splitter_states = {
        "ui/main_splitter": first.main_splitter.saveState(),
        "ui/workspace_splitter": first.workspace_splitter.saveState(),
        "ui/left_splitter": first.left_splitter.saveState(),
        "ui/view_splitter": first.view_splitter.saveState(),
    }
    first.close()
    first.deleteLater()
    app.processEvents()

    restored_settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
    assert restored_settings.value("ui/main_window_geometry") == expected_geometry
    for key, state in expected_splitter_states.items():
        assert restored_settings.value(key) == state
    second = MainWindow("library", settings=restored_settings)
    second.show()
    app.processEvents()

    # Qt clamps restored geometry to the offscreen test display; a normal
    # desktop restores the saved size unless the available screen is smaller.
    assert second.width() <= expected_size.width()
    assert second.height() <= expected_size.height()
    assert (second.width(), second.height()) != (1600, 900)
    assert second.view3d_panel.isHidden()
    assert not second.view3d_panel_action.isChecked()
    assert not second.front_panel.isHidden()
    second.close()
    second.deleteLater()
    app.processEvents()


def test_old_ui_settings_migrate_once_to_default_3d_only_layout(tmp_path) -> None:
    from piece_editor.ui import MainWindow, UI_LAYOUT_VERSION

    app = QApplication.instance() or QApplication([])
    settings_path = tmp_path / "old-ui-state.ini"
    settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
    settings.setValue("ui/layout_version", UI_LAYOUT_VERSION - 1)
    settings.setValue("ui/front_panel_visible", True)
    settings.setValue("ui/3d_panel_visible", False)
    settings.sync()

    migrated = MainWindow("library", settings=settings)
    migrated.show()
    app.processEvents()
    assert migrated.front_panel.isHidden()
    assert not migrated.view3d_panel.isHidden()
    migrated.close()
    migrated.deleteLater()
    app.processEvents()

    saved = QSettings(str(settings_path), QSettings.Format.IniFormat)
    assert saved.value("ui/layout_version", type=int) == UI_LAYOUT_VERSION
    assert not saved.value("ui/front_panel_visible", type=bool)
    assert saved.value("ui/3d_panel_visible", type=bool)

    restored = MainWindow("library", settings=saved)
    restored.show()
    app.processEvents()
    assert restored.front_panel.isHidden()
    assert not restored.view3d_panel.isHidden()
    restored._set_view_panel_visible("front", True)
    assert not restored.front_panel.isHidden()
    restored.close()
    restored.deleteLater()
    app.processEvents()


def test_side_widths_and_toolbox_palette_heights_stay_fixed_when_window_resizes() -> None:
    from piece_editor.ui import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow("library", persist_ui_state=False)
    window.resize(1300, 780)
    window.show()
    app.processEvents()
    window.main_splitter.setSizes([230, 760, 270])
    window.left_splitter.setSizes([175, 115, 220])
    app.processEvents()
    side_widths = (window.main_splitter.sizes()[0], window.main_splitter.sizes()[2])
    fixed_heights = tuple(window.left_splitter.sizes()[:2])

    window.resize(1580, 940)
    app.processEvents()

    assert (window.main_splitter.sizes()[0], window.main_splitter.sizes()[2]) == side_widths
    assert tuple(window.left_splitter.sizes()[:2]) == fixed_heights
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


def test_eraser_tool_uses_left_drag_without_changing_right_drag_behavior() -> None:
    app = QApplication.instance() or QApplication([])
    scene = Scene({"cube": PieceDef("cube", (1, 1, 1))})
    viewport = EditorViewport(scene, DEFAULT_PALETTE)
    viewport._begin_paint_stroke(Qt.MouseButton.LeftButton, (0, 0))
    viewport._continue_paint_stroke((2, 0))
    viewport._end_paint_stroke()

    viewport.set_tool(EditorTool.ERASE)
    viewport._begin_paint_stroke(Qt.MouseButton.LeftButton, (0, 0))
    viewport._continue_paint_stroke((1, 0))
    viewport._end_paint_stroke()
    assert [piece.position for piece in scene.pieces] == [(2, 0, 0)]

    viewport.set_tool(EditorTool.SELECT)
    viewport._begin_paint_stroke(Qt.MouseButton.RightButton, (2, 0))
    viewport._end_paint_stroke()
    assert scene.pieces == []
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
