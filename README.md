# Piece-Based Block Editor

A lightweight PySide6 editor for assembling static game pieces on an integer
grid and reconstructing a front-facing block model from a reference image.

## Run

```powershell
python -m pip install -r requirements.txt
python app.py
```

The default library is `library/`; additional piece folders can be opened from
**File > Open Piece Library**. Each piece folder contains a `piece.json` and an
optional mesh. Perspective mode renders actual binary FBX, GLB, GLTF, OBJ, PLY,
or STL geometry through ModernGL. Invalid or unsupported assets fall back to a
cuboid generated from the piece's declared grid size.

## Toolbox and views

Editing commands now live in a responsive Toolbox above the Palette. Buttons
fit the available panel width and height, with a centered icon and label below.
The first row is Brush, Eraser, Move, and Duplicate; the second row is Select,
Box Select, Mirror, and Paint. Toolbox artwork is loaded from `tool_icon/`;
Mirror uses the horizontal flip asset.

The Front Editor and 3D Brush are independent, resizable center panels backed
by one shared editor document: scene, selection, active tool, active piece,
active color, and undo history stay synchronized. A fresh or migrated layout
opens 3D across the center; toggle Front back on from the View menu. Later panel
visibility changes are restored normally.

Window geometry, maximize state, all splitter sizes, and Front/3D panel
visibility are saved automatically on exit and restored on the next launch.
Left and Properties widths are retained as fixed pixel sizes while the center
area absorbs window-width changes. Toolbox and Palette heights likewise stay
fixed while Piece Library absorbs height changes. Splitter handles remain
manually adjustable, and the new pixel sizes are saved on exit.

## Front controls

- Brush tool: left-click or drag to paint pieces continuously
- Eraser tool: left-click or drag to erase
- Right-click or drag: erase the piece under each grid cell
- Shift + click: add/remove a piece from selection
- Q / E: rotate selection
- Delete: delete selection
- Ctrl+D: duplicate selection
- Ctrl+Z / Ctrl+Y: undo / redo
- F / P: show or hide the Front / 3D panel
- H: center the Front origin near the bottom and reset the 3D camera
- Mouse wheel: zoom

## 3D Brush controls

- Left-click or drag: apply the active Attach, Erase, or Paint tool
- Right-drag: orbit
- Middle-drag: pan
- Mouse wheel: zoom
- T / R / G: Attach (Brush) / Erase / Paint
- Hold Shift with Attach or Erase: temporarily use the opposite operation
- Select: click to replace selection; Shift-click to toggle a piece
- H: reset the 3D camera

Orbit sensitivity is intentionally reduced for more precise camera control.
The 3D guide now uses a 1×1 horizontal floor grid, stronger 5-cell guide lines,
and world axes; the old upright grid and the Toolbox `Layer Z` control have been removed. Depth is editable on
both sides of the origin (`Z = -16` through `15` by default), while existing
projects using non-negative Z coordinates remain valid.

Attach places the selected Piece Library item against the pointed face. On an
empty scene or a missed object it uses the Y=0 construction floor. A drag locks
the first hit plane and fills intermediate cells so fast strokes do not leave
holes. Erase removes the whole piece under the brush, while Paint changes that
piece's `color_id`. A complete stroke is one undo step. The preview pass shows
valid placement in the active color, invalid placement in red, and whole-piece
Erase/Paint targets without modifying scene or instance-cache data. Ghost
geometry remains translucent but renders front faces only, preventing rear or
interior polygons from bleeding through the visible shell.

Move and Box Select remain Front-only in this milestone. If ModernGL cannot
initialize, 3D editing is disabled and the viewport reports the renderer error;
it never applies an edit through the fallback painter.

3D rendering includes depth testing, directional lighting, selection
highlighting, world axes, and uncluttered 5-cell major grids on the construction
plane and depth floor. Front mode retains the full 1-cell editing grid.

Piece shading uses a lightweight physically based path: linear-space albedo,
GGX specular, Schlick Fresnel, hemisphere ambient, key and fill lights, ACES
tone mapping, gamma correction, distance fog, and a 2048×2048 directional
shadow map with 3×3 PCF filtering.

Perspective rendering batches all instances of the same piece definition into
one GPU instanced draw. Model matrix, palette color, and selection state live in
a cached per-instance buffer that is only rebuilt when scene-visible data
changes. A floating panel inside the 3D viewport switches between **PBR +
Shadows** (`High`) and the faster **Simple Diffuse** (`Low`) shader. A segmented
view toggle selects **Perspective**, **Ortho**, or a fixed-angle **Iso** preset.
Orbiting from Iso automatically changes the projection state to Ortho. The same
panel reports source objects → cached batches, total rendered triangles, unique
cached triangles, and draw calls; it automatically hides in Front editing mode.
The compact 3D panel uses one shared six-column toggle grid, keeping the outer
edges of High/Low aligned with Perspective/Ortho/Iso.
The ModernGL viewport is resynchronized with the physical Qt framebuffer on
every frame, including after splitter resizing, DPI changes, and panel
hide/show transitions.

A complete mouse press/drag/release paint or erase stroke is recorded as one
undo step. Newly painted pieces are not selected.

New scenes extract their default color IDs from `Palette.png` in pixel order
(left-to-right, then top-to-bottom), then apply the preferred `color_id` order
from `Endesga 32 Palette color palette.txt`. Editing that TXT order takes
effect on the next app launch or New Project. Transparent and duplicate pixels
are ignored. The fixed construction canvas is 30×30 cells: X spans -15 through
14 and Y spans 0 through 29. Centered, bottom-aligned 10×10 and 20×20 guide
boxes are drawn more strongly than the normal grid; the 30×30 outer border is
strongest.

The 32-color palette is displayed as an 8×4 swatch grid at the top-left,
between the Toolbox and piece library. Swatches divide the available palette
width and height evenly. Drag either vertical splitter to resize the Toolbox,
Palette, or Piece Library; drag the main horizontal splitters to resize the
left column, both center views, and Properties.

AI Build defaults to nearest-neighbor sampling. When a reference image is
loaded, target width is calculated as `source width // scale`, with scale
defaulting to 4 and the result capped by the 30-cell canvas. Foreground pixels
are matched to the nearest available palette color in Lab color space; all 32
palette colors are enabled by default.

Projects preserve editor metadata such as selection groups. Game export emits
only piece ID, position, rotation, and color ID.
