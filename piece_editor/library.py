from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .domain import PieceDef


@dataclass(slots=True)
class PieceLibrary:
    root: Path
    pieces: dict[str, PieceDef] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, root: str | Path) -> "PieceLibrary":
        library = cls(Path(root).resolve())
        if not library.root.exists():
            library.warnings.append(f"Library directory does not exist: {library.root}")
            return library
        for definition_path in sorted(library.root.rglob("piece.json")):
            try:
                data = json.loads(definition_path.read_text(encoding="utf-8"))
                piece = PieceDef.from_dict(data, definition_path.parent)
                if piece.id in library.pieces:
                    raise ValueError(f"duplicate piece id {piece.id!r}")
                library.pieces[piece.id] = piece
                mesh_path = piece.mesh_path
                if mesh_path and not mesh_path.exists():
                    library.warnings.append(f"{piece.id}: mesh not found: {mesh_path}")
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                library.warnings.append(f"{definition_path}: {exc}")
        if not library.pieces:
            library.warnings.append(f"No piece definitions found below {library.root}")
        return library

    def by_category(self) -> dict[str, list[PieceDef]]:
        result: dict[str, list[PieceDef]] = {}
        for piece in self.pieces.values():
            result.setdefault(piece.category, []).append(piece)
        for values in result.values():
            values.sort(key=lambda p: (p.size, p.id))
        return dict(sorted(result.items()))

