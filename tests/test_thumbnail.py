from __future__ import annotations

import numpy as np

from piece_editor.domain import PieceDef
from piece_editor.thumbnail import _thumbnail_orientation, front_face_box_edges


def test_box_outline_contains_only_unique_camera_facing_grid_edges() -> None:
    assert len(front_face_box_edges((1, 1, 1))) == 9
    assert len(front_face_box_edges((2, 1, 2))) == 21
    assert len(front_face_box_edges((3, 1, 1))) == 19
    assert len(front_face_box_edges((2, 1, 2))) == len(set(front_face_box_edges((2, 1, 2))))


def test_ramp_thumbnail_adds_180_degrees_to_counter_clockwise_orientation() -> None:
    ramp = PieceDef("ramp", (2, 1, 1), category="Ramps")
    points = np.asarray(((2.0, 0.0, 0.5), (1.0, 0.0, 1.0)))

    rotated = _thumbnail_orientation(points, ramp)

    assert np.allclose(rotated[0], (1.0, 0.0, -0.5))
    assert np.allclose(rotated[1], (1.5, 0.0, 0.5))
