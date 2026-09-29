from __future__ import annotations

from functools import lru_cache

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QPolygonF

from .domain import PieceDef
from .mesh import load_piece_mesh


@lru_cache(maxsize=64)
def front_face_box_edges(
    size: tuple[int, int, int],
) -> tuple[tuple[tuple[int, int, int], tuple[int, int, int]], ...]:
    """Return the subdivided edges on the three camera-facing box faces."""
    edges: set[tuple[tuple[int, int, int], tuple[int, int, int]]] = set()

    def add(start: tuple[int, int, int], end: tuple[int, int, int]) -> None:
        edges.add((start, end) if start < end else (end, start))

    sx, sy, sz = size
    for z in range(sz + 1):
        for x in range(sx):
            add((x, sy, z), (x + 1, sy, z))
    for x in range(sx + 1):
        for z in range(sz):
            add((x, sy, z), (x, sy, z + 1))
    for z in range(sz + 1):
        for y in range(sy):
            add((sx, y, z), (sx, y + 1, z))
    for y in range(sy + 1):
        for z in range(sz):
            add((sx, y, z), (sx, y, z + 1))
    for y in range(sy + 1):
        for x in range(sx):
            add((x, y, sz), (x + 1, y, sz))
    for x in range(sx + 1):
        for y in range(sy):
            add((x, y, sz), (x, y + 1, sz))
    return tuple(sorted(edges))


def _thumbnail_orientation(points: np.ndarray, definition: PieceDef) -> np.ndarray:
    result = np.asarray(points, dtype=np.float64).copy()
    if definition.category.casefold() != "ramps":
        return result
    center_x = definition.size[0] * 0.5
    center_z = definition.size[2] * 0.5
    relative_x = result[..., 0] - center_x
    relative_z = result[..., 2] - center_z
    # Current art direction: 90° CCW, then another 180° around Y.
    result[..., 0] = center_x + relative_z
    result[..., 2] = center_z - relative_x
    return result


@lru_cache(maxsize=256)
def piece_thumbnail(definition: PieceDef, width: int = 64, height: int = 48) -> QPixmap:
    """Render a lightweight isometric thumbnail from the actual piece mesh."""
    mesh = load_piece_mesh(definition)
    triangles = _thumbnail_orientation(mesh.positions.reshape((-1, 3, 3)), definition)

    # Fixed isometric projection: X points right, Z left, Y upward.
    projected = np.empty((len(triangles), 3, 2), dtype=np.float64)
    projected[:, :, 0] = triangles[:, :, 0] - triangles[:, :, 2]
    projected[:, :, 1] = -triangles[:, :, 1] + 0.46 * (triangles[:, :, 0] + triangles[:, :, 2])
    minimum = projected.reshape((-1, 2)).min(axis=0)
    maximum = projected.reshape((-1, 2)).max(axis=0)
    extent = np.maximum(maximum - minimum, 1e-6)
    margin = 7.0
    scale = min((width - margin * 2) / extent[0], (height - margin * 2) / extent[1])
    offset = (np.asarray((width, height), dtype=np.float64) - extent * scale) * 0.5 - minimum * scale
    projected = projected * scale + offset

    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)

    light = np.asarray((-0.35, 0.8, 0.48), dtype=np.float64)
    light /= np.linalg.norm(light)
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    normal_lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    normals /= np.where(normal_lengths > 1e-8, normal_lengths, 1.0)
    brightness = np.clip(normals @ light, 0.0, 1.0) * 0.48 + 0.48
    depth = triangles.mean(axis=1) @ np.asarray((0.55, 0.35, 0.72), dtype=np.float64)

    for index in np.argsort(depth):
        shade = float(brightness[index])
        painter.setBrush(QColor(int(78 * shade), int(162 * shade), int(232 * shade)))
        painter.drawPolygon(QPolygonF([QPointF(float(x), float(y)) for x, y in projected[index]]))

    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(238, 244, 252, 72), 0.8))
    for start, end in front_face_box_edges(definition.size):
        points = _thumbnail_orientation(np.asarray((start, end), dtype=np.float64), definition)
        line = np.empty((2, 2), dtype=np.float64)
        line[:, 0] = points[:, 0] - points[:, 2]
        line[:, 1] = -points[:, 1] + 0.46 * (points[:, 0] + points[:, 2])
        line = line * scale + offset
        painter.drawLine(QPointF(float(line[0, 0]), float(line[0, 1])), QPointF(float(line[1, 0]), float(line[1, 1])))

    painter.end()
    return QPixmap.fromImage(image)
