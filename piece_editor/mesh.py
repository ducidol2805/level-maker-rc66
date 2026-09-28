from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .domain import PieceDef


@dataclass(frozen=True, slots=True)
class MeshData:
    """Non-indexed triangles ready for GPU upload."""

    positions: np.ndarray
    normals: np.ndarray
    source: str

    def interleaved(self) -> np.ndarray:
        return np.concatenate((self.positions, self.normals), axis=1).astype(np.float32, copy=False)


@dataclass(slots=True)
class _FbxNode:
    name: str
    properties: list[Any]
    children: list["_FbxNode"]


class MeshLoadError(ValueError):
    pass


def load_piece_mesh(definition: PieceDef) -> MeshData:
    path = definition.mesh_path
    if path and path.exists():
        try:
            suffix = path.suffix.lower()
            if suffix == ".fbx":
                positions = _load_binary_fbx(path)
            elif suffix in {".glb", ".gltf", ".obj", ".ply", ".stl"}:
                positions = _load_trimesh(path)
            else:
                raise MeshLoadError(f"Unsupported mesh format: {suffix}")
            positions = _fit_to_piece_bounds(positions, definition.size)
            return MeshData(positions, _flat_normals(positions), str(path))
        except (OSError, ValueError, RuntimeError, ImportError, struct.error, zlib.error):
            pass
    positions = _cuboid_triangles(definition.size)
    return MeshData(positions, _flat_normals(positions), "generated cuboid")


def _load_trimesh(path: Path) -> np.ndarray:
    import trimesh

    loaded = trimesh.load(path, force="scene")
    if isinstance(loaded, trimesh.Scene):
        if not loaded.geometry:
            raise MeshLoadError(f"Mesh file contains no geometry: {path}")
        mesh = loaded.to_mesh()
    else:
        mesh = loaded
    triangles = np.asarray(mesh.vertices, dtype=np.float64)[np.asarray(mesh.faces, dtype=np.int64)]
    return triangles.reshape((-1, 3)).astype(np.float32)


def _load_binary_fbx(path: Path) -> np.ndarray:
    data = path.read_bytes()
    if not data.startswith(b"Kaydara FBX Binary  \x00\x1a\x00"):
        raise MeshLoadError("Only binary FBX files are supported")
    if len(data) < 27:
        raise MeshLoadError("Truncated FBX header")
    version = struct.unpack_from("<I", data, 23)[0]
    offset = 27
    roots: list[_FbxNode] = []
    while offset < len(data):
        parsed = _parse_fbx_node(data, offset, version)
        if parsed is None:
            break
        node, offset = parsed
        roots.append(node)

    geometries = [node for root in roots for node in _walk_fbx(root) if node.name == "Geometry"]
    all_triangles: list[np.ndarray] = []
    for geometry in geometries:
        vertices_node = next((child for child in geometry.children if child.name == "Vertices"), None)
        polygon_node = next((child for child in geometry.children if child.name == "PolygonVertexIndex"), None)
        if not vertices_node or not polygon_node or not vertices_node.properties or not polygon_node.properties:
            continue
        vertices = np.asarray(vertices_node.properties[0], dtype=np.float64).reshape((-1, 3))
        polygon_indices = np.asarray(polygon_node.properties[0], dtype=np.int64)
        polygon: list[int] = []
        for raw_index in polygon_indices:
            index = int(raw_index)
            ended = index < 0
            polygon.append(-index - 1 if ended else index)
            if ended:
                if len(polygon) >= 3:
                    for corner in range(1, len(polygon) - 1):
                        all_triangles.append(vertices[[polygon[0], polygon[corner], polygon[corner + 1]]])
                polygon = []
    if not all_triangles:
        raise MeshLoadError(f"FBX contains no polygon mesh: {path}")
    return np.concatenate(all_triangles, axis=0).astype(np.float32)


def _parse_fbx_node(data: bytes, offset: int, version: int) -> tuple[_FbxNode, int] | None:
    wide = version >= 7500
    header_format = "<QQQB" if wide else "<IIIB"
    header_size = struct.calcsize(header_format)
    null_size = 25 if wide else 13
    if offset + header_size > len(data) or data[offset : offset + null_size] == bytes(null_size):
        return None
    end_offset, property_count, _property_bytes, name_length = struct.unpack_from(header_format, data, offset)
    if end_offset <= offset or end_offset > len(data):
        raise MeshLoadError("Invalid FBX node offset")
    cursor = offset + header_size
    name = data[cursor : cursor + name_length].decode("utf-8", errors="replace")
    cursor += name_length
    properties: list[Any] = []
    for _ in range(property_count):
        value, cursor = _parse_fbx_property(data, cursor)
        properties.append(value)
    children: list[_FbxNode] = []
    child_limit = int(end_offset) - null_size
    while cursor < child_limit:
        parsed = _parse_fbx_node(data, cursor, version)
        if parsed is None:
            break
        child, cursor = parsed
        children.append(child)
    return _FbxNode(name, properties, children), int(end_offset)


def _parse_fbx_property(data: bytes, offset: int) -> tuple[Any, int]:
    kind = chr(data[offset])
    offset += 1
    scalar_formats = {"Y": "<h", "C": "<?", "I": "<i", "F": "<f", "D": "<d", "L": "<q"}
    if kind in scalar_formats:
        fmt = scalar_formats[kind]
        return struct.unpack_from(fmt, data, offset)[0], offset + struct.calcsize(fmt)
    if kind in {"S", "R"}:
        length = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        raw = data[offset : offset + length]
        return (raw.decode("utf-8", errors="replace") if kind == "S" else raw), offset + length
    array_types = {
        "f": np.dtype("<f4"),
        "d": np.dtype("<f8"),
        "i": np.dtype("<i4"),
        "l": np.dtype("<i8"),
        "b": np.dtype("u1"),
        "c": np.dtype("u1"),
    }
    if kind in array_types:
        length, encoding, byte_length = struct.unpack_from("<III", data, offset)
        offset += 12
        raw = data[offset : offset + byte_length]
        if encoding == 1:
            raw = zlib.decompress(raw)
        elif encoding != 0:
            raise MeshLoadError(f"Unsupported FBX array encoding: {encoding}")
        array = np.frombuffer(raw, dtype=array_types[kind], count=length).copy()
        return array, offset + byte_length
    raise MeshLoadError(f"Unsupported FBX property type: {kind!r}")


def _walk_fbx(node: _FbxNode):
    yield node
    for child in node.children:
        yield from _walk_fbx(child)


def _fit_to_piece_bounds(positions: np.ndarray, size: tuple[int, int, int]) -> np.ndarray:
    positions = np.asarray(positions, dtype=np.float32).reshape((-1, 3)).copy()
    minimum = positions.min(axis=0)
    maximum = positions.max(axis=0)
    extent = maximum - minimum
    safe_extent = np.where(extent > 1e-7, extent, 1.0)
    positions = (positions - minimum) / safe_extent
    positions *= np.asarray(size, dtype=np.float32)
    return positions


def _flat_normals(positions: np.ndarray) -> np.ndarray:
    triangles = np.asarray(positions, dtype=np.float32).reshape((-1, 3, 3))
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = normals / np.where(lengths > 1e-8, lengths, 1.0)
    return np.repeat(normals, 3, axis=0).astype(np.float32)


def _cuboid_triangles(size: tuple[int, int, int]) -> np.ndarray:
    x, y, z = (float(value) for value in size)
    corners = np.array(
        ((0, 0, 0), (x, 0, 0), (x, y, 0), (0, y, 0), (0, 0, z), (x, 0, z), (x, y, z), (0, y, z)),
        dtype=np.float32,
    )
    faces = np.array(
        (
            (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
            (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
            (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
        ),
        dtype=np.int32,
    )
    return corners[faces].reshape((-1, 3))
