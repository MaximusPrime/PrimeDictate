DARK_GLASS_STYLE = """
QMainWindow, QDialog {
    background-color: #0d0e15;
    color: #f1f5f9;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
}

QWidget {
    color: #e2e8f0;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
}

QTabWidget::pane {
    border: 1px solid #1e293b;
    background-color: #0f172a;
    border-radius: 12px;
    padding: 12px;
}

QTabBar::tab {
    background-color: #1e293b;
    color: #94a3b8;
    padding: 10px 20px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 600;
    font-size: 13px;
}

QTabBar::tab:selected {
    background-color: #6366f1;
    color: #ffffff;
}

QTabBar::tab:hover:!selected {
    background-color: #334155;
    color: #e2e8f0;
}

QGroupBox {
    border: 1px solid #1e293b;
    border-radius: 10px;
    margin-top: 14px;
    padding-top: 14px;
    font-weight: bold;
    color: #818cf8;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    background-color: #0d0e15;
}

QLabel {
    font-size: 13px;
}

QLineEdit, QComboBox, QSpinBox, QTextEdit {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 8px 12px;
    color: #f8fafc;
    font-size: 13px;
}

QLineEdit:focus, QComboBox:focus, QTextEdit:focus {
    border: 1px solid #6366f1;
    background-color: #0f172a;
}

QPushButton {
    background-color: #6366f1;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-weight: 600;
    font-size: 13px;
}

QPushButton:hover {
    background-color: #4f46e5;
}

QPushButton:pressed {
    background-color: #4338ca;
}

QPushButton#secondary_btn {
    background-color: #334155;
    color: #f1f5f9;
}

QPushButton#secondary_btn:hover {
    background-color: #475569;
}

QCheckBox {
    spacing: 8px;
    font-size: 13px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #475569;
    background-color: #1e293b;
}

QCheckBox::indicator:checked {
    background-color: #6366f1;
    border-color: #6366f1;
}

QProgressBar {
    border: 1px solid #334155;
    border-radius: 6px;
    text-align: center;
    background-color: #1e293b;
}

QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366f1, stop:1 #06b6d4);
    border-radius: 5px;
}

QListWidget {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 6px;
}

QListWidget::item {
    padding: 10px;
    border-bottom: 1px solid #1e293b;
    border-radius: 6px;
    margin-bottom: 4px;
}

QListWidget::item:hover {
    background-color: #1e293b;
}

QListWidget::item:selected {
    background-color: #312e81;
    color: #ffffff;
}
"""
