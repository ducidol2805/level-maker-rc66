from __future__ import annotations

import numpy as np

from piece_editor.domain import PieceDef
from piece_editor.solver import EMPTY, GreedySolver, connected_regions


def test_solver_prefers_largest_exact_piece() -> None:
    definitions = [
        PieceDef("square", (2, 2, 1)),
        PieceDef("bar", (2, 1, 1)),
        PieceDef("cube", (1, 1, 1)),
    ]
    mask = np.array([[3, 3], [3, 3]], dtype=np.int16)

    pieces = GreedySolver(definitions).solve(mask)

    assert len(pieces) == 1
    assert pieces[0].piece_id == "square"
    assert pieces[0].position == (0, 0, 0)
    assert pieces[0].color_id == 3


def test_solver_respects_color_and_empty_cells() -> None:
    definitions = [PieceDef("bar", (2, 1, 1)), PieceDef("cube", (1, 1, 1))]
    mask = np.array([[0, 1, EMPTY], [0, 0, EMPTY]], dtype=np.int16)

    pieces = GreedySolver(definitions).solve(mask)

    cells_by_color: dict[int, int] = {}
    for piece in pieces:
        cells_by_color[piece.color_id] = cells_by_color.get(piece.color_id, 0) + definitions[
            0 if piece.piece_id == "bar" else 1
        ].volume
    assert cells_by_color == {0: 3, 1: 1}


def test_connected_regions_separate_colors_and_islands() -> None:
    mask = np.array([[0, 0, EMPTY, 0], [1, 0, EMPTY, 0]], dtype=np.int16)
    labels = connected_regions(mask)

    assert labels[0, 0] == labels[0, 1] == labels[1, 1]
    assert labels[1, 0] != labels[0, 0]
    assert labels[0, 3] != labels[0, 0]

