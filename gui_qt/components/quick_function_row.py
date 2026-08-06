"""quick_function_row — 首页「快速功能」图标行（按参考截图设计）。

一排小图标入口：图标方块 + 名称，点击跳转到对应页面。第 8 项为
「更多工具」，点击跳转「格式检测」或占位提示。hover 高亮。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QHBoxLayout, QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, FluentIcon, IconWidget)

from gui_qt.components import design_system as ds
from gui_qt.components.card import HoverCard


class _MiniIcon(QWidget):
    """小圆角图标块。"""

    def __init__(self, icon, color, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(40, 40)
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
        p.drawRoundedRect(self.rect(), 12, 12)


class QuickFunctionItem(HoverCard):
    """单个快速功能入口。"""

    def __init__(self, icon, title, accent, nav_key=None, parent=None):
        super().__init__(parent, radius=12)
        self.nav_key = nav_key
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumWidth(96)

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 14, 12, 12)
        v.setSpacing(6)
        self._icon_box = _MiniIcon(icon, accent, self)
        v.addWidget(self._icon_box, 0, Qt.AlignHCenter)
        self.title_label = CaptionLabel(title, self)
        self.title_label.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {ds.ink()};"
            "border: none; background: transparent;")
        self.title_label.setAlignment(Qt.AlignCenter)
        v.addWidget(self.title_label)

    def enterEvent(self, e):
        self.title_label.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {ds.accent()};"
            "border: none; background: transparent;")
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.title_label.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {ds.ink()};"
            "border: none; background: transparent;")
        super().leaveEvent(e)


class QuickFunctionRow(QWidget):
    """快速功能图标行。"""

    # 顺序与参考截图一致
    _ITEMS = [
        (FluentIcon.VIDEO,     "视频转换", "#38BDF8", "video"),
        (FluentIcon.MUSIC,     "音频转换", "#A78BFA", "audio"),
        (FluentIcon.PHOTO,     "图片转换", "#2FC99A", "image"),
        (FluentIcon.DOCUMENT,  "文档转换", "#F0A63A", "document"),
        (FluentIcon.ZIP_FOLDER, "视频压缩", "#EA7A23", "video_edit"),
        (FluentIcon.MOVIE,     "视频转GIF", "#EC4899", "gif"),
        (FluentIcon.DOWNLOAD,  "视频下载", "#F59E4C", "download"),
        (FluentIcon.ADD,       "更多工具", "#5F6472", "format_detect"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        self.items = []
        for icon, title, accent, key in self._ITEMS:
            item = QuickFunctionItem(icon, title, accent, key, self)
            self.items.append(item)
            lay.addWidget(item)

    def connect_nav(self, nav_fn):
        """把每一项点击连接到导航函数 nav_fn(nav_key)。"""
        for item in self.items:
            item.clicked.connect(
                lambda checked=False, k=item.nav_key: nav_fn(k))
