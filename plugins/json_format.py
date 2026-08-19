"""插件：JSON 格式化 / 压缩 / 校验 + 树形可视化视图。"""

import json
from plugins._i18n import t

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QHBoxLayout, QPlainTextEdit, QTabWidget,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)
from qfluentwidgets import PrimaryPushButton

PLUGIN_INFO = {
    "name": "JSON 格式化",
    "description": "JSON 美化 / 压缩 / 校验 / 树形视图",
    "version": "1.1.0",
}

_COL_STR = QColor("#0F9D58")
_COL_NUM = QColor("#E37400")
_COL_BOOL = QColor("#7B5ED7")
_COL_NULL = QColor("#888888")
_COL_KEY = QColor("#3B82F6")


def _fmt_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False)


def _render_json(tree, data, parent=None):
    """把 JSON 结构渲染进 QTreeWidget（键/值两列，值按类型着色）。"""
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                it = QTreeWidgetItem([f"{k}  ({len(v)})"])
                it.setForeground(0, _COL_KEY)
                (tree.addTopLevelItem(it) if parent is None
                 else parent.addChild(it))
                _render_json(tree, v, it)
            else:
                it = QTreeWidgetItem([str(k), _fmt_value(v)])
                it.setForeground(0, _COL_KEY)
                it.setForeground(1, _value_color(v))
                (tree.addTopLevelItem(it) if parent is None
                 else parent.addChild(it))
    elif isinstance(data, list):
        for i, v in enumerate(data):
            if isinstance(v, (dict, list)):
                it = QTreeWidgetItem([f"[{i}]  ({len(v)})"])
                it.setForeground(0, _COL_KEY)
                (tree.addTopLevelItem(it) if parent is None
                 else parent.addChild(it))
                _render_json(tree, v, it)
            else:
                it = QTreeWidgetItem([f"[{i}]", _fmt_value(v)])
                it.setForeground(0, _COL_KEY)
                it.setForeground(1, _value_color(v))
                (tree.addTopLevelItem(it) if parent is None
                 else parent.addChild(it))


def _value_color(v):
    if isinstance(v, bool):
        return _COL_BOOL
    if isinstance(v, (int, float)):
        return _COL_NUM
    if isinstance(v, str):
        return _COL_STR
    return _COL_NULL


class JsonFormatPanel(QWidget):
    """JSON 工具面板（文本视图 + 树形视图）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        self.ed_in = QPlainTextEdit()
        self.ed_in.setPlaceholderText(
            t('输入 JSON…\n例如：{"a": 1, "b": [1, 2]}'))
        v.addWidget(self.ed_in, 2)

        row = QHBoxLayout()
        row.setSpacing(8)
        btn_fmt = PrimaryPushButton(t("美化"))
        btn_fmt.clicked.connect(lambda: self._run(compact=False))
        row.addWidget(btn_fmt)
        btn_min = PrimaryPushButton(t("压缩"))
        btn_min.clicked.connect(lambda: self._run(compact=True))
        row.addWidget(btn_min)
        btn_chk = PrimaryPushButton(t("校验"))
        btn_chk.clicked.connect(self._validate)
        row.addWidget(btn_chk)
        btn_tree = PrimaryPushButton(t("树形视图"))
        btn_tree.clicked.connect(self._tree)
        row.addWidget(btn_tree)
        btn_copy = PrimaryPushButton(t("复制结果"))
        btn_copy.clicked.connect(self._copy)
        row.addWidget(btn_copy)
        row.addStretch(1)
        v.addLayout(row)

        # 输出区：文本视图 / 树形视图 两个标签页
        self.tabs = QTabWidget()
        self.ed_out = QPlainTextEdit()
        self.ed_out.setReadOnly(True)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels([t("键"), t("值")])
        self.tree.setRootIsDecorated(True)
        self.tabs.addTab(self.ed_out, t("文本视图"))
        self.tabs.addTab(self.tree, t("树形视图"))
        v.addWidget(self.tabs, 3)

        self._last_data = None
        self._apply_theme()
        from gui_qt.components import design_system as ds
        ds.bind_theme(self, self._apply_theme)

    def _apply_theme(self):
        from gui_qt.components import design_system as ds
        t = ds.tokens()
        self.setStyleSheet(
            f"QPlainTextEdit, QTreeWidget {{ background: {t['card_bg']};"
            f" color: {t['ink']}; border: 1px solid {t['border']};"
            f" border-radius: 6px; padding: 4px; font-size: 13px; }}"
            f"QTabWidget::pane {{ border: 1px solid {t['border']};"
            f" border-radius: 6px; }}")

    def _load(self):
        return json.loads(self.ed_in.toPlainText())

    def _run(self, compact):
        try:
            data = self._load()
            self._last_data = data
            if compact:
                out = json.dumps(data, ensure_ascii=False,
                                 separators=(",", ":"))
            else:
                out = json.dumps(data, ensure_ascii=False, indent=2)
            self.ed_out.setPlainText(out)
            self._render_tree(data)
        except json.JSONDecodeError as e:
            self.ed_out.setPlainText(
                f"JSON 错误：第 {e.lineno} 行 第 {e.colno} 列 — {e.msg}")

    def _validate(self):
        try:
            self._load()
            self.ed_out.setPlainText(t("✓ 合法 JSON"))
        except json.JSONDecodeError as e:
            self.ed_out.setPlainText(
                f"✗ 错误：第 {e.lineno} 行 第 {e.colno} 列 — {e.msg}")

    def _tree(self):
        """手动切到树视图并渲染。"""
        if self._last_data is None:
            try:
                self._last_data = self._load()
            except json.JSONDecodeError as e:
                self.ed_out.setPlainText(
                    f"✗ 错误：第 {e.lineno} 行 第 {e.colno} 列 — {e.msg}")
                return
            self._render_tree(self._last_data)
        self.tabs.setCurrentIndex(1)

    def _render_tree(self, data):
        self.tree.clear()
        _render_json(self.tree, data)
        self.tree.expandToDepth(1)

    def _copy(self):
        text = self.ed_out.toPlainText()
        if text:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(text)


PANEL_CLASS = JsonFormatPanel


def on_load(ctx):
    pass


def on_unload():
    pass
