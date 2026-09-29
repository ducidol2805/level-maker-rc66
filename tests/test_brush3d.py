from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from piece_editor.brush3d import BrushStroke3D, grid_line_on_plane, piece_position_for_target
from piece_editor.document import EditorDocument, EditorTool
from piece_editor.domain import DEFAULT_PALETTE, PieceDef, PieceInstance
from piece_editor.renderer3d import Camera3D, ModernGLSceneRenderer, RayHit, _grid_raycast
from piece_editor.scene import Scene
from piece_editor.viewport import EditorViewport, ViewMode


def test_grid_raycast_hits_all_six_cell_faces() -> None:
    piece = PieceInstance("cube", (0, 1, 2), 0, 0)
    scene = Scene({"cube": PieceDef("cube", (1, 1, 1))}, pieces=[piece])
    cases = (
        ((-4, 1.5, 2.5), (1, 0, 0), (-1, 0, 0)),
        ((4, 1.5, 2.5), (-1, 0, 0), (1, 0, 0)),
        ((0.5, -2, 2.5), (0, 1, 0), (0, -1, 0)),
        ((0.5, 5, 2.5), (0, -1, 0), (0, 1, 0)),
        ((0.5, 1.5, -2), (0, 0, 1), (0, 0, -1)),
        ((0.5, 1.5, 6), (0, 0, -1), (0, 0, 1)),
    )

    for origin, direction, normal in cases:
        hit = _grid_raycast(np.asarray(origin, dtype=np.float32), np.asarray(direction, dtype=np.float32), scene)
        assert hit is not None
        assert hit.instance_id == piece.instance_id
        assert hit.cell == (0, 1, 2)
        assert hit.normal == normal


def test_grid_raycast_uses_occupancy_lookup_with_4000_pieces() -> None:
    definition = PieceDef("cube", (1, 1, 1))
    pieces = [
        PieceInstance("cube", (x - 50, y, 0), 0, 0)
        for y in range(40)
        for x in range(100)
    ]
    scene = Scene({"cube": definition}, bounds=(100, 40, 4), pieces=pieces)

    hit = _grid_raycast(
        np.asarray((-60.0, 0.5, 0.5), dtype=np.float32),
        np.asarray((1.0, 0.0, 0.0), dtype=np.float32),
        scene,
    )

    assert hit is not None
    assert hit.cell == (-50, 0, 0)
    assert scene.piece_by_id(hit.instance_id or "") is scene.piece_at(hit.cell)


def test_grid_raycast_finds_piece_outside_thirty_cell_reference_frame() -> None:
    piece = PieceInstance("cube", (80, 1, -70), 0, 0)
    scene = Scene({"cube": PieceDef("cube", (1, 1, 1))}, pieces=[piece])

    hit = _grid_raycast(
        np.asarray((70.0, 1.5, -69.5), dtype=np.float32),
        np.asarray((1.0, 0.0, 0.0), dtype=np.float32),
        scene,
    )

    assert hit is not None
    assert hit.instance_id == piece.instance_id
    assert hit.cell == (80, 1, -70)


def test_raycast_falls_back_to_unbounded_y_zero_ground() -> None:
    renderer = ModernGLSceneRenderer.__new__(ModernGLSceneRenderer)
    renderer.screen_ray = lambda _x, _y: (  # type: ignore[method-assign]
        np.asarray((2.25, 5.0, -3.25), dtype=np.float32),
        np.asarray((0.0, -1.0, 0.0), dtype=np.float32),
    )
    scene = Scene({"cube": PieceDef("cube", (1, 1, 1))})

    hit = renderer.raycast_grid(10.0, 20.0, scene)

    assert hit is not None
    assert hit.ground
    assert hit.instance_id is None
    assert hit.cell == (2, 0, -4)
    assert hit.normal == (0, 1, 0)

    renderer.screen_ray = lambda _x, _y: (  # type: ignore[method-assign]
        np.asarray((125.25, 5.0, -203.25), dtype=np.float32),
        np.asarray((0.0, -1.0, 0.0), dtype=np.float32),
    )
    outside_hit = renderer.raycast_grid(10.0, 20.0, scene)
    assert outside_hit is not None
    assert outside_hit.cell == (125, 0, -204)


def test_screen_rays_support_perspective_ortho_and_iso_projection() -> None:
    renderer = ModernGLSceneRenderer.__new__(ModernGLSceneRenderer)
    renderer.viewport_size = (800, 600)
    renderer.camera = Camera3D()

    for mode in ("perspective", "orthographic", "iso"):
        renderer.projection_mode = mode
        origin, direction = renderer.screen_ray(240.0, 180.0)
        assert np.all(np.isfinite(origin))
        assert np.all(np.isfinite(direction))
        assert np.isclose(np.linalg.norm(direction), 1.0)
        projected_target = renderer.project_world(tuple(float(value) for value in renderer.camera.target))
        assert projected_target is not None
        assert np.allclose(projected_target, (400.0, 300.0))

    renderer.projection_mode = "orthographic"
    _, left = renderer.screen_ray(100.0, 300.0)
    _, right = renderer.screen_ray(700.0, 300.0)
    assert np.allclose(left, right)

    renderer.projection_mode = "perspective"
    _, left = renderer.screen_ray(100.0, 300.0)
    _, right = renderer.screen_ray(700.0, 300.0)
    assert not np.allclose(left, right)


def test_piece_anchor_uses_pivot_box_on_tangent_axes_and_stays_outside_hit_face() -> None:
    definition = PieceDef("shape", (2, 3, 4))
    target = (5, 6, 7)

    assert piece_position_for_target(definition, 0, target, (1, 0, 0)) == (5, 5, 7)
    assert piece_position_for_target(definition, 0, target, (-1, 0, 0)) == (4, 5, 7)
    assert piece_position_for_target(definition, 0, target, (0, 1, 0)) == (5, 6, 7)
    assert piece_position_for_target(definition, 0, target, (0, -1, 0)) == (5, 4, 7)
    assert piece_position_for_target(definition, 0, target, (0, 0, 1)) == (5, 5, 7)
    assert piece_position_for_target(definition, 0, target, (0, 0, -1)) == (5, 5, 4)


def test_locked_plane_line_interpolates_without_holes() -> None:
    cells = grid_line_on_plane((0, 2, 0), (4, 2, 2), (0, 1, 0))

    assert cells[0] == (0, 2, 0)
    assert cells[-1] == (4, 2, 2)
    assert all(cell[1] == 2 for cell in cells)
    assert all(
        max(abs(right[0] - left[0]), abs(right[2] - left[2])) == 1
        for left, right in zip(cells, cells[1:])
    )


def test_shared_document_records_whole_3d_stroke_as_one_undo_step() -> None:
    app = QApplication.instance() or QApplication([])
    scene = Scene({"cube": PieceDef("cube", (1, 1, 1))})
    document = EditorDocument(scene, DEFAULT_PALETTE[0].id)
    front = EditorViewport(document, DEFAULT_PALETTE, allow_3d=False)
    view3d = EditorViewport(document, DEFAULT_PALETTE)
    view3d.set_view_mode(ViewMode.PERSPECTIVE)
    view3d.brush_stroke3d = BrushStroke3D(EditorTool.PLACE, (0, 1, 0), 0.0)
    scene_updates: list[None] = []
    document.scene_changed.connect(lambda: scene_updates.append(None))
    document.begin_stroke()

    view3d._apply_3d_cells(((0, 0, 0), (1, 0, 0), (2, 0, 0)))
    document.end_stroke()

    assert len(scene.pieces) == 3
    assert len(scene_updates) == 1
    front.undo()
    assert scene.pieces == []
    front.redo()
    assert len(scene.pieces) == 3
    front.deleteLater()
    view3d.deleteLater()
    app.processEvents()


def test_3d_attach_can_place_outside_reference_frame_while_front_place_cannot() -> None:
    app = QApplication.instance() or QApplication([])
    scene = Scene({"cube": PieceDef("cube", (1, 1, 1))})
    document = EditorDocument(scene, DEFAULT_PALETTE[0].id)
    view3d = EditorViewport(document, DEFAULT_PALETTE)
    view3d.set_view_mode(ViewMode.PERSPECTIVE)
    view3d.brush_stroke3d = BrushStroke3D(EditorTool.PLACE, (0, 1, 0), 0.0)

    view3d._apply_3d_cells(((80, 0, -70),))
    assert scene.piece_at((80, 0, -70)) is not None

    front = EditorViewport(document, DEFAULT_PALETTE, allow_3d=False)
    front._place((scene.max_x, 0))
    assert scene.piece_at((scene.max_x, 0, front.current_layer)) is None
    front.deleteLater()
    view3d.deleteLater()
    app.processEvents()


def test_invalid_attach_stroke_is_skipped_without_empty_undo_checkpoint() -> None:
    app = QApplication.instance() or QApplication([])
    existing = PieceInstance("cube", (0, 0, 0), 0, 0)
    scene = Scene({"cube": PieceDef("cube", (1, 1, 1))}, pieces=[existing])
    document = EditorDocument(scene, DEFAULT_PALETTE[0].id)
    viewport = EditorViewport(document, DEFAULT_PALETTE)
    viewport.brush_stroke3d = BrushStroke3D(EditorTool.PLACE, (0, 1, 0), 0.0)
    document.begin_stroke()

    viewport._apply_3d_cells(((0, 0, 0), (0, scene.bounds[1], 0)))
    document.end_stroke()

    assert scene.pieces == [existing]
    assert not document.undo()
    viewport.deleteLater()
    app.processEvents()


def test_3d_erase_and_paint_affect_whole_piece_once_per_stroke() -> None:
    app = QApplication.instance() or QApplication([])
    definition = PieceDef("wide", (2, 1, 1))
    original = PieceInstance("wide", (0, 0, 0), 0, 0)
    scene = Scene({"wide": definition}, pieces=[original])
    document = EditorDocument(scene, 3)
    viewport = EditorViewport(document, DEFAULT_PALETTE)

    viewport.brush_stroke3d = BrushStroke3D(EditorTool.PAINT, (0, 1, 0), 1.0)
    document.begin_stroke()
    viewport._apply_3d_cells(((0, 0, 0), (1, 0, 0)))
    document.end_stroke()
    assert scene.pieces[0].color_id == 3
    viewport.undo()
    assert scene.pieces[0].color_id == 0

    viewport.brush_stroke3d = BrushStroke3D(EditorTool.ERASE, (0, 1, 0), 1.0)
    document.begin_stroke()
    viewport._apply_3d_cells(((0, 0, 0), (1, 0, 0)))
    document.end_stroke()
    assert scene.pieces == []
    viewport.undo()
    assert len(scene.pieces) == 1
    viewport.deleteLater()
    app.processEvents()


def test_hover_preview_does_not_mutate_scene() -> None:
    class FakeRenderer:
        def resize(self, *_args) -> None:
            pass

        def raycast_grid(self, *_args, **_kwargs) -> RayHit:
            return RayHit(None, (0, 0, 0), (0, 1, 0), (0.5, 0.0, 0.5), 1.0, True)

    app = QApplication.instance() or QApplication([])
    scene = Scene({"cube": PieceDef("cube", (1, 1, 1))})
    viewport = EditorViewport(scene, DEFAULT_PALETTE)
    viewport.renderer3d = FakeRenderer()  # type: ignore[assignment]

    viewport._update_3d_hover(QPoint(10, 10), Qt.KeyboardModifier.NoModifier)

    assert scene.pieces == []
    assert viewport.render_preview3d is not None
    assert viewport.render_preview3d.instance.position == (0, 0, 0)
    viewport.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_R, Qt.KeyboardModifier.NoModifier))
    assert viewport.active_rotation == 45
    assert viewport.render_preview3d is not None
    assert viewport.render_preview3d.instance.rotation == 45
    assert scene.pieces == []
    source_color = viewport._color(viewport.active_color_id)
    preview_color = viewport.render_preview3d.color
    assert all(
        preview > source
        for preview, source in zip(
            preview_color[:3],
            (source_color.redF(), source_color.greenF(), source_color.blueF()),
        )
    )
    viewport.deleteLater()
    app.processEvents()


def test_rotated_ghost_rotation_is_used_for_3d_placement() -> None:
    app = QApplication.instance() or QApplication([])
    definition = PieceDef("bar", (2, 1, 1))
    scene = Scene({"bar": definition})
    viewport = EditorViewport(scene, DEFAULT_PALETTE)

    before = viewport._candidate_for_target((0, 0, 0), (0, 1, 0))
    viewport.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_R, Qt.KeyboardModifier.NoModifier))
    after = viewport._candidate_for_target((0, 0, 0), (0, 1, 0))
    assert before is not None and after is not None
    assert after.position == before.position
    assert after.rotation == 45
    viewport.brush_stroke3d = BrushStroke3D(EditorTool.PLACE, (0, 1, 0), 0.0)
    viewport._apply_3d_cells(((0, 0, 0),))

    assert len(scene.pieces) == 1
    assert scene.pieces[0].rotation == 45
    assert scene.cells_for(scene.pieces[0]) == ((-1, 0, -1), (0, 0, -1), (1, 0, -1), (-1, 0, 0), (0, 0, 0), (1, 0, 0), (-1, 0, 1), (0, 0, 1), (1, 0, 1))
    viewport.deleteLater()
    app.processEvents()


def test_viewport_scales_raycast_coordinates_for_high_dpi() -> None:
    class HiDpiViewport(EditorViewport):
        def devicePixelRatioF(self) -> float:  # noqa: N802
            return 2.0

    class FakeRenderer:
        def __init__(self) -> None:
            self.resize_call = None
            self.raycast_call = None

        def resize(self, *args) -> None:
            self.resize_call = args

        def raycast_grid(self, x, y, scene, include_ground=True):
            self.raycast_call = (x, y, scene, include_ground)
            return None

    app = QApplication.instance() or QApplication([])
    scene = Scene({"cube": PieceDef("cube", (1, 1, 1))})
    viewport = HiDpiViewport(scene, DEFAULT_PALETTE)
    viewport.resize(320, 240)
    renderer = FakeRenderer()
    viewport.renderer3d = renderer  # type: ignore[assignment]

    assert viewport._raycast_3d(QPoint(7, 11), include_ground=False) is None
    assert renderer.resize_call == (viewport.width(), viewport.height(), 2.0)
    assert renderer.raycast_call == (14.0, 22.0, scene, False)
    viewport.deleteLater()
    app.processEvents()


def test_editor_shortcuts_switch_shared_tool_state_and_rotate_selection() -> None:
    app = QApplication.instance() or QApplication([])
    cube = PieceInstance("cube", (0, 0, 0), 0, 0)
    viewport = EditorViewport(Scene({"cube": PieceDef("cube", (1, 1, 1))}, pieces=[cube]), DEFAULT_PALETTE)
    shortcuts = (
        (Qt.Key.Key_B, EditorTool.PLACE),
        (Qt.Key.Key_E, EditorTool.ERASE),
        (Qt.Key.Key_M, EditorTool.MOVE),
        (Qt.Key.Key_P, EditorTool.SELECT),
        (Qt.Key.Key_G, EditorTool.PAINT),
    )
    for key, expected in shortcuts:
        viewport.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))
        assert viewport.tool == expected
    viewport.select_only(cube.instance_id)
    viewport.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_R, Qt.KeyboardModifier.NoModifier))
    assert viewport.selected_pieces()[0].rotation == 45
    viewport.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_R, Qt.KeyboardModifier.ShiftModifier))
    assert viewport.selected_pieces()[0].rotation == 0
    assert viewport._effective_3d_tool(Qt.KeyboardModifier.ShiftModifier) == EditorTool.PAINT
    viewport.set_tool(EditorTool.PLACE)
    assert viewport._effective_3d_tool(Qt.KeyboardModifier.ShiftModifier) == EditorTool.ERASE
    viewport.deleteLater()
    app.processEvents()


def test_move_shortcuts_offset_multi_selection_on_each_axis_and_are_undoable() -> None:
    app = QApplication.instance() or QApplication([])
    first = PieceInstance("cube", (0, 1, 0), 0, 0)
    second = PieceInstance("cube", (2, 1, 0), 0, 0)
    viewport = EditorViewport(
        Scene({"cube": PieceDef("cube", (1, 1, 1))}, pieces=[first, second]),
        DEFAULT_PALETTE,
    )
    viewport.selection = {first.instance_id, second.instance_id}

    for key in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_PageUp):
        viewport.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))
    assert [piece.position for piece in viewport.selected_pieces()] == [(1, 2, 1), (3, 2, 1)]

    for key in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageDown):
        viewport.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))
    assert [piece.position for piece in viewport.selected_pieces()] == [(0, 1, 0), (2, 1, 0)]

    viewport.undo()
    assert [piece.position for piece in viewport.selected_pieces()] == [(0, 2, 0), (2, 2, 0)]
    viewport.deleteLater()
    app.processEvents()


def test_box_select_includes_hidden_depths_unless_shift_requests_visible_layer_only() -> None:
    app = QApplication.instance() or QApplication([])
    visible = PieceInstance("cube", (0, 0, 0), 0, 0)
    hidden = PieceInstance("cube", (0, 0, 2), 0, 0)
    outside = PieceInstance("cube", (3, 0, 0), 0, 0)
    viewport = EditorViewport(
        Scene({"cube": PieceDef("cube", (1, 1, 1))}, pieces=[visible, hidden, outside]),
        DEFAULT_PALETTE,
    )
    viewport.offset = QPointF(100.0, 100.0)
    viewport.cell_size = 20.0
    viewport.current_layer = 0
    viewport.box_start = QPoint(95, 75)
    viewport.box_end = QPoint(125, 105)

    viewport._complete_box_select()
    assert viewport.selection == {visible.instance_id, hidden.instance_id}

    viewport._complete_box_select(visible_only=True)
    assert viewport.selection == {visible.instance_id}
    viewport.deleteLater()
    app.processEvents()


def test_3d_box_select_can_select_through_or_only_visible_pieces() -> None:
    class FakeRenderer:
        def __init__(self, visible_id: str) -> None:
            self.visible_id = visible_id

        def project_world(self, point):
            return (100.0 + point[0] * 20.0, 100.0 - point[1] * 20.0)

        def resize(self, *_args) -> None:
            pass

        def raycast_grid(self, *_args, **_kwargs) -> RayHit:
            return RayHit(self.visible_id, (0, 0, 0), (0, 0, 1), (0.0, 0.0, 0.0), 1.0)

    app = QApplication.instance() or QApplication([])
    visible = PieceInstance("cube", (0, 0, 0), 0, 0)
    hidden = PieceInstance("cube", (0, 0, 2), 0, 0)
    outside = PieceInstance("cube", (3, 0, 0), 0, 0)
    viewport = EditorViewport(
        Scene({"cube": PieceDef("cube", (1, 1, 1))}, pieces=[visible, hidden, outside]),
        DEFAULT_PALETTE,
    )
    viewport.set_view_mode(ViewMode.PERSPECTIVE)
    viewport.renderer3d = FakeRenderer(visible.instance_id)  # type: ignore[assignment]
    viewport.box_start = QPoint(95, 75)
    viewport.box_end = QPoint(125, 105)

    viewport._complete_box_select_3d()
    assert viewport.selection == {visible.instance_id, hidden.instance_id}

    viewport._complete_box_select_3d(visible_only=True)
    assert viewport.selection == {visible.instance_id}
    viewport.deleteLater()
    app.processEvents()


def test_move_shortcut_rejects_entire_selection_when_any_piece_would_collide() -> None:
    app = QApplication.instance() or QApplication([])
    first = PieceInstance("cube", (0, 0, 0), 0, 0)
    second = PieceInstance("cube", (1, 0, 0), 0, 0)
    blocker = PieceInstance("cube", (2, 0, 0), 0, 0)
    viewport = EditorViewport(
        Scene({"cube": PieceDef("cube", (1, 1, 1))}, pieces=[first, second, blocker]),
        DEFAULT_PALETTE,
    )
    viewport.selection = {first.instance_id, second.instance_id}

    viewport.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier))

    assert [piece.position for piece in viewport.selected_pieces()] == [(0, 0, 0), (1, 0, 0)]
    viewport.deleteLater()
    app.processEvents()


def test_3d_right_mouse_only_orbits_and_middle_mouse_only_pans() -> None:
    class FakeCamera:
        def __init__(self) -> None:
            self.orbits: list[tuple[float, float]] = []
            self.pans: list[tuple[float, float]] = []

        def orbit(self, dx: float, dy: float) -> None:
            self.orbits.append((dx, dy))

        def pan(self, dx: float, dy: float) -> None:
            self.pans.append((dx, dy))

    class FakeRenderer:
        def __init__(self) -> None:
            self.camera = FakeCamera()

        def resize(self, *_args) -> None:
            pass

    def mouse_event(event_type, position, button, buttons):
        point = QPointF(*position)
        return QMouseEvent(
            event_type,
            point,
            point,
            point,
            button,
            buttons,
            Qt.KeyboardModifier.NoModifier,
        )

    app = QApplication.instance() or QApplication([])
    scene = Scene({"cube": PieceDef("cube", (1, 1, 1))})
    viewport = EditorViewport(scene, DEFAULT_PALETTE)
    renderer = FakeRenderer()
    viewport.renderer3d = renderer  # type: ignore[assignment]
    viewport.set_view_mode(ViewMode.PERSPECTIVE)

    viewport.mousePressEvent(
        mouse_event(QEvent.Type.MouseButtonPress, (10, 10), Qt.MouseButton.RightButton, Qt.MouseButton.RightButton)
    )
    viewport.mouseMoveEvent(
        mouse_event(QEvent.Type.MouseMove, (20, 16), Qt.MouseButton.NoButton, Qt.MouseButton.RightButton)
    )
    viewport.mouseReleaseEvent(
        mouse_event(QEvent.Type.MouseButtonRelease, (20, 16), Qt.MouseButton.RightButton, Qt.MouseButton.NoButton)
    )
    assert renderer.camera.orbits == [(10, 6)]
    assert renderer.camera.pans == []
    assert scene.pieces == []

    viewport.mousePressEvent(
        mouse_event(QEvent.Type.MouseButtonPress, (20, 16), Qt.MouseButton.MiddleButton, Qt.MouseButton.MiddleButton)
    )
    viewport.mouseMoveEvent(
        mouse_event(QEvent.Type.MouseMove, (24, 25), Qt.MouseButton.NoButton, Qt.MouseButton.MiddleButton)
    )
    viewport.mouseReleaseEvent(
        mouse_event(QEvent.Type.MouseButtonRelease, (24, 25), Qt.MouseButton.MiddleButton, Qt.MouseButton.NoButton)
    )
    assert renderer.camera.orbits == [(10, 6)]
    assert renderer.camera.pans == [(4, 9)]
    assert scene.pieces == []
    viewport.deleteLater()
    app.processEvents()
