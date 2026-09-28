from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .domain import PieceDef, PieceInstance


EMPTY = -1


class SolverError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PlacementCandidate:
    definition: PieceDef
    rotation: int
    size: tuple[int, int, int]

    @property
    def volume(self) -> int:
        return self.size[0] * self.size[1] * self.size[2]


def connected_regions(mask: np.ndarray) -> np.ndarray:
    """Return stable 1-based connected region labels for non-empty mask cells."""
    if mask.ndim != 2:
        raise SolverError("Mask must be a two-dimensional array")
    height, width = mask.shape
    labels = np.zeros((height, width), dtype=np.int32)
    next_label = 1
    for row in range(height):
        for col in range(width):
            if mask[row, col] == EMPTY or labels[row, col]:
                continue
            color = int(mask[row, col])
            labels[row, col] = next_label
            queue = deque([(row, col)])
            while queue:
                current_row, current_col = queue.popleft()
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    rr, cc = current_row + dr, current_col + dc
                    if (
                        0 <= rr < height
                        and 0 <= cc < width
                        and not labels[rr, cc]
                        and int(mask[rr, cc]) == color
                    ):
                        labels[rr, cc] = next_label
                        queue.append((rr, cc))
            next_label += 1
    return labels


class GreedySolver:
    """Largest-first exact-cover solver for a palette-indexed front mask."""

    def __init__(self, piece_defs: Iterable[PieceDef]) -> None:
        candidates: list[PlacementCandidate] = []
        seen: set[tuple[str, tuple[int, int, int]]] = set()
        for definition in piece_defs:
            for rotation in definition.allowed_rotations:
                size = definition.rotated_size(rotation)
                key = (definition.id, size)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(PlacementCandidate(definition, rotation, size))
        self.candidates = sorted(
            candidates,
            key=lambda item: (-item.volume, -item.size[1], -item.size[0], item.definition.id),
        )

    def solve(self, mask: np.ndarray, depth: int = 1) -> list[PieceInstance]:
        if mask.ndim != 2 or not np.issubdtype(mask.dtype, np.integer):
            raise SolverError("Mask must be a two-dimensional integer array")
        if depth <= 0:
            raise SolverError("Depth must be positive")
        if not self.candidates:
            raise SolverError("Piece library is empty")

        height, width = mask.shape
        occupied = np.zeros((depth, height, width), dtype=bool)
        regions = connected_regions(mask)
        placements: list[PieceInstance] = []

        for z in range(depth):
            for row in range(height - 1, -1, -1):
                for x in range(width):
                    if int(mask[row, x]) == EMPTY or occupied[z, row, x]:
                        continue
                    color = int(mask[row, x])
                    candidate = self._best_fit(mask, occupied, x, row, z, color, depth)
                    if candidate is None:
                        raise SolverError(
                            f"No library piece can cover target cell x={x}, y={height - 1 - row}, z={z}"
                        )
                    sx, sy, sz = candidate.size
                    y = height - 1 - row
                    instance = PieceInstance(
                        piece_id=candidate.definition.id,
                        position=(x, y, z),
                        rotation=candidate.rotation,
                        color_id=color,
                        group_id=f"region_{int(regions[row, x])}",
                    )
                    placements.append(instance)
                    for dz in range(sz):
                        for dy in range(sy):
                            occupied[z + dz, row - dy, x : x + sx] = True

        target = np.broadcast_to(mask != EMPTY, (depth, height, width))
        if not np.array_equal(occupied, target):
            raise SolverError("Solver failed to cover the target exactly")
        return placements

    def _best_fit(
        self,
        mask: np.ndarray,
        occupied: np.ndarray,
        x: int,
        row: int,
        z: int,
        color: int,
        depth: int,
    ) -> PlacementCandidate | None:
        height, width = mask.shape
        for candidate in self.candidates:
            sx, sy, sz = candidate.size
            if x + sx > width or row - sy + 1 < 0 or z + sz > depth:
                continue
            target_slice = mask[row - sy + 1 : row + 1, x : x + sx]
            used_slice = occupied[z : z + sz, row - sy + 1 : row + 1, x : x + sx]
            if np.all(target_slice == color) and not np.any(used_slice):
                return candidate
        return None

