
from plugins._i18n import t
"""插件：文本去重 / 排序（按行处理，支持忽略空行）。"""

from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout,
                               QPlainTextEdit, QVBoxLayout, QWidget)
from qfluentwidgets import CaptionLabel, PrimaryPushButton

PLUGIN_INFO = {
    "name": "文本去重排序",
    "description": "按行去重 / 排序 / 忽略空行",
    "version": "1.0.0",
}


class TextSortPanel(QWidget):
    """文本去重排序面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        self.ed_in = QPlainTextEdit()
        self.ed_in.setPlaceholderText(t("输入文本（每行一条）…"))
        v.addWidget(self.ed_in, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(CaptionLabel(t("操作")))
        self.cb_op = QComboBox()
        self.cb_op.addItems([t("去重（保持顺序）"), t("去重 + 排序"),
                             t("排序（升序）"), t("排序（降序）"),
                             t("按长度排序"), t("反转行顺序")])
        row.addWidget(self.cb_op)
        self.cb_ignore = QCheckBox(t("忽略空行"))
        row.addWidget(self.cb_ignore)
        btn = PrimaryPushButton(t("执行"))
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
            f"QPlainTextEdit {{ background: {t['card_bg']};"
            f" color: {t['ink']}; border: 1px solid {t['border']};"
            f" border-radius: 6px; padding: 4px; font-size: 13px; }}"
            f"QCheckBox {{ color: {t['ink']}; }}")

    def _run(self):
        text = self.ed_in.toPlainText()
        lines = text.splitlines()
        if self.cb_ignore.isChecked():
            lines = [ln for ln in lines if ln.strip()]
        op = self.cb_op.currentIndex()
        if op == 0:      # 去重保持顺序
            seen, out = set(), []
            for ln in lines:
                if ln not in seen:
                    seen.add(ln)
                    out.append(ln)
            lines = out
        elif op == 1:    # 去重 + 排序
            lines = sorted(set(lines))
        elif op == 2:    # 升序
            lines = sorted(lines)
        elif op == 3:    # 降序
            lines = sorted(lines, reverse=True)
        elif op == 4:    # 按长度
            lines = sorted(lines, key=len)
        elif op == 5:    # 反转
            lines = list(reversed(lines))
        self.ed_out.setPlainText("\n".join(lines))
        self.ed_out.setToolTip(f"{len(lines)} 行")


PANEL_CLASS = TextSortPanel


def on_load(ctx):
    pass


def on_unload():
    pass
