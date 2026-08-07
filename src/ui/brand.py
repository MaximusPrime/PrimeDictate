from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from src.config import get_resource_path


def app_mark_pixmap(size: int) -> QPixmap:
    """Return the canonical rounded application logo at the requested size."""
    source = QPixmap(get_resource_path("assets/PrimeDictate-AppIcon.png"))
    if source.isNull():
        return source
    return source.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
