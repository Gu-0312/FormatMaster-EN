"""插件：字数统计（字符/汉字/单词/行数/段落）。"""

import re
from plugins._i18n import t

from PySide6.QtWidgets import (QHBoxLayout, QPlainTextEdit, QVBoxLayout,
                               QWidget)
from qfluentwidgets import PrimaryPushButton

PLUGIN_INFO = {
    "name": "字数统计",
    "description": "字符 / 汉字 / 单词 / 行数 / 段落统计",
    "version": "1.0.0",
}

_HANZI = re.compile(r"[\u4e00-\u9fff]")
_WORD = re.compile(r"[A-Za-z0-9]+")
_PUNCT = re.compile(r"[，。！？；：、,.!?;:'\"()（）\[\]【】]")
_SPACE = re.compile(r"\s")


def count_stats(text):
    """返回统计 dict。"""
    no_space = _SPACE.sub("", text)
    return {
        t("总字符"): len(text),
        t("去空白字符"): len(no_space),
        t("汉字"): len(_HANZI.findall(text)),
        t("英文/数字词"): len(_WORD.findall(text)),
        t("标点"): len(_PUNCT.findall(text)),
        t("行数"): len(text.splitlines()),
        t("段落"): len([p for p in text.split("\n\n") if p.strip()]),
    }


class WordCountPanel(QWidget):
    """字数统计面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        self.ed_in = QPlainTextEdit()
        self.ed_in.setPlaceholderText(t("粘贴或输入文本，自动实时统计…"))
        self.ed_in.textChanged.connect(self._stats)
        v.addWidget(self.ed_in, 1)

        row = QHBoxLayout()
        btn = PrimaryPushButton(t("统计"))
        btn.clicked.connect(self._stats)
        row.addWidget(btn)
        row.addStretch(1)
        v.addLayout(row)

        self.ed_out = QPlainTextEdit()
        self.ed_out.setReadOnly(True)
        self.ed_out.setMaximumHeight(180)
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

    def _stats(self):
        text = self.ed_in.toPlainText()
        if not text:
            self.ed_out.setPlainText("")
            return
        st = count_stats(text)
        lines = [f"{k}：{v}" for k, v in st.items()]
        self.ed_out.setPlainText("\n".join(lines))


PANEL_CLASS = WordCountPanel


def on_load(ctx):
    pass


def on_unload():
    pass
