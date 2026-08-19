# -*- coding: utf-8 -*-
"""range_slider_row — superqt 双滑块选段控件（懒加载）。

QRangeSlider 双滑块区间选择：起/止 + 时长实时显示，替代「开始秒/时长秒」
两个独立下拉，拖拽直观。superqt 未装时回退 QLabel 提示。
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QWidget)

from gui_qt.i18n import tr


class RangeSliderRow(QWidget):
    """双滑块区间控件。

    用法：
        row.set_range(0, 120)          # 时间范围（秒）
        row.set_values(10, 40)         # 当前区间（秒）
        row.values() -> (start, end)
        row.valueChanged 信号 -> (start, end)
    """

    valueChanged = Signal(float, float)  # (start_sec, end_sec)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._slider = None
        self._min, self._max = 0, 0
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.lb_cur = QLabel(tr("00:00 - 00:00", "00:00 - 00:00"))
        lay.addWidget(self.lb_cur)
        lay.addStretch(1)
        self.lb_dur = QLabel("")
        lay.addWidget(self.lb_dur)

        try:
            from superqt import QRangeSlider
            # superqt 0.8.x 签名：QRangeSlider(parent=None) —— 不接 orientation 参数
            self._slider = QRangeSlider(self)
            self._slider.setOrientation(Qt.Orientation.Horizontal)
            self._slider.valueChanged.connect(self._on_change)
            # 插入到中间：起止标签后、时长前
            lay.insertWidget(1, self._slider, 1)
        except Exception:  # noqa: BLE001
            self._slider = None

    # ── 公共接口 ────────────────────────────────
    def available(self):
        return self._slider is not None

    def set_range(self, lo, hi):
        self._min, self._max = float(lo), float(hi)
        if self._slider is None:
            return
        self._slider.blockSignals(True)
        self._slider.setMinimum(0)
        self._slider.setMaximum(1000)
        self._slider.setValue((0, 1000))
        self._slider.blockSignals(False)

    def set_values(self, start, end):
        if self._slider is None:
            return
        lo, hi = self._min, self._max
        span = max(0.001, hi - lo)
        a = int((float(start) - lo) / span * 1000)
        b = int((float(end) - lo) / span * 1000)
        a, b = max(0, min(1000, a)), max(0, min(1000, b))
        if a > b:
            a, b = b, a
        if a == b:
            b = min(1000, b + 1)
        self._slider.blockSignals(True)
        self._slider.setValue((a, b))
        self._slider.blockSignals(False)
        self._update_labels()

    def values(self):
        if self._slider is None:
            return self._min, self._max
        a, b = self._slider.value()
        lo, hi = self._min, self._max
        span = max(0.001, hi - lo)
        return lo + a / 1000 * span, lo + b / 1000 * span

    # ── 内部 ─────────────────────────────────────
    def _on_change(self, val):
        self._update_labels()
        s, e = self.values()
        self.valueChanged.emit(round(s, 2), round(e, 2))

    def _update_labels(self):
        s, e = self.values()
        self.lb_cur.setText(f"{_fmt(s)} - {_fmt(e)}")
        self.lb_dur.setText(tr("时长 {} 秒", "Duration {} s").format(max(0, round(e - s, 1))))


def _fmt(sec):
    sec = max(0, int(sec))
    return f"{sec // 60:02d}:{sec % 60:02d}"
