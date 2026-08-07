PREMIUM_STYLE = """
QMainWindow, QDialog {
    background-color: #0a0d12;
    color: #edf1f5;
    font-family: "Segoe UI";
}
QWidget {
    color: #d5dbe3;
    font-family: "Segoe UI";
    font-size: 13px;
}
QWidget#sidebar {
    background-color: #0d1117;
    border-right: 1px solid #252b34;
}
QLabel#brandTitle { color: #f8f6f1; font-size: 18px; font-weight: 700; }
QLabel#brandCaption {
    color: #b99b62;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#pageTitle { color: #f8f6f1; font-size: 25px; font-weight: 700; }
QLabel#pageSubtitle, QLabel#mutedLabel { color: #818b99; }
QLabel#sectionDescription { color: #9aa4b1; line-height: 1.4; }
QLabel#fieldLabel { color: #bdc5cf; font-weight: 600; min-width: 150px; }
QLabel#sectionEyebrow {
    color: #c4a76e;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#infoNote {
    background-color: #111921;
    border: 1px solid #24323d;
    border-left: 3px solid #5e8e9d;
    border-radius: 7px;
    color: #aebbc5;
    padding: 9px 11px;
}
QLabel#warningNote {
    background-color: #211d13;
    border: 1px solid #4a3d22;
    border-left: 3px solid #b99b62;
    border-radius: 7px;
    color: #cbbd9f;
    padding: 9px 11px;
}
QLabel#heroTitle { color: #f8f6f1; font-size: 28px; font-weight: 700; }
QLabel#heroCaption { color: #9aa4b1; font-size: 14px; }
QLabel#metricValue { color: #f5f3ee; font-size: 17px; font-weight: 600; }
QLabel#metricLabel { color: #828c99; font-size: 10px; font-weight: 700; letter-spacing: 1px; }
QFrame#headerActions {
    background-color: #10151c;
    border: 1px solid #272e38;
    border-radius: 13px;
}
QLabel#statusPill {
    background-color: #10231d;
    border: 1px solid #245441;
    border-radius: 9px;
    color: #78d6ad;
    font-weight: 600;
    padding: 0 14px;
}
QFrame#heroCard {
    background-color: #11161d;
    border: 1px solid #29313b;
    border-radius: 17px;
}
QFrame#pipelineCard {
    background-color: #0f141a;
    border: 1px solid #2b323c;
    border-radius: 14px;
}
QLabel#pipelineStage {
    background-color: #151b22;
    border: 1px solid #303944;
    border-radius: 9px;
    color: #e7eaee;
    font-size: 12px;
    font-weight: 600;
    padding: 13px 15px;
}
QLabel#pipelineArrow {
    color: #b99b62;
    font-size: 21px;
    font-weight: 700;
    padding: 0 5px;
}
QFrame#metricCard, QFrame#contentCard {
    background-color: #10151b;
    border: 1px solid #252d37;
    border-radius: 13px;
}
QFrame#onboardingCard {
    background-color: #10151b;
    border: 1px solid #333b45;
    border-radius: 14px;
}
QLabel#onboardingTitle { color: #f6f3ed; font-size: 20px; font-weight: 700; }
QLabel#onboardingSteps {
    background-color: #0c1117;
    border: 1px solid #2c343e;
    border-radius: 8px;
    color: #b6bec8;
    font-weight: 500;
    padding: 10px 12px;
}
QFrame#subCard {
    background-color: #0c1117;
    border: 1px solid #28313b;
    border-radius: 10px;
}
QFrame#aboutCard {
    background-color: #10151b;
    border: 1px solid #2f3741;
    border-radius: 18px;
}
QLabel#studioLogo { background: transparent; border: none; }
QLabel#aboutStudio { color: #f5f0e5; font-size: 24px; font-weight: 700; }
QLabel#aboutCredit { color: #d7dde4; font-size: 14px; font-weight: 600; }
QLabel#aboutVersion {
    color: #b99b62;
    font-size: 12px;
    font-weight: 700;
    padding: 6px 10px;
}
QPushButton#navButton {
    background: transparent;
    border: none;
    border-radius: 8px;
    color: #8d97a4;
    font-size: 13px;
    font-weight: 600;
    padding: 10px 13px;
    text-align: left;
}
QPushButton#navButton:hover { background-color: #151b22; color: #eceff2; }
QPushButton#navButton:checked {
    background-color: #20201d;
    color: #f5f0e5;
    border-left: 3px solid #b99b62;
}
QPushButton {
    background-color: #171d24;
    border: 1px solid #343d48;
    border-radius: 8px;
    color: #e7ebef;
    font-weight: 600;
    padding: 9px 16px;
}
QPushButton:hover { background-color: #202832; border-color: #9f895f; color: #ffffff; }
QPushButton:focus { border: 1px solid #c1a46d; color: #ffffff; }
QPushButton:pressed { background-color: #2a323c; border-color: #b99b62; color: #ffffff; }
QPushButton:disabled { background-color: #242a31; border-color: #303741; color: #68727f; }
QPushButton#primaryAction {
    background-color: #29241a;
    border: 1px solid #b99b62;
    border-radius: 9px;
    color: #f5efe2;
    font-size: 13px;
    font-weight: 600;
    padding: 0 20px;
}
QPushButton#primaryAction:hover { background-color: #3a3120; border-color: #d2b879; color: #ffffff; }
QPushButton#primaryAction:focus { background-color: #332b1d; border: 2px solid #d8bf83; color: #ffffff; }
QPushButton#primaryAction:pressed { background-color: #4a3c24; border-color: #e0c78b; color: #ffffff; }
QPushButton#primaryAction:disabled { background-color: #3a352b; border-color: #4b4333; color: #777065; }
QPushButton#dangerAction {
    background-color: #9f4650;
    border-color: #bb5964;
    border-radius: 9px;
    color: #ffffff;
    font-size: 13px;
    padding: 0 20px;
}
QPushButton#dangerAction:hover { background-color: #ae4e59; }
QPushButton#secondary_btn {
    background-color: #181e25;
    border-color: #323b46;
    color: #d5dbe2;
}
QPushButton#secondary_btn:hover { background-color: #222a33; border-color: #46515e; }
QGroupBox {
    background-color: #10151b;
    border: 1px solid #28313b;
    border-radius: 13px;
    color: #d7dce3;
    font-size: 13px;
    font-weight: 600;
    margin-top: 14px;
    padding: 20px 15px 15px 15px;
}
QGroupBox::title {
    background-color: #10151b;
    color: #f1eee7;
    left: 13px;
    padding: 0 7px;
    subcontrol-origin: margin;
}
QLineEdit, QComboBox, QSpinBox, QTextEdit, QListWidget {
    background-color: #0a0f14;
    border: 1px solid #323b46;
    border-radius: 8px;
    color: #edf0f3;
    padding: 8px 11px;
    selection-background-color: #806f4d;
    selection-color: #ffffff;
}
QLineEdit:hover, QComboBox:hover, QTextEdit:hover { border-color: #756747; color: #ffffff; }
QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QListWidget:focus {
    border: 1px solid #b99b62;
}
QComboBox::drop-down { border: none; width: 28px; }
QComboBox QAbstractItemView {
    background-color: #141a21;
    border: 1px solid #3a444f;
    color: #edf0f3;
    selection-background-color: #4a402d;
    padding: 5px;
}
QComboBox QAbstractItemView::item:selected { background-color: #5a4c31; color: #ffffff; }
QCheckBox { spacing: 9px; color: #c8cfd7; }
QCheckBox::indicator {
    width: 17px;
    height: 17px;
    background-color: #0a0f14;
    border: 1px solid #4a5562;
    border-radius: 5px;
}
QCheckBox::indicator:hover { border-color: #b99b62; }
QCheckBox::indicator:checked {
    background-color: #b99b62;
    border: 4px solid #4a402d;
}
QCheckBox:disabled { color: #68727f; }
QProgressBar {
    background-color: #090e13;
    border: 1px solid #2c3540;
    border-radius: 5px;
    color: #d5dbe2;
    min-height: 9px;
    text-align: center;
}
QProgressBar::chunk { background-color: #b99b62; border-radius: 4px; }
QListWidget { padding: 7px; }
QListWidget::item { border-radius: 7px; margin: 2px; padding: 11px; }
QListWidget::item:hover { background-color: #171e26; }
QListWidget::item:selected { background-color: #3b3427; color: #ffffff; }
QScrollArea { background-color: #0a0d12; border: none; }
QScrollArea QWidget#qt_scrollarea_viewport { background-color: #0a0d12; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #353e49; border-radius: 5px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: #4b5663; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background-color: #181e25; color: #f2f3f4; border: 1px solid #3a444f; padding: 6px; }
"""
