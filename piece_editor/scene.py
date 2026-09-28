from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .domain import PieceDef, PieceInstance, Vec3i


class PlacementError(ValueError):
    pass


EDITOR_BOUNDS: Vec3i = (30, 30, 16)


@dataclass(slots=True)
class Scene:
    piece_defs: dict[str, PieceDef]
    bounds: Vec3i = EDITOR_BOUNDS
    pieces: list[PieceInstance] = field(default_factory=list)
    _occupied: dict[Vec3i, str] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        if len(self.bounds) != 3 or any(value <= 0 for value in self.bounds):
            raise PlacementError(f"Scene bounds must contain three positive sizes: {self.bounds}")
        initial = list(self.pieces)
        self.pieces.clear()
        for piece in initial:
            self.add(piece)

    def cells_for(self, instance: PieceInstance) -> tuple[Vec3i, ...]:
        definition = self.require_definition(instance.piece_id)
        sx, sy, sz = definition.rotated_size(instance.rotation)
        px, py, pz = instance.position
        return tuple(
            (px + dx, py + dy, pz + dz)
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

    def validate(self, instance: PieceInstance, ignore_ids: Iterable[str] = ()) -> None:
        definition = self.require_definition(instance.piece_id)
        if instance.rotation not in definition.allowed_rotations:
            raise PlacementError(f"Rotation {instance.rotation} is not allowed for {instance.piece_id}")
        ignored = set(ignore_ids)
        _, by, bz = self.bounds
        for cell in self.cells_for(instance):
            if not (self.min_x <= cell[0] < self.max_x and 0 <= cell[1] < by and 0 <= cell[2] < bz):
                raise PlacementError(f"Piece is outside scene bounds at {cell}")
            occupant = self._occupied.get(cell)
            if occupant is not None and occupant not in ignored:
                raise PlacementError(f"Cell {cell} is already occupied")

    def add(self, instance: PieceInstance) -> None:
        if any(p.instance_id == instance.instance_id for p in self.pieces):
            raise PlacementError(f"Duplicate instance id: {instance.instance_id}")
        self.validate(instance)
        self.pieces.append(instance)
        for cell in self.cells_for(instance):
            self._occupied[cell] = instance.instance_id

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
        self.rebuild_occupancy()
        return removed

    def clear(self) -> None:
        self.pieces.clear()
        self._occupied.clear()

    def replace_many(self, replacements: dict[str, PieceInstance]) -> None:
        original = list(self.pieces)
        candidate = [replacements.get(piece.instance_id, piece) for piece in self.pieces]
        self.pieces.clear()
        self._occupied.clear()
        try:
            for piece in candidate:
                self.add(piece)
        except PlacementError:
            self.pieces.clear()
            self._occupied.clear()
            for piece in original:
                self.add(piece)
            raise

    def rebuild_occupancy(self) -> None:
        self._occupied.clear()
        for piece in self.pieces:
            for cell in self.cells_for(piece):
                if cell in self._occupied:
                    raise PlacementError(f"Overlapping scene data at {cell}")
                self._occupied[cell] = piece.instance_id

    def piece_at(self, cell: Vec3i) -> PieceInstance | None:
        instance_id = self._occupied.get(cell)
        if not instance_id:
            return None
        return next((p for p in self.pieces if p.instance_id == instance_id), None)

    def piece_by_id(self, instance_id: str) -> PieceInstance | None:
        return next((p for p in self.pieces if p.instance_id == instance_id), None)

    def snapshot(self) -> list[dict[str, object]]:
        return [piece.to_dict() for piece in self.pieces]

    def restore(self, snapshot: list[dict[str, object]]) -> None:
        restored = [PieceInstance.from_dict(item) for item in snapshot]
        old = list(self.pieces)
        self.pieces.clear()
        self._occupied.clear()
        try:
            for piece in restored:
                self.add(piece)
        except PlacementError:
            self.pieces.clear()
            self._occupied.clear()
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

