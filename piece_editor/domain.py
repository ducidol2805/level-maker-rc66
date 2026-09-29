from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
import re
from typing import Any, Iterable
from uuid import uuid4

from PIL import Image


Vec3i = tuple[int, int, int]


def _vec3(value: Iterable[int], field_name: str) -> Vec3i:
    result = tuple(int(v) for v in value)
    if len(result) != 3:
        raise ValueError(f"{field_name} must contain exactly three integers")
    return result  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class PaletteColor:
    id: int
    name: str
    rgb: str

    def __post_init__(self) -> None:
        if not self.rgb.startswith("#") or len(self.rgb) != 7:
            raise ValueError(f"Invalid palette color: {self.rgb!r}")

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "rgb": self.rgb.upper()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PaletteColor":
        return cls(int(data["id"]), str(data["name"]), str(data["rgb"]))


@dataclass(frozen=True, slots=True)
class PieceDef:
    id: str
    size: Vec3i
    pivot: tuple[float, float, float] | None = None
    mesh: str | None = None
    allowed_rotations: tuple[int, ...] = (0, 45, 90, 135, 180, 225, 270, 315)
    category: str = "General"
    tags: tuple[str, ...] = ()
    source_dir: Path | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Piece id cannot be empty")
        if len(self.size) != 3 or any(v <= 0 for v in self.size):
            raise ValueError(f"Invalid size for {self.id}: {self.size}")
        pivot = self.pivot or tuple(value / 2.0 if value % 2 else 0.5 for value in self.size)
        if len(pivot) != 3:
            raise ValueError("pivot must contain exactly three values")
        object.__setattr__(self, "pivot", tuple(float(value) for value in pivot))
        rotations = tuple(dict.fromkeys(int(r) % 360 for r in self.allowed_rotations))
        if not rotations or any(r % 45 for r in rotations):
            raise ValueError("Allowed rotations must be non-empty 45-degree increments")
        object.__setattr__(self, "allowed_rotations", rotations)

    def rotated_size(self, rotation: int) -> Vec3i:
        return self.rotated_bounds(rotation)[1]

    def rotated_bounds(self, rotation: int) -> tuple[Vec3i, Vec3i]:
        angle = math.radians(rotation % 360)
        cosine = math.cos(angle)
        sine = math.sin(angle)
        pivot_x, _, pivot_z = self.pivot  # type: ignore[misc]
        corners = ((0.0, 0.0), (float(self.size[0]), 0.0), (0.0, float(self.size[2])), (float(self.size[0]), float(self.size[2])))
        rotated = tuple(
            (
                pivot_x + cosine * (x - pivot_x) + sine * (z - pivot_z),
                pivot_z - sine * (x - pivot_x) + cosine * (z - pivot_z),
            )
            for x, z in corners
        )
        minimum_x = math.floor(min(x for x, _ in rotated) + 1e-7)
        maximum_x = math.ceil(max(x for x, _ in rotated) - 1e-7)
        minimum_z = math.floor(min(z for _, z in rotated) + 1e-7)
        maximum_z = math.ceil(max(z for _, z in rotated) - 1e-7)
        offset = (minimum_x, 0, minimum_z)
        size = (maximum_x - minimum_x, self.size[1], maximum_z - minimum_z)
        return offset, size

    @property
    def volume(self) -> int:
        return self.size[0] * self.size[1] * self.size[2]

    @property
    def mesh_path(self) -> Path | None:
        if not self.mesh:
            return None
        path = Path(self.mesh)
        if not path.is_absolute() and self.source_dir:
            path = self.source_dir / path
        return path.resolve()

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "size": list(self.size),
            "pivot": list(self.pivot or ()),
            "allowed_rotations": list(self.allowed_rotations),
            "category": self.category,
            "tags": list(self.tags),
        }
        if self.mesh:
            data["mesh"] = self.mesh
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any], source_dir: Path | None = None) -> "PieceDef":
        raw_pivot = data.get("pivot")
        pivot = tuple(float(v) for v in raw_pivot) if raw_pivot is not None else None
        return cls(
            id=str(data["id"]),
            size=_vec3(data["size"], "size"),
            pivot=pivot,  # type: ignore[arg-type]
            mesh=str(data["mesh"]) if data.get("mesh") else None,
            allowed_rotations=tuple(
                int(v) for v in data.get("allowed_rotations", (0, 45, 90, 135, 180, 225, 270, 315))
            ),
            category=str(data.get("category", "General")),
            tags=tuple(str(v) for v in data.get("tags", ())),
            source_dir=source_dir,
        )


@dataclass(slots=True)
class PieceInstance:
    piece_id: str
    position: Vec3i
    rotation: int
    color_id: int
    group_id: str | None = None
    instance_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        self.position = _vec3(self.position, "position")
        self.rotation = int(self.rotation) % 360
        self.color_id = int(self.color_id)

    def to_dict(self, editor_metadata: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "piece_id": self.piece_id,
            "position": list(self.position),
            "rotation": self.rotation,
            "color_id": self.color_id,
        }
        if editor_metadata:
            data["instance_id"] = self.instance_id
            if self.group_id:
                data["group_id"] = self.group_id
        return data

    def to_game_dict(self) -> dict[str, Any]:
        return {
            "id": self.piece_id,
            "pos": list(self.position),
            "rot": self.rotation,
            "color": self.color_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PieceInstance":
        return cls(
            piece_id=str(data.get("piece_id", data.get("id"))),
            position=_vec3(data.get("position", data.get("pos")), "position"),
            rotation=int(data.get("rotation", data.get("rot", 0))),
            color_id=int(data.get("color_id", data.get("color", 0))),
            group_id=data.get("group_id"),
            instance_id=str(data.get("instance_id") or uuid4().hex),
        )


FALLBACK_PALETTE = (
    PaletteColor(0, "Red", "#E84A45"),
    PaletteColor(1, "Blue", "#3488D9"),
    PaletteColor(2, "Yellow", "#F2C94C"),
    PaletteColor(3, "Green", "#47A866"),
    PaletteColor(4, "Orange", "#ED8A34"),
    PaletteColor(5, "Purple", "#8A63C7"),
    PaletteColor(6, "White", "#ECECEC"),
    PaletteColor(7, "Dark", "#343840"),
)


def load_palette_image(path: str | Path) -> tuple[PaletteColor, ...]:
    """Extract opaque colors in row-major order, preserving stable color IDs."""
    with Image.open(path) as source:
        image = source.convert("RGBA")
        colors: list[PaletteColor] = []
        seen: set[str] = set()
        for y in range(image.height):
            for x in range(image.width):
                red, green, blue, alpha = image.getpixel((x, y))
                if alpha == 0:
                    continue
                value = f"#{red:02X}{green:02X}{blue:02X}"
                if value in seen:
                    continue
                seen.add(value)
                colors.append(PaletteColor(len(colors), f"Color {len(colors) + 1:02d}", value))
    if not colors:
        raise ValueError(f"Palette image contains no opaque colors: {path}")
    return tuple(colors)


def load_palette_order(path: str | Path) -> tuple[str, ...]:
    """Read comma, semicolon, or whitespace separated RGB hex values."""
    text = Path(path).read_text(encoding="utf-8-sig")
    tokens = [token for token in re.split(r"[,;\s]+", text.strip()) if token]
    colors: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        value = token.strip().lstrip("#").upper()
        if not re.fullmatch(r"[0-9A-F]{6}", value):
            raise ValueError(f"Invalid palette color in {path}: {token!r}")
        normalized = f"#{value}"
        if normalized in seen:
            raise ValueError(f"Duplicate palette color in {path}: {normalized}")
        seen.add(normalized)
        colors.append(normalized)
    if not colors:
        raise ValueError(f"Palette order file contains no colors: {path}")
    return tuple(colors)


def reorder_palette(
    palette: tuple[PaletteColor, ...], order: Iterable[str]
) -> tuple[PaletteColor, ...]:
    """Apply a preferred RGB order and append any image colors not listed."""
    by_rgb = {color.rgb.upper(): color for color in palette}
    ordered_rgb = [value.upper() for value in order]
    unknown = [value for value in ordered_rgb if value not in by_rgb]
    if unknown:
        raise ValueError(f"Palette order contains colors missing from Palette.png: {', '.join(unknown)}")
    ordered_rgb.extend(color.rgb.upper() for color in palette if color.rgb.upper() not in ordered_rgb)
    return tuple(
        PaletteColor(index, f"Color {index + 1:02d}", rgb)
        for index, rgb in enumerate(ordered_rgb)
    )


def load_default_palette() -> tuple[PaletteColor, ...]:
    palette_path = Path(__file__).resolve().parent.parent / "Palette.png"
    try:
        palette = load_palette_image(palette_path)
    except (OSError, ValueError):
        return FALLBACK_PALETTE
    order_path = palette_path.parent / "Endesga 32 Palette color palette.txt"
    if order_path.exists():
        try:
            return reorder_palette(palette, load_palette_order(order_path))
        except (OSError, ValueError):
            return palette
    return palette


DEFAULT_PALETTE = load_default_palette()

