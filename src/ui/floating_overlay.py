import os
import math
from PySide6.QtCore import Qt, QTimer, QPoint, Signal
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QPixmap
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QVBoxLayout

LOGO_PATH = r"c:\Users\MAXIMUS\PROJECTS\PrimeDictate-Project\PrimeDictate-Logo.png"

class WaveVisualizer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(120, 28)
        self.level = 0.0
        self.phase = 0.0

    def set_level(self, level: float):
        self.level = level
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()
        cy = height / 2.0

        # Draw 5 dynamic audio wave bars
        num_bars = 7
        bar_width = 4
        spacing = 6
        total_width = num_bars * bar_width + (num_bars - 1) * spacing
        start_x = (width - total_width) / 2.0

        self.phase += 0.2

        for i in range(num_bars):
            x = start_x + i * (bar_width + spacing)
            sin_factor = math.sin(self.phase + i * 0.8)
            bar_h = max(6.0, (self.level * 22.0) * (0.5 + 0.5 * sin_factor) + 4.0)

            # Gradient color from violet to cyan
            color = QColor(99, 102, 241) if i % 2 == 0 else QColor(6, 182, 212)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(x, cy - bar_h / 2.0, bar_width, bar_h, 2, 2)

class FloatingOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool |
            Qt.SubWindow
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.drag_position = QPoint()

        self._setup_ui()
        self.hide()

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 8, 16, 8)
        main_layout.setSpacing(10)

        # Background Container
        self.container = QWidget(self)
        self.container.setStyleSheet("""
            QWidget {
                background-color: rgba(15, 23, 42, 225);
                border: 1px solid rgba(99, 102, 241, 150);
                border-radius: 20px;
            }
        """)

        container_layout = QHBoxLayout(self.container)
        container_layout.setContentsMargins(10, 6, 14, 6)
        container_layout.setSpacing(10)

        # Logo Icon
        self.logo_label = QLabel()
        if os.path.exists(LOGO_PATH):
            pix = QPixmap(LOGO_PATH).scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.logo_label.setPixmap(pix)
        else:
            self.logo_label.setText("🎙️")

        # Visualizer
        self.visualizer = WaveVisualizer()

        # Status text
        self.status_label = QLabel("Dinleniyor...")
        self.status_label.setStyleSheet("color: #f8fafc; font-weight: bold; font-size: 13px; border: none; background: transparent;")

        container_layout.addWidget(self.logo_label)
        container_layout.addWidget(self.visualizer)
        container_layout.addWidget(self.status_label)

        main_layout.addWidget(self.container)

    def set_status(self, text: str, color_hex: str = "#f8fafc"):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color_hex}; font-weight: bold; font-size: 13px; border: none; background: transparent;")

    def update_audio_level(self, level: float):
        self.visualizer.set_level(level)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
