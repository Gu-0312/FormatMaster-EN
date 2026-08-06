"""card — 统一圆角卡片基类（Prism 设计系统）。

所有卡片（统计卡/工具卡/任务卡/面板区块）继承本类，
保证圆角、背景、阴影与 hover 行为视觉一致。
Prism 风格：圆角 12px + 柔和阴影 + accent 色调 hover 高亮。
"""
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor
from qfluentwidgets import SimpleCardWidget, isDarkTheme

from gui_qt.components import design_system as ds


class Card(SimpleCardWidget):
    """基础圆角卡片：统一圆角 12px + 柔和阴影。"""

    def __init__(self, parent=None, radius=12):
        super().__init__(parent)
        self.setBorderRadius(radius)
        ds.apply_subtle_shadow(self)


class HoverCard(Card):
    """可点击卡片：hover 时棱镜色调高亮 + 边框渐显，点击发出 clicked。"""

    clicked = Signal()

    def __init__(self, parent=None, radius=12):
        super().__init__(parent, radius=radius)
        self.setCursor(Qt.PointingHandCursor)
        self._default_bg = None

    def _refresh_bg(self, hover):
        t = ds.tokens()
        if hover:
            c = QColor(t["card_hover"])
        elif self._default_bg is not None:
            c = self._default_bg
        else:
            return
        self.setBackgroundColor(c)

    def enterEvent(self, e):
        if self._default_bg is None:
            bg = self.backgroundColor
            self._default_bg = QColor(bg) if bg else None
        self._refresh_bg(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._refresh_bg(False)
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)
