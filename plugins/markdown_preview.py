"""插件：Markdown 实时预览（Qt 原生渲染，无第三方依赖，支持导入文件）。"""

import os
from plugins._i18n import t

from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QPlainTextEdit,
                               QSplitter, QTextBrowser, QVBoxLayout, QWidget)
from qfluentwidgets import PrimaryPushButton

PLUGIN_INFO = {
    "name": "Markdown 预览",
    "description": "Markdown 实时预览，支持导入 .md 文件",
    "version": "1.1.0",
}

_DEMO = """# 标题

**加粗**、*斜体*、`代码`、[链接](https://example.com)

- 列表项 1
- 列表项 2

> 引用块

```python
print("hello")
```
"""


class MarkdownPanel(QWidget):
    """Markdown 预览面板：左输入右预览，支持导入文件。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.btn_pick = PrimaryPushButton(t("导入 Markdown 文件"))
        self.btn_pick.clicked.connect(self._pick)
        bar.addWidget(self.btn_pick)
        self.btn_new = PrimaryPushButton(t("新建"))
        self.btn_new.clicked.connect(self._new)
        bar.addWidget(self.btn_new)
        bar.addStretch(1)
        lay.addLayout(bar)

        split = QSplitter()
        self.ed_in = QPlainTextEdit()
        self.ed_in.setPlaceholderText(t("输入 Markdown，或导入 .md 文件…"))
        self.ed_in.setPlainText(_DEMO)
        self.ed_in.textChanged.connect(self._render)
        split.addWidget(self.ed_in)
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(True)
        split.addWidget(self.preview)
        split.setSizes([320, 320])
        lay.addWidget(split)
        self._render()
        self._apply_theme()
        from gui_qt.components import design_system as ds
        ds.bind_theme(self, self._apply_theme)

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t("选择 Markdown 文件"), "",
            "Markdown (*.md *.markdown *.txt);;所有文件 (*)")
        if not path:
            return
        try:
            text = _read_text(path)
        except OSError as e:
            self.ed_in.setPlainText(t("读取失败：{e}").format(e=e))
            return
        self.ed_in.setPlainText(text)
        self.preview.setToolTip(path)

    def _new(self):
        self.ed_in.setPlainText(_DEMO)
        self.preview.setToolTip("")

    def _apply_theme(self):
        from gui_qt.components import design_system as ds
        t = ds.tokens()
        self.ed_in.setStyleSheet(
            f"QPlainTextEdit {{ background: {t['card_bg']};"
            f" color: {t['ink']}; border: 1px solid {t['border']};"
            f" border-radius: 6px; padding: 4px; font-size: 13px; }}")
        self.preview.setStyleSheet(
            f"QTextBrowser {{ background: {t['card_bg']};"
            f" color: {t['ink']}; border: 1px solid {t['border']};"
            f" border-radius: 6px; font-size: 13px; }}")

    def _render(self):
        self.preview.setMarkdown(self.ed_in.toPlainText())


def _read_text(path):
    """自动检测编码读取文本文件。"""
    with open(path, "rb") as fh:
        data = fh.read()
    for enc in ("utf-8-sig", "utf-8", "gbk", "big5", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


PANEL_CLASS = MarkdownPanel


def on_load(ctx):
    pass


def on_unload():
    pass
