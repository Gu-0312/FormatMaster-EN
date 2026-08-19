# -*- coding: utf-8 -*-
"""echarts_view — ECharts 交互数据大屏对话框（QtWebEngine 渲染）。

本地 echarts.min.js（assets/echarts/），离线可用；setHtml + baseUrl
使模板内相对引用加载本地资源；__DATA__ 占位符注入 JSON 数据。
深/浅主题自适应由 HTML 内 JS 判断（无系统级集成，保持简单）。
"""
import json
import os

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout
from PySide6.QtCore import Qt

from gui_qt.i18n import tr

# 项目根/assets/echarts（__file__ → components → gui_qt → 根）
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ASSET_DIR = os.path.join(_ROOT, "assets", "echarts")


class EchartsStatsDialog(QDialog):
    """数据大屏对话框：set_data(days, ok, fail, types, counts) 后渲染。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("转换数据大屏", "Conversion dashboard"))
        self.resize(900, 640)
        self.setMinimumSize(720, 520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._view = self._build_view()
        lay.addWidget(self._view, 1)

    def _build_view(self):
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            self._web = QWebEngineView(self)
            return self._web
        except Exception as e:  # noqa: BLE001
            lb = QLabel(tr("数据大屏不可用：{}", "Dashboard unavailable: {}").format(e), self)
            lb.setAlignment(Qt.AlignCenter)
            return lb

    def available(self):
        return hasattr(self, "_web")

    def set_data(self, days, ok_list, fail_list, types, counts):
        """注入数据并渲染（未加载组件时静默跳过）。"""
        if not self.available():
            return False
        tpl_path = os.path.join(_ASSET_DIR, "report.html")
        try:
            with open(tpl_path, "r", encoding="utf-8") as f:
                html = f.read()
        except OSError:
            return False
        payload = {
            "days": days, "ok": ok_list, "fail": fail_list,
            "types": types, "typeCounts": counts,
        }
        html = html.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
        base = QUrl.fromLocalFile(_ASSET_DIR + os.sep)
        self._web.setHtml(html, base)
        return True
