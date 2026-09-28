from __future__ import annotations

import math
from dataclasses import replace
from enum import Enum

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen, QPolygonF, QWheelEvent
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .domain import PaletteColor, PieceInstance
from .renderer3d import ModernGLSceneRenderer, RenderStats
from .scene import PlacementError, Scene, SceneHistory


_UNCHANGED = object()


class RendererPanel(QFrame):
    shader_changed = Signal(str)
    projection_changed = Signal(str)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.projection_mode = "perspective"
        self.setObjectName("rendererPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            """
            QFrame#rendererPanel {
                background: rgba(18, 22, 28, 225);
                border: 1px solid #586577;
                border-radius: 5px;
            }
            QFrame#rendererPanel QLabel { background: transparent; }
            QFrame#rendererPanel QComboBox, QFrame#rendererPanel QPushButton {
                background: #303946;
                border: 1px solid #566273;
                padding: 4px 2px;
                font-size: 9px;
            }
            QFrame#rendererPanel QPushButton:checked {
                background: #2d78c4;
                border-color: #78b7f0;
                color: white;
            }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 7, 9, 8)
        layout.setSpacing(5)
        title = QLabel("3D Renderer")
        title.setStyleSheet("font-weight: 600; color: #f0f2f5;")
        layout.addWidget(title)
        self.stats_label = QLabel("OBJ 0 → 0 cached\nTris 0  •  Draws 0")
        self.stats_label.setStyleSheet("color: #c9d1dc;")
        layout.addWidget(self.stats_label)
        self.cache_label = QLabel("Cached tris 0")
        self.cache_label.setStyleSheet("color: #8f9bad;")
        layout.addWidget(self.cache_label)
        self.controls_grid = QGridLayout()
        self.controls_grid.setContentsMargins(0, 0, 0, 0)
        self.controls_grid.setHorizontalSpacing(3)
        self.controls_grid.setVerticalSpacing(4)
        for column in range(6):
            self.controls_grid.setColumnStretch(column, 1)
        self.controls_grid.addWidget(QLabel("Quality"), 0, 0, 1, 6)
        self.shader_group = QButtonGroup(self)
        self.shader_group.setExclusive(True)
        self.shader_buttons: dict[str, QPushButton] = {}
        for index, (label, mode) in enumerate((("High", "pbr"), ("Low", "simple"))):
            button = QPushButton(label)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, selected=mode: self.shader_changed.emit(selected))
            self.shader_group.addButton(button)
            self.shader_buttons[mode] = button
            self.controls_grid.addWidget(button, 1, index * 3, 1, 3)
        self.shader_buttons["pbr"].setChecked(True)

        self.controls_grid.addWidget(QLabel("View"), 2, 0, 1, 6)
        self.projection_group = QButtonGroup(self)
        self.projection_group.setExclusive(True)
        self.projection_buttons: dict[str, QPushButton] = {}
        for index, (label, mode) in enumerate(
            (("Perspective", "perspective"), ("Ortho", "orthographic"), ("Iso", "iso"))
        ):
            button = QPushButton(label)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, selected=mode: self.projection_changed.emit(selected))
            self.projection_group.addButton(button)
            self.projection_buttons[mode] = button
            self.controls_grid.addWidget(button, 3, index * 2, 1, 2)
        self.projection_buttons["perspective"].setChecked(True)
        layout.addLayout(self.controls_grid)
        self.setFixedWidth(210)
        self.adjustSize()

    def update_stats(self, stats: RenderStats) -> None:
        self.stats_label.setText(
            f"OBJ {stats.source_objects:,} → {stats.cached_objects:,} cached"
            f"\nTris {stats.triangles:,}  •  Draws {stats.draw_calls:,}"
        )
        self.cache_label.setText(f"Cached tris {stats.cached_triangles:,}")

    def show_error(self, message: str) -> None:
        self.stats_label.setText("3D renderer unavailable")
        self.cache_label.setText(message)

    def set_shader(self, mode: str) -> None:
        if mode in self.shader_buttons:
            self.shader_buttons[mode].setChecked(True)

    def set_projection(self, mode: str) -> None:
        self.projection_mode = mode
        if mode in self.projection_buttons:
            self.projection_buttons[mode].setChecked(True)


class EditorTool(str, Enum):
    PLACE = "Place"
    ERASE = "Eraser"
    SELECT = "Select"
    MOVE = "Move"
    BOX_SELECT = "Box Select"


class ViewMode(str, Enum):
    FRONT = "Front"
    PERSPECTIVE = "Perspective"


class EditorViewport(QOpenGLWidget):
    selection_changed = Signal()
    scene_changed = Signal()
    status_message = Signal(str)

    def __init__(
        self,
        scene: Scene,
        palette: tuple[PaletteColor, ...],
        parent: QWidget | None = None,
        *,
        allow_3d: bool = True,
        read_only: bool = False,
    ) -> None:
        super().__init__(parent)
        self.allow_3d = allow_3d
        self.read_only = read_only
        self.scene = scene
        self.history = SceneHistory(scene)
        self.palette = palette
        self.tool = EditorTool.PLACE
        self.view_mode = ViewMode.FRONT
        self.shading_mode = "pbr"
        self.projection_mode = "perspective"
        self.active_piece_id = next(iter(scene.piece_defs), "")
        self.active_color_id = palette[0].id
        self.current_layer = 0
        self.selection: set[str] = set()
        self.cell_size = 28.0
        self.offset = QPointF(54.0, 0.0)
        self.hover_cell: tuple[int, int] | None = None
        self.drag_start_cell: tuple[int, int] | None = None
        self.paint_button: Qt.MouseButton | None = None
        self.last_paint_cell: tuple[int, int] | None = None
        self._stroke_checkpointed = False
        self.box_start: QPoint | None = None
        self.box_end: QPoint | None = None
        self.pan_start: QPoint | None = None
        self.camera_drag_start: QPoint | None = None
        self.camera_drag_last: QPoint | None = None
        self.camera_drag_button: Qt.MouseButton | None = None
        self.camera_drag_moved = False
        self.renderer3d: ModernGLSceneRenderer | None = None
        self.renderer3d_error: str | None = None
        self._perspective_hits: list[tuple[QPolygonF, str]] = []
        self.renderer_panel = RendererPanel(self)
        self.renderer_panel.shader_changed.connect(self.set_shading_mode)
        self.renderer_panel.projection_changed.connect(self.set_projection_mode)
        self.renderer_panel.hide()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumSize(320, 320)

    def resizeEvent(self, event) -> None:  # noqa: N802
        if self.offset.y() == 0:
            self.offset.setY(self.height() - 54.0)
        panel_width = max(180, min(210, self.width() - 24))
        self.renderer_panel.setFixedWidth(panel_width)
        self.renderer_panel.adjustSize()
        self.renderer_panel.move(12, 12)
        self.renderer_panel.raise_()
        super().resizeEvent(event)

    def initializeGL(self) -> None:  # noqa: N802
        if not self.allow_3d:
            return
        try:
            self.renderer3d = ModernGLSceneRenderer()
            self.renderer3d.resize(self.width(), self.height(), self.devicePixelRatioF())
            self.renderer3d.reset_camera(self.scene)
            self.renderer3d.projection_mode = self.projection_mode
            self.renderer3d_error = None
        except Exception as exc:  # OpenGL errors vary by driver and platform.
            self.renderer3d = None
            self.renderer3d_error = str(exc)
            self.status_message.emit(f"3D renderer fallback: {exc}")

    def resizeGL(self, width: int, height: int) -> None:  # noqa: N802
        if self.renderer3d:
            self.renderer3d.resize(width, height, self.devicePixelRatioF())

    def set_scene(self, scene: Scene) -> None:
        self.scene = scene
        self.history = SceneHistory(scene)
        if self.renderer3d:
            self.renderer3d.reset_camera(scene)
        self.selection.clear()
        self.selection_changed.emit()
        self.scene_changed.emit()
        self.update()

    def set_palette(self, palette: tuple[PaletteColor, ...]) -> None:
        self.palette = palette
        if self.active_color_id not in {color.id for color in palette}:
            self.active_color_id = palette[0].id
        self.update()

    def set_tool(self, tool: EditorTool) -> None:
        self.tool = tool
        self.setCursor(
            Qt.CursorShape.CrossCursor
            if tool in (EditorTool.PLACE, EditorTool.ERASE)
            else Qt.CursorShape.ArrowCursor
        )
        self.update()

    def set_view_mode(self, mode: ViewMode) -> None:
        if mode == ViewMode.PERSPECTIVE and not self.allow_3d:
            return
        self.view_mode = mode
        self.renderer_panel.setVisible(mode == ViewMode.PERSPECTIVE)
        if mode == ViewMode.PERSPECTIVE:
            self.renderer_panel.raise_()
        self.status_message.emit(f"{mode.value} view")
        self.update()

    def set_shading_mode(self, mode: str) -> None:
        if mode not in {"pbr", "simple"}:
            raise ValueError(f"Unknown shading mode: {mode}")
        self.shading_mode = mode
        self.renderer_panel.set_shader(mode)
        label = "PBR + Shadows" if mode == "pbr" else "Simple Diffuse"
        self.status_message.emit(f"3D shader: {label}")
        self.update()

    def set_projection_mode(self, mode: str) -> None:
        if mode not in {"perspective", "orthographic", "iso"}:
            raise ValueError(f"Unknown projection mode: {mode}")
        self.projection_mode = mode
        self.renderer_panel.set_projection(mode)
        if self.renderer3d:
            self.renderer3d.projection_mode = mode
            if mode == "iso":
                self.renderer3d.camera.yaw = 45.0
                self.renderer3d.camera.pitch = 35.264
        label = {"perspective": "Perspective", "orthographic": "Ortho", "iso": "Iso"}[mode]
        self.status_message.emit(f"3D projection: {label}")
        self.update()

    def center_view(self) -> None:
        if self.view_mode == ViewMode.PERSPECTIVE and self.renderer3d:
            self.renderer3d.reset_camera(self.scene)
            if self.projection_mode == "iso":
                self.renderer3d.camera.yaw = 45.0
                self.renderer3d.camera.pitch = 35.264
            self.status_message.emit("3D camera reset")
        else:
            self.offset = QPointF(self.width() / 2.0, self.height() - 54.0)
            self.status_message.emit("View centered with origin near bottom")
        self.update()

    def set_layer(self, layer: int) -> None:
        self.current_layer = max(0, min(self.scene.bounds[2] - 1, layer))
        self.update()

    def selected_pieces(self) -> list[PieceInstance]:
        return [piece for piece in self.scene.pieces if piece.instance_id in self.selection]

    def select_only(self, instance_id: str | None) -> None:
        self.selection = {instance_id} if instance_id else set()
        self.selection_changed.emit()
        self.update()

    def delete_selection(self) -> None:
        if not self.selection:
            return
        self.history.checkpoint()
        self.scene.remove_many(self.selection)
        self.selection.clear()
        self._changed()

    def rotate_selection(self, delta: int) -> None:
        pieces = self.selected_pieces()
        if not pieces:
            return
        replacements: dict[str, PieceInstance] = {}
        for piece in pieces:
            definition = self.scene.require_definition(piece.piece_id)
            desired = (piece.rotation + delta) % 360
            if desired not in definition.allowed_rotations:
                allowed = definition.allowed_rotations
                direction = 1 if delta > 0 else -1
                index = allowed.index(piece.rotation) if piece.rotation in allowed else 0
                desired = allowed[(index + direction) % len(allowed)]
            replacements[piece.instance_id] = replace(piece, rotation=desired)
        self._apply_replacements(replacements)

    def recolor_selection(self, color_id: int) -> None:
        self.active_color_id = color_id
        pieces = self.selected_pieces()
        if not pieces:
            self.update()
            return
        replacements = {piece.instance_id: replace(piece, color_id=color_id) for piece in pieces}
        self._apply_replacements(replacements)

    def duplicate_selection(self) -> None:
        pieces = self.selected_pieces()
        if not pieces:
            return
        copies = [
            PieceInstance(
                piece.piece_id,
                (piece.position[0] + 1, piece.position[1], piece.position[2]),
                piece.rotation,
                piece.color_id,
                piece.group_id,
            )
            for piece in pieces
        ]
        try:
            # Validate as a batch against both the scene and other copies.
            simulation = Scene(self.scene.piece_defs, self.scene.bounds, list(self.scene.pieces))
            simulation.add_many(copies)
            self.history.checkpoint()
            self.scene.add_many(copies)
        except PlacementError as exc:
            self.status_message.emit(str(exc))
            return
        self.selection = {piece.instance_id for piece in copies}
        self._changed()

    def mirror_selection(self) -> None:
        pieces = self.selected_pieces()
        if not pieces:
            return
        left = min(piece.position[0] for piece in pieces)
        right = max(
            piece.position[0] + self.scene.require_definition(piece.piece_id).rotated_size(piece.rotation)[0]
            for piece in pieces
        )
        replacements: dict[str, PieceInstance] = {}
        for piece in pieces:
            definition = self.scene.require_definition(piece.piece_id)
            width = definition.rotated_size(piece.rotation)[0]
            rotation = (-piece.rotation) % 360
            if rotation not in definition.allowed_rotations:
                rotation = piece.rotation
            replacements[piece.instance_id] = replace(
                piece,
                position=(left + right - piece.position[0] - width, piece.position[1], piece.position[2]),
                rotation=rotation,
            )
        self._apply_replacements(replacements)

    def update_selected(
        self,
        *,
        position: tuple[int, int, int] | None = None,
        rotation: int | None = None,
        color_id: int | None = None,
        group_id: str | None | object = _UNCHANGED,
    ) -> None:
        pieces = self.selected_pieces()
        if not pieces:
            return
        if position is not None and len(pieces) != 1:
            self.status_message.emit("Position editing requires a single selected piece")
            return
        replacements: dict[str, PieceInstance] = {}
        for piece in pieces:
            replacements[piece.instance_id] = replace(
                piece,
                position=position if position is not None else piece.position,
                rotation=rotation if rotation is not None else piece.rotation,
                color_id=color_id if color_id is not None else piece.color_id,
                group_id=piece.group_id if group_id is _UNCHANGED else group_id,  # type: ignore[arg-type]
            )
        self._apply_replacements(replacements)

    def replace_all(self, pieces: list[PieceInstance]) -> bool:
        try:
            candidate = Scene(self.scene.piece_defs, self.scene.bounds, pieces)
        except PlacementError as exc:
            self.status_message.emit(str(exc))
            return False
        self.history.checkpoint()
        self.scene.clear()
        self.scene.add_many(candidate.pieces)
        self.selection.clear()
        self._changed()
        return True

    def undo(self) -> None:
        if self.history.undo():
            self.selection.intersection_update(piece.instance_id for piece in self.scene.pieces)
            self._changed()

    def redo(self) -> None:
        if self.history.redo():
            self.selection.intersection_update(piece.instance_id for piece in self.scene.pieces)
            self._changed()

    def paintGL(self) -> None:  # noqa: N802
        if self.view_mode == ViewMode.FRONT:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.fillRect(self.rect(), QColor("#20242b"))
            self._paint_front(painter)
            painter.end()
        elif self.renderer3d:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            native_painting = False
            try:
                painter.beginNativePainting()
                native_painting = True
                # Splitter restore and hide/show transitions do not reliably
                # emit resizeGL on every Qt/driver combination. Sync the
                # physical framebuffer size immediately before each 3D frame.
                self.renderer3d.resize(self.width(), self.height(), self.devicePixelRatioF())
                self.renderer3d.render(
                    self.scene,
                    self.palette,
                    self.selection,
                    self.defaultFramebufferObject(),
                    self.shading_mode,
                )
                self.renderer3d.context.finish()
                painter.endNativePainting()
                native_painting = False
                painter.end()
                self.renderer_panel.update_stats(self.renderer3d.stats)
                self.renderer_panel.raise_()
            except Exception as exc:
                if native_painting:
                    painter.endNativePainting()
                self.renderer3d_error = str(exc)
                painter.fillRect(self.rect(), QColor("#20242b"))
                self._paint_perspective(painter)
                painter.setPen(QColor("#ef8f8f"))
                painter.drawText(16, 48, f"OpenGL fallback: {exc}")
                painter.end()
                self.renderer_panel.show_error(str(exc))
        else:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.fillRect(self.rect(), QColor("#20242b"))
            self._paint_perspective(painter)
            if self.renderer3d_error:
                painter.setPen(QColor("#ef8f8f"))
                painter.drawText(16, 48, f"OpenGL unavailable: {self.renderer3d_error}")
                self.renderer_panel.show_error(self.renderer3d_error)
            painter.end()

    def _paint_front(self, painter: QPainter) -> None:
        self._paint_grid(painter)
        self._paint_size_guides(painter)
        pieces = sorted(self.scene.pieces, key=lambda p: (p.position[2], p.position[1], p.position[0]))
        for piece in pieces:
            definition = self.scene.require_definition(piece.piece_id)
            sx, sy, sz = definition.rotated_size(piece.rotation)
            if not (piece.position[2] <= self.current_layer < piece.position[2] + sz):
                continue
            rect = self._grid_rect(piece.position[0], piece.position[1], sx, sy)
            color = self._color(piece.color_id)
            if piece.position[2] != self.current_layer:
                color = color.darker(155)
            painter.fillRect(rect.adjusted(1, 1, -1, -1), color)
            selected = piece.instance_id in self.selection
            painter.setPen(QPen(QColor("#fff4a8") if selected else color.lighter(155), 3 if selected else 1))
            painter.drawRect(rect.adjusted(1, 1, -1, -1))
            if rect.width() > 40:
                painter.setPen(QColor("#15181d"))
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, definition.id)

        if self.tool == EditorTool.PLACE and self.hover_cell and self.active_piece_id:
            definition = self.scene.piece_defs.get(self.active_piece_id)
            if definition:
                sx, sy, _ = definition.rotated_size(definition.allowed_rotations[0])
                rect = self._grid_rect(*self.hover_cell, sx, sy)
                ghost = self._color(self.active_color_id)
                ghost.setAlpha(110)
                painter.fillRect(rect, ghost)
        if self.box_start and self.box_end:
            rect = QRectF(self.box_start, self.box_end).normalized()
            painter.fillRect(rect, QColor(80, 150, 255, 45))
            painter.setPen(QPen(QColor("#6ea8ff"), 1, Qt.PenStyle.DashLine))
            painter.drawRect(rect)

    def _paint_grid(self, painter: QPainter) -> None:
        cell = self.cell_size
        left = max(self.scene.min_x, math.floor((-self.offset.x()) / cell))
        right = min(self.scene.max_x, math.ceil((self.width() - self.offset.x()) / cell))
        bottom = max(0, math.floor((self.offset.y() - self.height()) / cell))
        top = min(self.scene.bounds[1], math.ceil(self.offset.y() / cell))
        painter.setPen(QPen(QColor("#343a44"), 1))
        for x in range(left, right + 1):
            px = self.offset.x() + x * cell
            painter.drawLine(QPointF(px, self.offset.y() - bottom * cell), QPointF(px, self.offset.y() - top * cell))
        for y in range(bottom, top + 1):
            py = self.offset.y() - y * cell
            painter.drawLine(QPointF(self.offset.x() + left * cell, py), QPointF(self.offset.x() + right * cell, py))
        painter.setPen(QPen(QColor("#657080"), 2))
        painter.drawLine(QPointF(self.offset.x(), 0), QPointF(self.offset.x(), self.height()))
        painter.drawLine(QPointF(0, self.offset.y()), QPointF(self.width(), self.offset.y()))

    def _paint_size_guides(self, painter: QPainter) -> None:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        guides = (
            (10, QColor("#566171"), 1.5),
            (20, QColor("#68778a"), 2.0),
            (30, QColor("#8292a8"), 2.5),
        )
        for size, color, width in guides:
            if size > self.scene.bounds[0] or size > self.scene.bounds[1]:
                continue
            left = -(size // 2)
            painter.setPen(QPen(color, width))
            painter.drawRect(self._grid_rect(left, 0, size, size))

    def _paint_perspective(self, painter: QPainter) -> None:
        self._perspective_hits.clear()
        origin = self.offset
        scale = max(8.0, self.cell_size * 0.65)
        pieces = sorted(self.scene.pieces, key=lambda p: (sum(p.position), p.position[1]))
        for piece in pieces:
            definition = self.scene.require_definition(piece.piece_id)
            sx, sy, sz = definition.rotated_size(piece.rotation)
            x, y, z = piece.position
            base = self._iso_point(x, y, z, origin, scale)
            vx = QPointF(scale, scale * 0.42)
            vz = QPointF(-scale, scale * 0.42)
            vy = QPointF(0, -scale)
            a = base
            b = base + vx * sx
            c = b + vy * sy
            d = base + vy * sy
            top = QPolygonF([d, c, c + vz * sz, d + vz * sz])
            front = QPolygonF([a, b, c, d])
            side = QPolygonF([b, b + vz * sz, c + vz * sz, c])
            color = self._color(piece.color_id)
            painter.setPen(QPen(QColor("#16191e"), 1))
            painter.setBrush(color)
            painter.drawPolygon(front)
            painter.setBrush(color.darker(125))
            painter.drawPolygon(side)
            painter.setBrush(color.lighter(125))
            painter.drawPolygon(top)
            if piece.instance_id in self.selection:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor("#fff4a8"), 3))
                painter.drawPolygon(front)
            self._perspective_hits.append((front.united(side).united(top), piece.instance_id))
        painter.setPen(QColor("#aab2bf"))
        painter.drawText(16, 26, "Perspective preview — switch to Front (F) to edit")

    @staticmethod
    def _iso_point(x: int, y: int, z: int, origin: QPointF, scale: float) -> QPointF:
        return origin + QPointF((x - z) * scale, (x + z) * scale * 0.42 - y * scale)

    def _grid_rect(self, x: int, y: int, width: int, height: int) -> QRectF:
        return QRectF(
            self.offset.x() + x * self.cell_size,
            self.offset.y() - (y + height) * self.cell_size,
            width * self.cell_size,
            height * self.cell_size,
        )

    def _screen_to_grid(self, point: QPoint) -> tuple[int, int]:
        x = math.floor((point.x() - self.offset.x()) / self.cell_size)
        y = math.floor((self.offset.y() - point.y()) / self.cell_size)
        return x, y

    def _color(self, color_id: int) -> QColor:
        color = next((item.rgb for item in self.palette if item.id == color_id), "#D0D0D0")
        return QColor(color)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.setFocus()
        if self.view_mode == ViewMode.PERSPECTIVE and event.button() in (
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.MiddleButton,
        ):
            point = event.position().toPoint()
            self.camera_drag_start = point
            self.camera_drag_last = point
            self.camera_drag_button = event.button()
            self.camera_drag_moved = False
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            self.pan_start = event.position().toPoint()
            return
        if self.view_mode == ViewMode.PERSPECTIVE:
            if event.button() != Qt.MouseButton.LeftButton:
                return
            for polygon, instance_id in reversed(self._perspective_hits):
                if polygon.containsPoint(event.position(), Qt.FillRule.OddEvenFill):
                    self.select_only(instance_id)
                    return
            return

        cell = self._screen_to_grid(event.position().toPoint())
        if event.button() == Qt.MouseButton.RightButton:
            self._begin_paint_stroke(Qt.MouseButton.RightButton, cell)
        elif event.button() != Qt.MouseButton.LeftButton:
            return
        elif self.tool == EditorTool.PLACE:
            self._begin_paint_stroke(Qt.MouseButton.LeftButton, cell)
        elif self.tool == EditorTool.ERASE:
            self._begin_paint_stroke(Qt.MouseButton.LeftButton, cell)
        elif self.tool == EditorTool.BOX_SELECT:
            self.box_start = event.position().toPoint()
            self.box_end = self.box_start
        else:
            piece = self.scene.piece_at((cell[0], cell[1], self.current_layer))
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                if piece:
                    if piece.instance_id in self.selection:
                        self.selection.remove(piece.instance_id)
                    else:
                        self.selection.add(piece.instance_id)
                    self.selection_changed.emit()
                    self.update()
            else:
                if not piece or piece.instance_id not in self.selection:
                    self.select_only(piece.instance_id if piece else None)
            if self.tool == EditorTool.MOVE and piece:
                self.drag_start_cell = cell

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        point = event.position().toPoint()
        if self.view_mode == ViewMode.PERSPECTIVE and self.camera_drag_last and self.renderer3d:
            delta = point - self.camera_drag_last
            if abs(point.x() - self.camera_drag_start.x()) + abs(point.y() - self.camera_drag_start.y()) > 3:
                self.camera_drag_moved = True
            if self.camera_drag_button == Qt.MouseButton.LeftButton:
                if self.projection_mode == "iso" and (delta.x() or delta.y()):
                    self.set_projection_mode("orthographic")
                self.renderer3d.camera.orbit(delta.x(), delta.y())
            elif self.camera_drag_button == Qt.MouseButton.MiddleButton:
                self.renderer3d.camera.pan(delta.x(), delta.y())
            self.camera_drag_last = point
            self.update()
            return
        if self.pan_start:
            delta = point - self.pan_start
            self.offset += QPointF(delta)
            self.pan_start = point
            self.update()
            return
        if self.box_start:
            self.box_end = point
            self.update()
            return
        if self.view_mode == ViewMode.FRONT:
            self.hover_cell = self._screen_to_grid(point)
            if self.paint_button is not None and event.buttons() & self.paint_button:
                self._continue_paint_stroke(self.hover_cell)
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self.view_mode == ViewMode.PERSPECTIVE and event.button() == self.camera_drag_button:
            if (
                event.button() == Qt.MouseButton.LeftButton
                and not self.camera_drag_moved
                and self.renderer3d
            ):
                ratio = self.devicePixelRatioF()
                instance_id = self.renderer3d.pick(
                    event.position().x() * ratio,
                    event.position().y() * ratio,
                    self.scene,
                )
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier and instance_id:
                    if instance_id in self.selection:
                        self.selection.remove(instance_id)
                    else:
                        self.selection.add(instance_id)
                    self.selection_changed.emit()
                    self.update()
                else:
                    self.select_only(instance_id)
            self.camera_drag_start = None
            self.camera_drag_last = None
            self.camera_drag_button = None
            self.camera_drag_moved = False
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            self.pan_start = None
            return
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton) and self.paint_button == event.button():
            self._end_paint_stroke()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self.box_start and self.box_end:
            self._complete_box_select()
            self.box_start = self.box_end = None
            self.update()
            return
        if self.drag_start_cell:
            end = self._screen_to_grid(event.position().toPoint())
            dx, dy = end[0] - self.drag_start_cell[0], end[1] - self.drag_start_cell[1]
            self.drag_start_cell = None
            if dx or dy:
                replacements = {
                    piece.instance_id: replace(
                        piece,
                        position=(piece.position[0] + dx, piece.position[1] + dy, piece.position[2]),
                    )
                    for piece in self.selected_pieces()
                }
                self._apply_replacements(replacements)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if self.view_mode == ViewMode.PERSPECTIVE and self.renderer3d:
            self.renderer3d.camera.zoom(event.angleDelta().y() / 120.0)
            self.update()
            return
        before = self._screen_to_grid(event.position().toPoint())
        factor = 1.12 if event.angleDelta().y() > 0 else 1 / 1.12
        self.cell_size = max(8.0, min(72.0, self.cell_size * factor))
        self.offset = QPointF(
            event.position().x() - before[0] * self.cell_size,
            event.position().y() + before[1] * self.cell_size,
        )
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_H:
            self.center_view()
        elif self.read_only:
            super().keyPressEvent(event)
        elif event.key() == Qt.Key.Key_Delete:
            self.delete_selection()
        elif event.key() == Qt.Key.Key_Q:
            self.rotate_selection(-90)
        elif event.key() == Qt.Key.Key_E:
            self.rotate_selection(90)
        elif event.key() == Qt.Key.Key_F and self.allow_3d:
            self.set_view_mode(ViewMode.FRONT)
        elif event.key() == Qt.Key.Key_P and self.allow_3d:
            self.set_view_mode(ViewMode.PERSPECTIVE)
        else:
            super().keyPressEvent(event)

    def _begin_paint_stroke(self, button: Qt.MouseButton, cell: tuple[int, int]) -> None:
        self.paint_button = button
        self.last_paint_cell = None
        self._stroke_checkpointed = False
        self._continue_paint_stroke(cell)

    def _continue_paint_stroke(self, cell: tuple[int, int]) -> None:
        if cell == self.last_paint_cell:
            return
        cells = (cell,) if self.last_paint_cell is None else self._grid_line(self.last_paint_cell, cell)[1:]
        for target in cells:
            self.last_paint_cell = target
            if self.paint_button == Qt.MouseButton.LeftButton and self.tool == EditorTool.PLACE:
                self._place(target)
            elif self.paint_button == Qt.MouseButton.RightButton or (
                self.paint_button == Qt.MouseButton.LeftButton and self.tool == EditorTool.ERASE
            ):
                self._erase_at(target)

    def _end_paint_stroke(self) -> None:
        self.paint_button = None
        self.last_paint_cell = None
        self._stroke_checkpointed = False

    def _checkpoint_paint_stroke(self) -> None:
        if not self._stroke_checkpointed:
            self.history.checkpoint()
            self._stroke_checkpointed = True

    @staticmethod
    def _grid_line(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
        """Return every grid cell crossed by a drag using Bresenham's algorithm."""
        x0, y0 = start
        x1, y1 = end
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        step_x = 1 if x0 < x1 else -1
        step_y = 1 if y0 < y1 else -1
        error = dx + dy
        cells: list[tuple[int, int]] = []
        while True:
            cells.append((x0, y0))
            if x0 == x1 and y0 == y1:
                return cells
            doubled = 2 * error
            if doubled >= dy:
                error += dy
                x0 += step_x
            if doubled <= dx:
                error += dx
                y0 += step_y

    def _place(self, cell: tuple[int, int]) -> None:
        definition = self.scene.piece_defs.get(self.active_piece_id)
        if not definition:
            self.status_message.emit("Select a piece from the library")
            return
        instance = PieceInstance(
            definition.id,
            (cell[0], cell[1], self.current_layer),
            definition.allowed_rotations[0],
            self.active_color_id,
        )
        try:
            self.scene.validate(instance)
            self._checkpoint_paint_stroke()
            self.scene.add(instance)
        except PlacementError as exc:
            self.status_message.emit(str(exc))
            return
        self.selection.clear()
        self._changed()

    def _erase_at(self, cell: tuple[int, int]) -> None:
        piece = self.scene.piece_at((cell[0], cell[1], self.current_layer))
        if piece is None:
            return
        self._checkpoint_paint_stroke()
        self.scene.remove_many((piece.instance_id,))
        self.selection.discard(piece.instance_id)
        self._changed()

    def _complete_box_select(self) -> None:
        assert self.box_start and self.box_end
        screen_rect = QRectF(self.box_start, self.box_end).normalized()
        selected: set[str] = set()
        for piece in self.scene.pieces:
            definition = self.scene.require_definition(piece.piece_id)
            sx, sy, sz = definition.rotated_size(piece.rotation)
            if piece.position[2] <= self.current_layer < piece.position[2] + sz:
                if screen_rect.intersects(self._grid_rect(piece.position[0], piece.position[1], sx, sy)):
                    selected.add(piece.instance_id)
        self.selection = selected
        self.selection_changed.emit()

    def _apply_replacements(self, replacements: dict[str, PieceInstance]) -> None:
        if not replacements:
            return
        try:
            simulation = Scene(self.scene.piece_defs, self.scene.bounds, list(self.scene.pieces))
            simulation.replace_many(replacements)
            self.history.checkpoint()
            self.scene.replace_many(replacements)
        except PlacementError as exc:
            self.status_message.emit(str(exc))
            return
        self._changed()

    def _changed(self) -> None:
        self.selection_changed.emit()
        self.scene_changed.emit()
        self.update()

