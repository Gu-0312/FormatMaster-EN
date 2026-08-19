
from plugins._i18n import t
"""示例插件：文本反转工具。

插件约定：
    PLUGIN_INFO  — 元数据（name 必填）
    PANEL_CLASS  — 可选，提供界面（QWidget 子类），插件管理面板可打开
    on_load(ctx) — 可选，加载回调
    on_unload()  — 可选，卸载回调
"""

from PySide6.QtWidgets import (QHBoxLayout, QPlainTextEdit, QVBoxLayout,
                               QWidget)
from qfluentwidgets import PrimaryPushButton

PLUGIN_INFO = {
    "name": "文本反转",
    "description": "把输入的每一行文本反转（示例插件）",
    "version": "1.0.0",
}


class TextReversePanel(QWidget):
    """示例插件面板：输入文本 → 反转输出。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        self.ed_in = QPlainTextEdit()
        self.ed_in.setPlaceholderText(t("输入要反转的文本…"))
        v.addWidget(self.ed_in)
        row = QHBoxLayout()
        btn = PrimaryPushButton(t("反转"))
        btn.clicked.connect(self._reverse)
        row.addStretch(1)
        row.addWidget(btn)
        v.addLayout(row)
        self.ed_out = QPlainTextEdit()
        self.ed_out.setReadOnly(True)
        v.addWidget(self.ed_out)

    def _reverse(self):
        lines = [ln[::-1] for ln in self.ed_in.toPlainText().splitlines()]
        self.ed_out.setPlainText("\n".join(lines))


PANEL_CLASS = TextReversePanel


def on_load(ctx):
    """加载回调：ctx 为 dict（含 window/services，可按需使用）。"""
    pass


def on_unload():
    pass
