"""tool_card — 首页快捷工具卡片（Prism 设计系统）。

图标使用分组色系圆角方块背景，hover 时 accent 色调高亮，
右侧提供浅色箭头提示可点击。点击后切换到对应导航页。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, FluentIcon, IconWidget,
                            isDarkTheme)

from gui_qt.components.card import HoverCard
from gui_qt.components import design_system as ds


class _GroupIconBox(QWidget):
    """带分组色系圆角背景的图标方块。"""

    def __init__(self, icon, color, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(42, 42)
        self._icon = IconWidget(icon, self)
        self._icon.setFixedSize(24, 24)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._icon, 0, Qt.AlignCenter)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing)
        bg = QColor(self._color)
        bg.setAlpha(35)
        p.setBrush(bg)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(self.rect(), 12, 12)


class ToolCard(HoverCard):
    """快捷工具卡：点击后切换到对应导航页（由页面连接 clicked）。"""

    def __init__(self, icon, title, desc="", nav_key=None,
                 group_key="manage", parent=None):
        super().__init__(parent)
        self.nav_key = nav_key
        self.setFixedHeight(92)

        h = QHBoxLayout(self)
        h.setContentsMargins(16, 14, 16, 14)
        h.setSpacing(12)

        fg, _ = ds.group_colors(group_key)
        iw = _GroupIconBox(icon, fg, self)
        h.addWidget(iw)

        v = QVBoxLayout()
        v.setSpacing(2)
        self.title_label = BodyLabel(title, self)
        self.title_label.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {ds.ink()};")
        v.addWidget(self.title_label)
        if desc:
            self.desc_label = CaptionLabel(desc, self)
            self.desc_label.setStyleSheet(
                f"font-size: 12px; color: {ds.ink_sec()};")
            self.desc_label.setWordWrap(True)
            v.addWidget(self.desc_label)
        else:
            self.desc_label = None
        v.setAlignment(Qt.AlignLeft)
        h.addLayout(v, 1)

        self.arrow = IconWidget(FluentIcon.CHEVRON_RIGHT, self)
        self.arrow.setFixedSize(16, 16)
        self.arrow.setStyleSheet(f"color: {ds.ink_dis()};")
        h.addWidget(self.arrow, 0, Qt.AlignVCenter)

    def enterEvent(self, e):
        self.arrow.setStyleSheet(f"color: {ds.accent()};")
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.arrow.setStyleSheet(f"color: {ds.ink_dis()};")
        super().leaveEvent(e)
