# -*- coding: utf-8 -*-
"""pdf_preview — QtPdf 内置 PDF 预览对话框（零外调）。

PySide6-Addons 已内置 QtPdf（QPdfDocument + QPdfView），免安装。
懒加载：仅在打开预览时 import，不拖累启动。
加载失败/缺库时兜底提示，不影响宿主面板。
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout)
from qfluentwidgets import FluentIcon, ToolButton

from gui_qt.i18n import tr

# 模块级导入：_zoom/_goto 等均引用 QPdfView 枚举，必须在模块作用域可用
try:
    from PySide6.QtPdfWidgets import QPdfView
except Exception:  # noqa: BLE001 - 缺库时兜底
    QPdfView = None


class PdfPreviewDialog(QDialog):
    """PDF 预览对话框：页面导航 + 缩放 + 页码跳转。"""

    def __init__(self, path="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("PDF 预览", "PDF preview"))
        self.resize(760, 640)
        self._doc = None
        self._page = 0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)

        # 顶部工具条（毛玻璃背景 GlassBar）：上一页 / 页码输入 / 下一页 / 缩放
        from gui_qt.components.glass_bar import GlassBar
        self._toolbar = GlassBar(self)
        self._toolbar.setFixedHeight(44)
        bar = QHBoxLayout(self._toolbar)
        bar.setContentsMargins(12, 4, 12, 4)
        bar.setSpacing(8)
        self.btn_prev = QPushButton(tr("‹ 上一页", "‹ Prev"))
        self.btn_prev.clicked.connect(lambda: self._goto(self._page - 1))
        bar.addWidget(self.btn_prev)

        self.ed_page = QLineEdit("1")
        self.ed_page.setFixedWidth(56)
        self.ed_page.setAlignment(Qt.AlignCenter)
        self.ed_page.returnPressed.connect(self._jump_to_page)
        bar.addWidget(self.ed_page)
        self.lb_total = QLabel("")
        bar.addWidget(self.lb_total)
        bar.addSpacing(8)

        self.btn_next = QPushButton(tr("下一页 ›", "Next ›"))
        self.btn_next.clicked.connect(lambda: self._goto(self._page + 1))
        bar.addWidget(self.btn_next)
        bar.addStretch(1)

        # 缩放按钮：用 FluentIcon 图标（文本「−/+」在部分字体下渲染空白）
        self.btn_zoom_out = ToolButton(FluentIcon.ZOOM_OUT, self)
        self.btn_zoom_out.setToolTip(tr("缩小", "Zoom out"))
        self.btn_zoom_out.setFixedSize(32, 32)
        self.btn_zoom_out.clicked.connect(lambda: self._zoom(0.8))
        bar.addWidget(self.btn_zoom_out)
        self.btn_zoom_in = ToolButton(FluentIcon.ZOOM_IN, self)
        self.btn_zoom_in.setToolTip(tr("放大", "Zoom in"))
        self.btn_zoom_in.setFixedSize(32, 32)
        self.btn_zoom_in.clicked.connect(lambda: self._zoom(1.25))
        bar.addWidget(self.btn_zoom_in)
        lay.addWidget(self._toolbar)

        self._view = None
        self._build_view()
        lay.addWidget(self._view, 1)

        # 加载失败提示标签（_build_view 里设置）
        if path:
            self.open_pdf(path)

    def _build_view(self):
        """构建 QPdfView；缺库时显示提示。"""
        try:
            from PySide6.QtPdf import QPdfDocument
            self._view = QPdfView(self)
            self._doc = QPdfDocument(self)
            self._view.setDocument(self._doc)
            self._view.setPageMode(QPdfView.PageMode.MultiPage)
            self._view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        except Exception as e:  # noqa: BLE001
            self._view = QLabel(
                tr("PDF 预览组件不可用：{}", "PDF preview unavailable: {}").format(e), self)
            self._view.setAlignment(Qt.AlignCenter)
            self._doc = None

    # ── 公共接口 ────────────────────────────────
    def open_pdf(self, path):
        if self._doc is None:
            return False
        status = self._doc.load(path)
        ok = status == self._doc.Error.None_
        if ok:
            self._page = 0
            self._goto(0)
        return ok

    def page_count(self):
        return self._doc.pageCount() if self._doc is not None else 0

    # ── 内部 ─────────────────────────────────────
    def _goto(self, page):
        if self._doc is None:
            return
        n = self._doc.pageCount()
        page = max(0, min(n - 1, page))
        self._page = page
        # QPdfView 无 setCurrentPage：走 pageNavigator().jump() 翻页
        nav = self._view.pageNavigator()
        nav.jump(page, nav.currentLocation(), nav.currentZoom())
        self.ed_page.setText(str(page + 1))
        self.lb_total.setText(tr("/ {}", "/ {}").format(n))
        self.btn_prev.setEnabled(page > 0)
        self.btn_next.setEnabled(page < n - 1)

    def _jump_to_page(self):
        try:
            p = int(self.ed_page.text()) - 1
        except ValueError:
            return
        self._goto(p)

    def _zoom(self, factor):
        if self._view is None or QPdfView is None or isinstance(self._view, QLabel):
            return
        mode = self._view.zoomMode()
        if mode == QPdfView.ZoomMode.FitToWidth:
            # 退出适配模式，转为按当前宽度缩放
            self._view.setZoomMode(QPdfView.ZoomMode.Custom)
        self._view.setZoomFactor(self._view.zoomFactor() * factor)
