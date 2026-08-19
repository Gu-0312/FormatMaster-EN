
from plugins._i18n import t
"""插件：数字转人民币大写（支持小数角分、负数）。"""

from PySide6.QtWidgets import (QHBoxLayout, QLineEdit, QPlainTextEdit,
                               QVBoxLayout, QWidget)
from qfluentwidgets import PrimaryPushButton

PLUGIN_INFO = {
    "name": "数字大写",
    "description": "金额 / 数字转人民币大写",
    "version": "1.0.0",
}

_UPPER = "零壹贰叁肆伍陆柒捌玖"
_UNITS = ["", "拾", "佰", "仟"]
_BIG = ["", "万", "亿", "万亿", "京"]


def _group_to_upper(num):
    """0-9999 → 大写（不含单位级）。"""
    if num == 0:
        return "零"
    out = []
    pending_zero = False   # 刚越过零段：若后面出现非零数字则补一个「零」
    for i in range(3, -1, -1):
        d = num // (10 ** i) % 10
        if d == 0:
            pending_zero = True
        else:
            if pending_zero and out:
                out.append("零")
            out.append(_UPPER[d] + _UNITS[i])
            pending_zero = False
    return "".join(out)


def money_upper(amount):
    """金额 → 人民币大写。amount 可为 str/int/float。"""
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return t("无效数字")
    if abs(amount) < 0.005:
        return t("零元整")
    neg = amount < 0
    amount = abs(amount)
    # 分以下四舍五入，拆元/角/分
    fen = round(amount * 100)
    yuan, fen = divmod(fen, 100)
    jiao, fen = divmod(fen, 10)

    parts = []
    if yuan > 0:
        groups = []
        while yuan > 0:
            groups.append(yuan % 10000)
            yuan //= 10000
        text = ""
        for i in range(len(groups) - 1, -1, -1):
            g = groups[i]
            if g == 0:
                continue
            seg = _group_to_upper(g) + _BIG[i]
            # 组间零衔接：上一组以零结尾且本组非零
            if text and (g < 1000 or seg.startswith("零")):
                text += "零" if not text.endswith("零") else ""
            text += seg
        text = text.rstrip("零")
        if text == "":
            text = "零"
        parts.append(text + "元")
    # 整数为 0 时省略「零元」，直接写角分
    if jiao == 0 and fen == 0:
        parts.append("整")
    else:
        if jiao:
            parts.append(_UPPER[jiao] + "角")
        else:
            if parts:
                parts.append("零")
        if fen:
            parts.append(_UPPER[fen] + "分")
    out = "".join(parts)
    return ("负" if neg else "") + out


class MoneyPanel(QWidget):
    """数字大写面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        self.ed_in = QLineEdit()
        self.ed_in.setPlaceholderText(t("输入金额，如 123456.78 或 10005"))
        self.ed_in.returnPressed.connect(self._run)
        v.addWidget(self.ed_in)

        row = QHBoxLayout()
        btn = PrimaryPushButton(t("转大写"))
        btn.clicked.connect(self._run)
        row.addWidget(btn)
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
            f"QLineEdit, QPlainTextEdit {{ background: {t['card_bg']};"
            f" color: {t['ink']}; border: 1px solid {t['border']};"
            f" border-radius: 6px; padding: 4px; font-size: 13px; }}")

    def _run(self):
        self.ed_out.setPlainText(money_upper(self.ed_in.text()))


PANEL_CLASS = MoneyPanel


def on_load(ctx):
    pass


def on_unload():
    pass
