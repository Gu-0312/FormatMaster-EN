
from plugins._i18n import t
"""插件：Unicode 编解码（中文 ↔ \\uXXXX 转义序列）。"""

from PySide6.QtWidgets import (QHBoxLayout, QPlainTextEdit, QVBoxLayout,
                               QWidget)
from qfluentwidgets import PrimaryPushButton

PLUGIN_INFO = {
    "name": "Unicode 编解码",
    "description": "文本 ↔ \\uXXXX 转义（如 中 → \\u4e2d）",
    "version": "1.0.0",
}


def encode_unicode(text):
    """非 ASCII 字符 → \\uXXXX；ASCII 保留。"""
    out = []
    for ch in text:
        code = ord(ch)
        if code < 128:
            out.append(ch)
        elif code <= 0xFFFF:
            out.append(f"\\u{code:04x}")
        else:
            out.append(f"\\U{code:08x}")
    return "".join(out)


def decode_unicode(text):
    """\\uXXXX / \\UXXXXXXXX → 字符；普通文本原样保留。"""
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "\\" and i + 1 < n and text[i + 1] in "uU":
            k = 4 if text[i + 1] == "u" else 8
            seg = text[i + 2:i + 2 + k]
            if len(seg) == k:
                try:
                    out.append(chr(int(seg, 16)))
                    i += 2 + k
                    continue
                except ValueError:
                    pass
        out.append(text[i])
        i += 1
    return "".join(out)


class UnicodePanel(QWidget):
    """Unicode 编解码面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        self.ed_in = QPlainTextEdit()
        self.ed_in.setPlaceholderText(t("输入文本或 \\uXXXX 转义序列…\n如：你好 / \\u4f60\\u597d"))
        v.addWidget(self.ed_in, 1)

        row = QHBoxLayout()
        btn_enc = PrimaryPushButton(t("编码"))
        btn_enc.clicked.connect(self._encode)
        row.addWidget(btn_enc)
        btn_dec = PrimaryPushButton(t("解码"))
        btn_dec.clicked.connect(self._decode)
        row.addWidget(btn_dec)
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
            f" border-radius: 6px; padding: 4px; font-size: 13px; }}")

    def _encode(self):
        self.ed_out.setPlainText(encode_unicode(self.ed_in.toPlainText()))

    def _decode(self):
        self.ed_out.setPlainText(decode_unicode(self.ed_in.toPlainText()))


PANEL_CLASS = UnicodePanel


def on_load(ctx):
    pass


def on_unload():
    pass
