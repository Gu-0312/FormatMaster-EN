
from plugins._i18n import t
"""插件：进制转换（2-36 任意进制互转，支持前缀自动识别与大小写）。

输入支持十进制、0x/0b/0o 前缀，也可选择「源进制」手动指定；
目标进制可自由选择（2-36），十六进制输出可选大写。
"""

from PySide6.QtWidgets import (QHBoxLayout, QLineEdit, QPlainTextEdit,
                               QVBoxLayout, QWidget)
from qfluentwidgets import CaptionLabel, ComboBox, PrimaryPushButton

PLUGIN_INFO = {
    "name": "进制转换",
    "description": "2-36 任意进制互转（自动识别前缀 / 手动指定源进制）",
    "version": "2.0.0",
}

_BASES = [str(b) for b in range(2, 37)]  # 2-36


def parse_int(text, src_base=None):
    """解析数字字符串 → int。

    src_base 为 None 时自动识别 0x/0b/0o 前缀，否则按十进制；
    显式指定 src_base 时按该进制解析。
    """
    s = text.strip().replace("_", "").replace(",", "")
    if not s:
        return None
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    try:
        if src_base is not None:
            return -int(s, src_base) if neg else int(s, src_base)
        low = s.lower()
        if low.startswith("0x"):
            return -int(s, 16) if neg else int(s, 16)
        if low.startswith("0b"):
            return -int(s, 2) if neg else int(s, 2)
        if low.startswith("0o"):
            return -int(s, 8) if neg else int(s, 8)
        return -int(s, 10) if neg else int(s, 10)
    except ValueError:
        return None


def to_base(n, base, upper=False):
    """整数 → 指定进制字符串（负数带 - 前缀）。"""
    digits = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ" if upper \
        else "0123456789abcdefghijklmnopqrstuvwxyz"
    if n == 0:
        return "0"
    neg = n < 0
    n = abs(n)
    out = []
    while n:
        n, r = divmod(n, base)
        out.append(digits[r])
    if neg:
        out.append("-")
    return "".join(reversed(out))


def convert_all(text, src_base=None, target_base=10, upper=True):
    """任意进制文本 → {目标进制名: 字符串}；失败返回 None。"""
    n = parse_int(text, src_base)
    if n is None:
        return None
    return to_base(n, target_base, upper)


class BaseConvertPanel(QWidget):
    """进制转换面板（2-36 全进制）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setSpacing(8)

        # 输入行：数字 + 源进制
        row = QHBoxLayout()
        row.addWidget(CaptionLabel(t("数字")))
        self.ed_in = QLineEdit()
        self.ed_in.setPlaceholderText(t("如 255、0xFF、11111111、-128…"))
        self.ed_in.returnPressed.connect(self._convert)
        row.addWidget(self.ed_in, 1)
        v.addLayout(row)

        # 进制选择行：源进制（自动/2-36）+ 目标进制（2-36）
        brow = QHBoxLayout()
        brow.addWidget(CaptionLabel(t("源进制")))
        self.cb_src = ComboBox()
        self.cb_src.addItems([t("自动识别")] + [f"{b} {t('进制')}" for b in _BASES])
        self.cb_src.setCurrentIndex(0)
        self.cb_src.setFixedWidth(120)
        brow.addWidget(self.cb_src)
        brow.addWidget(CaptionLabel(t("目标进制")))
        self.cb_dst = ComboBox()
        self.cb_dst.addItems([f"{b} {t('进制')}" for b in _BASES])
        self.cb_dst.setCurrentText(f"10 {t('进制')}")
        self.cb_dst.setFixedWidth(110)
        brow.addWidget(self.cb_dst)
        brow.addWidget(CaptionLabel(t("大写")))
        self.cb_case = ComboBox()
        self.cb_case.addItems([t("大写 A-F"), t("小写 a-f")])
        self.cb_case.setCurrentIndex(0)
        self.cb_case.setFixedWidth(90)
        brow.addWidget(self.cb_case)
        brow.addStretch(1)
        v.addLayout(brow)

        row2 = QHBoxLayout()
        btn = PrimaryPushButton(t("转换"))
        btn.clicked.connect(self._convert)
        row2.addWidget(btn)
        row2.addStretch(1)
        v.addLayout(row2)

        self.ed_out = QPlainTextEdit()
        self.ed_out.setReadOnly(True)
        v.addWidget(self.ed_out, 1)
        self._apply_theme()
        from gui_qt.components import design_system as ds
        ds.bind_theme(self, self._apply_theme)
        self.ed_in.setText("255")
        self._convert()

    def _apply_theme(self):
        from gui_qt.components import design_system as ds
        t = ds.tokens()
        self.setStyleSheet(
            f"QLineEdit, QPlainTextEdit {{ background: {t['card_bg']};"
            f" color: {t['ink']}; border: 1px solid {t['border']};"
            f" border-radius: 6px; padding: 4px; font-size: 13px; }}")

    def _convert(self):
        src_text = self.cb_src.currentText()
        src_base = None if src_text.startswith(t("自动识别")) else int(src_text.split()[0])
        dst_base = int(self.cb_dst.currentText().split()[0])
        upper = self.cb_case.currentIndex() == 0
        n = parse_int(self.ed_in.text(), src_base)
        if n is None:
            self.ed_out.setPlainText(t("无法解析（支持 2-36 进制，可带 0x/0b/0o 前缀）"))
            return
        result = to_base(n, dst_base, upper)
        self.ed_out.setPlainText(
            f"十进制 DEC：{n}\n"
            f"{dst_base} 进制（{self.cb_dst.currentText()}）：{result}\n"
            f"二进制 BIN：{to_base(n, 2, upper)}\n"
            f"八进制 OCT：{to_base(n, 8, upper)}\n"
            f"十六进制 HEX：{to_base(n, 16, upper)}")


PANEL_CLASS = BaseConvertPanel


def on_load(ctx):
    pass


def on_unload():
    pass
