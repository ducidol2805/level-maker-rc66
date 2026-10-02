from __future__ import annotations

from enum import Enum
from typing import Iterable

from PySide6.QtCore import QObject, Signal

from .domain import PieceInstance
from .scene import PlacementError, Scene, SceneHistory


class EditorTool(str, Enum):
    PLACE = "Place"
    ERASE = "Eraser"
    PAINT = "Paint"
    SELECT = "Select"
    MOVE = "Move"
    BOX_SELECT = "Box Select"


class EditorDocument(QObject):
    """Shared scene, edit state, selection, and history for every viewport."""

    scene_changed = Signal()
    selection_changed = Signal()
    tool_changed = Signal(object)
    active_piece_changed = Signal(str)
    active_rotation_changed = Signal(int)
    active_rotation_x_changed = Signal(int)
    active_color_changed = Signal(int)

    def __init__(self, scene: Scene, active_color_id: int = 0) -> None:
        super().__init__()
        self.scene = scene
        self.history = SceneHistory(scene)
        self.selection: set[str] = set()
        self.tool = EditorTool.PLACE
        self.active_piece_id = next(iter(scene.piece_defs), "")
        self.active_rotation = self._default_rotation(self.active_piece_id)
        self.active_rotation_x = self._default_rotation(self.active_piece_id)
        self.active_color_id = active_color_id
        self._stroke_active = False
        self._stroke_checkpointed = False

    def reset_scene(self, scene: Scene) -> None:
        old_active_piece = self.active_piece_id
        old_active_rotation = self.active_rotation
        old_active_rotation_x = self.active_rotation_x
        self.scene = scene
        self.history = SceneHistory(scene)
        self.selection.clear()
        if self.active_piece_id not in scene.piece_defs:
            self.active_piece_id = next(iter(scene.piece_defs), "")
        if self.active_rotation not in self._allowed_rotations(self.active_piece_id):
            self.active_rotation = self._default_rotation(self.active_piece_id)
        if self.active_rotation_x not in self._allowed_rotations(self.active_piece_id):
            self.active_rotation_x = self._default_rotation(self.active_piece_id)
        self._stroke_active = False
        self._stroke_checkpointed = False
        self.selection_changed.emit()
        if self.active_piece_id != old_active_piece:
            self.active_piece_changed.emit(self.active_piece_id)
        if self.active_rotation != old_active_rotation:
            self.active_rotation_changed.emit(self.active_rotation)
        if self.active_rotation_x != old_active_rotation_x:
            self.active_rotation_x_changed.emit(self.active_rotation_x)
        self.scene_changed.emit()

    def set_tool(self, tool: EditorTool) -> None:
        if self.tool == tool:
            return
        self.tool = tool
        self.tool_changed.emit(tool)

    def set_active_piece(self, piece_id: str) -> None:
        if piece_id == self.active_piece_id:
            return
        self.active_piece_id = piece_id
        if self.active_rotation not in self._allowed_rotations(piece_id):
            self.active_rotation = self._default_rotation(piece_id)
            self.active_rotation_changed.emit(self.active_rotation)
        if self.active_rotation_x not in self._allowed_rotations(piece_id):
            self.active_rotation_x = self._default_rotation(piece_id)
            self.active_rotation_x_changed.emit(self.active_rotation_x)
        self.active_piece_changed.emit(piece_id)

    def rotate_active_piece(self, delta: int) -> None:
        self._rotate_active_axis("y", delta)

    def rotate_active_piece_x(self, delta: int) -> None:
        self._rotate_active_axis("x", delta)

    def _rotate_active_axis(self, axis: str, delta: int) -> None:
        allowed = self._allowed_rotations(self.active_piece_id)
        if not allowed:
            return
        current = self.active_rotation_x if axis == "x" else self.active_rotation
        desired = (current + delta) % 360
        if desired not in allowed:
            direction = 1 if delta > 0 else -1
            index = allowed.index(current) if current in allowed else 0
            desired = allowed[(index + direction) % len(allowed)]
        if desired == current:
            return
        if axis == "x":
            self.active_rotation_x = desired
            self.active_rotation_x_changed.emit(desired)
        else:
            self.active_rotation = desired
            self.active_rotation_changed.emit(desired)

    def _allowed_rotations(self, piece_id: str) -> tuple[int, ...]:
        definition = self.scene.piece_defs.get(piece_id)
        return definition.allowed_rotations if definition else ()

    def _default_rotation(self, piece_id: str) -> int:
        allowed = self._allowed_rotations(piece_id)
        return allowed[0] if allowed else 0

    def set_active_color(self, color_id: int) -> None:
        if color_id == self.active_color_id:
            return
        self.active_color_id = color_id
        self.active_color_changed.emit(color_id)

    def set_selection(self, instance_ids: Iterable[str]) -> None:
        existing = {piece.instance_id for piece in self.scene.pieces}
        value = set(instance_ids) & existing
        if value == self.selection:
            return
        self.selection = value
        self.selection_changed.emit()

    def begin_stroke(self) -> None:
        self._stroke_active = True
        self._stroke_checkpointed = False

    def end_stroke(self) -> None:
        self._stroke_active = False
        self._stroke_checkpointed = False

    def _checkpoint(self) -> None:
        if self._stroke_active:
            if self._stroke_checkpointed:
                return
            self._stroke_checkpointed = True
        self.history.checkpoint()

    def add_instances(self, instances: Iterable[PieceInstance]) -> tuple[list[PieceInstance], list[PlacementError]]:
        added: list[PieceInstance] = []
        errors: list[PlacementError] = []
        checkpointed_for_call = False
        for instance in instances:
            try:
                if self.scene.piece_by_id(instance.instance_id) is not None:
                    raise PlacementError(f"Duplicate instance id: {instance.instance_id}")
                self.scene.validate(instance)
                if not checkpointed_for_call:
                    self._checkpoint()
                    checkpointed_for_call = True
                self.scene.add(instance)
                added.append(instance)
            except PlacementError as exc:
                errors.append(exc)
        if added:
            if self.selection:
                self.selection.clear()
                self.selection_changed.emit()
            self.scene_changed.emit()
        return added, errors

    def remove_ids(self, instance_ids: Iterable[str]) -> list[PieceInstance]:
        ids = {instance_id for instance_id in instance_ids if self.scene.piece_by_id(instance_id)}
        if not ids:
            return []
        self._checkpoint()
        removed = self.scene.remove_many(ids)
        old_selection = set(self.selection)
        self.selection.difference_update(ids)
        if self.selection != old_selection:
            self.selection_changed.emit()
        self.scene_changed.emit()
        return removed

    def replace_many(self, replacements: dict[str, PieceInstance]) -> bool:
        replacements = {
            instance_id: replacement
            for instance_id, replacement in replacements.items()
            if self.scene.piece_by_id(instance_id) != replacement
        }
        if not replacements:
            return False
        simulation = Scene(self.scene.piece_defs, self.scene.bounds, list(self.scene.pieces))
        simulation.replace_many(replacements)
        self._checkpoint()
        self.scene.replace_many(replacements)
        self.scene_changed.emit()
        return True

    def replace_all(self, pieces: list[PieceInstance]) -> None:
        candidate = Scene(self.scene.piece_defs, self.scene.bounds, pieces)
        self._checkpoint()
        self.scene.clear()
        self.scene.add_many(candidate.pieces)
        self.selection.clear()
        self.selection_changed.emit()
        self.scene_changed.emit()

    def undo(self) -> bool:
        if not self.history.undo():
            return False
        existing = {piece.instance_id for piece in self.scene.pieces}
        self.selection.intersection_update(existing)
        self.selection_changed.emit()
        self.scene_changed.emit()
        return True

    def redo(self) -> bool:
        if not self.history.redo():
            return False
        existing = {piece.instance_id for piece in self.scene.pieces}
        self.selection.intersection_update(existing)
        self.selection_changed.emit()
        self.scene_changed.emit()
        return True
