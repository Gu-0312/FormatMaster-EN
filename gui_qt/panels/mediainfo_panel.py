"""mediainfo_panel — 媒体信息检测面板（MediaInfo 风格）。

添加媒体文件（视频/音频/图片），双击或点击文件即在下方表格显示
详细的容器/编码/流信息（ffprobe 后台线程读取）。
"""

import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView,
                               QTableWidget, QTableWidgetItem, QWidget)
from qfluentwidgets import CaptionLabel, FluentIcon, PushButton

from gui_qt.components import toast
from gui_qt.components.form_widgets import FormSection
from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.widgets import FileListCard

MEDIA_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v",
              ".mpg", ".mpeg", ".ts", ".3gp", ".mp3", ".wav", ".aac", ".flac",
              ".ogg", ".m4a", ".wma", ".opus", ".amr", ".png", ".jpg",
              ".jpeg", ".bmp", ".gif", ".tiff", ".webp"}


class _InfoWorker(QThread):
    """后台读取媒体信息，避免大文件 ffprobe 阻塞 UI。"""

    sig_done = Signal(str, object)  # (路径, sections 或 None)

    def __init__(self, fp, parent=None):
        super().__init__(parent)
        self._fp = fp

    def run(self):
        from core.mediainfo import get_mediainfo
        try:
            sections = get_mediainfo(self._fp)
        except Exception:  # noqa: BLE001
            sections = None
        self.sig_done.emit(self._fp, sections)


class MediaInfoPanelPage(BaseQtPanel):
    """媒体信息页。"""

    panel_key = "mediainfo"

    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("媒体信息", "Media Info")))
        lay.addWidget(CaptionLabel(
            tr("查看视频/音频/图片的容器、编码器、分辨率、码率等详细信息",
               "Inspect container, codec, resolution, bitrate etc. of media files")))

        self.file_card = FileListCard(tr("媒体文件", "Media files"),
                                      file_exts=MEDIA_EXTS)
        lay.addWidget(self.file_card)
        self.file_card.files_changed.connect(self._on_files_changed)
        self.file_card.file_double_clicked.connect(self._inspect)

        # 操作行
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_inspect = PushButton(FluentIcon.INFO, tr("查看信息", "Inspect"))
        self.btn_inspect.clicked.connect(self._inspect_first)
        bar.addWidget(self.btn_inspect)
        self.lb_status = CaptionLabel(tr("双击文件或点「查看信息」",
                                         "Double-click a file or hit Inspect"))
        self.lb_status.setStyleSheet(
            f"font-size: 12px; color: {self._ink_sec()};")
        bar.addWidget(self.lb_status)
        bar.addStretch(1)
        lay.addLayout(bar)

        # 信息表格
        card = FormSection(tr("详细信息", "Details"), FluentIcon.INFO)
        self.table = QTableWidget(0, 2, card)
        self.table.setHorizontalHeaderLabels(
            [tr("字段", "Field"), tr("值", "Value")])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setMinimumHeight(280)
        self.table.setAlternatingRowColors(True)
        card.add_widget(self.table)
        lay.addWidget(card)

        self._worker = None

    def _ink_sec(self):
        from gui_qt.components import design_system as ds
        return ds.ink_sec()

    # ── 交互 ────────────────────────────────────
    def _on_files_changed(self):
        if self.file_card.files():
            self._inspect_first()

    def _inspect_first(self):
        files = self.file_card.files()
        if files:
            self._inspect(files[0])

    def _inspect(self, fp):
        if not os.path.isfile(fp):
            return
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)
        self._clear_table()
        self.lb_status.setText(tr("正在读取信息…", "Reading info…"))
        self._worker = _InfoWorker(fp, self)
        self._worker.sig_done.connect(self._on_done)
        self._worker.start()

    def _on_done(self, fp, sections):
        if fp not in self.file_card.files():
            return  # 文件已变化，丢弃过期结果
        if not sections:
            self.lb_status.setText(tr("无法读取媒体信息", "Cannot read media info"))
            toast.show_warning(self, tr("无法读取该文件的媒体信息",
                                        "Cannot read media info"))
            return
        self._show(sections)
        self.lb_status.setText(
            tr("已加载：", "Loaded: ") + os.path.basename(fp))

    # ── 展示 ────────────────────────────────────
    def _clear_table(self):
        self.table.setRowCount(0)

    def _show(self, sections):
        self._clear_table()
        rows = 0
        for title, pairs in sections:
            self.table.insertRow(rows)
            item = QTableWidgetItem(title)
            f = item.font()
            f.setBold(True)
            item.setFont(f)
            self.table.setItem(rows, 0, item)
            self.table.setSpan(rows, 0, 1, 2)
            rows += 1
            for k, v in pairs:
                self.table.insertRow(rows)
                self.table.setItem(rows, 0, QTableWidgetItem(str(k)))
                self.table.setItem(rows, 1, QTableWidgetItem(str(v)))
                rows += 1
