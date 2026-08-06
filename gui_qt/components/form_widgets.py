"""form_widgets — 统一参数表单组件（Prism 设计系统）。

所有功能面板的参数区换用本组件，统一视觉：
- FormSection：带图标的卡片区块（标题 + 内容）
- FormGrid：等宽参数网格（label 在上 / 控件在下，悬停高亮提示）
- FormItem：单个参数项（图标 + 标签 + 控件 + 悬停提示）

风格：左对齐标签、等宽控件、区块内分组、hover 提示图标，
与首页 Prism 视觉语言一致。
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QVBoxLayout,
                               QWidget)
from qfluentwidgets import CaptionLabel, IconWidget

from gui_qt.components import design_system as ds
from gui_qt.components.card import Card


class FormSection(Card):
    """带图标的参数区块卡片。"""

    def __init__(self, title, icon=None, parent=None):
        super().__init__(parent, radius=12)
        self.setObjectName("formSection")

        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(18, 16, 18, 18)
        self.v.setSpacing(12)

        # 区块标题（图标 + 文字）—— L2 区块标题 15px/700
        head = QHBoxLayout()
        head.setSpacing(8)
        if icon is not None:
            iw = IconWidget(icon, self)
            iw.setFixedSize(16, 16)
            iw.setStyleSheet(f"color: {ds.accent()};")
            head.addWidget(iw)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {ds.ink()};"
            "border: none; background: transparent;")
        head.addWidget(self.title_label)
        head.addStretch(1)
        self.v.addLayout(head)

    def add_form(self, grid):
        """添加一个 FormGrid 内容区。"""
        self.v.addLayout(grid)

    def add_widget(self, w):
        self.v.addWidget(w)

    def add_layout(self, layout):
        """添加一个子布局（QHBoxLayout 等）。"""
        self.v.addLayout(layout)

    def add_spacing(self, h=6):
        self.v.addSpacing(h)


class FormGrid(QGridLayout):
    """等宽参数网格：每列 label 在上、控件在下。"""

    def __init__(self, columns=2):
        super().__init__()
        self._columns = columns
        self._col = 0
        self._row = 0
        self.setHorizontalSpacing(16)
        self.setVerticalSpacing(12)

    def add_field(self, label, control, icon=None, hint=None, colspan=1):
        """添加一个参数项。control 为任意 Qt 控件。"""
        col = self._col
        row = self._row
        # 标签（带可选图标）
        lbl_row = QHBoxLayout()
        lbl_row.setSpacing(4)
        if icon is not None:
            iw = IconWidget(icon, None)
            iw.setFixedSize(14, 14)
            iw.setStyleSheet(f"color: {ds.ink_dis()};")
            lbl_row.addWidget(iw)
        lbl = CaptionLabel(label)
        lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {ds.ink_sec()};"
            "border: none; background: transparent;")
        lbl_row.addWidget(lbl)
        if hint:
            tip = CaptionLabel("ⓘ")
            tip.setStyleSheet(
                f"font-size: 11px; color: {ds.ink_dis()};"
                "border: none; background: transparent;")
            tip.setToolTip(hint)
            lbl_row.addWidget(tip)
        lbl_row.addStretch(1)
        self.addLayout(lbl_row, row, col, 1, colspan)
        # 控件
        self.addWidget(control, row + 1, col, 1, colspan)
        self.setColumnStretch(col, 1)
        # 下一个位置：右移一列，到底换行
        self._col += colspan
        if self._col >= self._columns:
            self._col = 0
            self._row += 2
        return control


class FormRow(QHBoxLayout):
    """水平排布的表单行（两个控件并排）。"""

    def __init__(self, label, control, hint=None):
        super().__init__()
        self.setSpacing(8)
        lbl = CaptionLabel(label)
        lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {ds.ink_sec()};"
            "border: none; background: transparent;")
        self.addWidget(lbl)
        self.addWidget(control, 1)
