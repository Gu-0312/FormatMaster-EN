"""插件：SQL 格式化（关键字换行缩进，保留字符串，纯标准库）。"""

import re
from plugins._i18n import t

from PySide6.QtWidgets import (QHBoxLayout, QPlainTextEdit, QVBoxLayout,
                               QWidget)
from qfluentwidgets import PrimaryPushButton

PLUGIN_INFO = {
    "name": "SQL 格式化",
    "description": "美化 SQL：关键字换行缩进",
    "version": "1.0.0",
}

_MAJOR = re.compile(r"\b(SELECT|INSERT INTO|UPDATE|DELETE FROM|CREATE "
                    r"TABLE|ALTER TABLE|DROP TABLE)\b", re.I)
_MINOR = re.compile(r"\b(FROM|WHERE|JOIN|LEFT JOIN|RIGHT JOIN|INNER JOIN|"
                    r"GROUP BY|ORDER BY|HAVING|LIMIT|SET|VALUES|ON|UNION"
                    r"|UNION ALL|AND|OR|RETURNING)\b", re.I)
_STRING = re.compile(r"('(?:[^']|'')*'|\"(?:[^\"]|\"\")*\")")


def format_sql(sql):
    """美化 SQL：保护字符串 → 关键字前后加换行 → 缩进重排。"""
    # 1) 字符串占位保护
    strings = []

    def _save(m):
        strings.append(m.group(0))
        return f"\x00{len(strings) - 1}\x00"

    sql = _STRING.sub(_save, sql)
    # 2) 主关键字前换行
    sql = _MAJOR.sub(lambda m: "\n" + m.group(0), sql)
    # 3) 次要关键字前换行（AND/OR 单独缩进处理）
    sql = _MINOR.sub(lambda m: "\n" + m.group(0), sql)
    # 4) 压缩多余空白（保留换行，避免把关键字分行压回一行）
    sql = re.sub(r"[^\S\n]+", " ", sql)
    # 5) 还原字符串
    for i, s in enumerate(strings):
        sql = sql.replace(f"\x00{i}\x00", s)
    # 6) 按行缩进：AND/OR 两级，其余一级
    lines = [ln.strip() for ln in sql.splitlines() if ln.strip()]
    out = []
    depth = 0
    for ln in lines:
        up = ln.upper()
        if up.startswith(("AND ", "OR ")):
            indent = "    " * max(depth - 1, 0)
        else:
            indent = "    " * depth
        out.append(indent + ln)
        if up.startswith("SELECT") or up.startswith("INSERT"):
            depth = 1
        elif up.startswith(("FROM", "UPDATE", "SET", "VALUES")):
            depth = 1
        elif up.startswith("WHERE"):
            depth = 2
        elif up.startswith("ORDER BY"):
            depth = 1
    return "\n".join(out)


class SqlFormatPanel(QWidget):
    """SQL 格式化面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        self.ed_in = QPlainTextEdit()
        self.ed_in.setPlaceholderText(t("粘贴 SQL…\n如：select a,b from t where x=1 and y=2"))
        v.addWidget(self.ed_in, 1)

        row = QHBoxLayout()
        btn = PrimaryPushButton(t("格式化"))
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
            f" border-radius: 6px; padding: 4px; font-size: 13px; }}")

    def _run(self):
        sql = self.ed_in.toPlainText()
        if not sql.strip():
            self.ed_out.setPlainText("")
            return
        self.ed_out.setPlainText(format_sql(sql))


PANEL_CLASS = SqlFormatPanel


def on_load(ctx):
    pass


def on_unload():
    pass
