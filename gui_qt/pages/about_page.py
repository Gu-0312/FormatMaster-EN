"""about_page — 关于页（Prism 设计系统）。

卡片式布局：应用信息 + 技术栈 + 检查更新，统一使用 PageHeader 标题。
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, FluentIcon,
                            PrimaryPushButton, ScrollArea, TitleLabel)

from gui_qt.components import toast
from gui_qt.components.card import Card
from gui_qt.components.page_header import PageHeader
from gui_qt.components import design_system as ds
from gui_qt.update_checker import (RELEASES_URL, UpdateChecker,
                                   show_update_dialog, version_gt)
from utils.config import APP_VERSION, get_resource_path


class AboutPage(ScrollArea):
    """关于页。"""

    def __init__(self, window, services, parent=None):
        super().__init__(parent)
        self.setObjectName("about")
        self.window = window
        self.services = services
        self.setWidgetResizable(True)
        self.setViewportMargins(0, 0, 0, 0)

        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(24, 20, 24, 24)
        v.setSpacing(14)
        self.setWidget(content)
        content.setAutoFillBackground(False)

        # ── 页面标题 ───────────────────────────────
        v.addWidget(PageHeader(
            "关于格式大师", "版本、技术栈与更新检查", icon=FluentIcon.INFO))

        # ── 应用信息卡片 ────────────────────────────
        card, card_layout = self._make_card()
        app_box = QHBoxLayout()
        app_box.setSpacing(18)

        icon_path = get_resource_path(os.path.join("assets", "icon.ico"))
        if icon_path and os.path.isfile(icon_path):
            from qfluentwidgets import ImageLabel
            logo = ImageLabel(icon_path)
            logo.scaledToWidth(80)
            logo.setBorderRadius(16, 16, 16, 16)
            app_box.addWidget(logo, 0, Qt.AlignTop)

        app_texts = QVBoxLayout()
        app_texts.setSpacing(4)
        app_texts.addWidget(TitleLabel("格式大师 FormatMaster"))
        ver_label = BodyLabel(f"版本 {APP_VERSION}")
        ver_label.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {ds.accent()};")
        app_texts.addWidget(ver_label)
        app_texts.addWidget(BodyLabel(
            "Windows 桌面全能格式转换工具"))
        app_texts.addWidget(CaptionLabel(
            "视频 / 音频 / 图片 / 文档转换，PDF 处理，下载与 OCR 识别"))
        app_box.addLayout(app_texts, 1)
        card_layout.addLayout(app_box)
        v.addWidget(card)

        # ── 技术栈卡片 ──────────────────────────────
        card2, cl2 = self._make_card()
        sec_title = BodyLabel("技术栈")
        sec_title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {ds.ink()};")
        cl2.addWidget(sec_title)
        cl2.addSpacing(4)
        cl2.addWidget(CaptionLabel(
            "Python + PySide6 + Fluent Widgets 构建，"
            "转换内核由 FFmpeg 提供"))
        cl2.addWidget(CaptionLabel(
            "支持 NVIDIA / AMD / Intel 硬件加速编码"))
        v.addWidget(card2)

        # ── 检查更新 ─────────────────────────────────
        card3, cl3 = self._make_card()
        sec_title2 = BodyLabel("检查更新")
        sec_title2.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {ds.ink()};")
        cl3.addWidget(sec_title2)
        cl3.addSpacing(4)

        ver_row = QHBoxLayout()
        self.version_label = CaptionLabel(f"当前版本 v{APP_VERSION}", self)
        self.version_label.setStyleSheet(
            f"font-size: 12px; color: {ds.ink_sec()};")
        ver_row.addWidget(self.version_label)
        ver_row.addStretch(1)
        cl3.addLayout(ver_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_check = PrimaryPushButton(FluentIcon.SYNC, "检查更新", self)
        self.btn_check.setMinimumWidth(120)
        self.btn_check.clicked.connect(self._on_check_update)
        btn_row.addWidget(self.btn_check)
        self.btn_releases = BodyLabel("前往 GitHub Releases ›", self)
        self.btn_releases.setCursor(Qt.PointingHandCursor)
        self.btn_releases.setStyleSheet(
            f"font-size: 12px; color: {ds.accent()}; font-weight: 600;")
        self.btn_releases.mousePressEvent = lambda e: (
            QDesktopServices.openUrl(QUrl(RELEASES_URL)))
        btn_row.addWidget(self.btn_releases)
        btn_row.addStretch(1)
        cl3.addLayout(btn_row)
        v.addWidget(card3)

        v.addStretch(1)

    # ── 检查更新 ─────────────────────────────────
    def _on_check_update(self):
        """手动触发检查更新。后台线程请求，结果回来后在主线程弹提示。"""
        if getattr(self, "_checking", False):
            return
        self._checking = True
        self.btn_check.setEnabled(False)
        self.btn_check.setText("检查中…")
        toast.show_info(self, "正在检查更新，请稍候…")

        def _done(version, url):
            self._checking = False
            self.btn_check.setEnabled(True)
            self.btn_check.setText("检查更新")
            if version and version_gt(version, APP_VERSION):
                show_update_dialog(self, version, url or RELEASES_URL)
            else:
                toast.show_success(self, f"当前已是最新版本 v{APP_VERSION}")

        self._checker = UpdateChecker(self)
        self._checker.checked.connect(_done)
        self._checker.check_async()

    def _make_card(self):
        """创建 Prism 风格信息卡片。"""
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(4)
        return card, layout
