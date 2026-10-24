"""通用控件：开关、属性行、折线图、空状态等。"""

from __future__ import annotations

import math
import time
from typing import Any

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDoubleValidator,
    QFont,
    QFontMetrics,
    QIntValidator,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .theme import active_colors

# --------------------------------------------------------------------------- #
# 基础组件
# --------------------------------------------------------------------------- #


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None, *, flat: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("CardFlat" if flat else "Card")


class HLine(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HLine")
        self.setFixedHeight(1)


def section_card(title: str, subtitle: str = "") -> tuple[Card, QVBoxLayout]:
    """带标题的卡片容器，返回 (卡片, 内容布局)。"""
    card = Card()
    outer = QVBoxLayout(card)
    outer.setContentsMargins(18, 16, 18, 16)
    outer.setSpacing(10)

    head = QHBoxLayout()
    head.setSpacing(8)
    head.addWidget(label(title, "h2"))
    if subtitle:
        head.addWidget(label(subtitle, "faint"))
    head.addStretch(1)
    outer.addLayout(head)

    body = QVBoxLayout()
    body.setSpacing(2)
    outer.addLayout(body)
    return card, body


def label(text: str, kind: str = "", parent: QWidget | None = None) -> QLabel:
    item = QLabel(text, parent)
    if kind:
        item.setProperty("kind", kind)
    return item


def badge(text: str, kind: str = "badge") -> QLabel:
    item = QLabel(text)
    item.setProperty("kind", kind)
    item.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return item


class ToggleSwitch(QAbstractButton):
    """iOS 风格开关，纯手绘，跟随主题。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(42, 24)
        self._offset = 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float) -> None:
        self._offset = value
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt 命名
        super().setChecked(checked)
        self._anim.stop()
        self._set_offset(1.0 if checked else 0.0)

    def paintEvent(self, event) -> None:  # noqa: N802
        colors = active_colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        track = QRectF(1, 3, self.width() - 2, self.height() - 6)
        off_color = QColor(colors["border_strong"])
        on_color = QColor(colors["accent"])
        base = QColor(
            int(off_color.red() + (on_color.red() - off_color.red()) * self._offset),
            int(off_color.green() + (on_color.green() - off_color.green()) * self._offset),
            int(off_color.blue() + (on_color.blue() - off_color.blue()) * self._offset),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(base if self.isEnabled() else QColor(colors["surface3"]))
        painter.drawRoundedRect(track, track.height() / 2, track.height() / 2)

        knob_d = self.height() - 8
        x = 3 + (self.width() - 6 - knob_d) * self._offset
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(x, 4, knob_d, knob_d))
        painter.end()


class EmptyState(QWidget):
    def __init__(self, title: str, hint: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 60, 24, 60)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = label(title, "h2")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint = label(hint, "faint")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.hint)
        self.button: QPushButton | None = None

    def add_button(self, text: str) -> QPushButton:
        self.button = QPushButton(text)
        self.button.setProperty("kind", "primary")
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = self.layout()
        assert layout is not None
        layout.addSpacing(8)
        layout.addWidget(self.button, alignment=Qt.AlignmentFlag.AlignCenter)
        return self.button


# --------------------------------------------------------------------------- #
# 属性行
# --------------------------------------------------------------------------- #


def _display_name(prop: dict) -> str:
    desc = str(prop.get("description") or "")
    if " / " in desc:
        left, right = desc.split(" / ", 1)
        if right.strip():
            return right.strip()
        return left.strip()
    return desc or prop.get("name", "")


def _tooltip(prop: dict) -> str:
    parts = [f"属性名：{prop.get('name')}", f"类型：{prop.get('type')}　读写：{prop.get('rw')}"]
    if prop.get("range"):
        rng = prop["range"]
        parts.append(f"范围：{rng[0]} ~ {rng[1]}" + (f"　步长：{rng[2]}" if len(rng) > 2 else ""))
    if prop.get("value_list"):
        parts.append("可选：" + "、".join(str(v.get("value")) for v in prop["value_list"][:12]))
    return "\n".join(parts)


class PropertyRow(QWidget):
    """根据 MIoT 属性类型自动生成控件。

    changed(name, value) 只在用户提交时触发（滑块松手 / 输入框失焦 / 开关切换）。
    """

    changed = Signal(str, object)

    def __init__(self, prop: dict, value: Any = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.prop = prop
        self.name = prop["name"]
        self._building = True
        self._writable = "w" in prop.get("rw", "")
        self._switch: ToggleSwitch | None = None
        self._slider: QSlider | None = None
        self._edit: QLineEdit | None = None
        self._choices: list[dict] | None = None
        self._numeric = False

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(_tooltip(prop))

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 3, 0, 3)
        grid.setHorizontalSpacing(14)
        grid.setColumnMinimumWidth(0, 132)
        grid.setColumnStretch(1, 1)

        caption = QLabel(_display_name(prop))
        caption.setToolTip(_tooltip(prop))
        grid.addWidget(caption, 0, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.control = self._build_control(prop, value, self._writable)
        grid.addWidget(self.control, 0, 1)

        self.set_value(value)
        self._building = False

    # ---- 控件工厂 ----

    def _build_control(self, prop: dict, value: Any, writable: bool) -> QWidget:
        ptype = prop.get("type")
        choices = prop.get("value-list") or prop.get("value_list")
        self._choices = choices

        if not writable:
            return label(self._describe(value), "muted")

        if ptype == "bool":
            holder = QWidget()
            row = QHBoxLayout(holder)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(10)
            switch = ToggleSwitch()
            switch.toggled.connect(lambda checked: self._emit(bool(checked)))
            row.addWidget(switch)
            status = label("", "faint")
            row.addWidget(status)
            row.addStretch(1)
            self._switch = switch
            self._status = status
            return holder

        if choices:
            combo = QComboBox()
            for item in choices:
                combo.addItem(str(item.get("description") or item.get("value")), item.get("value"))
            combo.currentIndexChanged.connect(lambda _i: self._emit(combo.currentData()))
            return combo

        if ptype in ("int", "uint"):
            rng = prop.get("range") or []
            if len(rng) >= 2:
                lo, hi = int(rng[0]), int(rng[1])
            else:
                lo, hi = (0, 1_000_000) if ptype == "uint" else (-1_000_000, 1_000_000)
            step = int(rng[2]) if len(rng) > 2 and rng[2] else 1
            if len(rng) >= 2 and 0 <= hi - lo <= 5000:
                return self._int_slider(lo, hi, step)
            self._numeric = True
            return self._number_edit(lo, hi, False)

        if ptype == "float":
            rng = prop.get("range") or []
            lo = float(rng[0]) if len(rng) > 0 and rng[0] is not None else -1e6
            hi = float(rng[1]) if len(rng) > 1 and rng[1] is not None else 1e6
            self._numeric = True
            return self._number_edit(lo, hi, True)

        edit = QLineEdit()
        edit.editingFinished.connect(lambda: self._emit(edit.text()))
        return edit

    def _number_edit(self, lo: float, hi: float, is_float: bool) -> QLineEdit:
        edit = QLineEdit()
        edit.setAlignment(Qt.AlignmentFlag.AlignRight)
        edit.setFixedWidth(78)
        if is_float:
            validator = QDoubleValidator(lo, hi, 2, edit)
            validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        else:
            validator = QIntValidator(int(lo), int(hi), edit)
        edit.setValidator(validator)
        edit.editingFinished.connect(lambda: self._commit_number(edit, is_float))
        return edit

    def _commit_number(self, edit: QLineEdit, is_float: bool) -> None:
        text = edit.text().strip()
        if not text:
            return
        try:
            value: float | int = float(text) if is_float else int(float(text))
        except ValueError:
            return
        self._emit(value)

    def _int_slider(self, lo: int, hi: int, step: int) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(lo, hi)
        slider.setSingleStep(step)
        slider.setPageStep(max(step, (hi - lo) // 10))

        edit = self._number_edit(lo, hi, False)

        def on_slider(value: int) -> None:
            edit.blockSignals(True)
            edit.setText(str(value))
            edit.blockSignals(False)

        def on_edit() -> None:
            try:
                value = int(float(edit.text() or lo))
            except ValueError:
                return
            value = max(lo, min(hi, value))
            slider.blockSignals(True)
            slider.setValue(value)
            slider.blockSignals(False)
            edit.setText(str(value))
            self._emit(value)

        slider.valueChanged.connect(on_slider)
        slider.sliderReleased.connect(lambda: self._emit(slider.value()))
        edit.editingFinished.connect(on_edit)

        self._slider = slider
        self._edit = edit
        row.addWidget(slider, 1)
        row.addWidget(edit)
        return holder

    # ---- 数据 ----

    def _emit(self, value: Any) -> None:
        if self._building:
            return
        self.changed.emit(self.name, value)

    def set_value(self, value: Any) -> None:
        if value is None:
            return
        control = self.control
        control.blockSignals(True)
        try:
            if self._switch is not None:
                self._switch.blockSignals(True)
                self._switch.setChecked(bool(value))
                self._switch.blockSignals(False)
                self._status.setText("开启" if value else "关闭")
            elif isinstance(control, QComboBox):
                index = control.findData(value)
                if index < 0:
                    index = control.findText(str(value))
                if index >= 0:
                    control.setCurrentIndex(index)
            elif isinstance(control, QDoubleSpinBox):
                control.setValue(float(value))
            elif isinstance(control, QSpinBox):
                control.setValue(int(value))
            elif self._slider is not None and self._edit is not None:
                number = int(value)
                self._slider.blockSignals(True)
                self._slider.setValue(number)
                self._slider.blockSignals(False)
                self._edit.setText(str(number))
            elif isinstance(control, QLineEdit):
                if self._numeric:
                    control.setText(f"{float(value):g}" if isinstance(value, float) else str(int(value)))
                else:
                    control.setText(str(value))
            elif isinstance(control, QLabel):
                control.setText(self._describe(value))
        except (TypeError, ValueError):
            pass
        finally:
            control.blockSignals(False)

    def _describe(self, value: Any) -> str:
        for item in self._choices or []:
            if item.get("value") == value:
                return str(item.get("description") or value)
        return self._format(value)

    @staticmethod
    def _format(value: Any) -> str:
        if isinstance(value, bool):
            return "开" if value else "关"
        if isinstance(value, float):
            return f"{value:.1f}"
        return "" if value is None else str(value)


# --------------------------------------------------------------------------- #
# 折线图
# --------------------------------------------------------------------------- #


class StatChart(QWidget):
    """轻量折线图：网格 + 渐变面积 + 悬停提示。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._points: list[tuple[int, float]] = []
        self._unit = ""
        self._hover = -1
        self.setMinimumHeight(260)
        self.setMouseTracking(True)

    def set_data(self, points: list[tuple[int, float]], unit: str = "") -> None:
        self._points = points
        self._unit = unit
        self._hover = -1
        self.update()

    # ---- 坐标 ----

    def _plot_rect(self) -> QRectF:
        return QRectF(56, 18, max(10.0, self.width() - 76), max(10.0, self.height() - 56))

    def _xy(self, index: int, value: float, lo: float, hi: float) -> QPointF:
        rect = self._plot_rect()
        n = max(1, len(self._points) - 1)
        x = rect.left() + rect.width() * index / n
        span = hi - lo or 1.0
        y = rect.bottom() - rect.height() * (value - lo) / span
        return QPointF(x, y)

    def paintEvent(self, event) -> None:  # noqa: N802
        colors = active_colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self._plot_rect()

        painter.fillRect(self.rect(), QColor(colors["surface"]))

        if len(self._points) < 1:
            painter.setPen(QColor(colors["faint"]))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "暂无数据")
            painter.end()
            return

        values = [p[1] for p in self._points]
        lo, hi = min(values), max(values)
        if math.isclose(lo, hi):
            lo, hi = lo - 1, hi + 1
        pad = (hi - lo) * 0.12
        lo, hi = lo - pad, hi + pad

        # 网格与 Y 轴刻度
        grid_pen = QPen(QColor(colors["border"]))
        grid_pen.setWidthF(1)
        small = QFont(self.font())
        small.setPointSizeF(max(8.0, self.font().pointSizeF() - 2))
        painter.setFont(small)
        for i in range(5):
            y = rect.top() + rect.height() * i / 4
            painter.setPen(grid_pen)
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            value = hi - (hi - lo) * i / 4
            painter.setPen(QColor(colors["faint"]))
            text = f"{value:,.0f}" if max(abs(lo), abs(hi)) >= 100 else f"{value:.1f}"
            painter.drawText(
                QRectF(0, y - 9, rect.left() - 8, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                text,
            )

        # X 轴标签（最多 5 个）
        count = len(self._points)
        ticks = min(5, count)
        for i in range(ticks):
            idx = round(i * (count - 1) / max(1, ticks - 1))
            ts = self._points[idx][0]
            text = time.strftime("%m-%d %H:%M" if self._span_small() else "%Y-%m-%d", time.localtime(ts))
            x = rect.left() + rect.width() * idx / max(1, count - 1)
            box = QRectF(x - 46, rect.bottom() + 8, 92, 18)
            if box.right() > self.width() - 4:
                box.moveRight(self.width() - 4)
            if box.left() < 4:
                box.moveLeft(4)
            painter.setPen(QColor(colors["faint"]))
            painter.drawText(box, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, text)

        # 折线与面积
        path = QPainterPath()
        first = self._xy(0, values[0], lo, hi)
        path.moveTo(first)
        for i, value in enumerate(values[1:], start=1):
            path.lineTo(self._xy(i, value, lo, hi))

        area = QPainterPath(path)
        area.lineTo(QPointF(rect.right(), rect.bottom()))
        area.lineTo(QPointF(rect.left(), rect.bottom()))
        area.closeSubpath()

        gradient = QLinearGradient(0, rect.top(), 0, rect.bottom())
        accent = QColor(colors["accent"])
        top = QColor(accent)
        top.setAlpha(70)
        bottom = QColor(accent)
        bottom.setAlpha(0)
        gradient.setColorAt(0, top)
        gradient.setColorAt(1, bottom)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(area)

        line_pen = QPen(accent)
        line_pen.setWidthF(2.0)
        line_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(line_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # 悬停点
        if 0 <= self._hover < count:
            point = self._xy(self._hover, values[self._hover], lo, hi)
            painter.setPen(QPen(QColor(colors["surface"]), 2))
            painter.setBrush(accent)
            painter.drawEllipse(point, 4.5, 4.5)

            ts, value = self._points[self._hover]
            text = f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(ts))}   {value:g}{self._unit}"
            fm2 = QFontMetrics(self.font())
            width = fm2.horizontalAdvance(text) + 18
            box = QRectF(
                min(max(point.x() - width / 2, 4), self.width() - width - 4),
                max(point.y() - 40, 4),
                width,
                24,
            )
            painter.setPen(QPen(QColor(colors["border"]), 1))
            painter.setBrush(QColor(colors["surface"]))
            painter.drawRoundedRect(box, 6, 6)
            painter.setPen(QColor(colors["text"]))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

        painter.end()

    def _span_small(self) -> bool:
        if len(self._points) < 2:
            return False
        return self._points[-1][0] - self._points[0][0] < 3 * 24 * 3600

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        rect = self._plot_rect()
        if not self._points or not rect.contains(event.position()):
            if self._hover != -1:
                self._hover = -1
                self.update()
            return
        ratio = (event.position().x() - rect.left()) / rect.width()
        index = round(ratio * (len(self._points) - 1))
        index = max(0, min(index, len(self._points) - 1))
        if index != self._hover:
            self._hover = index
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = -1
        self.update()
