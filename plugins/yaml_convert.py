"""插件：JSON ↔ YAML 双向转换（pyyaml，缺失时给出安装提示）。"""

import json
from plugins._i18n import t

from PySide6.QtWidgets import (QHBoxLayout, QPlainTextEdit, QVBoxLayout,
                               QWidget)
from qfluentwidgets import PrimaryPushButton

PLUGIN_INFO = {
    "name": "JSON YAML 转换",
    "description": "JSON ↔ YAML 双向转换",
    "version": "1.0.0",
}

try:
    import yaml
    _YAML_OK = True
except Exception:  # noqa: BLE001
    yaml = None
    _YAML_OK = False

_MISSING = t("缺少 pyyaml 模块（pip install pyyaml）")


class YamlPanel(QWidget):
    """JSON ↔ YAML 转换面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        self.ed_in = QPlainTextEdit()
        self.ed_in.setPlaceholderText(t("输入 JSON 或 YAML…"))
        v.addWidget(self.ed_in, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        btn_j2y = PrimaryPushButton("JSON → YAML")
        btn_j2y.clicked.connect(self._j2y)
        row.addWidget(btn_j2y)
        btn_y2j = PrimaryPushButton("YAML → JSON")
        btn_y2j.clicked.connect(self._y2j)
        row.addWidget(btn_y2j)
        btn_detect = PrimaryPushButton(t("自动识别转换"))
        btn_detect.clicked.connect(self._auto)
        row.addWidget(btn_detect)
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

    def _j2y(self):
        if not _YAML_OK:
            self.ed_out.setPlainText(_MISSING)
            return
        try:
            data = json.loads(self.ed_in.toPlainText())
            out = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
            self.ed_out.setPlainText(out)
        except json.JSONDecodeError as e:
            self.ed_out.setPlainText(t("JSON 解析失败：第 {lineno} 行 {msg}").format(lineno=e.lineno, msg=e.msg))

    def _y2j(self):
        if not _YAML_OK:
            self.ed_out.setPlainText(_MISSING)
            return
        try:
            data = yaml.safe_load(self.ed_in.toPlainText())
            out = json.dumps(data, ensure_ascii=False, indent=2)
            self.ed_out.setPlainText(out)
        except Exception as e:  # noqa: BLE001
            self.ed_out.setPlainText(t("YAML 解析失败：{e}").format(e=e))

    def _auto(self):
        text = self.ed_in.toPlainText().strip()
        if not text:
            self.ed_out.setPlainText("")
            return
        try:
            json.loads(text)
            self._j2y()
        except json.JSONDecodeError:
            self._y2j()


PANEL_CLASS = YamlPanel


def on_load(ctx):
    pass


def on_unload():
    pass
