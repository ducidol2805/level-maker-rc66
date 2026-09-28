# Piece-Based Block Editor with AI Reconstruction

## 1. Goal

Build a lightweight custom editor in Python for creating destructible block-based objects.

The game uses flat block pieces without studs. Pieces attach to each other on a grid, similar to Minecraft-style construction, but each placed item comes from a custom piece library.

The editor is not a physics sandbox and does not need rigidbody simulation.

Primary goals:

- Load custom pieces from a local piece library.
- Place pieces manually on a grid.
- Select colors from a fixed palette.
- Keep all objects kinematic/static in the editor.
- Export piece position, rotation, piece ID, and color ID.
- Allow an AI agent to inspect a reference image and automatically reconstruct the object.
- Initial AI requirement: at minimum, reproduce the front-facing silhouette and main colors correctly.

---

# 2. Core Design Principle

This should not be a general-purpose voxel editor.

It is a:

> Piece-based construction editor + image-to-block reconstruction tool.

Avoid rebuilding Blender, MagicaVoxel, or a full game engine.

The editor should focus on:

- fast grid-based placement,
- custom piece support,
- predictable structured data,
- agent-friendly automation.

---

# 3. Recommended Stack

## UI

Use:

```text
PySide6
```

Avoid Tkinter.

Recommended layout:

```text
┌──────────────┬───────────────────────┬──────────────┐
│ Piece Library│                       │ Properties   │
│              │       Viewport        │              │
│ 1x1          │                       │ Position     │
│ 1x2          │                       │ Rotation     │
│ 1x3          │                       │ Color        │
│ Slope        │                       │ Layer        │
│ Wedge        │                       │ Group        │
│ ...          │                       │              │
├──────────────┴───────────────────────┴──────────────┤
│ Palette / Layers / AI Build                         │
└─────────────────────────────────────────────────────┘
```

## Rendering

Recommended:

```text
PySide6 + ModernGL
```

Alternative:

```text
PySide6 + pyqtgraph.opengl
```

ModernGL is preferable if the editor is expected to grow.

No game engine is required.

---

# 4. Scene Coordinate System

Use a simple integer grid.

```text
X = horizontal
Y = vertical
Z = depth
```

All placements snap to integer coordinates.

The primary editing view should be:

```text
Front Orthographic
```

Optional views:

```text
Front
Back
Left
Right
Top
Perspective
```

The front orthographic mode is the most important because the AI reconstruction system initially targets front-view matching.

---

# 5. Piece Library

Pieces are loaded from an external library rather than hardcoded into the editor.

Example directory:

```text
library/
    block_1x1/
        model.glb
        piece.json

    block_1x2/
        model.glb
        piece.json

    block_1x3/
        model.glb
        piece.json

    slope_2x1/
        model.glb
        piece.json

    wedge_2x2/
        model.glb
        piece.json
```

The editor scans the library at startup.

Adding a new piece should not require source-code changes.

---

# 6. Piece Definition

Example:

```json
{
    "id": "block_2x1",
    "size": [2, 1, 1],
    "pivot": [0, 0, 0],
    "mesh": "model.glb",
    "allowed_rotations": [0, 90, 180, 270]
}
```

Recommended fields:

```text
id
size
pivot
mesh
allowed_rotations
category
tags
```

Optional future fields:

```text
symmetry
connection_rules
preferred_orientation
solver_priority
```

---

# 7. Piece Instance

Each placed piece should contain only structured construction data.

Example:

```json
{
    "piece_id": "block_2x1",
    "position": [5, 3, 0],
    "rotation": 90,
    "color_id": 4
}
```

Suggested Python structure:

```python
class PieceInstance:
    piece_id: str
    position: tuple[int, int, int]
    rotation: int
    color_id: int
    group_id: str | None
```

No physics state is required.

---

# 8. Color System

Do not allow unrestricted arbitrary RGB colors during normal construction.

Use a fixed palette.

Example:

```json
[
    {
        "id": 0,
        "name": "Red",
        "rgb": "#E84A45"
    },
    {
        "id": 1,
        "name": "Blue",
        "rgb": "#3488D9"
    },
    {
        "id": 2,
        "name": "Yellow",
        "rgb": "#F2C94C"
    }
]
```

Scene data stores only:

```text
color_id
```

The game maps:

```text
color_id -> material
```

This makes the editor output compact and deterministic.

---

# 9. No Physics

The editor should not simulate physical behavior.

Do not use:

```text
rigidbody
gravity
collision response
joints
forces
constraints
```

All pieces are effectively kinematic/static.

Placement validation should be grid-based.

Use an occupancy structure such as:

```python
occupied[x][y][z]
```

Placement checks:

```text
Is the target cell available?
Does the new piece overlap another piece?
Is the piece inside editor bounds?
Are all occupied cells valid?
```

No physics raycast is required for construction logic.

---

# 10. Manual Editing Features

Minimum manual tools:

```text
Place
Select
Move
Delete
Rotate
Recolor
Duplicate
Mirror
Box Select
Undo
Redo
```

Useful hotkeys:

```text
Q / E       Rotate
Delete      Delete selection
Ctrl+D      Duplicate
Ctrl+Z      Undo
Ctrl+Y      Redo
F           Front view
P           Perspective
```

Pieces always snap to the construction grid.

---

# 11. Export Format

The game-side export should stay minimal.

Example:

```json
{
    "pieces": [
        {
            "id": "block_2x1",
            "pos": [5, 3, 0],
            "rot": 90,
            "color": 4
        },
        {
            "id": "block_1x1",
            "pos": [7, 3, 0],
            "rot": 0,
            "color": 2
        }
    ]
}
```

Required fields:

```text
piece_id
x
y
z
rotation
color_id
```

Optional editor-only metadata should not be required by the game runtime.

---

# 12. AI Reconstruction

The AI should not control the mouse.

Do not build the automation around visual clicking.

Use:

```text
Reference Image
      ↓
Vision Analysis
      ↓
Structured Shape Representation
      ↓
Piece Solver
      ↓
PieceInstance[]
      ↓
Editor Scene
```

The AI should generate structured data directly.

---

# 13. Important Separation of Responsibilities

The AI should decide:

```text
shape
silhouette
major regions
color regions
proportions
important visual features
```

The deterministic solver should decide:

```text
which piece to use
piece rotation
piece position
piece count
overlap prevention
tiling
grid validity
```

Do not make the AI manually output every piece unless necessary.

This separation improves:

```text
reliability
repeatability
token efficiency
debuggability
```

---

# 14. AI V1: Front-View Reconstruction

Initial requirement:

> Reproduce the front-facing appearance of the reference image.

Ignore complex 3D reconstruction in V1.

Treat the generated object as approximately:

```text
depth = 1
```

or a small fixed depth.

This turns the problem into a controlled 2D-to-piece reconstruction problem.

---

# 15. AI Pipeline

Recommended pipeline:

```text
SOURCE IMAGE
     │
     ▼
Object segmentation
     │
     ▼
Crop / normalize
     │
     ▼
Resize to target grid
     │
     ▼
Palette quantization
     │
     ▼
2D color mask
     │
     ▼
Piece solver
     │
     ▼
PieceInstance[]
     │
     ▼
Editor
```

---

# 16. Step A: Image to 2D Color Mask

The AI first produces a simplified block representation.

Example:

```text
............
....RR......
...RRRR.....
..BBBBBB....
..BBBBBB....
....BB......
...B..B.....
..B....B....
```

Where:

```text
. = empty
R = red palette ID
B = blue palette ID
```

Equivalent matrix representation:

```json
[
    [0, 0, 0, 0, 0],
    [0, 0, 2, 0, 0],
    [0, 2, 2, 2, 0]
]
```

The numeric value should correspond to a palette ID.

---

# 17. Image Simplification Controls

The AI Build panel should expose a few useful controls.

Example:

```text
AI Build
────────────────────────

[ Drop Reference Image ]

Target Width
[ 20 ]

Max Height
[ 30 ]

Depth
[ 1 ]

Simplification
[---------|---]

[x] Preserve silhouette
[x] Preserve major colors

[ Generate ]
```

Recommended parameters:

```text
target width
maximum height
fixed depth
simplification strength
palette size
silhouette priority
```

Avoid exposing too many low-level settings.

---

# 18. Palette Quantization

The reference image should be converted to the editor's existing palette.

Do not let AI invent new colors.

Pipeline:

```text
source RGB
    ↓
nearest allowed palette color
    ↓
color_id
```

Useful approaches:

```text
RGB distance
Lab color distance
Delta E
```

Lab/Delta E is preferable if color matching quality matters.

---

# 19. Step B: Piece Solver

After the AI creates the target 2D mask, the solver converts the mask into actual library pieces.

Example target:

```text
RRRR
RRRR
```

Available pieces:

```text
1x1
1x2
1x3
1x4
2x2
```

The solver may choose:

```text
2 x 2x2
```

instead of:

```text
8 x 1x1
```

The AI does not need to know the exact construction.

---

# 20. Solver Objectives

The solver can minimize a score such as:

```text
score =
    piece_count
  + seam_penalty
  + unsupported_penalty
  + mismatch_penalty
```

For V1, begin with a greedy solver.

Suggested order:

```text
largest valid piece first
↓
try allowed rotations
↓
fit exact same-color region
↓
fill remaining cells with smaller pieces
```

This is simple and fast.

---

# 21. Future Solver Upgrade

If greedy placement becomes insufficient, use:

```text
Google OR-Tools CP-SAT
```

The construction problem can be modeled as:

```text
2D tiling
exact cover
constraint optimization
```

Constraints may include:

```text
all occupied target cells covered
no overlaps
no placement outside target
matching color
allowed rotations only
```

Objective:

```text
minimize number of pieces
minimize seams
prefer selected piece types
```

---

# 22. Semantic Groups

The editor should support editor-only semantic groups.

Example:

```text
head
body
left_arm
right_arm
left_leg
right_leg
weapon
```

Piece instance:

```python
group_id = "left_arm"
```

This is especially useful for AI-assisted editing.

Examples:

```text
recolor body
move head
mirror left arm
regenerate right arm
make head wider
```

These group IDs do not need to be exported to the final game format.

---

# 23. AI Region Editing

After initial reconstruction, allow the user to select a region and prompt the agent.

Example:

```text
Select: HEAD

Prompt:
make the head wider
```

The agent should regenerate only the selected bounding region.

Other examples:

```text
make arms longer
make the body wider
reduce head height
change torso to red
make both legs symmetrical
```

Do not regenerate the entire model unless necessary.

---

# 24. Image Preview Mode

After generation, show:

```text
Original | Block Reconstruction
```

Useful buttons:

```text
Accept
Regenerate
Simplify More
Add Detail
```

This gives the user a quick review loop before committing the generated object.

---

# 25. Future 3D Reconstruction

Do not solve full 3D reconstruction in V1.

A future version may infer depth after the front view is correct.

Example:

```text
Front Image
    ↓
2D Reconstruction
    ↓
Semantic Regions
    ↓
Depth Assignment
    ↓
3D Extrusion
```

Example depth rules:

```text
head depth = 3
body depth = 3
arms depth = 2
legs depth = 2
```

This can later become AI-driven.

---

# 26. Suggested Project Architecture

```text
editor/
    app.py

    viewport/
        renderer.py
        camera.py
        grid.py

    tools/
        place_tool.py
        select_tool.py
        move_tool.py
        paint_tool.py

    ui/
        main_window.py
        piece_library_panel.py
        properties_panel.py
        palette_panel.py
        ai_panel.py

library/
    loader.py
    piece_def.py

scene/
    scene.py
    piece_instance.py
    occupancy.py
    selection.py

ai/
    image_analyzer.py
    segmentation.py
    mask_generator.py
    palette_mapper.py
    reconstruction.py

solver/
    greedy_solver.py
    placement.py
    optimizer.py

io/
    project_file.py
    export_game.py
    import_game.py
```

Keep AI logic separate from editor rendering.

Keep solver logic separate from AI reasoning.

---

# 27. Recommended V1 Scope

V1 should remain intentionally small.

Implement:

1. Front orthographic viewport.
2. Perspective preview.
3. Load custom piece library.
4. Place pieces.
5. Move pieces.
6. Delete pieces.
7. Rotate pieces.
8. Grid snapping.
9. Fixed color palette.
10. Recolor selected pieces.
11. Selection and multi-selection.
12. Undo/redo.
13. Save/load editor project.
14. Export piece ID, XYZ, rotation, and color ID.
15. Load a reference image.
16. Convert image to a simplified front-view color mask.
17. Run solver to convert mask into library pieces.
18. Preview generated construction.
19. Accept or regenerate.

Do not add physics.

Do not add complex animation.

Do not add full 3D AI reconstruction yet.

---

# 28. Development Order

Recommended implementation sequence:

## Phase 1 — Data

Build:

```text
PieceDef
PieceInstance
Scene
Palette
Project serialization
```

## Phase 2 — Basic Editor

Build:

```text
viewport
grid
camera
piece rendering
placement
selection
movement
rotation
deletion
```

## Phase 3 — Library

Build:

```text
piece folder scanning
thumbnail generation
piece categories
search/filter
```

## Phase 4 — Export

Build:

```text
JSON export
Unity-compatible format
validation
```

## Phase 5 — Image Reconstruction

Build:

```text
reference image import
segmentation
target grid generation
palette quantization
2D mask
```

## Phase 6 — Solver

Build:

```text
mask coverage
piece fitting
rotation testing
greedy optimization
```

## Phase 7 — Agent Integration

Build:

```text
AI Build panel
reference-image understanding
semantic regions
localized regeneration
```

---

# 29. Key Rule

The most important architectural rule is:

> AI should describe the target shape.  
> The solver should construct the shape using real game pieces.

Do not ask the vision model to manually place hundreds of exact pieces unless absolutely necessary.

This keeps the system stable and makes reconstruction independent from the exact contents of the piece library.

---

# 30. Final V1 Concept

The editor should behave like this:

```text
Manual workflow:

Choose piece
    ↓
Choose color
    ↓
Click grid
    ↓
Snap / rotate / move
    ↓
Export
```

AI workflow:

```text
Drop image
    ↓
Choose target size
    ↓
AI creates front-view blueprint
    ↓
Palette quantization
    ↓
Piece solver
    ↓
Preview
    ↓
Manual correction
    ↓
Export
```

Core concept:

> The AI creates a pixel-art-like construction blueprint, then a deterministic solver converts that blueprint into the real pieces from the project's custom library.

This should be the foundation of the editor.
