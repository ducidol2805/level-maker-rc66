from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication

from .ui import MainWindow, apply_dark_theme


def main() -> int:
    surface_format = QSurfaceFormat()
    surface_format.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
    surface_format.setVersion(3, 3)
    surface_format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    surface_format.setDepthBufferSize(24)
    surface_format.setStencilBufferSize(8)
    surface_format.setSamples(4)
    QSurfaceFormat.setDefaultFormat(surface_format)
    app = QApplication(sys.argv)
    app.setApplicationName("Piece-Based Block Editor")
    app.setOrganizationName("Local Tools")
    apply_dark_theme(app)
    default_library = Path(__file__).resolve().parent.parent / "library"
    window = MainWindow(default_library)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

