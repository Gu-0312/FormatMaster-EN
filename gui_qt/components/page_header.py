"""page_header — 页面统一标题组件（Prism 设计系统）。

标题区由左侧彩色强调条 + 标题 + 副标题组成，
所有页面与功能面板共用，保证层级一致。
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, IconWidget, SubtitleLabel

from gui_qt.components import design_system as ds


class PageHeader(QWidget):
    """页面标题：强调条 + 主标题 + 可选副标题与图标。"""

    def __init__(self, title, subtitle="", icon=None, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")

        h = QHBoxLayout(self)
        h.setContentsMargins(4, 0, 4, 0)
        h.setSpacing(12)

        # 左侧彩色强调条
        bar = QWidget()
        bar.setFixedSize(3, 34)
        bar.setStyleSheet(
            f"background: {ds.accent()}; border-radius: 2px;")
        h.addWidget(bar, 0, Qt.AlignVCenter)

        if icon is not None:
            iw = IconWidget(icon, self)
            iw.setFixedSize(20, 20)
            iw.setStyleSheet(f"color: {ds.accent()};")
            h.addWidget(iw, 0, Qt.AlignVCenter)

        v = QVBoxLayout()
        v.setSpacing(2)
        self.title_label = SubtitleLabel(title)
        self.title_label.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {ds.ink()};")
        v.addWidget(self.title_label)
        if subtitle:
            self.subtitle_label = CaptionLabel(subtitle)
            self.subtitle_label.setStyleSheet(
                f"font-size: 12px; color: {ds.ink_sec()};")
            v.addWidget(self.subtitle_label)
        else:
            self.subtitle_label = None
        v.setAlignment(Qt.AlignVCenter)
        h.addLayout(v, 1)

        self.setFixedHeight(56 if subtitle else 46)

    def set_title(self, text):
        self.title_label.setText(text)

    def set_subtitle(self, text):
        if self.subtitle_label is not None:
            self.subtitle_label.setText(text)
