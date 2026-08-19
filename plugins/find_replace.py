"""插件：批量查找替换（支持正则）。

纯文本处理，无文件系统副作用。界面：输入区 + 查找/替换词 + 正则开关。
"""

import re
from plugins._i18n import t

from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLineEdit,
                               QPlainTextEdit, QVBoxLayout, QWidget)
from qfluentwidgets import PrimaryPushButton

PLUGIN_INFO = {
    "name": "批量查找替换",
    "description": "文本批量查找替换，可选正则表达式",
    "version": "1.0.0",
}


class FindReplacePanel(QWidget):
    """查找替换面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        self.ed_in = QPlainTextEdit()
        self.ed_in.setPlaceholderText(t("输入要处理的文本…"))
        v.addWidget(self.ed_in, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.ed_find = QLineEdit()
        self.ed_find.setPlaceholderText(t("查找"))
        row.addWidget(self.ed_find, 1)
        self.ed_rep = QLineEdit()
        self.ed_rep.setPlaceholderText(t("替换为"))
        row.addWidget(self.ed_rep, 1)
        self.cb_regex = QCheckBox(t("正则"))
        row.addWidget(self.cb_regex)
        btn = PrimaryPushButton(t("替换"))
        btn.clicked.connect(self._run)
        row.addWidget(btn)
        v.addLayout(row)

        self.ed_out = QPlainTextEdit()
        self.ed_out.setReadOnly(True)
        v.addWidget(self.ed_out, 1)
        self._apply_theme()
        from gui_qt.components import design_system as ds
        ds.bind_theme(self, self._apply_theme)

    def _apply_theme(self):
        """按当前主题刷新输入区样式（亮/暗切换即时生效）。"""
        from gui_qt.components import design_system as ds
        t = ds.tokens()
        self.setStyleSheet(
            f"QPlainTextEdit, QLineEdit {{ background: {t['card_bg']};"
            f" color: {t['ink']}; border: 1px solid {t['border']};"
            f" border-radius: 6px; padding: 4px; font-size: 13px; }}"
            f"QCheckBox {{ color: {t['ink']}; }}")

    def _run(self):
        text = self.ed_in.toPlainText()
        find = self.ed_find.text()
        rep = self.ed_rep.text()
        if not find:
            self.ed_out.setPlainText(text)
            return
        try:
            if self.cb_regex.isChecked():
                out, n = re.subn(find, rep, text)
            else:
                out, n = text.replace(find, rep), text.count(find)
            self.ed_out.setPlainText(out)
            self.ed_out.setToolTip(t("替换 {n} 处").format(n=n))
        except re.error as e:
            self.ed_out.setPlainText(t("正则错误：{e}").format(e=e))


PANEL_CLASS = FindReplacePanel


def on_load(ctx):
    pass


def on_unload():
    pass
