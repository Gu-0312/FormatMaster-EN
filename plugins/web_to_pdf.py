"""插件：网页转 PDF（Qt WebEngine 浏览器渲染，所见即所得，零第三方依赖）。

输入 URL → 浏览器引擎完整渲染整页（CSS/JS/图片）→ 可预览 → 导出 PDF。
"""

import os
from plugins._i18n import t

# 在 WebEngine 初始化前禁用其沙箱（部分受限环境/系统下必需，官方支持，无害）
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLineEdit,
                               QVBoxLayout, QWidget)
from qfluentwidgets import CaptionLabel, PrimaryPushButton

PLUGIN_INFO = {
    "name": "网页转 PDF",
    "description": "浏览器级渲染整页，导出所见即所得的 PDF",
    "version": "3.0.0",
}


class WebToPdfPanel(QWidget):
    """网页转 PDF 面板（WebEngine 整页渲染 + 实时预览）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.addWidget(CaptionLabel(t("输入网页地址，加载后整页渲染预览，一键导出 PDF：")))
        self.ed_url = QLineEdit()
        self.ed_url.setPlaceholderText(t("输入网页 URL，如 https://example.com"))
        self.ed_url.returnPressed.connect(self._load)
        v.addWidget(self.ed_url)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_load = PrimaryPushButton(t("加载网页"))
        self.btn_load.clicked.connect(self._load)
        row.addWidget(self.btn_load)
        self.btn_pdf = PrimaryPushButton(t("导出 PDF"))
        self.btn_pdf.clicked.connect(self._to_pdf)
        self.btn_pdf.setEnabled(False)
        row.addWidget(self.btn_pdf)
        self.btn_open = PrimaryPushButton(t("打开输出文件夹"))
        self.btn_open.clicked.connect(self._open_out)
        self.btn_open.setEnabled(False)
        row.addWidget(self.btn_open)
        row.addStretch(1)
        v.addLayout(row)

        # 浏览器渲染预览（所见即所得）
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            self.view = QWebEngineView()
            self._webengine_ok = True
        except ImportError:
            self.view = None
            self._webengine_ok = False
        self.lb_status = CaptionLabel(
            t("缺少 QtWebEngine 组件，无法渲染网页") if not self._webengine_ok
            else "输入地址后点「加载网页」预览，再「导出 PDF」。首次加载稍慢。")
        self.lb_status.setWordWrap(True)
        v.addWidget(self.lb_status)
        if self.view is not None:
            v.addWidget(self.view, 1)

        self._target = ""
        self._last_out = ""
        self._busy = False
        self._apply_theme()
        from gui_qt.components import design_system as ds
        ds.bind_theme(self, self._apply_theme)

    def _apply_theme(self):
        from gui_qt.components import design_system as ds
        t = ds.tokens()
        self.setStyleSheet(
            f"QLineEdit {{ background: {t['card_bg']}; color: {t['ink']};"
            f" border: 1px solid {t['border']}; border-radius: 6px;"
            f" padding: 4px; font-size: 13px; }}")

    def _norm_url(self):
        url = self.ed_url.text().strip()
        if not url:
            self.lb_status.setText(t("请先输入网页地址"))
            return None
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            self.ed_url.setText(url)
        return url

    def _load(self):
        if not self._webengine_ok or self._busy:
            return
        url = self._norm_url()
        if not url:
            return
        self._busy = True
        self.btn_load.setEnabled(False)
        self.lb_status.setText(t("正在加载网页…（首次启动稍慢）"))
        self.view.loadFinished.connect(self._on_loaded)
        self.view.load(QUrl(url))

    def _on_loaded(self, ok):
        self._busy = False
        self.btn_load.setEnabled(True)
        if ok:
            self.btn_pdf.setEnabled(True)
            self.lb_status.setText(t("网页已加载，可导出 PDF（整页渲染）"))
        else:
            self.lb_status.setText(t("网页加载失败（检查地址或网络）"))

    def _to_pdf(self):
        if not self._webengine_ok or not self.btn_pdf.isEnabled():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, t("保存 PDF"), "webpage.pdf", "PDF (*.pdf)")
        if not path:
            return
        self._target = path
        self.lb_status.setText(t("正在导出 PDF…"))
        page = self.view.page()
        # 一次性连接（避免多次点击累积）
        page.pdfPrintingFinished.connect(self._on_pdf_done)
        page.printToPdf(path)   # 浏览器打印语义：整页分页导出

    def _on_pdf_done(self, path, success):
        # 断开一次性连接
        try:
            self.view.page().pdfPrintingFinished.disconnect(self._on_pdf_done)
        except Exception:  # noqa: BLE001
            pass
        if success and os.path.isfile(path):
            self._last_out = os.path.dirname(path)
            self.btn_open.setEnabled(True)
            self.lb_status.setText(t("已生成 PDF：{path}").format(path=path))
        else:
            self.lb_status.setText(t("PDF 生成失败"))

    def _open_out(self):
        if self._last_out and os.path.isdir(self._last_out):
            try:
                os.startfile(self._last_out)   # noqa: S606
                return
            except Exception:  # noqa: BLE001
                import subprocess
                try:
                    subprocess.Popen(["explorer", self._last_out])
                    return
                except Exception:  # noqa: BLE001
                    pass
        self.lb_status.setText(t("输出目录不存在"))


PANEL_CLASS = WebToPdfPanel


def on_load(ctx):
    pass


def on_unload():
    pass
