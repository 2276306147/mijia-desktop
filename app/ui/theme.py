"""浅色 / 深色两套主题与全局样式表。"""

from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

LIGHT = {
    "bg": "#f5f6f8",
    "surface": "#ffffff",
    "surface2": "#f8fafc",
    "surface3": "#eef2f7",
    "text": "#111827",
    "muted": "#6b7280",
    "faint": "#9ca3af",
    "border": "#e5e7eb",
    "border_strong": "#d7dce5",
    "accent": "#ff6900",
    "accent_hover": "#ef5f00",
    "accent_soft": "#fff1e6",
    "accent_text": "#ffffff",
    "success": "#16a34a",
    "danger": "#dc2626",
    "warn": "#d97706",
    "shadow": "rgba(15, 23, 42, 0.06)",
}

DARK = {
    "bg": "#0f1115",
    "surface": "#171a21",
    "surface2": "#1c2029",
    "surface3": "#242a35",
    "text": "#e8eaed",
    "muted": "#9aa3b2",
    "faint": "#6b7484",
    "border": "#272d39",
    "border_strong": "#333b49",
    "accent": "#ff7a1a",
    "accent_hover": "#ff8c3a",
    "accent_soft": "#33210f",
    "accent_text": "#1a1205",
    "success": "#22c55e",
    "danger": "#f87171",
    "warn": "#fbbf24",
    "shadow": "rgba(0, 0, 0, 0.35)",
}


def palette(theme: str) -> dict[str, str]:
    return DARK if theme == "dark" else LIGHT


_ACTIVE: dict[str, str] = LIGHT


def active_colors() -> dict[str, str]:
    """当前主题色板，供手绘控件使用。"""
    return _ACTIVE


def app_font() -> QFont:
    if sys.platform == "win32":
        families = ["Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"]
    elif sys.platform == "darwin":
        families = ["PingFang SC", "Helvetica Neue"]
    else:
        families = ["Noto Sans CJK SC", "Source Han Sans SC", "DejaVu Sans"]
    font = QFont()
    font.setFamilies(families)
    font.setPointSize(10)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    return font


def stylesheet(theme: str) -> str:
    c = palette(theme)
    return f"""
* {{ outline: none; }}

QWidget {{
    color: {c['text']};
    font-size: 14px;
}}
QMainWindow, QDialog, #Root {{ background: {c['bg']}; }}

/* ---------- 侧边栏 ---------- */
#Sidebar {{
    background: {c['surface']};
    border-right: 1px solid {c['border']};
}}
#BrandName {{ font-size: 16px; font-weight: 700; letter-spacing: .3px; }}
#BrandSub {{ color: {c['faint']}; font-size: 11px; }}
#BrandMark {{
    background: {c['accent']};
    color: #ffffff;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 700;
}}

QPushButton#NavButton {{
    text-align: left;
    padding: 9px 14px;
    border: none;
    border-radius: 9px;
    background: transparent;
    color: {c['muted']};
    font-size: 14px;
    font-weight: 500;
}}
QPushButton#NavButton:hover {{ background: {c['surface2']}; color: {c['text']}; }}
QPushButton#NavButton:checked {{
    background: {c['accent_soft']};
    color: {c['accent']};
    font-weight: 650;
}}

/* ---------- 顶栏 ---------- */
#TopBar {{
    background: {c['surface']};
    border-bottom: 1px solid {c['border']};
}}
#PageTitle {{ font-size: 18px; font-weight: 700; }}
#PageSub {{ color: {c['faint']}; font-size: 12px; }}

/* ---------- 卡片 ---------- */
QFrame#Card {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 12px;
}}
QFrame#CardFlat {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 10px;
}}
QFrame#HLine {{ background: {c['border']}; max-height: 1px; border: none; }}

/* ---------- 文本 ---------- */
QLabel[kind="h1"] {{ font-size: 21px; font-weight: 700; }}
QLabel[kind="h2"] {{ font-size: 15px; font-weight: 650; }}
QLabel[kind="muted"] {{ color: {c['muted']}; }}
QLabel[kind="faint"] {{ color: {c['faint']}; font-size: 12px; }}
QLabel[kind="value"] {{ font-size: 14px; font-weight: 600; }}
QLabel[kind="badge"] {{
    background: {c['surface3']}; color: {c['muted']};
    border-radius: 8px; padding: 2px 8px; font-size: 11px;
}}
QLabel[kind="badgeOk"] {{
    background: rgba(22,163,74,.12); color: {c['success']};
    border-radius: 8px; padding: 2px 8px; font-size: 11px;
}}
QLabel[kind="badgeWarn"] {{
    background: rgba(217,119,6,.14); color: {c['warn']};
    border-radius: 8px; padding: 2px 8px; font-size: 11px;
}}

/* ---------- 按钮 ---------- */
QPushButton {{
    background: {c['surface']};
    border: 1px solid {c['border_strong']};
    border-radius: 8px;
    padding: 6px 14px;
    color: {c['text']};
}}
QPushButton:hover {{ background: {c['surface2']}; border-color: {c['faint']}; }}
QPushButton:pressed {{ background: {c['surface3']}; }}
QPushButton:disabled {{ color: {c['faint']}; border-color: {c['border']}; background: {c['surface2']}; }}

QPushButton[kind="primary"] {{
    background: {c['accent']}; border: 1px solid {c['accent']};
    color: {c['accent_text']}; font-weight: 600;
}}
QPushButton[kind="primary"]:hover {{ background: {c['accent_hover']}; border-color: {c['accent_hover']}; }}
QPushButton[kind="primary"]:disabled {{ background: {c['surface3']}; border-color: {c['border']}; color: {c['faint']}; }}

QPushButton[kind="ghost"] {{
    background: transparent; border: 1px solid transparent; color: {c['muted']};
    padding: 5px 9px;
}}
QPushButton[kind="ghost"]:hover {{ background: {c['surface2']}; color: {c['text']}; }}

QPushButton[kind="danger"] {{ color: {c['danger']}; border-color: {c['border_strong']}; }}
QPushButton[kind="danger"]:hover {{ background: rgba(220,38,38,.08); border-color: {c['danger']}; }}

QPushButton[kind="star"] {{
    background: transparent; border: none; font-size: 17px; padding: 0 4px; color: {c['faint']};
}}
QPushButton[kind="star"]:checked {{ color: #f59e0b; }}

/* ---------- 输入控件 ---------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {c['surface']};
    border: 1px solid {c['border_strong']};
    border-radius: 8px;
    padding: 6px 10px;
    selection-background-color: {c['accent']};
    selection-color: #fff;
    min-height: 20px;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {c['accent']};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ background: {c['surface2']}; color: {c['muted']}; }}
QComboBox {{ padding-right: 6px; }}
QComboBox QAbstractItemView {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    selection-background-color: {c['accent_soft']};
    selection-color: {c['text']};
    outline: none;
    padding: 4px;
}}

/* ---------- 滑块 ---------- */
QSlider::groove:horizontal {{
    height: 4px; background: {c['surface3']}; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {c['accent']}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: #ffffff; border: 2px solid {c['accent']};
    width: 14px; height: 14px; margin: -6px 0; border-radius: 8px;
}}

/* ---------- 树 / 列表 ---------- */
QTreeWidget, QListWidget, QTableWidget {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 10px;
    outline: none;
    padding: 4px;
}}
QTreeWidget::item, QListWidget::item {{ padding: 5px 6px; border-radius: 6px; }}
QTreeWidget::item:hover, QListWidget::item:hover {{ background: {c['surface2']}; }}
QTreeWidget::item:selected, QListWidget::item:selected {{
    background: {c['accent_soft']}; color: {c['text']};
}}
QTreeWidget::item:selected:!active, QListWidget::item:selected:!active {{
    background: {c['accent_soft']}; color: {c['text']};
}}
QCheckBox {{ spacing: 8px; }}
QSpinBox, QDoubleSpinBox {{ padding: 3px 8px; }}
QHeaderView::section {{
    background: {c['surface2']}; border: none; border-bottom: 1px solid {c['border']};
    padding: 7px 8px; color: {c['muted']}; font-size: 12px;
}}
QTableWidget {{ gridline-color: {c['border']}; }}
QTableWidget::item {{ padding: 6px; }}

/* ---------- 滚动 ---------- */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: {c['border_strong']}; border-radius: 4px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {c['faint']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c['border_strong']}; border-radius: 4px; min-width: 30px; }}

/* ---------- 其他 ---------- */
QMenu {{
    background: {c['surface']}; border: 1px solid {c['border']};
    border-radius: 8px; padding: 6px;
}}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c['accent_soft']}; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 5px 8px; }}

QToolTip {{
    background: {c['surface']}; color: {c['text']};
    border: 1px solid {c['border']}; padding: 5px 8px; border-radius: 6px;
}}
QProgressBar {{
    background: {c['surface3']}; border: none; border-radius: 4px;
    height: 8px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}

QStatusBar {{ background: {c['surface']}; border-top: 1px solid {c['border']}; color: {c['muted']}; }}
QSplitter::handle {{ background: {c['border']}; }}
QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 10px; background: {c['surface']}; }}
QTabBar::tab {{
    padding: 7px 16px; margin-right: 4px; border-radius: 8px; color: {c['muted']};
}}
QTabBar::tab:selected {{ background: {c['accent_soft']}; color: {c['accent']}; font-weight: 600; }}

#LogView {{
    background: {c['surface2']}; border: none; border-top: 1px solid {c['border']};
    font-family: "Cascadia Mono", "Consolas", "SF Mono", monospace; font-size: 11.5px;
    color: {c['muted']}; padding: 6px;
}}
"""


def apply_theme(app: QApplication, theme: str) -> None:
    global _ACTIVE
    _ACTIVE = palette(theme)
    app.setStyle("Fusion")
    app.setFont(app_font())
    app.setStyleSheet(stylesheet(theme))
