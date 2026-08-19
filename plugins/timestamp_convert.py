"""插件：时间戳 ↔ 日期时间互转（自动识别秒/毫秒）。"""

import datetime
from plugins._i18n import t

from PySide6.QtWidgets import (QHBoxLayout, QLineEdit, QPlainTextEdit,
                               QVBoxLayout, QWidget)
from qfluentwidgets import PrimaryPushButton

PLUGIN_INFO = {
    "name": "时间戳转换",
    "description": "时间戳与日期互转，支持秒/毫秒",
    "version": "1.0.0",
}

_FMT = "%Y-%m-%d %H:%M:%S"


class TimestampPanel(QWidget):
    """时间戳转换面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        self.ed_in = QLineEdit()
        self.ed_in.setPlaceholderText(t("输入时间戳（如 1700000000）或日期（如 2023-11-15 10:00:00）"))
        v.addWidget(self.ed_in)

        row = QHBoxLayout()
        row.setSpacing(8)
        btn_ts = PrimaryPushButton(t("时间戳 → 日期"))
        btn_ts.clicked.connect(self._ts_to_str)
        row.addWidget(btn_ts)
        btn_dt = PrimaryPushButton(t("日期 → 时间戳"))
        btn_dt.clicked.connect(self._str_to_ts)
        row.addWidget(btn_dt)
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

    def _ts_to_str(self):
        raw = self.ed_in.text().strip()
        try:
            ts = float(raw)
        except ValueError:
            self.ed_out.setPlainText(t("无法解析：{raw!r} 不是数字").format(raw=raw))
            return
        # 微秒级（16 位）→ 毫秒（13 位）→ 秒；10-12 位按秒处理
        if abs(ts) > 1e14:
            ts /= 1_000_000
        elif abs(ts) > 1e11:
            ts /= 1000
        dt = datetime.datetime.fromtimestamp(ts)
        self.ed_out.setPlainText(
            f"本地时间：{dt.strftime(_FMT)}\n"
            f"UTC 时间：{dt.utcfromtimestamp(ts).strftime(_FMT)}")

    def _str_to_ts(self):
        raw = self.ed_in.text().strip()
        if not raw:
            self.ed_out.setPlainText(t("请输入日期"))
            return
        dt = None
        for fmt in (_FMT, "%Y-%m-%d %H:%M", "%Y-%m-%d",
                    "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
            try:
                dt = datetime.datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
        if dt is None:
            try:
                dt = datetime.datetime.fromisoformat(raw)
            except ValueError:
                self.ed_out.setPlainText(t("无法解析日期：{raw!r}").format(raw=raw))
                return
        ts = dt.timestamp()
        self.ed_out.setPlainText(
            f"秒级时间戳：{int(ts)}\n"
            f"毫秒级时间戳：{int(ts * 1000)}\n"
            f"微秒级时间戳：{int(ts * 1_000_000)}")


PANEL_CLASS = TimestampPanel


def on_load(ctx):
    pass


def on_unload():
    pass
