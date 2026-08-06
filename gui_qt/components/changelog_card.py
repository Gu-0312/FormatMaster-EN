"""changelog_card — 首页「更新日志」面板（替代原「公告通知」）。

从真实版本历史渲染（替代硬编码商业公告，契合开源软件定位）。
每个版本一行：版本号徽章 + 版本名 + 日期，点击展开该版本的更新明细。
底部「查看完整更新日志 ›」链接。
"""
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                               QWidget)
from qfluentwidgets import (CaptionLabel, FluentIcon, IconWidget)

from gui_qt.components import design_system as ds
from gui_qt.components.card import Card

# 真实版本历史（与 README 更新日志一致，倒序）
_CHANGELOG = [
    ("v1.3.1", "2026-08-03", [
        "架构重构：16 个功能面板 DI 化迁移至独立模块",
        "新增硬件加速支持（NVENC / QSV / AMF）",
        "新增 pytest 单元测试套件",
        "修复批量重命名大小写转换误改扩展名问题",
    ]),
    ("v1.3.0", "2026-07-23", [
        "新增视频下载功能（基于 yt-dlp）",
        "新增 PDF 加密 / 解密（AES-256/AES-128）",
        "新增 PDF 压缩、预设裁剪",
        "启动自动更新检查",
    ]),
    ("v1.1.0", "2026-07-16", [
        "新增音频音量调节、图片水印",
        "新增格式检测（批量扫描分类）",
        "修复拖拽与进度条卡顿",
    ]),
    ("v1.0.0", "2026-05-31", [
        "首次发布：视频/音频/图片/文档转换",
        "PDF 合并/拆分、图片压缩、批量重命名",
        "内置 REST API 接口",
    ]),
]


class ChangelogCard(Card):
    """更新日志面板。"""

    def __init__(self, parent=None):
        super().__init__(parent, radius=12)
        self._version_rows = []

        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 12)
        v.setSpacing(6)

        header = QHBoxLayout()
        icon = IconWidget(FluentIcon.SYNC, self)
        icon.setFixedSize(18, 18)
        header.addWidget(icon)
        title = QLabel("更新日志")
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {ds.ink()};"
            "border: none; background: transparent;")
        header.addWidget(title)
        header.addStretch(1)
        v.addLayout(header)

        for ver, date, notes in _CHANGELOG:
            row = _VersionRow(ver, date, notes, self)
            self._version_rows.append(row)
            v.addWidget(row)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self.btn_more = QPushButton("查看完整更新日志 ›", self)
        self.btn_more.setStyleSheet(
            "font-size: 12px; background: transparent; color: %s;"
            "border: none; padding: 4px 8px; font-weight: 600;" % ds.accent())
        self.btn_more.setCursor(Qt.PointingHandCursor)
        self.btn_more.clicked.connect(self._open_releases)
        footer.addWidget(self.btn_more)
        v.addLayout(footer)

    def _open_releases(self):
        """打开 GitHub Releases 页查看完整更新日志。"""
        QDesktopServices.openUrl(QUrl(
            "https://github.com/Gu-0312/FormatMaster-EN/releases"))

    def toggle_all(self, expanded):
        """展开/收起所有版本明细。"""
        for row in self._version_rows:
            if row._expanded != expanded:
                row._toggle()


class _VersionRow(QWidget):
    """单版本行：版本徽章 + 日期 + 可展开明细。"""

    def __init__(self, ver, date, notes, parent=None):
        super().__init__(parent)
        self._notes = notes
        self._expanded = False

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # 版本行（可点击展开）
        head = QWidget(self)
        head.setCursor(Qt.PointingHandCursor)
        hh = QHBoxLayout(head)
        hh.setContentsMargins(6, 5, 6, 5)
        hh.setSpacing(8)

        badge = CaptionLabel(ver, head)
        badge.setStyleSheet(
            f"background: {ds.with_alpha(ds.accent(), 26)};"
            f"color: {ds.accent()}; border-radius: 8px;"
            "padding: 1px 10px; font-size: 11px; font-weight: 700;")
        hh.addWidget(badge)

        date_lbl = CaptionLabel(date, head)
        date_lbl.setStyleSheet(
            f"font-size: 11px; color: {ds.ink_dis()};"
            "border: none; background: transparent;")
        hh.addWidget(date_lbl)
        hh.addStretch(1)

        self.arrow = IconWidget(FluentIcon.CHEVRON_RIGHT, head)
        self.arrow.setFixedSize(14, 14)
        self.arrow.setStyleSheet(f"color: {ds.ink_dis()};")
        hh.addWidget(self.arrow)
        v.addWidget(head)

        # 明细（默认隐藏）
        self.detail_box = QWidget(self)
        dv = QVBoxLayout(self.detail_box)
        dv.setContentsMargins(12, 2, 6, 6)
        dv.setSpacing(2)
        for note in notes:
            n = CaptionLabel(note, self.detail_box)
            n.setStyleSheet(
                f"font-size: 12px; color: {ds.ink_sec()};"
                "border: none; background: transparent;")
            dv.addWidget(n)
        self.detail_box.setVisible(False)
        v.addWidget(self.detail_box)

        head.mousePressEvent = lambda e: self._toggle()

    def _toggle(self):
        self._expanded = not self._expanded
        self.detail_box.setVisible(self._expanded)
        if self._expanded:
            self.arrow.setStyleSheet(
                f"color: {ds.accent()};")
        else:
            self.arrow.setStyleSheet(f"color: {ds.ink_dis()};")

    def enterEvent(self, e):
        self.arrow.setStyleSheet(f"color: {ds.accent()};")
        super().enterEvent(e)

    def leaveEvent(self, e):
        if not self._expanded:
            self.arrow.setStyleSheet(f"color: {ds.ink_dis()};")
        super().leaveEvent(e)
