from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from src.config import get_resource_path


def app_mark_pixmap(size: int) -> QPixmap:
    """Return the canonical rounded application logo at the requested size."""
    # Keep an independently bundled fallback so the UI never degrades to
    # initials when an assets directory is missing from a distribution.
    for relative_path in ("assets/PrimeDictate-AppIcon.png", "PrimeDictate-Logo.png"):
        source = QPixmap(get_resource_path(relative_path))
        if not source.isNull():
            return source.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return QPixmap()
