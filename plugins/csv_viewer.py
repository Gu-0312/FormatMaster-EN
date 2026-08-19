"""插件：CSV 表格查看器（QTableWidget 可视化，自动编码检测）。"""

import csv
from plugins._i18n import t
import os

from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QHeaderView,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)
from qfluentwidgets import CaptionLabel, PrimaryPushButton

PLUGIN_INFO = {
    "name": "CSV 表格查看",
    "description": "CSV 文件表格化查看（UTF-8 / GBK 自动识别）",
    "version": "1.0.0",
}

_MAX_ROWS = 10000


def read_csv(path):
    """读取 CSV，返回 (rows, used_encoding)。rows 为二维列表。"""
    with open(path, "rb") as fh:
        data = fh.read()
    text = None
    used = "utf-8"
    for enc in ("utf-8-sig", "utf-8", "gbk", "big5"):
        try:
            text = data.decode(enc)
            used = enc
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = data.decode("utf-8", errors="replace")
    rows = list(csv.reader(text.splitlines()))
    return rows, used


class CsvPanel(QWidget):
    """CSV 表格查看面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        row = QHBoxLayout()
        self.btn_pick = PrimaryPushButton(t("选择 CSV 文件"))
        self.btn_pick.clicked.connect(self._pick)
        row.addWidget(self.btn_pick)
        self.lb_info = CaptionLabel("")
        row.addWidget(self.lb_info)
        row.addStretch(1)
        v.addLayout(row)

        self.table = QTableWidget(0, 0)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setStretchLastSection(True)
        v.addWidget(self.table, 1)
        self._apply_theme()
        from gui_qt.components import design_system as ds
        ds.bind_theme(self, self._apply_theme)

    def _apply_theme(self):
        from gui_qt.components import design_system as ds
        t = ds.tokens()
        self.setStyleSheet(
            f"QTableWidget {{ background: {t['card_bg']};"
            f" color: {t['ink']}; border: 1px solid {t['border']};"
            f" border-radius: 6px; font-size: 12px; }}"
            f"QHeaderView::section {{ background: {t['card_bg']};"
            f" color: {t['ink']}; border: none;"
            f" border-bottom: 1px solid {t['border']}; padding: 4px; }}")

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t("选择 CSV"), "", "CSV (*.csv);;所有文件 (*)")
        if not path:
            return
        try:
            rows, used = read_csv(path)
        except Exception as e:  # noqa: BLE001
            self.lb_info.setText(t("读取失败：{e}").format(e=e))
            return
        if not rows:
            self.lb_info.setText(t("空文件"))
            return
        total = len(rows)
        if total > _MAX_ROWS:
            rows = rows[:_MAX_ROWS]
            truncated = True
        else:
            truncated = False
        cols = max(len(r) for r in rows)
        self.table.setColumnCount(cols)
        self.table.setRowCount(len(rows))
        headers = [t("列 {n}").format(n=i + 1) for i in range(cols)]
        if rows:
            headers = [f"列 {i+1} ({rows[0][i] if i < len(rows[0]) else ''})"
                       for i in range(cols)]
        self.table.setHorizontalHeaderLabels(headers)
        for ri, r in enumerate(rows):
            for ci in range(cols):
                val = r[ci] if ci < len(r) else ""
                self.table.setItem(ri, ci, QTableWidgetItem(val))
        note = f" · 已截断到 {_MAX_ROWS} 行" if truncated else ""
        self.lb_info.setText(
            f"{os.path.basename(path)} · {total} 行 × {cols} 列 · "
            f"编码 {used}{note}")


PANEL_CLASS = CsvPanel


def on_load(ctx):
    pass


def on_unload():
    pass
