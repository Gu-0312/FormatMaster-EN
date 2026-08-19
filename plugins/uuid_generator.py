"""插件：UUID（v1/v3/v4/v5）与随机密码批量生成，支持移除连字符。"""

import secrets
from plugins._i18n import t
import string
import uuid

from PySide6.QtWidgets import (QHBoxLayout, QPlainTextEdit, QVBoxLayout,
                               QWidget)
from qfluentwidgets import (CaptionLabel, CheckBox, ComboBox,
                            PrimaryPushButton, SpinBox)

PLUGIN_INFO = {
    "name": "UUID 生成器",
    "description": "批量生成 UUID v1/v3/v4/v5 或随机密码（可选移除连字符）",
    "version": "2.0.0",
}

_CHARS = string.ascii_letters + string.digits
_UUID_TYPES = ("UUID v1", "UUID v3", "UUID v4", "UUID v5")


def gen_uuid(uuid_type, i):
    """按类型生成 UUID（v3/v5 用 DNS 命名空间 + 序号名保证稳定可重复）。"""
    if uuid_type == "UUID v1":
        return str(uuid.uuid1())
    if uuid_type == "UUID v3":
        return str(uuid.uuid3(uuid.NAMESPACE_DNS, str(i)))
    if uuid_type == "UUID v5":
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(i)))
    return str(uuid.uuid4())


class UuidPanel(QWidget):
    """UUID / 随机密码生成面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(CaptionLabel(t("类型")))
        self.cb_type = ComboBox()
        self.cb_type.addItems([*_UUID_TYPES, t("随机密码")])
        self.cb_type.currentIndexChanged.connect(self._type_changed)
        row.addWidget(self.cb_type)
        row.addWidget(CaptionLabel(t("数量")))
        self.sb_count = SpinBox()
        self.sb_count.setRange(1, 1000)
        self.sb_count.setValue(10)
        row.addWidget(self.sb_count)
        row.addWidget(CaptionLabel(t("长度")))
        self.sb_len = SpinBox()
        self.sb_len.setRange(6, 64)
        self.sb_len.setValue(16)
        row.addWidget(self.sb_len)
        self.chk_compact = CheckBox(t("移除连字符"))
        row.addWidget(self.chk_compact)
        btn = PrimaryPushButton(t("生成"))
        btn.clicked.connect(self._generate)
        row.addWidget(btn)
        self.btn_copy = PrimaryPushButton(t("复制结果"))
        self.btn_copy.clicked.connect(self._copy)
        row.addWidget(self.btn_copy)
        row.addStretch(1)
        v.addLayout(row)

        self.ed_out = QPlainTextEdit()
        self.ed_out.setReadOnly(True)
        v.addWidget(self.ed_out, 1)
        self._type_changed()
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

    def _type_changed(self):
        self.sb_len.setEnabled(self.cb_type.currentIndex() == 1)

    def _generate(self):
        n = self.sb_count.value()
        compact = self.chk_compact.isChecked()
        if self.cb_type.currentIndex() < len(_UUID_TYPES):
            uuid_type = _UUID_TYPES[self.cb_type.currentIndex()]
            lines = [gen_uuid(uuid_type, i) for i in range(n)]
            if compact:
                lines = [u.replace("-", "") for u in lines]
        else:
            length = self.sb_len.value()
            lines = ["".join(secrets.choice(_CHARS) for _ in range(length))
                     for _ in range(n)]
        self.ed_out.setPlainText("\n".join(lines))

    def _copy(self):
        text = self.ed_out.toPlainText()
        if text:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(text)


PANEL_CLASS = UuidPanel


def on_load(ctx):
    pass


def on_unload():
    pass
