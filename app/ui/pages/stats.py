"""统计页：按设备查询用电量/时长等，折线图 + CSV 导出。"""

from __future__ import annotations

import csv
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.config import Config
from app.core.service import MijiaService
from app.core.tasks import run_async
from app.ui.widgets import StatChart, label, section_card

GRANULARITY = [
    ("按小时", "stat_hour_v3"),
    ("按天", "stat_day_v3"),
    ("按周", "stat_week_v3"),
    ("按月", "stat_month_v3"),
]

RANGES = [("近 7 天", 7), ("近 30 天", 30), ("近 90 天", 90), ("近 180 天", 180)]


class StatsPage(QWidget):
    status = Signal(str)

    def __init__(self, service: MijiaService, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.config = config
        self._points: list[tuple[int, float]] = []
        self._loading = False
        self._devices_loaded = False
        self._auto_query_done = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)

        # 查询条件
        card, body = section_card("查询条件", "仅部分设备支持统计接口")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(240)
        self.key_edit = QLineEdit(self.config.stats_key or "7.1")
        self.key_edit.setPlaceholderText("通常为 siid.piid，例如 7.1")
        self.key_edit.setMinimumWidth(160)
        self.gran_combo = QComboBox()
        for text, value in GRANULARITY:
            self.gran_combo.addItem(text, value)
        self.range_combo = QComboBox()
        for text, days in RANGES:
            self.range_combo.addItem(text, days)
        self.range_combo.setCurrentIndex(1)

        grid.addWidget(label("设备", "muted"), 0, 0)
        grid.addWidget(self.device_combo, 1, 0)
        grid.addWidget(label("统计键 key", "muted"), 0, 1)
        grid.addWidget(self.key_edit, 1, 1)
        grid.addWidget(label("粒度", "muted"), 0, 2)
        grid.addWidget(self.gran_combo, 1, 2)
        grid.addWidget(label("时间范围", "muted"), 0, 3)
        grid.addWidget(self.range_combo, 1, 3)

        self.query_btn = QPushButton("查询")
        self.query_btn.setProperty("kind", "primary")
        self.query_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.query_btn.clicked.connect(self.query)
        self.export_btn = QPushButton("导出 CSV")
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export)
        grid.addWidget(self.query_btn, 1, 4)
        grid.addWidget(self.export_btn, 1, 5)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 1)
        body.addLayout(grid)
        outer.addWidget(card)

        # 汇总
        summary, summary_body = section_card("汇总")
        row = QHBoxLayout()
        row.setSpacing(32)
        self.total_value = self._metric(row, "总计")
        self.avg_value = self._metric(row, "平均")
        self.max_value = self._metric(row, "峰值")
        self.count_value = self._metric(row, "数据点")
        row.addStretch(1)
        summary_body.addLayout(row)
        outer.addWidget(summary)

        # 图表
        chart_card, chart_body = section_card("趋势")
        self.chart = StatChart()
        chart_body.addWidget(self.chart)
        outer.addWidget(chart_card, 1)

        self.hint = label(
            "统计接口因设备型号而异：key 与 data_type 可能不同（例如空调伴侣 Pro 用 7.1，"
            "老款用 powerCost）。查询为空时先确认型号是否支持。",
            "faint",
        )
        self.hint.setWordWrap(True)
        outer.addWidget(self.hint)

    @staticmethod
    def _metric(row: QHBoxLayout, title: str):
        holder = QVBoxLayout()
        holder.setSpacing(0)
        value = label("—", "h1")
        holder.addWidget(value)
        holder.addWidget(label(title, "faint"))
        row.addLayout(holder)
        return value

    # ------------------------------------------------------------------

    def ensure_data(self) -> None:
        if self._devices_loaded:
            return
        devices = self.service.snapshot.devices
        if devices:
            self._fill_devices(devices)
            return

        def done(snapshot) -> None:
            self._fill_devices(snapshot.devices)

        run_async(self.service.load_snapshot, done, lambda m, _t: self.status.emit(f"设备加载失败：{m}"))

    def reset(self) -> None:
        self._devices_loaded = False
        self._points = []
        self._loading = False
        self._auto_query_done = False
        self.device_combo.clear()
        self.chart.set_data([])
        self.export_btn.setEnabled(False)
        for widget in (self.total_value, self.avg_value, self.max_value):
            widget.setText("—")
        self.count_value.setText("0")

    def _fill_devices(self, devices) -> None:
        if not devices:
            return
        self._devices_loaded = True
        current = self.device_combo.currentData()
        self.device_combo.clear()
        for dev in devices:
            self.device_combo.addItem(f"{dev.name}　{dev.model}", dev.did)
        if current:
            index = self.device_combo.findData(current)
            if index >= 0:
                self.device_combo.setCurrentIndex(index)
        elif self.config.stats_device:
            index = self.device_combo.findData(self.config.stats_device)
            if index >= 0:
                self.device_combo.setCurrentIndex(index)

        if not self._auto_query_done and self.device_combo.count():
            self._auto_query_done = True
            QTimer.singleShot(300, self.query)

    def query(self) -> None:
        did = self.device_combo.currentData()
        if not did:
            QMessageBox.information(self, "请选择设备", "先选一台设备再查询")
            return
        key = self.key_edit.text().strip()
        if not key:
            QMessageBox.information(self, "缺少 key", "请填写统计键，例如 7.1")
            return

        days = int(self.range_combo.currentData())
        data_type = self.gran_combo.currentData()
        limit = {
            "stat_hour_v3": days * 24,
            "stat_day_v3": days,
            "stat_week_v3": max(1, days // 7),
            "stat_month_v3": max(1, days // 30),
        }.get(data_type, days)
        limit = min(limit + 2, 500)
        end = int(time.time())
        start = end - days * 24 * 3600

        self.config.stats_device = did
        self.config.stats_key = key
        self.config.save()
        self.query_btn.setEnabled(False)
        self.status.emit("正在查询统计数据…")

        def job():
            return self.service.statistics(did, key, data_type, limit, start, end)

        run_async(job, self._on_data, self._on_error)

    def _on_data(self, points: list[tuple[int, float]]) -> None:
        self._points = points
        self.query_btn.setEnabled(True)
        self.chart.set_data(points)
        self.export_btn.setEnabled(bool(points))

        if not points:
            self.total_value.setText("—")
            self.avg_value.setText("—")
            self.max_value.setText("—")
            self.count_value.setText("0")
            self.status.emit("没有查到数据，可能该设备不支持此 key / 粒度")
            return

        values = [p[1] for p in points]
        self.total_value.setText(f"{sum(values):,.1f}")
        self.avg_value.setText(f"{sum(values) / len(values):,.1f}")
        self.max_value.setText(f"{max(values):,.1f}")
        self.count_value.setText(str(len(points)))
        self.status.emit(f"查询完成，共 {len(points)} 个数据点")

    def _on_error(self, message: str, _trace: str = "") -> None:
        self.query_btn.setEnabled(True)
        self.status.emit(f"查询失败：{message}")
        QMessageBox.warning(self, "查询失败", message)

    def _export(self) -> None:
        if not self._points:
            return
        default = f"mijia-statistics-{time.strftime('%Y%m%d-%H%M')}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出 CSV", str(Path.home() / default), "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(["时间", "时间戳", "数值"])
                for ts, value in self._points:
                    writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)), ts, value])
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        self.status.emit(f"已导出到 {path}")
