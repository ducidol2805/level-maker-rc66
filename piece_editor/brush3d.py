from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .document import EditorTool
from .domain import PieceDef, Vec3i
from .renderer3d import RayHit


@dataclass(slots=True)
class BrushStroke3D:
    mode: EditorTool
    normal: Vec3i
    plane_coordinate: float
    last_cell: Vec3i | None = None
    affected_ids: set[str] = field(default_factory=set)
    placed_positions: set[Vec3i] = field(default_factory=set)


def piece_position_for_target(
    definition: PieceDef,
    rotation: int,
    target_cell: Vec3i,
    normal: Vec3i,
) -> Vec3i:
    size = definition.rotated_size(rotation)
    axis = normal_axis(normal)
    result = [target_cell[index] - size[index] // 2 for index in range(3)]
    if normal[axis] > 0:
        result[axis] = target_cell[axis]
    else:
        result[axis] = target_cell[axis] - size[axis] + 1
    return result[0], result[1], result[2]


def stroke_from_hit(mode: EditorTool, hit: RayHit) -> BrushStroke3D:
    axis = normal_axis(hit.normal)
    plane_coordinate = float(hit.cell[axis] + (1 if hit.normal[axis] > 0 and not hit.ground else 0))
    if hit.ground:
        plane_coordinate = 0.0
    return BrushStroke3D(mode, hit.normal, plane_coordinate)


def cell_on_stroke_plane(
    origin: np.ndarray,
    direction: np.ndarray,
    stroke: BrushStroke3D,
) -> Vec3i | None:
    axis = normal_axis(stroke.normal)
    component = float(direction[axis])
    if abs(component) < 1e-8:
        return None
    distance = (stroke.plane_coordinate - float(origin[axis])) / component
    if distance < 0.0:
        return None
    point = origin + direction * distance
    cell = [math.floor(float(value)) for value in point]
    if stroke.mode == EditorTool.PLACE:
        cell[axis] = int(stroke.plane_coordinate) if stroke.normal[axis] > 0 else int(stroke.plane_coordinate) - 1
    else:
        cell[axis] = int(stroke.plane_coordinate) - 1 if stroke.normal[axis] > 0 else int(stroke.plane_coordinate)
    return cell[0], cell[1], cell[2]


def grid_line_on_plane(start: Vec3i, end: Vec3i, normal: Vec3i) -> list[Vec3i]:
    axis = normal_axis(normal)
    tangent_axes = [index for index in range(3) if index != axis]
    u0, v0 = start[tangent_axes[0]], start[tangent_axes[1]]
    u1, v1 = end[tangent_axes[0]], end[tangent_axes[1]]
    du, dv = abs(u1 - u0), -abs(v1 - v0)
    step_u = 1 if u0 < u1 else -1
    step_v = 1 if v0 < v1 else -1
    error = du + dv
    cells: list[Vec3i] = []
    while True:
        cell = list(start)
        cell[tangent_axes[0]] = u0
        cell[tangent_axes[1]] = v0
        cells.append((cell[0], cell[1], cell[2]))
        if u0 == u1 and v0 == v1:
            return cells
        doubled = 2 * error
        if doubled >= dv:
            error += dv
            u0 += step_u
        if doubled <= du:
            error += du
            v0 += step_v


def normal_axis(normal: Vec3i) -> int:
    for axis, value in enumerate(normal):
        if value:
            return axis
    raise ValueError("Brush surface normal cannot be zero")
