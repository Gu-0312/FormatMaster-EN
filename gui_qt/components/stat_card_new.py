"""stat_card_new — 首页统计卡（按参考截图设计）。

形态：色条 + 图标 + 数值 + 标题 + 「较昨日 ±x%」副标签。
与旧版 StatCard 的差异：多了 delta 副标签、更紧凑的高度。
"""
from gui_qt.i18n import tr
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QVBoxLayout,
                               QWidget)
from qfluentwidgets import (CaptionLabel, FluentIcon, IconWidget)

from gui_qt.components import design_system as ds
from gui_qt.components.card import Card


def _dpi_scale():
    """Windows 逻辑 DPI 缩放（125% → 1.25，150% → 1.5）。"""
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            return 1.0
        s = app.primaryScreen()
        return max(1.0, s.logicalDotsPerInch() / 96.0) if s else 1.0
    except Exception:  # noqa: BLE001
        return 1.0


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
        # 按 DPI 缩放预留高度：Windows 150% 缩放下 21px 大字实际约 31px，
        # 固定 96px 会导致 value 与下方 title 重叠（视觉上"大数字两遍"）
        self.setMinimumHeight(max(96, int(96 * _dpi_scale())))

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
        v.setSpacing(4)
        self.value_label = QLabel(value, self)
        self.value_label.setWordWrap(False)
        self.value_label.setStyleSheet(
            f"font-size: 21px; font-weight: 700;"
            "border: none; background: transparent;")
        v.addWidget(self.value_label)
        self.title_label = CaptionLabel(title, self)
        self.title_label.setStyleSheet(
            f"font-size: 12px;"
            "border: none; background: transparent;")
        v.addWidget(self.title_label)
        self.delta_label = CaptionLabel(delta, self)
        self.delta_label.setStyleSheet(
            "font-size: 11px; border: none; background: transparent;")
        self._set_delta_style(delta)
        v.addWidget(self.delta_label)
        v.addStretch(1)
        h.addLayout(v, 1)
        # 主题切换时重刷文字颜色（QSS 创建时写死，深色下不会自动变浅）
        try:
            from qfluentwidgets import qconfig
            qconfig.themeChanged.connect(self._apply_theme)
        except Exception:  # noqa: BLE001
            pass

    def _apply_theme(self, *args):
        """主题切换后重刷 value/title/delta 颜色（深色模式保持可读）。"""
        try:
            self.value_label.setStyleSheet(
                f"font-size: 21px; font-weight: 700;"
                "border: none; background: transparent;")
            self.title_label.setStyleSheet(
                f"font-size: 12px;"
                "border: none; background: transparent;")
            self._set_delta_style(self.delta_label.text())
        except Exception:  # noqa: BLE001
            pass

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
