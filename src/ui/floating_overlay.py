import math
import os

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QBrush, QColor, QCursor, QPainter
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton, QWidget

from src.config import config_manager, get_resource_path
from src.i18n import t
from src.ui.brand import app_mark_pixmap


class WaveVisualizer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(96, 28)
        self.level = 0.0
        self.phase = 0.0

    def set_level(self, level: float):
        self.level = max(0.0, min(1.0, level))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cy = self.height() / 2.0
        num_bars = 9
        bar_width = 3
        spacing = 5
        total_width = num_bars * bar_width + (num_bars - 1) * spacing
        start_x = (self.width() - total_width) / 2.0
        self.phase += 0.2

        for index in range(num_bars):
            x = start_x + index * (bar_width + spacing)
            wave = math.sin(self.phase + index * 0.72)
            bar_height = max(5.0, (self.level * 22.0) * (0.5 + 0.5 * wave) + 4.0)
            color = QColor("#c3a56b") if index % 2 == 0 else QColor("#6fa6b4")
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(x, cy - bar_height / 2.0, bar_width, bar_height, 1.5, 1.5)


class OverlaySurface(QWidget):
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.window()._begin_drag(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.window()._drag_to(event.globalPosition().toPoint())
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.window()._finish_drag()
            event.accept()


class FloatingOverlay(QWidget):
    def __init__(self, stop_callback=None):
        super().__init__()
        self.stop_callback = stop_callback
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint
            | Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(438, 74)
        self.drag_position = QPoint()
        self._has_saved_position = False

        self._setup_ui()
        self._load_position()
        self.hide()

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)

        self.container = OverlaySurface(self)
        self.container.setObjectName("overlaySurface")
        self.container.setStyleSheet("""
            QWidget#overlaySurface {
                background-color: rgba(14, 18, 24, 245);
                border: 1px solid rgba(185, 155, 98, 175);
                border-radius: 15px;
            }
            QLabel#overlayLogo, QLabel#overlayStatus, QLabel#dragGrip {
                background: transparent;
                border: none;
            }
            QLabel#overlayStatus {
                color: #edf0f3;
                font-family: "Segoe UI";
                font-size: 12px;
                font-weight: 600;
            }
            QLabel#dragGrip {
                color: #606a76;
                font-size: 15px;
                padding-left: 2px;
            }
            QPushButton#overlayStop {
                background-color: #28171a;
                border: 1px solid #71343b;
                border-radius: 8px;
                color: #f3c4c8;
                font-family: "Segoe UI";
                font-size: 12px;
                font-weight: 600;
                min-width: 62px;
                padding: 7px 10px;
            }
            QPushButton#overlayStop:hover {
                background-color: #3a1d22;
                border-color: #a9505a;
                color: #ffffff;
            }
            QPushButton#overlayStop:pressed { background-color: #521f28; }
            QPushButton#overlayStop:disabled { color: #766268; border-color: #493036; }
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(0, 0, 0, 170))
        self.container.setGraphicsEffect(shadow)

        container_layout = QHBoxLayout(self.container)
        container_layout.setContentsMargins(13, 8, 12, 8)
        container_layout.setSpacing(10)

        self.logo_label = QLabel()
        self.logo_label.setObjectName("overlayLogo")
        self.logo_label.setFixedSize(42, 42)
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        logo_path = get_resource_path(os.path.join("assets", "PrimeDictate-AppIcon.png"))
        if os.path.exists(logo_path):
            self.logo_label.setPixmap(app_mark_pixmap(40))
        else:
            self.logo_label.setText("PD")

        self.visualizer = WaveVisualizer()
        self.visualizer.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.status_label = QLabel(t("Dinleniyor..."))
        self.status_label.setObjectName("overlayStatus")
        self.status_label.setMinimumWidth(105)
        self.status_label.setMaximumWidth(105)
        self.status_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.status_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.stop_button = QPushButton(t("Durdur"))
        self.stop_button.setObjectName("overlayStop")
        self.stop_button.setCursor(Qt.PointingHandCursor)
        self.stop_button.clicked.connect(self._request_stop)
        self.drag_grip = QLabel("⋮⋮")
        self.drag_grip.setObjectName("dragGrip")
        self.drag_grip.setAttribute(Qt.WA_TransparentForMouseEvents)

        container_layout.addWidget(self.logo_label)
        container_layout.addWidget(self.visualizer)
        container_layout.addWidget(self.status_label, 1)
        container_layout.addWidget(self.stop_button)
        container_layout.addWidget(self.drag_grip)
        main_layout.addWidget(self.container)

    def _target_screen(self, point: QPoint = None):
        app = QApplication.instance()
        if point is not None:
            screen = app.screenAt(point)
            if screen:
                return screen
        return app.screenAt(QCursor.pos()) or app.primaryScreen()

    def _default_position(self) -> QPoint:
        geometry = self._target_screen().availableGeometry()
        return QPoint(
            geometry.center().x() - self.width() // 2,
            geometry.bottom() - self.height() - 42,
        )

    def _clamped_position(self, position: QPoint) -> QPoint:
        center = position + QPoint(self.width() // 2, self.height() // 2)
        geometry = self._target_screen(center).availableGeometry()
        margin = 10
        x = max(geometry.left() + margin, min(position.x(), geometry.right() - self.width() - margin + 1))
        y = max(geometry.top() + margin, min(position.y(), geometry.bottom() - self.height() - margin + 1))
        return QPoint(x, y)

    def _load_position(self):
        position = config_manager.get("overlay_position", None)
        if isinstance(position, dict):
            x = position.get("x")
            y = position.get("y")
            if isinstance(x, int) and isinstance(y, int):
                self.move(self._clamped_position(QPoint(x, y)))
                self._has_saved_position = True
                return
        self.move(self._default_position())

    def showEvent(self, event):
        if not self._has_saved_position:
            self.move(self._default_position())
        else:
            self.move(self._clamped_position(self.pos()))
        super().showEvent(event)

    def set_status(self, text: str, color_hex: str = "#edf0f3"):
        self.status_label.setText(t(text))
        self.status_label.setStyleSheet(
            f"color: {color_hex}; background: transparent; border: none; "
            'font-family: "Segoe UI"; font-size: 12px; font-weight: 600;'
        )

    def set_recording_active(self, active: bool):
        self.stop_button.setVisible(active)
        self.stop_button.setEnabled(active)

    def _request_stop(self):
        if self.stop_callback and self.stop_button.isEnabled():
            self.stop_button.setEnabled(False)
            self.stop_callback()

    def update_audio_level(self, level: float):
        self.visualizer.set_level(level)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._begin_drag(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._drag_to(event.globalPosition().toPoint())
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._finish_drag()
            event.accept()

    def _begin_drag(self, global_position: QPoint):
        self.drag_position = global_position - self.frameGeometry().topLeft()

    def _drag_to(self, global_position: QPoint):
        self.move(self._clamped_position(global_position - self.drag_position))

    def _finish_drag(self):
        position = self._clamped_position(self.pos())
        self.move(position)
        self._has_saved_position = True
        config_manager.set("overlay_position", {"x": position.x(), "y": position.y()})
