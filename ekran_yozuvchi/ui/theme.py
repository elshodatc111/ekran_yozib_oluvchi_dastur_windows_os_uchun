"""Ranglar va umumiy uslub (QSS)."""

from __future__ import annotations

BG = "#1B1D24"
PANEL = "#252833"
PANEL_HOVER = "#2E3240"
BORDER = "#343848"
TEXT = "#EDEEF3"
MUTED = "#8D93A7"
RED = "#FF4D5E"
RED_HOVER = "#FF6677"
GREEN = "#35D49A"
AMBER = "#FFB84D"
BLUE = "#5B8CFF"

FONT_FAMILY = "Segoe UI"


def app_qss() -> str:
    return f"""
    QWidget {{ color: {TEXT}; font-family: "{FONT_FAMILY}", "Segoe UI Variable", sans-serif; font-size: 13px; }}
    QDialog, QMessageBox {{ background: {BG}; }}
    QLabel {{ background: transparent; }}
    QLabel[muted="true"] {{ color: {MUTED}; }}
    QLabel[section="true"] {{ color: {MUTED}; font-size: 11px; font-weight: 600; }}
    QLineEdit, QComboBox {{
        background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px;
        padding: 6px 10px; min-height: 22px; selection-background-color: {BLUE};
    }}
    QLineEdit:focus, QComboBox:focus {{ border: 1px solid {BLUE}; }}
    QLineEdit:disabled, QComboBox:disabled {{ color: {MUTED}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{
        background: {PANEL}; border: 1px solid {BORDER}; selection-background-color: {PANEL_HOVER};
        outline: none; padding: 4px;
    }}
    QPushButton {{
        background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px;
        padding: 6px 14px; min-height: 22px;
    }}
    QPushButton:hover {{ background: {PANEL_HOVER}; }}
    QPushButton:disabled {{ color: {MUTED}; }}
    QCheckBox {{ spacing: 8px; background: transparent; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {BORDER}; background: {PANEL}; }}
    QCheckBox::indicator:checked {{ background: {BLUE}; border: 1px solid {BLUE}; }}
    QCheckBox:disabled {{ color: {MUTED}; }}
    QMessageBox QLabel {{ color: {TEXT}; }}
    """
