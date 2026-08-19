"""插件：URL 编解码（quote / unquote，支持 + 空格模式）。"""

import urllib.parse
from plugins._i18n import t

from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QPlainTextEdit,
                               QVBoxLayout, QWidget)
from qfluentwidgets import PrimaryPushButton

PLUGIN_INFO = {
    "name": "URL 编解码",
    "description": "URL / 文本编码解码（quote / unquote）",
    "version": "1.0.0",
}


class UrlCodecPanel(QWidget):
    """URL 编解码面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        self.ed_in = QPlainTextEdit()
        self.ed_in.setPlaceholderText(t("输入要编码/解码的文本…"))
        v.addWidget(self.ed_in, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        btn_enc = PrimaryPushButton(t("编码"))
        btn_enc.clicked.connect(self._encode)
        row.addWidget(btn_enc)
        btn_dec = PrimaryPushButton(t("解码"))
        btn_dec.clicked.connect(self._decode)
        row.addWidget(btn_dec)
        self.cb_plus = QCheckBox(t("空格用 + 表示"))
        row.addWidget(self.cb_plus)
        row.addStretch(1)
        v.addLayout(row)

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
            f"QPlainTextEdit {{ background: {t['card_bg']};"
            f" color: {t['ink']}; border: 1px solid {t['border']};"
            f" border-radius: 6px; padding: 4px; font-size: 13px; }}"
            f"QCheckBox {{ color: {t['ink']}; }}")

    def _encode(self):
        text = self.ed_in.toPlainText()
        if self.cb_plus.isChecked():
            out = urllib.parse.quote_plus(text)
        else:
            out = urllib.parse.quote(text)
        self.ed_out.setPlainText(out)

    def _decode(self):
        text = self.ed_in.toPlainText()
        if self.cb_plus.isChecked():
            out = urllib.parse.unquote_plus(text)
        else:
            out = urllib.parse.unquote(text)
        self.ed_out.setPlainText(out)


PANEL_CLASS = UrlCodecPanel


def on_load(ctx):
    pass


def on_unload():
    pass
