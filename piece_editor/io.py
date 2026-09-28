from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .domain import PaletteColor, PieceInstance
from .scene import Scene


PROJECT_VERSION = 1


def save_project(
    path: str | Path,
    scene: Scene,
    palette: Iterable[PaletteColor],
    library_path: str | Path,
) -> None:
    payload = {
        "version": PROJECT_VERSION,
        "library": str(Path(library_path)),
        "bounds": list(scene.bounds),
        "palette": [color.to_dict() for color in palette],
        "pieces": [piece.to_dict(editor_metadata=True) for piece in scene.pieces],
    }
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_project_data(path: str | Path) -> dict[str, object]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if int(data.get("version", 0)) != PROJECT_VERSION:
        raise ValueError(f"Unsupported project version: {data.get('version')}")
    for key in ("library", "bounds", "palette", "pieces"):
        if key not in data:
            raise ValueError(f"Project is missing required field: {key}")
    return data


def export_game(path: str | Path, pieces: Iterable[PieceInstance]) -> None:
    payload = {"pieces": [piece.to_game_dict() for piece in pieces]}
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def import_game_data(path: str | Path) -> list[PieceInstance]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data.get("pieces"), list):
        raise ValueError("Game file must contain a pieces array")
    return [PieceInstance.from_dict(item) for item in data["pieces"]]

