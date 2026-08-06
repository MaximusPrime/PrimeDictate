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

PREMIUM_STYLE = """
QMainWindow, QDialog {
    background-color: #090b10;
    color: #f4f7fb;
    font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
}
QWidget {
    color: #dce3ed;
    font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
    font-size: 13px;
}
QWidget#sidebar {
    background-color: #0d1119;
    border-right: 1px solid #202735;
}
QLabel#brandTitle { color: #ffffff; font-size: 18px; font-weight: 700; }
QLabel#brandCaption, QLabel#pageSubtitle, QLabel#mutedLabel { color: #7f8a9b; }
QLabel#pageTitle { color: #ffffff; font-size: 25px; font-weight: 700; }
QLabel#heroTitle { color: #ffffff; font-size: 28px; font-weight: 700; }
QLabel#heroCaption { color: #97a3b5; font-size: 14px; }
QLabel#metricValue { color: #ffffff; font-size: 17px; font-weight: 650; }
QLabel#metricLabel { color: #7f8a9b; font-size: 11px; font-weight: 600; }
QLabel#statusPill {
    background-color: #15251f;
    border: 1px solid #235441;
    border-radius: 14px;
    color: #69ddb0;
    font-weight: 650;
    padding: 6px 12px;
}
QFrame#heroCard {
    background-color: #111721;
    border: 1px solid #263044;
    border-radius: 18px;
}
QFrame#pipelineCard {
    background-color: #111827;
    border: 1px solid #303b55;
    border-radius: 14px;
}
QLabel#pipelineStage {
    background-color: #171e2d;
    border: 1px solid #29354c;
    border-radius: 10px;
    color: #eef2ff;
    font-size: 12px;
    font-weight: 650;
    padding: 12px 14px;
}
QLabel#pipelineArrow {
    color: #8589ff;
    font-size: 22px;
    font-weight: 700;
    padding: 0 6px;
}
QFrame#metricCard, QFrame#contentCard {
    background-color: #10151e;
    border: 1px solid #202a3a;
    border-radius: 14px;
}
QPushButton#navButton {
    background: transparent;
    border: none;
    border-radius: 9px;
    color: #8e9aac;
    font-size: 13px;
    font-weight: 600;
    padding: 10px 13px;
    text-align: left;
}
QPushButton#navButton:hover { background-color: #151c28; color: #f2f5f9; }
QPushButton#navButton:checked {
    background-color: #202943;
    color: #ffffff;
    border-left: 3px solid #7c83ff;
}
QPushButton {
    background-color: #6d6ff5;
    border: 1px solid #8588ff;
    border-radius: 9px;
    color: #ffffff;
    font-weight: 650;
    padding: 9px 16px;
}
QPushButton:hover { background-color: #7a7cff; }
QPushButton:pressed { background-color: #5d5fdc; }
QPushButton:disabled { background-color: #252b38; border-color: #303746; color: #667083; }
QPushButton#primaryAction { border-radius: 12px; font-size: 14px; padding: 12px 22px; }
QPushButton#dangerAction { background-color: #d95162; border-color: #eb7180; }
QPushButton#secondary_btn {
    background-color: #171d28;
    border-color: #2a3343;
    color: #d4dbe5;
}
QPushButton#secondary_btn:hover { background-color: #222a38; }
QGroupBox {
    background-color: #10151e;
    border: 1px solid #202a3a;
    border-radius: 14px;
    color: #cfd7e4;
    font-size: 13px;
    font-weight: 650;
    margin-top: 13px;
    padding: 18px 14px 14px 14px;
}
QGroupBox::title {
    background-color: #10151e;
    color: #f2f5f9;
    left: 12px;
    padding: 0 6px;
    subcontrol-origin: margin;
}
QLineEdit, QComboBox, QSpinBox, QTextEdit, QListWidget {
    background-color: #0c1119;
    border: 1px solid #2a3445;
    border-radius: 9px;
    color: #eef2f7;
    padding: 8px 11px;
    selection-background-color: #5e63d9;
}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QListWidget:focus {
    border: 1px solid #777cff;
}
QComboBox::drop-down { border: none; width: 28px; }
QComboBox QAbstractItemView {
    background-color: #131a25;
    border: 1px solid #303a4c;
    color: #eef2f7;
    selection-background-color: #303b66;
    padding: 5px;
}
QCheckBox, QRadioButton { spacing: 9px; color: #cbd3df; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 17px; height: 17px;
    background-color: #0b1018;
    border: 1px solid #465166;
}
QCheckBox::indicator { border-radius: 5px; }
QRadioButton::indicator { border-radius: 9px; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: #7377ff;
    border: 4px solid #272c52;
}
QProgressBar {
    background-color: #0b1018;
    border: 1px solid #273143;
    border-radius: 5px;
    color: #dce3ed;
    min-height: 9px;
    text-align: center;
}
QProgressBar::chunk { background-color: #7478ff; border-radius: 4px; }
QListWidget { padding: 7px; }
QListWidget::item { border-radius: 8px; margin: 2px; padding: 11px; }
QListWidget::item:hover { background-color: #171f2c; }
QListWidget::item:selected { background-color: #252f50; color: #ffffff; }
QScrollArea { background-color: #090b10; border: none; }
QScrollArea QWidget#qt_scrollarea_viewport { background-color: #090b10; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #313b4c; border-radius: 5px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background-color: #181f2b; color: #ffffff; border: 1px solid #343e50; padding: 6px; }
"""
