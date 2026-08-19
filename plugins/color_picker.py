"""插件：颜色选择器（拾色器 + HEX/RGB/HSL 转换，Qt 原生 + colorsys）。"""

import colorsys
from plugins._i18n import t

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QColorDialog, QHBoxLayout, QLabel, QLineEdit,
                               QVBoxLayout, QWidget)
from qfluentwidgets import CaptionLabel, PrimaryPushButton

PLUGIN_INFO = {
    "name": "颜色选择器",
    "description": "拾色器 + HEX / RGB / HSL 互转",
    "version": "1.0.0",
}


def _to_hex(r, g, b):
    return "#%02X%02X%02X" % (r, g, b)


def _to_hsl(r, g, b):
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    return h * 360, s * 100, l * 100


def _parse_hex(text):
    """#RGB / #RRGGBB / RRGGBB → QColor 或 None。"""
    s = text.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        return None
    try:
        return QColor(int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return None


class ColorPickerPanel(QWidget):
    """颜色选择器面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        row = QHBoxLayout()
        self.btn_pick = PrimaryPushButton(t("打开拾色器"))
        self.btn_pick.clicked.connect(self._pick)
        row.addWidget(self.btn_pick)
        self.ed_hex = QLineEdit("#4F6EF7")
        self.ed_hex.setPlaceholderText(t("输入 HEX（如 #4F6EF7）"))
        self.ed_hex.returnPressed.connect(self._from_hex)
        row.addWidget(self.ed_hex, 1)
        btn_parse = PrimaryPushButton(t("解析"))
        btn_parse.clicked.connect(self._from_hex)
        row.addWidget(btn_parse)
        v.addLayout(row)

        self.preview = QLabel()
        self.preview.setFixedHeight(48)
        self.preview.setAlignment(Qt.AlignCenter)
        v.addWidget(self.preview)

        self.lb_rgb = CaptionLabel("")
        self.lb_hsl = CaptionLabel("")
        v.addWidget(self.lb_rgb)
        v.addWidget(self.lb_hsl)
        v.addStretch(1)
        self._apply_theme()
        from gui_qt.components import design_system as ds
        ds.bind_theme(self, self._apply_theme)
        self._show(QColor("#4F6EF7"))

    def _apply_theme(self):
        from gui_qt.components import design_system as ds
        t = ds.tokens()
        self.setStyleSheet(
            f"QLineEdit {{ background: {t['card_bg']}; color: {t['ink']};"
            f" border: 1px solid {t['border']}; border-radius: 6px;"
            f" padding: 4px; font-size: 13px; }}")

    def _pick(self):
        c = QColorDialog.getColor(QColor(self.ed_hex.text().lstrip("#") or
                                         "#4F6EF7"), self, t("选择颜色"))
        if c.isValid():
            self._show(c)

    def _from_hex(self):
        c = _parse_hex(self.ed_hex.text())
        if c is None:
            self.preview.setText(t("无效 HEX"))
            self.preview.setStyleSheet("background: transparent;")
            return
        self._show(c)

    def _show(self, c):
        r, g, b = c.red(), c.green(), c.blue()
        h, s, l = _to_hsl(r, g, b)
        hexv = _to_hex(r, g, b)
        self.ed_hex.setText(hexv)
        self.preview.setText(hexv)
        self.preview.setStyleSheet(
            f"background: {hexv}; border-radius: 8px; font-weight: 600;")
        self.lb_rgb.setText(f"RGB：{r}, {g}, {b}")
        self.lb_hsl.setText(f"HSL：{h:.0f}°, {s:.0f}%, {l:.0f}%")


PANEL_CLASS = ColorPickerPanel


def on_load(ctx):
    pass


def on_unload():
    pass
