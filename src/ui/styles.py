def get_styled_app(font_size_mode: str = "normal") -> str:
    sizes = {
        "small": {"base": 11, "nav": 12, "title": 22, "hero": 24, "sub": 12},
        "normal": {"base": 13, "nav": 13, "title": 25, "hero": 28, "sub": 13},
        "large": {"base": 14, "nav": 14, "title": 27, "hero": 30, "sub": 14},
    }
    s = sizes.get(font_size_mode, sizes["normal"])

    return f"""
QMainWindow, QDialog {{
    background-color: #0a0d12;
    color: #edf1f5;
    font-family: "Segoe UI";
}}
QWidget {{
    color: #d5dbe3;
    font-family: "Segoe UI";
    font-size: {s['base']}px;
}}
QWidget#sidebar {{
    background-color: #0d1117;
    border-right: 1px solid #252b34;
}}
QLabel#brandTitle {{ color: #f8f6f1; font-size: 18px; font-weight: 700; }}
QLabel#brandCaption {{
    color: #b99b62;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#pageTitle {{ color: #f8f6f1; font-size: {s['title']}px; font-weight: 700; }}
QLabel#pageSubtitle, QLabel#mutedLabel {{ color: #818b99; }}
QLabel#sectionDescription {{ color: #9aa4b1; line-height: 1.4; }}
QLabel#fieldLabel {{ color: #bdc5cf; font-weight: 600; min-width: 150px; }}
QLabel#sectionEyebrow {{
    color: #c4a76e;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#infoNote {{
    background-color: #111921;
    border: 1px solid #24323d;
    border-left: 3px solid #5e8e9d;
    border-radius: 7px;
    color: #aebbc5;
    padding: 9px 11px;
}}
QLabel#warningNote {{
    background-color: #211d13;
    border: 1px solid #4a3d22;
    border-left: 3px solid #b99b62;
    border-radius: 7px;
    color: #cbbd9f;
    padding: 9px 11px;
}}
QLabel#heroTitle {{ color: #f8f6f1; font-size: {s['hero']}px; font-weight: 700; }}
QLabel#heroCaption {{ color: #9aa4b1; font-size: 14px; }}
QLabel#metricValue {{ color: #f5f3ee; font-size: 17px; font-weight: 600; }}
QLabel#metricLabel {{ color: #828c99; font-size: 10px; font-weight: 700; letter-spacing: 1px; }}
QFrame#headerActions {{
    background-color: transparent;
    border: none;
}}
QLabel#statusPill {{
    background-color: #1a160e;
    border: 1px solid #3d321d;
    border-radius: 9px;
    color: #d2b879;
    font-weight: 600;
    padding: 0 14px;
}}
QFrame#heroCard {{
    background-color: #11161d;
    border: 1px solid #29313b;
    border-radius: 17px;
}}
QFrame#heroFocus {{
    background-color: #0c1117;
    border: 1px solid #3a3528;
    border-radius: 13px;
    min-width: 255px;
    max-width: 300px;
}}
QLabel#heroFocusEyebrow {{
    color: #b99b62;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.2px;
}}
QLabel#heroHotkey {{
    color: #f8f4e9;
    font-size: 21px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QFrame#pipelineCard {{
    background-color: #0f141a;
    border: 1px solid #2b323c;
    border-radius: 14px;
}}
QLabel#pipelineStage {{
    background-color: #151b22;
    border: 1px solid #303944;
    border-radius: 9px;
    color: #e7eaee;
    font-size: 12px;
    font-weight: 600;
    padding: 13px 15px;
}}
QLabel#pipelineArrow {{
    color: #b99b62;
    font-size: 21px;
    font-weight: 700;
    padding: 0 5px;
}}
QFrame#metricCard, QFrame#contentCard {{
    background-color: #10151b;
    border: 1px solid #252d37;
    border-radius: 13px;
}}
QFrame#onboardingCard {{
    background-color: #10151b;
    border: 1px solid #333b45;
    border-radius: 14px;
}}
QLabel#onboardingTitle {{ color: #f6f3ed; font-size: 20px; font-weight: 700; }}
QLabel#onboardingSteps {{
    background-color: #0c1117;
    border: 1px solid #2c343e;
    border-radius: 8px;
    color: #b6bec8;
    font-weight: 500;
    padding: 10px 12px;
}}
QFrame#subCard {{
    background-color: #0c1117;
    border: 1px solid #28313b;
    border-radius: 10px;
}}
QFrame#aboutCard {{
    background-color: #10151b;
    border: 1px solid #2f3741;
    border-radius: 18px;
}}
QLabel#studioLogo {{ background: transparent; border: none; }}
QLabel#aboutStudio {{ color: #f5f0e5; font-size: 24px; font-weight: 700; }}
QLabel#aboutCredit {{ color: #d7dde4; font-size: 14px; font-weight: 600; }}
QLabel#aboutVersion {{
    color: #b99b62;
    font-size: 12px;
    font-weight: 700;
    padding: 6px 10px;
}}
QPushButton#navButton {{
    background: transparent;
    border: none;
    border-radius: 9px;
    color: #9aa5b5;
    font-size: {s['nav']}px;
    font-weight: 700;
    padding: 9px 12px;
    text-align: left;
}}
QPushButton#navButton:hover {{
    background-color: #171f2a;
    color: #ffffff;
}}
QPushButton#navButton:focus {{
    background-color: #1b2430;
    border: 2px solid #c4a76e;
    color: #ffffff;
}}
QPushButton#navButton:checked {{
    background-color: #212520;
    color: #f5efe2;
    border-left: 4px solid #c4a76e;
}}
QPushButton {{
    background-color: #171d24;
    border: 1px solid #343d48;
    border-radius: 8px;
    color: #e7ebef;
    font-weight: 600;
    padding: 9px 16px;
}}
QPushButton:hover {{ background-color: #202832; border-color: #9f895f; color: #ffffff; }}
QPushButton:focus {{ border: 1px solid #c1a46d; color: #ffffff; }}
QPushButton:pressed {{ background-color: #2a323c; border-color: #b99b62; color: #ffffff; }}
QPushButton:disabled {{ background-color: #242a31; border-color: #303741; color: #68727f; }}
QPushButton#primaryAction {{
    background-color: #29241a;
    border: 1px solid #b99b62;
    border-radius: 9px;
    color: #f5efe2;
    font-size: 13px;
    font-weight: 600;
    padding: 0 20px;
}}
QPushButton#primaryAction:hover {{ background-color: #3a3120; border-color: #d2b879; color: #ffffff; }}
QPushButton#primaryAction:focus {{ background-color: #332b1d; border: 2px solid #d8bf83; color: #ffffff; }}
QPushButton#primaryAction:pressed {{ background-color: #4a3c24; border-color: #e0c78b; color: #ffffff; }}
QPushButton#primaryAction:disabled {{ background-color: #3a352b; border-color: #4b4333; color: #777065; }}
QPushButton#dangerAction {{
    background-color: #9f4650;
    border-color: #bb5964;
    border-radius: 9px;
    color: #ffffff;
    font-size: 13px;
    padding: 0 20px;
}}
QPushButton#dangerAction:hover {{ background-color: #ae4e59; }}
QPushButton#secondary_btn {{
    background-color: #181e25;
    border-color: #323b46;
    color: #d5dbe2;
}}
QPushButton#secondary_btn:hover {{ background-color: #222a33; border-color: #46515e; }}
QPushButton#hotkeyRecorderBtn {{
    background-color: #0b1016;
    border: 1px solid #343d48;
    border-radius: 9px;
    color: #f5efe2;
    font-weight: 700;
    padding: 9px 16px;
    text-align: center;
    letter-spacing: 0.5px;
}}
QPushButton#hotkeyRecorderBtn:hover {{
    background-color: #141c25;
    border-color: #c4a76e;
}}
QPushButton#hotkeyRecorderBtn[recording="true"] {{
    background-color: #241e14;
    border: 1px solid rgba(196, 167, 110, 0.85);
    color: #ffffff;
}}
QPushButton#testKeyBtn {{
    background-color: #131922;
    border: 1px solid #303a47;
    border-radius: 8px;
    color: #c4a76e;
    font-size: 12px;
    font-weight: 600;
    padding: 6px 12px;
}}
QPushButton#testKeyBtn:hover {{
    background-color: #1f2734;
    border-color: #c4a76e;
    color: #ffffff;
}}
QLabel#apiTestStatus {{
    font-size: 12px;
    font-weight: 600;
    padding-left: 4px;
}}
QGroupBox {{
    background-color: #10151b;
    border: 1px solid #28313b;
    border-radius: 13px;
    color: #d7dce3;
    font-size: 13px;
    font-weight: 600;
    margin-top: 14px;
    padding: 20px 15px 15px 15px;
}}
QGroupBox::title {{
    background-color: #10151b;
    color: #f1eee7;
    left: 13px;
    padding: 0 7px;
    subcontrol-origin: margin;
}}
QLineEdit, QComboBox, QSpinBox, QTextEdit, QListWidget {{
    background-color: #0a0f14;
    border: 1px solid #323b46;
    border-radius: 8px;
    color: #edf0f3;
    padding: 8px 11px;
    selection-background-color: #806f4d;
    selection-color: #ffffff;
}}
QLineEdit:hover, QComboBox:hover, QTextEdit:hover {{ border-color: #756747; color: #ffffff; }}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QListWidget:focus {{
    border: 1px solid #b99b62;
}}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox::down-arrow {{
    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23b99b62' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'><polyline points='6 9 12 15 18 9'/></svg>");
    width: 12px;
    height: 12px;
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background-color: #141a21;
    border: 1px solid #3a444f;
    color: #edf0f3;
    selection-background-color: #5a4c31;
    padding: 4px;
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    border: none;
    outline: none;
    min-height: 26px;
    padding: 4px 8px;
    border-radius: 4px;
}}
QComboBox QAbstractItemView::item:selected, QComboBox QAbstractItemView::item:hover {{
    background-color: #5a4c31;
    color: #ffffff;
    border: none;
    outline: none;
}}
QCheckBox {{ spacing: 9px; color: #c8cfd7; outline: none; border: none; }}
QCheckBox:focus {{ color: #ffffff; outline: none; border: none; }}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    background-color: #0a0f14;
    border: 1px solid #4a5562;
    border-radius: 4px;
}}
QCheckBox::indicator:hover {{ border-color: #b99b62; }}
QCheckBox::indicator:checked {{
    background-color: #b99b62;
    border: 1px solid #b99b62;
    image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%230a0f14' stroke-width='3.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='20 6 9 17 4 12'%3E%3C/polyline%3E%3C/svg%3E");
}}
QCheckBox:disabled {{ color: #68727f; }}
QProgressBar {{
    background-color: #090e13;
    border: 1px solid #2c3540;
    border-radius: 5px;
    color: #d5dbe2;
    min-height: 9px;
    text-align: center;
}}
QProgressBar::chunk {{ background-color: #b99b62; border-radius: 4px; }}
QListWidget {{ padding: 7px; }}
QListWidget::item {{ border-radius: 7px; margin: 2px; padding: 11px; }}
QListWidget::item:hover {{ background-color: #171e26; }}
QListWidget::item:selected {{ background-color: #3b3427; color: #ffffff; }}
QScrollArea {{ background-color: #0a0d12; border: none; }}
QScrollArea QWidget#qt_scrollarea_viewport {{ background-color: #0a0d12; }}
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: #28303b;
    border-radius: 3px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{
    background: #b99b62;
}}
QScrollBar::handle:vertical:pressed {{
    background: #d8c392;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    height: 0px;
    width: 0px;
    background: transparent;
    border: none;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
    margin: 0px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: #28303b;
    border-radius: 3px;
    min-width: 28px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #b99b62;
}}
QScrollBar::handle:horizontal:pressed {{
    background: #d8c392;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    height: 0px;
    width: 0px;
    background: transparent;
    border: none;
}}
QToolTip {{ background-color: #181e25; color: #f2f3f4; border: 1px solid #3a444f; padding: 6px; }}
"""

PREMIUM_STYLE = get_styled_app("normal")
