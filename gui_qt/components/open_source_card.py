"""open_source_card — 首页「开源项目」面板（替代原「新手指南」）。

面向开源软件定位：MIT 协议、GitHub 仓库、Star / 提交 Issue / 参与贡献
三个动作入口。点击跳转浏览器打开对应链接。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, FluentIcon, IconWidget)

from gui_qt.i18n import tr
from gui_qt.components import design_system as ds
from gui_qt.components.card import Card

GITHUB_URL = "https://github.com/Gu-0312/FormatMaster-EN"
# 开源动作：图标 / 标题 / 描述 / URL
_ACTIONS = [
    (FluentIcon.HEART, "支持这个项目",
     "你的支持是开源项目前进的动力",
     f"{GITHUB_URL}"),
    (FluentIcon.FEEDBACK, "提交 Issue",
     "反馈 Bug 或提出新功能建议",
     f"{GITHUB_URL}/issues"),
    (FluentIcon.CODE, "参与贡献",
     "Fork 仓库，提交你的代码改进",
     f"{GITHUB_URL}"),
]


class _ActionRow(QWidget):
    """单个开源动作行。"""

    def __init__(self, icon, title, desc, url, parent=None):
        super().__init__(parent)
        self._url = url
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(54)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(12)

        iw = IconWidget(icon, self)
        iw.setFixedSize(20, 20)
        iw.setStyleSheet(f"color: {ds.accent()};")
        lay.addWidget(iw, 0, Qt.AlignVCenter)

        v = QVBoxLayout()
        v.setSpacing(1)
        self.title_label = CaptionLabel(title, self)
        self.title_label.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {ds.ink()};"
            "border: none; background: transparent;")
        v.addWidget(self.title_label)
        self.desc_label = CaptionLabel(desc, self)
        self.desc_label.setStyleSheet(
            f"font-size: 11px; color: {ds.ink_sec()};"
            "border: none; background: transparent;")
        v.addWidget(self.desc_label)
        v.addStretch(1)
        lay.addLayout(v, 1)

        self.go = IconWidget(FluentIcon.CHEVRON_RIGHT, self)
        self.go.setFixedSize(14, 14)
        self.go.setStyleSheet(f"color: {ds.ink_dis()};")
        lay.addWidget(self.go, 0, Qt.AlignVCenter)

    def mouseReleaseEvent(self, e):
        if self.rect().contains(e.position().toPoint()):
            QDesktopServices.openUrl(QUrl(self._url))
        super().mouseReleaseEvent(e)

    def enterEvent(self, e):
        self.title_label.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {ds.accent()};"
            "border: none; background: transparent;")
        self.go.setStyleSheet(f"color: {ds.accent()};")
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.title_label.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {ds.ink()};"
            "border: none; background: transparent;")
        self.go.setStyleSheet(f"color: {ds.ink_dis()};")
        super().leaveEvent(e)


class OpenSourceCard(Card):
    """开源项目面板。"""

    def __init__(self, parent=None):
        super().__init__(parent, radius=12)

        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 14)
        v.setSpacing(8)

        header = QHBoxLayout()
        icon = IconWidget(FluentIcon.GITHUB, self)
        icon.setFixedSize(18, 18)
        header.addWidget(icon)
        title = QLabel(tr("开源项目", "Open source"))
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {ds.ink()};"
            "border: none; background: transparent;")
        header.addWidget(title)
        header.addStretch(1)
        v.addLayout(header)

        for act_icon, t, d, url in _ACTIONS:
            v.addWidget(_ActionRow(act_icon, t, d, url, self))

        v.addStretch(1)
