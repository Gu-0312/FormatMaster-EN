"""插件：文本对比 Diff（左右并排，行级差异高亮，difflib 标准库）。"""

import difflib
from plugins._i18n import t

from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QHBoxLayout, QPlainTextEdit, QSplitter,
                               QVBoxLayout, QWidget, QTextEdit)
from qfluentwidgets import CaptionLabel, PrimaryPushButton

PLUGIN_INFO = {
    "name": "文本对比",
    "description": "左右对比两段文本，高亮差异行",
    "version": "1.0.0",
}


class TextDiffPanel(QWidget):
    """文本对比面板：左/右两栏 + 差异行高亮。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        split = QSplitter()
        self.ed_left = QPlainTextEdit()
        self.ed_left.setPlaceholderText(t("文本 A…"))
        self.ed_right = QPlainTextEdit()
        self.ed_right.setPlaceholderText(t("文本 B…"))
        split.addWidget(self.ed_left)
        split.addWidget(self.ed_right)
        split.setSizes([300, 300])
        v.addWidget(split, 1)

        row = QHBoxLayout()
        btn = PrimaryPushButton(t("对比"))
        btn.clicked.connect(self._diff)
        row.addWidget(btn)
        self.lb_stat = CaptionLabel("")
        row.addWidget(self.lb_stat)
        row.addStretch(1)
        v.addLayout(row)

        self.ed_out = QPlainTextEdit()
        self.ed_out.setReadOnly(True)
        self.ed_out.setMaximumHeight(150)
        v.addWidget(self.ed_out)
        self._apply_theme()
        from gui_qt.components import design_system as ds
        ds.bind_theme(self, self._apply_theme)

    def _apply_theme(self):
        from gui_qt.components import design_system as ds
        t = ds.tokens()
        self.setStyleSheet(
            f"QPlainTextEdit {{ background: {t['card_bg']};"
            f" color: {t['ink']}; border: 1px solid {t['border']};"
            f" border-radius: 6px; padding: 4px; font-size: 13px; }}")

    def _diff(self):
        a = self.ed_left.toPlainText().splitlines()
        b = self.ed_right.toPlainText().splitlines()
        sm = difflib.SequenceMatcher(None, a, b)
        self.ed_left.setExtraSelections([])
        self.ed_right.setExtraSelections([])
        del_fmt = QTextCharFormat()
        del_fmt.setBackground(QColor(255, 100, 100, 70))
        add_fmt = QTextCharFormat()
        add_fmt.setBackground(QColor(100, 220, 100, 70))

        dels = adds = 0
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            if tag in ("delete", "replace"):
                self._mark_lines(self.ed_left, i1, i2, del_fmt)
                dels += i2 - i1
            if tag in ("insert", "replace"):
                self._mark_lines(self.ed_right, j1, j2, add_fmt)
                adds += j2 - j1
        self.lb_stat.setText(
            t("差异：删除 {dels} 行 · 新增 {adds} 行").format(dels=dels, adds=adds)
            + (" · " + t("文本一致") if dels + adds == 0 else ""))

        # 详细 diff 文本
        ud = list(difflib.unified_diff(a, b, lineterm="", n=1))
        self.ed_out.setPlainText("\n".join(ud[2:]) if len(ud) > 2
                                 else t("（文本完全一致）"))

    def _mark_lines(self, edit, start, end, fmt):
        sel = list(edit.extraSelections())
        doc = edit.document()
        for ln in range(start, end):
            block = doc.findBlockByNumber(ln)
            if not block.isValid():
                continue
            c = QTextCursor(block)
            c.setPosition(block.position())
            c.setPosition(block.position() + block.length() - 1,
                          QTextCursor.KeepAnchor)
            sel.append(QTextEdit.ExtraSelection(cursor=c, format=fmt))
        edit.setExtraSelections(sel)


PANEL_CLASS = TextDiffPanel


def on_load(ctx):
    pass


def on_unload():
    pass
