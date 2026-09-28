from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QAction, QColor, QDragEnterEvent, QDropEvent, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .domain import DEFAULT_PALETTE, PaletteColor, PieceInstance, load_default_palette
from .io import export_game, import_game_data, load_project_data, save_project
from .library import PieceLibrary
from .reconstruction import ReconstructionResult, ReconstructionSettings, reconstruct_image
from .scene import EDITOR_BOUNDS, PlacementError, Scene
from .solver import GreedySolver, SolverError
from .viewport import EditorTool, EditorViewport, ViewMode


class ReferenceDrop(QFrame):
    path_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        self.label = QLabel("Drop reference image here")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setMinimumHeight(72)
        self.button = QPushButton("Browse…")
        self.button.clicked.connect(self.browse)
        layout.addWidget(self.label)
        layout.addWidget(self.button)
        self.path: str | None = None

    def browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Reference Image", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self.set_path(path)

    def set_path(self, path: str) -> None:
        self.path = path
        self.label.setText(Path(path).name)
        self.path_changed.emit(path)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls() and len(event.mimeData().urls()) == 1:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        path = event.mimeData().urls()[0].toLocalFile()
        if Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            self.set_path(path)
            event.acceptProposedAction()


class ReconstructionPreview(QDialog):
    def __init__(
        self,
        result: ReconstructionResult,
        palette: tuple[PaletteColor, ...],
        piece_count: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.action = "cancel"
        self.setWindowTitle("AI Build Preview")
        self.resize(850, 560)
        layout = QVBoxLayout(self)
        images = QHBoxLayout()
        self.source_label = self._image_panel("Original", QPixmap.fromImage(ImageQt(result.source)))
        self.result_label = self._image_panel("Block Reconstruction", QPixmap.fromImage(ImageQt(result.preview(palette))))
        images.addWidget(self.source_label)
        images.addWidget(self.result_label)
        layout.addLayout(images, 1)
        occupied = int((result.mask >= 0).sum())
        layout.addWidget(QLabel(f"Grid: {result.mask.shape[1]} × {result.mask.shape[0]}  •  {occupied} cells  •  {piece_count} pieces"))
        controls = QDialogButtonBox()
        for text, action in (
            ("Accept", "accept"),
            ("Regenerate", "regenerate"),
            ("Simplify More", "simplify"),
            ("Add Detail", "detail"),
            ("Cancel", "cancel"),
        ):
            button = controls.addButton(text, QDialogButtonBox.ButtonRole.AcceptRole if action == "accept" else QDialogButtonBox.ButtonRole.ActionRole)
            button.clicked.connect(lambda checked=False, selected=action: self._finish(selected))
        layout.addWidget(controls)

    def _image_panel(self, title: str, pixmap: QPixmap) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        label = QLabel(title)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image = QLabel()
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image.setStyleSheet("background: #252a32; border: 1px solid #3c4450;")
        image.setPixmap(pixmap.scaled(390, 440, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(label)
        layout.addWidget(image, 1)
        return panel

    def _finish(self, action: str) -> None:
        self.action = action
        self.accept() if action != "cancel" else self.reject()


class PieceLibraryPanel(QWidget):
    piece_selected = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(QLabel("Piece Library"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search pieces…")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.currentItemChanged.connect(self._selected)
        layout.addWidget(self.list, 1)
        self.library: PieceLibrary | None = None

    def set_library(self, library: PieceLibrary) -> None:
        self.library = library
        self.list.clear()
        for category, pieces in library.by_category().items():
            header = QListWidgetItem(category)
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setForeground(QColor("#8f9aa9"))
            self.list.addItem(header)
            for piece in pieces:
                item = QListWidgetItem(f"  {piece.id}  ({piece.size[0]}×{piece.size[1]}×{piece.size[2]})")
                item.setData(Qt.ItemDataRole.UserRole, piece.id)
                item.setToolTip("Tags: " + ", ".join(piece.tags))
                self.list.addItem(item)
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(Qt.ItemDataRole.UserRole):
                self.list.setCurrentItem(item)
                break

    def _filter(self, text: str) -> None:
        query = text.strip().lower()
        for row in range(self.list.count()):
            item = self.list.item(row)
            piece_id = item.data(Qt.ItemDataRole.UserRole)
            if piece_id:
                definition = self.library.pieces[piece_id] if self.library else None
                haystack = " ".join((piece_id, definition.category, *definition.tags)).lower() if definition else piece_id
                item.setHidden(query not in haystack)

    def _selected(self, item: QListWidgetItem | None) -> None:
        if item and item.data(Qt.ItemDataRole.UserRole):
            self.piece_selected.emit(item.data(Qt.ItemDataRole.UserRole))


class PropertiesPanel(QWidget):
    apply_requested = Signal(object)

    def __init__(self, palette: tuple[PaletteColor, ...]) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.title = QLabel("Properties — no selection")
        layout.addWidget(self.title)
        form = QFormLayout()
        self.position = [QSpinBox() for _ in range(3)]
        for axis, spin in zip("XYZ", self.position):
            spin.setRange(0, 1024)
            form.addRow(axis, spin)
        self.position[0].setRange(-1024, 1024)
        self.rotation = QComboBox()
        self.rotation.addItems(["0", "90", "180", "270"])
        form.addRow("Rotation", self.rotation)
        self.color = QComboBox()
        self.set_palette(palette)
        form.addRow("Color", self.color)
        self.group = QLineEdit()
        self.group.setPlaceholderText("Optional semantic group")
        form.addRow("Group", self.group)
        layout.addLayout(form)
        self.apply = QPushButton("Apply")
        self.apply.clicked.connect(self._emit)
        layout.addWidget(self.apply)
        layout.addStretch()
        self.setEnabled(False)

    def set_scene_bounds(self, scene: Scene) -> None:
        self.position[0].setRange(scene.min_x, scene.max_x - 1)
        self.position[1].setRange(0, scene.bounds[1] - 1)
        self.position[2].setRange(0, scene.bounds[2] - 1)

    def set_palette(self, palette: tuple[PaletteColor, ...]) -> None:
        self.color.clear()
        for color in palette:
            self.color.addItem(color.name, color.id)

    def show_selection(self, pieces: list[PieceInstance]) -> None:
        self.setEnabled(bool(pieces))
        if not pieces:
            self.title.setText("Properties — no selection")
            return
        first = pieces[0]
        self.title.setText(f"Properties — {len(pieces)} selected")
        for spin, value in zip(self.position, first.position):
            QSignalBlocker(spin)
            spin.setValue(value)
        self.position[0].setEnabled(len(pieces) == 1)
        self.position[1].setEnabled(len(pieces) == 1)
        self.position[2].setEnabled(len(pieces) == 1)
        self.rotation.setCurrentText(str(first.rotation))
        color_index = self.color.findData(first.color_id)
        if color_index >= 0:
            self.color.setCurrentIndex(color_index)
        self.group.setText(first.group_id or "")

    def _emit(self) -> None:
        values = {
            "position": tuple(spin.value() for spin in self.position) if self.position[0].isEnabled() else None,
            "rotation": int(self.rotation.currentText()),
            "color_id": int(self.color.currentData()),
            "group_id": self.group.text().strip() or None,
        }
        self.apply_requested.emit(values)


class PalettePanel(QWidget):
    color_selected = Signal(int)

    def __init__(self, palette: tuple[PaletteColor, ...]) -> None:
        super().__init__()
        self.selected_color_id = palette[0].id if palette else -1
        self.buttons: dict[int, QPushButton] = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 4)
        outer.setSpacing(4)
        outer.addWidget(QLabel("Palette"))
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(3)
        self.grid.setVerticalSpacing(3)
        for column in range(8):
            self.grid.setColumnStretch(column, 1)
        for row in range(4):
            self.grid.setRowStretch(row, 1)
        outer.addLayout(self.grid)
        self.setMinimumHeight(90)
        self.set_palette(palette)

    def set_palette(self, palette: tuple[PaletteColor, ...]) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.buttons.clear()
        if palette and self.selected_color_id not in {color.id for color in palette}:
            self.selected_color_id = palette[0].id
        for index, color in enumerate(palette):
            button = QPushButton("")
            button.setMinimumSize(12, 12)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            button.setToolTip(f"{color.name} — ID {color.id} — {color.rgb}")
            button.clicked.connect(lambda checked=False, color_id=color.id: self._select_color(color_id))
            self.buttons[color.id] = button
            self.grid.addWidget(button, index // 8, index % 8)
        self._refresh_selection()

    def _select_color(self, color_id: int) -> None:
        self.selected_color_id = color_id
        self._refresh_selection()
        self.color_selected.emit(color_id)

    def _refresh_selection(self) -> None:
        for color_id, button in self.buttons.items():
            border = "3px solid #FFFFFF" if color_id == self.selected_color_id else "1px solid #15181d"
            color = button.toolTip().rsplit(" — ", 1)[-1]
            button.setStyleSheet(f"background: {color}; border: {border}; padding: 0;")


class AIBuildPanel(QWidget):
    generate_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        self.drop = ReferenceDrop()
        layout.addWidget(self.drop, 1)
        form = QFormLayout()
        self.width = QSpinBox()
        self.width.setRange(1, 30)
        self.width.setValue(20)
        self.height = QSpinBox()
        self.height.setRange(4, 30)
        self.height.setValue(30)
        self.depth = QSpinBox()
        self.depth.setRange(1, 8)
        self.depth.setValue(1)
        self.scale = QSpinBox()
        self.scale.setRange(1, 64)
        self.scale.setValue(4)
        self.scale.setToolTip("Source pixels per one target grid cell")
        self.sample_mode = QComboBox()
        self.sample_mode.addItem("Nearest Neighbor", "nearest")
        self.sample_mode.addItem("Bilinear", "bilinear")
        self.sample_mode.addItem("Bicubic", "bicubic")
        self.sample_mode.addItem("Lanczos", "lanczos")
        self.palette_size = QSpinBox()
        self.palette_size.setRange(1, 32)
        self.palette_size.setValue(32)
        self.simplification = QSlider(Qt.Orientation.Horizontal)
        self.simplification.setRange(0, 100)
        self.simplification.setValue(35)
        self.silhouette = QCheckBox("Preserve silhouette")
        self.silhouette.setChecked(True)
        self.colors = QCheckBox("Preserve major colors")
        self.colors.setChecked(True)
        form.addRow("Target width", self.width)
        form.addRow("Max height", self.height)
        form.addRow("Depth", self.depth)
        form.addRow("Scale", self.scale)
        form.addRow("Sample mode", self.sample_mode)
        form.addRow("Palette size", self.palette_size)
        form.addRow("Simplification", self.simplification)
        form.addRow(self.silhouette)
        form.addRow(self.colors)
        self.generate = QPushButton("Generate")
        self.generate.clicked.connect(self._emit)
        form.addRow(self.generate)
        layout.addLayout(form, 1)
        self.drop.path_changed.connect(self._reference_changed)
        self.scale.valueChanged.connect(self._scale_changed)

    def settings(self) -> ReconstructionSettings:
        return ReconstructionSettings(
            target_width=self.width.value(),
            max_height=self.height.value(),
            depth=self.depth.value(),
            sample_mode=str(self.sample_mode.currentData()),
            simplification=self.simplification.value(),
            palette_size=self.palette_size.value(),
            preserve_silhouette=self.silhouette.isChecked(),
            preserve_major_colors=self.colors.isChecked(),
        )

    def _reference_changed(self, path: str) -> None:
        try:
            with Image.open(path) as image:
                source_width, source_height = image.size
        except OSError:
            return
        self.drop.label.setText(f"{Path(path).name}  ({source_width}×{source_height})")
        self._update_width_from_scale(source_width)

    def _scale_changed(self) -> None:
        if not self.drop.path:
            return
        try:
            with Image.open(self.drop.path) as image:
                source_width = image.width
        except OSError:
            return
        self._update_width_from_scale(source_width)

    def _update_width_from_scale(self, source_width: int) -> None:
        calculated = max(1, source_width // self.scale.value())
        self.width.setValue(min(self.width.maximum(), calculated))
        if calculated > self.width.maximum():
            self.width.setToolTip(
                f"Source width {source_width} ÷ scale {self.scale.value()} = {calculated}; limited to 30 by canvas"
            )
        else:
            self.width.setToolTip(f"Source width {source_width} ÷ scale {self.scale.value()} = {calculated}")

    def _emit(self) -> None:
        if not self.drop.path:
            QMessageBox.information(self, "Reference image", "Choose or drop a reference image first.")
            return
        self.generate_requested.emit((self.drop.path, self.settings()))


class MainWindow(QMainWindow):
    def __init__(self, library_path: str | Path) -> None:
        super().__init__()
        self.setWindowTitle("Piece-Based Block Editor")
        self.resize(1320, 820)
        self.project_path: Path | None = None
        self.dirty = False
        self.palette = DEFAULT_PALETTE
        self.library_path = Path(library_path).resolve()
        self.library = PieceLibrary.load(self.library_path)
        self.scene = Scene(self.library.pieces)
        self.viewport = EditorViewport(self.scene, self.palette)
        self.library_panel = PieceLibraryPanel()
        self.library_panel.set_library(self.library)
        self.properties = PropertiesPanel(self.palette)
        self.properties.set_scene_bounds(self.scene)
        self.palette_panel = PalettePanel(self.palette)
        self.ai_panel = AIBuildPanel()
        self._build_layout()
        self._build_toolbar()
        self._build_menu()
        self._connect()
        self._show_library_status()

    def _build_layout(self) -> None:
        self.left_splitter = QSplitter(Qt.Orientation.Vertical)
        self.left_splitter.setChildrenCollapsible(False)
        self.left_splitter.addWidget(self.palette_panel)
        self.left_splitter.addWidget(self.library_panel)
        self.left_splitter.setSizes([150, 500])
        horizontal = QSplitter(Qt.Orientation.Horizontal)
        horizontal.addWidget(self.left_splitter)
        horizontal.addWidget(self.viewport)
        horizontal.addWidget(self.properties)
        horizontal.setSizes([250, 810, 260])
        tabs = QTabWidget()
        tabs.addTab(self.ai_panel, "AI Build")
        vertical = QSplitter(Qt.Orientation.Vertical)
        vertical.addWidget(horizontal)
        vertical.addWidget(tabs)
        vertical.setSizes([520, 300])
        self.setCentralWidget(vertical)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Editor Tools")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.tool_actions: dict[EditorTool, QAction] = {}
        for tool in EditorTool:
            action = QAction(tool.value, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, selected=tool: self._set_tool(selected))
            toolbar.addAction(action)
            self.tool_actions[tool] = action
        self.tool_actions[EditorTool.PLACE].setChecked(True)
        toolbar.addSeparator()
        for title, callback in (
            ("Delete", self.viewport.delete_selection),
            ("Rotate Left", lambda: self.viewport.rotate_selection(-90)),
            ("Rotate Right", lambda: self.viewport.rotate_selection(90)),
            ("Duplicate", self.viewport.duplicate_selection),
            ("Mirror X", self.viewport.mirror_selection),
        ):
            toolbar.addAction(title, callback)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Layer "))
        layer = QSpinBox()
        layer.setRange(0, self.scene.bounds[2] - 1)
        layer.valueChanged.connect(self.viewport.set_layer)
        toolbar.addWidget(layer)
        toolbar.addSeparator()
        toolbar.addAction("Front", lambda: self.viewport.set_view_mode(ViewMode.FRONT))
        toolbar.addAction("Perspective", lambda: self.viewport.set_view_mode(ViewMode.PERSPECTIVE))
        toolbar.addAction("Center", self.viewport.center_view)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        actions = (
            ("&New", QKeySequence.StandardKey.New, self.new_project),
            ("&Open Project…", QKeySequence.StandardKey.Open, self.open_project),
            ("&Save Project", QKeySequence.StandardKey.Save, self.save_project),
            ("Save Project &As…", QKeySequence.StandardKey.SaveAs, self.save_project_as),
            ("Open Piece &Library…", None, self.open_library),
            ("&Import Game JSON…", None, self.import_game),
            ("&Export Game JSON…", None, self.export_game),
        )
        for text, shortcut, callback in actions:
            action = file_menu.addAction(text)
            if shortcut:
                action.setShortcut(shortcut)
            action.triggered.connect(callback)
        file_menu.addSeparator()
        file_menu.addAction("E&xit", self.close)

        edit_menu = self.menuBar().addMenu("&Edit")
        undo = edit_menu.addAction("Undo", self.viewport.undo)
        undo.setShortcut(QKeySequence.StandardKey.Undo)
        redo = edit_menu.addAction("Redo", self.viewport.redo)
        redo.setShortcut(QKeySequence.StandardKey.Redo)
        duplicate = edit_menu.addAction("Duplicate", self.viewport.duplicate_selection)
        duplicate.setShortcut(QKeySequence("Ctrl+D"))
        delete = edit_menu.addAction("Delete", self.viewport.delete_selection)
        delete.setShortcut(QKeySequence.StandardKey.Delete)

        view_menu = self.menuBar().addMenu("&View")
        front = view_menu.addAction("Front", lambda: self.viewport.set_view_mode(ViewMode.FRONT))
        front.setShortcut(QKeySequence("F"))
        perspective = view_menu.addAction("Perspective", lambda: self.viewport.set_view_mode(ViewMode.PERSPECTIVE))
        perspective.setShortcut(QKeySequence("P"))
        center = view_menu.addAction("Center on Origin", self.viewport.center_view)
        center.setShortcut(QKeySequence("H"))

    def _connect(self) -> None:
        self.library_panel.piece_selected.connect(self._select_piece)
        self.palette_panel.color_selected.connect(self.viewport.recolor_selection)
        self.properties.apply_requested.connect(lambda data: self.viewport.update_selected(**data))
        self.viewport.selection_changed.connect(self._selection_changed)
        self.viewport.scene_changed.connect(self._scene_changed)
        self.viewport.status_message.connect(lambda text: self.statusBar().showMessage(text, 5000))
        self.ai_panel.generate_requested.connect(self._generate)

    def _set_tool(self, tool: EditorTool) -> None:
        for candidate, action in self.tool_actions.items():
            action.setChecked(candidate == tool)
        self.viewport.set_tool(tool)

    def _select_piece(self, piece_id: str) -> None:
        self.viewport.active_piece_id = piece_id
        self._set_tool(EditorTool.PLACE)
        self.statusBar().showMessage(f"Active piece: {piece_id}", 3000)

    def _selection_changed(self) -> None:
        self.properties.show_selection(self.viewport.selected_pieces())

    def _scene_changed(self) -> None:
        self.dirty = True
        self._update_title()

    def _update_title(self) -> None:
        name = self.project_path.name if self.project_path else "Untitled"
        self.setWindowTitle(f"{'*' if self.dirty else ''}{name} — Piece-Based Block Editor")

    def _show_library_status(self) -> None:
        message = f"Loaded {len(self.library.pieces)} piece(s) from {self.library_path}"
        if self.library.warnings:
            message += f" — {len(self.library.warnings)} warning(s)"
        self.statusBar().showMessage(message, 8000)

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        self.palette = load_default_palette()
        self.palette_panel.set_palette(self.palette)
        self.properties.set_palette(self.palette)
        self.viewport.set_palette(self.palette)
        self.scene = Scene(self.library.pieces)
        self.viewport.set_scene(self.scene)
        self.properties.set_scene_bounds(self.scene)
        self.project_path = None
        self.dirty = False
        self._update_title()

    def open_library(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open Piece Library", str(self.library_path))
        if not path:
            return
        library = PieceLibrary.load(path)
        if not library.pieces:
            QMessageBox.warning(self, "Piece library", "No valid piece.json definitions were found.")
            return
        unknown = [piece.piece_id for piece in self.scene.pieces if piece.piece_id not in library.pieces]
        if unknown:
            QMessageBox.warning(self, "Piece library", "The current scene uses pieces missing from that library.")
            return
        self.library = library
        self.library_path = library.root
        self.scene.piece_defs = library.pieces
        self.library_panel.set_library(library)
        self.viewport.update()
        self._show_library_status()

    def save_project(self) -> None:
        if not self.project_path:
            self.save_project_as()
            return
        try:
            save_project(self.project_path, self.scene, self.palette, self.library_path)
            self.dirty = False
            self._update_title()
            self.statusBar().showMessage(f"Saved {self.project_path}", 4000)
        except OSError as exc:
            QMessageBox.critical(self, "Save project", str(exc))

    def save_project_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Project", str(self.project_path or "untitled.piece-project.json"), "Piece Project (*.piece-project.json);;JSON (*.json)")
        if path:
            self.project_path = Path(path)
            self.save_project()

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "Piece Project (*.piece-project.json *.json)")
        if not path:
            return
        try:
            data = load_project_data(path)
            library_path = Path(str(data["library"]))
            if not library_path.is_absolute():
                library_path = Path(path).parent / library_path
            library = PieceLibrary.load(library_path)
            if not library.pieces:
                raise ValueError(f"Project piece library is unavailable: {library_path}")
            palette = tuple(PaletteColor.from_dict(item) for item in data["palette"])
            saved_bounds = tuple(int(value) for value in data["bounds"])
            bounds = (EDITOR_BOUNDS[0], EDITOR_BOUNDS[1], saved_bounds[2])
            pieces = [PieceInstance.from_dict(item) for item in data["pieces"]]
            scene = Scene(library.pieces, bounds, pieces)  # type: ignore[arg-type]
        except (OSError, ValueError, KeyError, TypeError, PlacementError) as exc:
            QMessageBox.critical(self, "Open project", str(exc))
            return
        self.library = library
        self.library_path = library.root
        self.palette = palette
        self.scene = scene
        self.library_panel.set_library(library)
        self.palette_panel.set_palette(palette)
        self.properties.set_palette(palette)
        self.viewport.set_palette(palette)
        self.viewport.set_scene(scene)
        self.properties.set_scene_bounds(scene)
        self.project_path = Path(path)
        self.dirty = False
        self._update_title()

    def export_game(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Game JSON", "construction.json", "JSON (*.json)")
        if not path:
            return
        try:
            export_game(path, self.scene.pieces)
            self.statusBar().showMessage(f"Exported {len(self.scene.pieces)} pieces", 4000)
        except OSError as exc:
            QMessageBox.critical(self, "Export", str(exc))

    def import_game(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Game JSON", "", "JSON (*.json)")
        if not path:
            return
        try:
            pieces = import_game_data(path)
            if not self.viewport.replace_all(pieces):
                return
        except (OSError, ValueError, PlacementError) as exc:
            QMessageBox.critical(self, "Import", str(exc))

    def _generate(self, payload: object) -> None:
        path, settings = payload  # type: ignore[misc]
        current = settings
        while True:
            try:
                result = reconstruct_image(path, self.palette, current)
                pieces = GreedySolver(self.library.pieces.values()).solve(result.mask, current.depth)
                x_offset = -(result.mask.shape[1] // 2)
                pieces = [
                    replace(piece, position=(piece.position[0] + x_offset, piece.position[1], piece.position[2]))
                    for piece in pieces
                ]
            except (OSError, ValueError, SolverError) as exc:
                QMessageBox.critical(self, "AI Build", str(exc))
                return
            preview = ReconstructionPreview(result, self.palette, len(pieces), self)
            preview.exec()
            if preview.action == "accept":
                if self.scene.pieces:
                    answer = QMessageBox.question(
                        self,
                        "Replace scene?",
                        "Accepting this reconstruction replaces the current scene. Continue?",
                    )
                    if answer != QMessageBox.StandardButton.Yes:
                        return
                if self.viewport.replace_all(pieces):
                    self.statusBar().showMessage(f"Accepted reconstruction with {len(pieces)} pieces", 5000)
                return
            if preview.action == "simplify":
                current = replace(current, simplification=min(100, current.simplification + 10))
                self.ai_panel.simplification.setValue(current.simplification)
                continue
            if preview.action == "detail":
                current = replace(current, simplification=max(0, current.simplification - 10))
                self.ai_panel.simplification.setValue(current.simplification)
                continue
            if preview.action == "regenerate":
                continue
            return

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, "Unsaved changes", "Discard unsaved changes?")
        return answer == QMessageBox.StandardButton.Yes

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()


def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(
        """
        QWidget { background: #252a32; color: #e5e8ec; }
        QMainWindow, QMenuBar, QMenu, QToolBar { background: #1d2127; }
        QLineEdit, QSpinBox, QComboBox, QListWidget, QTabWidget::pane {
            background: #1f242b; border: 1px solid #3b4350; padding: 3px;
        }
        QPushButton { background: #343c48; border: 1px solid #4a5565; padding: 5px 9px; }
        QPushButton:hover { background: #414c5b; }
        QPushButton:pressed { background: #2d78c4; }
        QToolBar { spacing: 4px; border-bottom: 1px solid #343b45; }
        QToolButton:checked { background: #2d78c4; }
        QStatusBar { background: #1d2127; }
        """
    )

