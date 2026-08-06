"""stat_card_new — 首页统计卡（按参考截图设计）。

形态：色条 + 图标 + 数值 + 标题 + 「较昨日 ±x%」副标签。
与旧版 StatCard 的差异：多了 delta 副标签、更紧凑的高度。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QVBoxLayout,
                               QWidget)
from qfluentwidgets import (CaptionLabel, FluentIcon, IconWidget)

from gui_qt.components import design_system as ds
from gui_qt.components.card import Card


class _CardIcon(QWidget):
    """圆角图标方块。"""

    def __init__(self, icon, color, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(38, 38)
        self._icon = IconWidget(icon, self)
        self._icon.setFixedSize(20, 20)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._icon, 0, Qt.AlignCenter)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor(self._color)
        c.setAlpha(42 if not ds.is_dark() else 55)
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(self.rect(), 10, 10)


class StatCard(Card):
    """单张统计卡。value 为当前值，delta 为「较昨日」变化文字。"""

    def __init__(self, title, value, delta, accent, icon, parent=None):
        super().__init__(parent, radius=12)
        self.setMinimumHeight(96)

        h = QHBoxLayout(self)
        h.setContentsMargins(16, 14, 16, 14)
        h.setSpacing(12)

        bar = QFrame(self)
        bar.setFixedSize(4, 42)
        bar.setStyleSheet(f"background: {accent}; border-radius: 2px;")
        h.addWidget(bar)

        icon_box = _CardIcon(icon, accent, self)
        h.addWidget(icon_box)

        v = QVBoxLayout()
        v.setSpacing(1)
        self.value_label = QLabel(value, self)
        self.value_label.setStyleSheet(
            f"font-size: 21px; font-weight: 700; color: {ds.ink()};"
            "border: none; background: transparent;")
        v.addWidget(self.value_label)
        self.title_label = CaptionLabel(title, self)
        self.title_label.setStyleSheet(
            f"font-size: 12px; color: {ds.ink_sec()};"
            "border: none; background: transparent;")
        v.addWidget(self.title_label)
        self.delta_label = CaptionLabel(delta, self)
        self.delta_label.setStyleSheet(
            "font-size: 11px; border: none; background: transparent;")
        self._set_delta_style(delta)
        v.addWidget(self.delta_label)
        v.addStretch(1)
        h.addLayout(v, 1)

    def _set_delta_style(self, delta):
        text = str(delta or "")
        if "+" in text or "↑" in text:
            color = "#2FC99A"
        elif "-" in text or "↓" in text:
            color = "#F26D6D"
        else:
            color = ds.ink_dis()
        self.delta_label.setStyleSheet(
            f"font-size: 11px; color: {color}; border: none;"
            "background: transparent;")

    def set_value(self, text):
        self.value_label.setText(str(text))

    def set_delta(self, text):
        self.delta_label.setText(str(text))
        self._set_delta_style(text)
