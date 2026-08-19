"""插件：JWT 解码器（解析 header/payload，纯标准库，不验证签名）。"""

import base64
from plugins._i18n import t
import datetime
import json

from PySide6.QtWidgets import (QHBoxLayout, QPlainTextEdit, QVBoxLayout,
                               QWidget)
from qfluentwidgets import PrimaryPushButton

PLUGIN_INFO = {
    "name": "JWT 解码器",
    "description": "解析 JWT 的 Header / Payload（含过期时间）",
    "version": "1.0.0",
}


def decode_jwt(token):
    """解码 JWT，返回 (文本, 错误信息)。不验证签名。"""
    token = token.strip()
    parts = token.split(".")
    if len(parts) != 3:
        return None, t("格式错误：JWT 应为三段 header.payload.signature")
    out = []
    try:
        for name, part in zip(("Header", "Payload"), parts[:2]):
            pad = "=" * (-len(part) % 4)
            data = base64.urlsafe_b64decode(part + pad)
            obj = json.loads(data)
            block = f"=== {name} ===\n" + \
                json.dumps(obj, ensure_ascii=False, indent=2)
            if name == "Payload" and isinstance(obj.get("exp"), (int, float)):
                exp = datetime.datetime.fromtimestamp(obj["exp"])
                now = datetime.datetime.now()
                left = exp - now
                state = (f"已过期 {abs(left)}" if left.total_seconds() < 0
                         else f"剩余 {left}")
                block += f"\n过期时间：{exp:%Y-%m-%d %H:%M:%S}（{state}）"
            out.append(block)
        out.append("=== Signature ===\n" + t("（需密钥验证，此处仅解码展示）"))
        return "\n\n".join(out), None
    except Exception as e:  # noqa: BLE001
        return None, t("解码失败：{e}").format(e=e)


class JwtPanel(QWidget):
    """JWT 解码面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        self.ed_in = QPlainTextEdit()
        self.ed_in.setPlaceholderText(t("粘贴 JWT token…\n格式：xxxxx.yyyyy.zzzzz"))
        v.addWidget(self.ed_in, 1)

        row = QHBoxLayout()
        btn = PrimaryPushButton(t("解码"))
        btn.clicked.connect(self._run)
        row.addWidget(btn)
        row.addStretch(1)
        v.addLayout(row)

        self.ed_out = QPlainTextEdit()
        self.ed_out.setReadOnly(True)
        v.addWidget(self.ed_out, 2)
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

    def _run(self):
        text, err = decode_jwt(self.ed_in.toPlainText())
        self.ed_out.setPlainText(err if err else text)


PANEL_CLASS = JwtPanel


def on_load(ctx):
    pass


def on_unload():
    pass
