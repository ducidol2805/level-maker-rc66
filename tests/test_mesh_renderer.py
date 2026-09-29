from __future__ import annotations

from pathlib import Path

import numpy as np

from piece_editor.domain import PieceDef, PieceInstance
from piece_editor.library import PieceLibrary
from piece_editor.mesh import load_piece_mesh
from piece_editor.renderer3d import (
    Camera3D,
    ModernGLSceneRenderer,
    build_grid_lines,
    light_view_projection_matrix,
    model_matrix,
)
from piece_editor.scene import Scene


def test_existing_binary_fbx_loads_as_real_triangle_mesh() -> None:
    library = PieceLibrary.load(Path(__file__).resolve().parents[1] / "library")
    definition = library.pieces["blk_001"]

    mesh = load_piece_mesh(definition)

    assert mesh.source.endswith("BLK_001.fbx")
    assert mesh.positions.shape[0] > 36
    assert mesh.positions.shape == mesh.normals.shape
    assert np.all(np.isfinite(mesh.positions))
    assert np.allclose(mesh.positions.min(axis=0), (0, 0, 0))
    assert np.allclose(mesh.positions.max(axis=0), definition.size)


def test_missing_mesh_uses_cuboid_fallback() -> None:
    definition = PieceDef("missing", (2, 3, 1), mesh="not-there.glb")

    mesh = load_piece_mesh(definition)

    assert mesh.source == "generated cuboid"
    assert mesh.positions.shape == (36, 3)
    assert np.allclose(mesh.positions.max(axis=0), definition.size)


def test_rotated_model_matrix_stays_inside_scene_footprint() -> None:
    definition = PieceDef("bar", (2, 1, 1))
    local_corners = np.array(
        ((0, 0, 0, 1), (2, 0, 0, 1), (0, 1, 0, 1), (2, 1, 1, 1)),
        dtype=np.float32,
    )
    piece = PieceInstance("bar", (-3, 4, 2), 90, 0)

    world = (model_matrix(piece, definition) @ local_corners.T).T[:, :3]

    assert np.allclose(world.min(axis=0), (-3, 4, 1))
    assert np.allclose(world.max(axis=0), (-2, 5, 3))
    local_pivot = np.asarray((*definition.pivot, 1), dtype=np.float32)
    assert np.allclose((model_matrix(piece, definition) @ local_pivot)[:3], (-2.5, 4.5, 2.5))


def test_diagonal_model_matrix_is_shifted_into_positive_local_footprint() -> None:
    definition = PieceDef("bar", (2, 1, 1))
    local_corners = np.array(
        ((0, 0, 0, 1), (2, 0, 0, 1), (0, 1, 0, 1), (2, 1, 1, 1)),
        dtype=np.float32,
    )
    piece = PieceInstance("bar", (-3, 4, 2), 45, 0)

    world = (model_matrix(piece, definition) @ local_corners.T).T[:, :3]

    offset, size = definition.rotated_bounds(45)
    bounds_min = np.asarray(piece.position) + np.asarray(offset)
    bounds_max = bounds_min + np.asarray(size)
    assert np.all(world.min(axis=0) >= bounds_min - 1e-6)
    assert np.all(world.max(axis=0) <= bounds_max + 1e-6)
    local_pivot = np.asarray((*definition.pivot, 1), dtype=np.float32)
    assert np.allclose((model_matrix(piece, definition) @ local_pivot)[:3], (-2.5, 4.5, 2.5))


def test_3d_grid_contains_finite_colored_line_vertices() -> None:
    scene = Scene({"cube": PieceDef("cube", (1, 1, 1))})

    vertices = build_grid_lines(scene)

    assert vertices.ndim == 2 and vertices.shape[1] == 6
    assert vertices.shape[0] % 2 == 0
    assert np.all(np.isfinite(vertices))
    assert vertices[:, 2].min() == scene.min_z
    assert vertices[:, 2].max() == scene.max_z
    segments = vertices.reshape(-1, 2, 6)
    depth_lines = {
        int(start[2])
        for start, end in segments
        if start[1] == end[1] == 0
        and start[0] == scene.min_x
        and end[0] == scene.max_x
        and start[2] == end[2]
    }
    x_lines = {
        int(start[0])
        for start, end in segments
        if start[1] == end[1] == 0
        and start[2] == scene.min_z
        and end[2] == scene.max_z
        and start[0] == end[0]
    }
    assert depth_lines == set(range(scene.min_z, scene.max_z + 1))
    assert x_lines == set(range(scene.min_x, scene.max_x + 1))
    for start, end in segments:
        if start[1] != 0 or end[1] != 0:
            assert np.allclose(start[:3], (0, 0, 0))
            assert np.allclose(end[:3], (0, scene.bounds[1], 0))


def test_orbit_uses_reduced_sensitivity() -> None:
    camera = Camera3D()

    camera.orbit(10, 10)

    assert np.isclose(camera.yaw, 39.8)
    assert np.isclose(camera.pitch, 25.8)


def test_directional_shadow_matrix_is_finite_and_invertible() -> None:
    scene = Scene({"cube": PieceDef("cube", (1, 1, 1))})

    matrix = light_view_projection_matrix(scene)

    assert matrix.shape == (4, 4)
    assert np.all(np.isfinite(matrix))
    assert not np.isclose(np.linalg.det(matrix), 0.0)


def test_renderer_redetects_qt_framebuffer_after_physical_resize() -> None:
    class FakeFramebuffer:
        def __init__(self, size: tuple[int, int]) -> None:
            self.size = size
            self.used = False

        def use(self) -> None:
            self.used = True

    class FakeContext:
        def __init__(self) -> None:
            self.viewport = (0, 0, 1, 1)
            self.detected: list[int] = []
            self.framebuffer = FakeFramebuffer((600, 400))

        def detect_framebuffer(self, framebuffer_id: int) -> FakeFramebuffer:
            self.detected.append(framebuffer_id)
            return self.framebuffer

    renderer = object.__new__(ModernGLSceneRenderer)
    renderer.context = FakeContext()
    renderer.viewport_size = (300, 200)
    renderer.qt_framebuffer = FakeFramebuffer((300, 200))
    renderer.qt_framebuffer_id = 7

    renderer.resize(300, 200, 2.0)

    assert renderer.viewport_size == (600, 400)
    assert renderer.context.viewport == (0, 0, 600, 400)
    assert renderer.qt_framebuffer is None
    renderer._bind_qt_framebuffer(7)
    assert renderer.context.detected == [7]
    assert renderer.qt_framebuffer is renderer.context.framebuffer
    assert renderer.qt_framebuffer.used
