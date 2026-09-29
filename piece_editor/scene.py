from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .domain import PieceDef, PieceInstance, Vec3i


class PlacementError(ValueError):
    pass


EDITOR_BOUNDS: Vec3i = (30, 30, 30)


@dataclass(slots=True)
class Scene:
    piece_defs: dict[str, PieceDef]
    bounds: Vec3i = EDITOR_BOUNDS
    pieces: list[PieceInstance] = field(default_factory=list)
    _occupied: dict[Vec3i, str] = field(default_factory=dict, init=False, repr=False)
    _by_id: dict[str, PieceInstance] = field(default_factory=dict, init=False, repr=False)
    _occupied_bounds: tuple[Vec3i, Vec3i] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if len(self.bounds) != 3 or any(value <= 0 for value in self.bounds):
            raise PlacementError(f"Scene bounds must contain three positive sizes: {self.bounds}")
        initial = list(self.pieces)
        self.pieces.clear()
        self._by_id.clear()
        self._occupied_bounds = None
        for piece in initial:
            self.add(piece)

    def cells_for(self, instance: PieceInstance) -> tuple[Vec3i, ...]:
        definition = self.require_definition(instance.piece_id)
        offset, (sx, sy, sz) = definition.rotated_bounds(instance.rotation)
        px, py, pz = instance.position
        return tuple(
            (px + offset[0] + dx, py + offset[1] + dy, pz + offset[2] + dz)
            for dz in range(sz)
            for dy in range(sy)
            for dx in range(sx)
        )

    def require_definition(self, piece_id: str) -> PieceDef:
        try:
            return self.piece_defs[piece_id]
        except KeyError as exc:
            raise PlacementError(f"Unknown piece id: {piece_id}") from exc

    @property
    def min_x(self) -> int:
        return -(self.bounds[0] // 2)

    @property
    def max_x(self) -> int:
        """Exclusive upper X bound."""
        return self.min_x + self.bounds[0]

    @property
    def min_z(self) -> int:
        """Inclusive centered depth bound."""
        return -(self.bounds[2] // 2)

    @property
    def max_z(self) -> int:
        """Exclusive centered depth bound."""
        return self.min_z + self.bounds[2]

    def validate(self, instance: PieceInstance, ignore_ids: Iterable[str] = ()) -> None:
        definition = self.require_definition(instance.piece_id)
        if instance.rotation not in definition.allowed_rotations:
            raise PlacementError(f"Rotation {instance.rotation} is not allowed for {instance.piece_id}")
        ignored = set(ignore_ids)
        _, by, _ = self.bounds
        for cell in self.cells_for(instance):
            if not 0 <= cell[1] < by:
                raise PlacementError(f"Piece is outside scene bounds at {cell}")
            occupant = self._occupied.get(cell)
            if occupant is not None and occupant not in ignored:
                raise PlacementError(f"Cell {cell} is already occupied")

    def validate_reference_bounds(self, instance: PieceInstance) -> None:
        for cell in self.cells_for(instance):
            if not (self.min_x <= cell[0] < self.max_x and self.min_z <= cell[2] < self.max_z):
                raise PlacementError(f"Piece is outside the 30x30 Front canvas at {cell}")

    @property
    def occupied_bounds(self) -> tuple[Vec3i, Vec3i] | None:
        """Inclusive minimum and exclusive maximum occupied cell bounds."""
        return self._occupied_bounds

    def _include_occupied_cell(self, cell: Vec3i) -> None:
        if self._occupied_bounds is None:
            self._occupied_bounds = (cell, tuple(value + 1 for value in cell))  # type: ignore[assignment]
            return
        minimum, maximum = self._occupied_bounds
        self._occupied_bounds = (
            tuple(min(minimum[index], cell[index]) for index in range(3)),
            tuple(max(maximum[index], cell[index] + 1) for index in range(3)),
        )  # type: ignore[assignment]

    def add(self, instance: PieceInstance) -> None:
        if instance.instance_id in self._by_id:
            raise PlacementError(f"Duplicate instance id: {instance.instance_id}")
        self.validate(instance)
        self.pieces.append(instance)
        self._by_id[instance.instance_id] = instance
        for cell in self.cells_for(instance):
            self._occupied[cell] = instance.instance_id
            self._include_occupied_cell(cell)

    def add_many(self, instances: Iterable[PieceInstance]) -> None:
        added: list[str] = []
        try:
            for instance in instances:
                self.add(instance)
                added.append(instance.instance_id)
        except PlacementError:
            self.remove_many(added)
            raise

    def remove_many(self, instance_ids: Iterable[str]) -> list[PieceInstance]:
        ids = set(instance_ids)
        removed = [piece for piece in self.pieces if piece.instance_id in ids]
        self.pieces[:] = [piece for piece in self.pieces if piece.instance_id not in ids]
        for instance_id in ids:
            self._by_id.pop(instance_id, None)
        self.rebuild_occupancy()
        return removed

    def clear(self) -> None:
        self.pieces.clear()
        self._occupied.clear()
        self._by_id.clear()
        self._occupied_bounds = None

    def replace_many(self, replacements: dict[str, PieceInstance]) -> None:
        original = list(self.pieces)
        candidate = [replacements.get(piece.instance_id, piece) for piece in self.pieces]
        self.pieces.clear()
        self._occupied.clear()
        self._by_id.clear()
        self._occupied_bounds = None
        try:
            for piece in candidate:
                self.add(piece)
        except PlacementError:
            self.pieces.clear()
            self._occupied.clear()
            self._by_id.clear()
            self._occupied_bounds = None
            for piece in original:
                self.add(piece)
            raise

    def rebuild_occupancy(self) -> None:
        self._occupied.clear()
        self._by_id = {piece.instance_id: piece for piece in self.pieces}
        self._occupied_bounds = None
        for piece in self.pieces:
            for cell in self.cells_for(piece):
                if cell in self._occupied:
                    raise PlacementError(f"Overlapping scene data at {cell}")
                self._occupied[cell] = piece.instance_id
                self._include_occupied_cell(cell)

    def piece_at(self, cell: Vec3i) -> PieceInstance | None:
        instance_id = self._occupied.get(cell)
        return self._by_id.get(instance_id) if instance_id else None

    def instance_id_at(self, cell: Vec3i) -> str | None:
        return self._occupied.get(cell)

    def piece_by_id(self, instance_id: str) -> PieceInstance | None:
        return self._by_id.get(instance_id)

    def snapshot(self) -> list[dict[str, object]]:
        return [piece.to_dict() for piece in self.pieces]

    def restore(self, snapshot: list[dict[str, object]]) -> None:
        restored = [PieceInstance.from_dict(item) for item in snapshot]
        old = list(self.pieces)
        self.pieces.clear()
        self._occupied.clear()
        self._by_id.clear()
        self._occupied_bounds = None
        try:
            for piece in restored:
                self.add(piece)
        except PlacementError:
            self.pieces.clear()
            self._occupied.clear()
            self._by_id.clear()
            self._occupied_bounds = None
            for piece in old:
                self.add(piece)
            raise


class SceneHistory:
    def __init__(self, scene: Scene, limit: int = 100) -> None:
        self.scene = scene
        self.limit = limit
        self._undo: list[list[dict[str, object]]] = []
        self._redo: list[list[dict[str, object]]] = []

    def checkpoint(self) -> None:
        self._undo.append(self.scene.snapshot())
        self._undo = self._undo[-self.limit :]
        self._redo.clear()

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.scene.snapshot())
        self.scene.restore(self._undo.pop())
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.scene.snapshot())
        self.scene.restore(self._redo.pop())
        return True

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

