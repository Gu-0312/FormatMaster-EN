# -*- coding: utf-8 -*-
"""html_preview — QtWebEngine HTML 预览对话框（懒加载）。

QtWebEngine 基于 Chromium，import 较重且必须在 QApplication 之后，
因此只在打开预览时加载，不拖累程序启动。
"""
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout
from PySide6.QtCore import Qt

from gui_qt.i18n import tr


class HtmlPreviewDialog(QDialog):
    """HTML 文件预览对话框（本地 file:// 加载）。"""

    def __init__(self, path="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("HTML 预览", "HTML preview"))
        self.resize(860, 640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._view = self._build_view()
        lay.addWidget(self._view, 1)
        if path:
            self.load_html(path)

    def _build_view(self):
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            return QWebEngineView(self)
        except Exception as e:  # noqa: BLE001
            lb = QLabel(tr("HTML 预览组件不可用：{}", "HTML preview unavailable: {}").format(e), self)
            lb.setAlignment(Qt.AlignCenter)
            return lb

    def load_html(self, path):
        if isinstance(self._view, QLabel):
            return
        self._view.load(QUrl.fromLocalFile(path))
