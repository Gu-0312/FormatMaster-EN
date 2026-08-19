"""插件：HTML 实时预览（Qt 原生渲染，无第三方依赖，支持导入文件）。"""

import os
from plugins._i18n import t

from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QPlainTextEdit,
                               QSplitter, QTextBrowser, QVBoxLayout, QWidget)
from qfluentwidgets import PrimaryPushButton

PLUGIN_INFO = {
    "name": "HTML 预览",
    "description": "HTML 实时预览，支持导入 .html 文件",
    "version": "1.1.0",
}

_DEMO = """<h2 style="color:#4F6EF7">HTML 预览</h2>
<p>支持 <b>加粗</b>、<i>斜体</i>、<a href="https://example.com">链接</a>。</p>
<ul><li>列表项一</li><li>列表项二</li></ul>
<button style="background:#4F6EF7;color:#fff;border:none;border-radius:6px;
padding:8px 16px">按钮</button>
<div style="margin-top:12px;background:#E6F1FB;border-radius:8px;
padding:12px">浅色卡片</div>
"""


class HtmlPanel(QWidget):
    """HTML 预览面板：左输入右预览，支持导入文件。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.btn_pick = PrimaryPushButton(t("导入 HTML 文件"))
        self.btn_pick.clicked.connect(self._pick)
        bar.addWidget(self.btn_pick)
        self.btn_new = PrimaryPushButton(t("新建"))
        self.btn_new.clicked.connect(self._new)
        bar.addWidget(self.btn_new)
        bar.addStretch(1)
        lay.addLayout(bar)

        split = QSplitter()
        self.ed_in = QPlainTextEdit()
        self.ed_in.setPlaceholderText(t("输入 HTML，或导入 .html 文件…"))
        self.ed_in.setPlainText(_DEMO)
        self.ed_in.textChanged.connect(self._render)
        split.addWidget(self.ed_in)
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(True)
        split.addWidget(self.preview)
        split.setSizes([300, 340])
        lay.addWidget(split)
        self._render()
        self._apply_theme()
        from gui_qt.components import design_system as ds
        ds.bind_theme(self, self._apply_theme)

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t("选择 HTML 文件"), "",
            "HTML (*.html *.htm);;所有文件 (*)")
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
            f" border: 1px solid {t['border']};"
            f" border-radius: 6px; }}")

    def _render(self):
        self.preview.setHtml(self.ed_in.toPlainText())


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


PANEL_CLASS = HtmlPanel


def on_load(ctx):
    pass


def on_unload():
    pass
