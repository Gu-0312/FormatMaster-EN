"""插件：摩斯电码互转（字母 / 数字 → 点划；点划 → 文本）。"""

import re
from plugins._i18n import t

from PySide6.QtWidgets import (QHBoxLayout, QPlainTextEdit, QVBoxLayout,
                               QWidget)
from qfluentwidgets import PrimaryPushButton

PLUGIN_INFO = {
    "name": "摩斯电码",
    "description": "文本 ↔ 摩斯电码（字母/数字/标点）互转",
    "version": "1.1.0",
}

_MORSE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".",
    "F": "..-.", "G": "--.", "H": "....", "I": "..", "J": ".---",
    "K": "-.-", "L": ".-..", "M": "--", "N": "-.", "O": "---",
    "P": ".--.", "Q": "--.-", "R": ".-.", "S": "...", "T": "-",
    "U": "..-", "V": "...-", "W": ".--", "X": "-..-", "Y": "-.--",
    "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--",
    "4": "....-", "5": ".....", "6": "-....", "7": "--...",
    "8": "---..", "9": "----.",
    # 常用标点符号（ITU 标准）
    ".": ".-.-.-", ",": "--..--", "?": "..--..", "!": "-.-.--",
    ":": "---...", ";": "-.-.-.", "(": "-.--.", ")": "-.--.-",
    "'": ".----.", '"': ".-..-.", "-": "-....-", "/": "-..-.",
    "=": "-...-", "+": ".-.-.", "@": ".--.-.", "_": "..--.-",
    "$": "...-..-", "&": ".-...",
}
_REV = {v: k for k, v in _MORSE.items()}


def encode_morse(text):
    """文本 → 摩斯（字母/数字转码，其余忽略；词间空行分隔）。"""
    out = []
    for word in re.split(r"\s+", text.strip()):
        codes = [_MORSE.get(ch.upper()) for ch in word if ch.upper() in _MORSE]
        if codes:
            out.append(" ".join(codes))
    return "  /  ".join(out) if out else ""


def decode_morse(text):
    """摩斯 → 文本（/ 分隔单词，空格分隔字母）。"""
    words = []
    for token in text.replace("/", " / ").split():
        if token == "/":
            words.append(" ")
        else:
            ch = _REV.get(token)
            if ch:
                words.append(ch)
    return "".join(words).strip()


class MorsePanel(QWidget):
    """摩斯电码面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        self.ed_in = QPlainTextEdit()
        self.ed_in.setPlaceholderText(t("输入文本或摩斯电码…\n文本：SOS  hello\n摩斯：... --- ..."))
        v.addWidget(self.ed_in, 1)

        row = QHBoxLayout()
        btn_enc = PrimaryPushButton(t("转摩斯"))
        btn_enc.clicked.connect(self._encode)
        row.addWidget(btn_enc)
        btn_dec = PrimaryPushButton(t("转文本"))
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
        self.ed_out.setPlainText(encode_morse(self.ed_in.toPlainText()))

    def _decode(self):
        self.ed_out.setPlainText(decode_morse(self.ed_in.toPlainText()))


PANEL_CLASS = MorsePanel


def on_load(ctx):
    pass


def on_unload():
    pass
