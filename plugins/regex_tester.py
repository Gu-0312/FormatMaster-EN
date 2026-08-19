"""插件：正则表达式测试器（实时匹配计数 + 文本高亮）。"""

import re
from plugins._i18n import t

from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QHBoxLayout, QLineEdit, QPlainTextEdit,
                               QVBoxLayout, QWidget, QTextEdit)
from qfluentwidgets import CaptionLabel, PrimaryPushButton

PLUGIN_INFO = {
    "name": "正则测试器",
    "description": "实时测试正则表达式，高亮匹配结果",
    "version": "1.0.0",
}


class RegexTesterPanel(QWidget):
    """正则测试面板：输入正则 + 文本 → 实时高亮 + 匹配列表。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(CaptionLabel(t("正则")))
        self.ed_regex = QLineEdit()
        self.ed_regex.setPlaceholderText(t("例如：\d+ 或 [a-z]+"))
        self.ed_regex.textChanged.connect(self._test)
        row.addWidget(self.ed_regex, 1)
        btn = PrimaryPushButton(t("测试"))
        btn.clicked.connect(self._test)
        row.addWidget(btn)
        v.addLayout(row)

        self.ed_text = QPlainTextEdit()
        self.ed_text.setPlaceholderText(t("输入要匹配的文本…"))
        self.ed_text.textChanged.connect(self._test)
        v.addWidget(self.ed_text, 2)

        self.lb_count = CaptionLabel("")
        v.addWidget(self.lb_count)

        self.ed_out = QPlainTextEdit()
        self.ed_out.setReadOnly(True)
        v.addWidget(self.ed_out, 1)
        self._apply_theme()
        from gui_qt.components import design_system as ds
        ds.bind_theme(self, self._apply_theme)

    def _apply_theme(self):
        from gui_qt.components import design_system as ds
        t = ds.tokens()
        self.setStyleSheet(
            f"QPlainTextEdit, QLineEdit {{ background: {t['card_bg']};"
            f" color: {t['ink']}; border: 1px solid {t['border']};"
            f" border-radius: 6px; padding: 4px; font-size: 13px; }}"
            f"QLineEdit {{ color: {t['ink']}; }}")

    def _test(self):
        pattern = self.ed_regex.text()
        text = self.ed_text.toPlainText()
        if not pattern or not text:
            self.ed_text.setExtraSelections([])
            self.lb_count.setText("")
            self.ed_out.setPlainText("")
            return
        try:
            matches = list(re.finditer(pattern, text))
        except re.error as e:
            self.ed_text.setExtraSelections([])
            self.lb_count.setText(t("正则错误：{e}").format(e=e))
            self.ed_out.setPlainText("")
            return
        # 高亮全部匹配
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(255, 213, 0, 110))
        selections = []
        for m in matches:
            c = QTextCursor(self.ed_text.document())
            c.setPosition(m.start())
            c.setPosition(m.end(), QTextCursor.KeepAnchor)
            selections.append(QTextEdit.ExtraSelection(cursor=c, format=fmt))
        self.ed_text.setExtraSelections(selections)
        self.lb_count.setText(f"匹配 {len(matches)} 处")
        lines = []
        for i, m in enumerate(matches[:200], 1):
            groups = m.groups()
            tail = f" 组={groups}" if groups else ""
            lines.append(f"{i}. 「{m.group()}」 @ {m.start()}{tail}")
        self.ed_out.setPlainText("\n".join(lines))


PANEL_CLASS = RegexTesterPanel


def on_load(ctx):
    pass


def on_unload():
    pass
