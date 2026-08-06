"""empty_state — 空态组件（Prism 设计系统）。

图标使用棱镜色调柔和背景圆角方块，文字层次更精致，
支持可选的动作按钮。用于未迁移功能的占位页与空列表。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, FluentIcon, IconWidget,
                            PrimaryPushButton, SubtitleLabel)

from gui_qt.components import design_system as ds


class _SoftIconBox(QWidget):
    """带柔和棱镜色背景的图标方块。"""

    def __init__(self, icon, parent=None):
        super().__init__(parent)
        self.setFixedSize(68, 68)
        self._icon = IconWidget(icon, self)
        self._icon.setFixedSize(36, 36)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._icon, 0, Qt.AlignCenter)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing)
        colors = ds.prism_colors()
        c = QColor(colors[0])
        c.setAlpha(24)
        p.setBrush(c)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(self.rect(), 18, 18)


class EmptyState(QVBoxLayout):
    """居中展示的空态布局，直接 setLayout 到页面即可。

    btn_text / btn_clicked: 可选的动作按钮。
    """

    def __init__(self, icon=FluentIcon.INFO, title="即将上线",
                 desc="该功能正在迁移中，敬请期待",
                 btn_text=None, btn_clicked=None, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setSpacing(10)

        self.icon_w = _SoftIconBox(icon)
        self.title_label = SubtitleLabel(title)
        self.title_label.setStyleSheet(
            f"font-size: 17px; font-weight: 600; color: {ds.ink()};")
        self.desc_label = BodyLabel(desc)
        self.desc_label.setStyleSheet(
            f"font-size: 13px; color: {ds.ink_sec()};")
        self.desc_label.setWordWrap(True)
        self.desc_label.setAlignment(Qt.AlignCenter)
        self.desc_label.setMaximumWidth(460)

        self.addStretch(1)
        self.addWidget(self.icon_w, 0, Qt.AlignHCenter)
        self.addSpacing(4)
        self.addWidget(self.title_label, 0, Qt.AlignHCenter)
        self.addWidget(self.desc_label, 0, Qt.AlignHCenter)

        if btn_text and btn_clicked:
            self.addSpacing(8)
            btn = PrimaryPushButton(btn_text)
            btn.setFixedWidth(150)
            btn.clicked.connect(btn_clicked)
            self.addWidget(btn, 0, Qt.AlignHCenter)

        self.addStretch(2)
