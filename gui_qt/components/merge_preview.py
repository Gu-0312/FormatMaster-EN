"""merge_preview — 视频合并预览器（独立窗口）。

多片段列表拖拽排序（上移/下移），选中片段在预览播放器中播放，
确认后返回排序结果，主面板按新顺序提交合并任务。
"""

import os

from PySide6.QtCore import Qt, QSize
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QListWidget,
                               QListWidgetItem, QVBoxLayout)
from qfluentwidgets import (CaptionLabel, FluentIcon, PrimaryPushButton,
                            PushButton)

from gui_qt.components import design_system as ds
from gui_qt.components.video_preview import VideoPlayerWidget
from gui_qt.i18n import tr


class MergePreviewDialog(QDialog):
    """视频合并预览器：拖拽排序 + 选中预览。

    方法：
        ordered_files()  返回排序后的文件路径列表
    """

    def __init__(self, files, parent=None):
        super().__init__(parent)
        self._files = list(files or [])
        self.setWindowTitle(tr("视频合并预览器", "Merge Preview"))
        self.resize(860, 620)
        self.setMinimumSize(720, 500)
        self._tokens = ds.tokens()
        self._apply_theme_style()
        ds.bind_theme(self, self._refresh_theme)

        main = QVBoxLayout(self)
        main.setContentsMargins(14, 14, 14, 14)
        main.setSpacing(12)

        main.addLayout(self._build_top_bar())

        self.player = VideoPlayerWidget(self)
        self.player.setMinimumHeight(220)
        main.addWidget(self.player, 1)

        main.addWidget(self._label(
            tr("合并顺序（从上到下）——拖动列表项或使用上移/下移调整，"
               "点击片段可预览", "Merge order (top→bottom) — drag rows or use arrows, click to preview")))

        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QListWidget.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.MoveAction)
        self.list_widget.setSelectionMode(QListWidget.SingleSelection)
        self.list_widget.currentRowChanged.connect(self._on_row_changed)
        main.addWidget(self.list_widget, 1)

        main.addLayout(self._build_bottom())

        self._fill_list()
        if self._files:
            self.list_widget.setCurrentRow(0)
        self._sync_play(self.player.player.playbackState())

        self.btn_up.clicked.connect(self._move_up)
        self.btn_down.clicked.connect(self._move_down)
        self.btn_play.clicked.connect(self.player.toggle_play)
        self.player.player.playbackStateChanged.connect(self._sync_play)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self.accept)
        # 子控件全部就绪后按当前主题统一刷新
        self._apply_theme_style()

    # ── UI ──────────────────────────────────────
    def _build_top_bar(self):
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_play = PushButton(FluentIcon.PLAY, tr("播放", "Play"))
        self.btn_play.setFixedSize(88, 32)
        bar.addWidget(self.btn_play)
        self.lb_status = CaptionLabel(
            tr("共 {} 个片段", "{} clips").format(len(self._files)))
        bar.addWidget(self.lb_status)
        bar.addStretch(1)
        self.lb_time = CaptionLabel("--:-- / --:--")
        bar.addWidget(self.lb_time)
        return bar

    def _build_bottom(self):
        root = QHBoxLayout()
        root.setSpacing(8)
        self.btn_up = PushButton(FluentIcon.UP, tr("上移", "Move up"))
        self.btn_down = PushButton(FluentIcon.DOWN, tr("下移", "Move down"))
        for b in (self.btn_up, self.btn_down):
            b.setFixedHeight(30)
            root.addWidget(b)
        root.addStretch(1)
        self.lb_hint = CaptionLabel("")
        root.addWidget(self.lb_hint)
        self.btn_cancel = PushButton(tr("取消", "Cancel"))
        self.btn_cancel.setFixedHeight(34)
        self.btn_ok = PrimaryPushButton(
            FluentIcon.PLAY_SOLID, tr("开始合并", "Start Merging"))
        self.btn_ok.setFixedHeight(34)
        root.addWidget(self.btn_cancel)
        root.addWidget(self.btn_ok)
        return root

    def _label(self, text):
        lb = CaptionLabel(text)
        lb.setStyleSheet(
            f"font-size: 12px; color: {self._tokens['ink_sec']};"
            " background: transparent;")
        return lb

    def _apply_theme_style(self):
        """按当前主题应用对话框与子控件样式（返回 QSS 供 bind_theme 刷新）。"""
        t = self._tokens
        qss = f"""
            QDialog {{ background: {t['page_bg']}; }}
            PushButton {{
                background: {t['card_hover']}; color: {t['ink']};
                border: 1px solid {t['border']}; border-radius: 6px;
                padding: 5px 12px; font-size: 12px;
            }}
            PushButton:hover {{ background: {t['card_active']};
                border-color: {t['accent_soft']}; }}
            PrimaryPushButton {{
                background: {t['accent']}; color: #FFFFFF; border: none;
                border-radius: 6px; padding: 5px 14px; font-size: 12px;
                font-weight: 500;
            }}
            PrimaryPushButton:hover {{ background: {t['accent_hover']}; }}
        """
        self.setStyleSheet(qss)
        # 子控件样式（构造完成后才创建，用 hasattr 保护）
        if hasattr(self, "list_widget"):
            self.list_widget.setStyleSheet(
                f"QListWidget {{ background: {t['card_bg']};"
                f" color: {t['ink']};"
                f" border: 1px solid {t['border']};"
                " border-radius: 8px; font-size: 12px;"
                " padding: 6px; outline: none; }"
                f"QListWidget::item {{ color: {t['ink']}; padding: 8px 10px;"
                " border-radius: 6px; }"
                f"QListWidget::item:hover {{ background:"
                f" {t['card_hover']}; color: {t['ink']}; }}"
                f"QListWidget::item:selected {{ background:"
                f" {t['card_active']}; color: #FFFFFF; }}")
            from PySide6.QtGui import QBrush, QColor
            for r in range(self.list_widget.count()):
                it = self.list_widget.item(r)
                if it is not None:
                    it.setForeground(QBrush(QColor(t['ink'])))
        if hasattr(self, "lb_status"):
            self.lb_status.setStyleSheet(
                f"font-size: 12px; color: {t['ink_sec']};"
                " background: transparent;")
        if hasattr(self, "lb_time"):
            self.lb_time.setStyleSheet(
                f"font-size: 13px; color: {t['ink']};"
                " font-family: Consolas; background: transparent;")
        if hasattr(self, "lb_hint"):
            self.lb_hint.setStyleSheet(
                f"font-size: 11px; color: {t['ink_dis']};"
                " background: transparent;")
        return qss

    def _refresh_theme(self):
        """主题切换时刷新颜色令牌与对话框样式。"""
        self._tokens = ds.tokens()
        return self._apply_theme_style()

    # ── 列表 ────────────────────────────────────
    def _fill_list(self):
        from PySide6.QtGui import QBrush, QColor
        self.list_widget.clear()
        for i, fp in enumerate(self._files, 1):
            item = QListWidgetItem(f"#{i}  {os.path.basename(fp)}")
            item.setData(Qt.UserRole, fp)
            item.setIcon(FluentIcon.VIDEO.icon())
            item.setForeground(QBrush(QColor(self._tokens['ink'])))  # 跟随主题文字色
            item.setSizeHint(QSize(0, 34))
            self.list_widget.addItem(item)

    def _ordered(self):
        return [self.list_widget.item(r).data(Qt.UserRole)
                for r in range(self.list_widget.count())]

    def ordered_files(self):
        return self._ordered()

    def _on_row_changed(self, row):
        files = self._ordered()
        if 0 <= row < len(files):
            self.player.set_source(files[row], autoplay=True)

    def _move_up(self):
        r = self.list_widget.currentRow()
        if r > 0:
            it = self.list_widget.takeItem(r)
            self.list_widget.insertItem(r - 1, it)
            self.list_widget.setCurrentRow(r - 1)

    def _move_down(self):
        r = self.list_widget.currentRow()
        if 0 <= r < self.list_widget.count() - 1:
            it = self.list_widget.takeItem(r)
            self.list_widget.insertItem(r + 1, it)
            self.list_widget.setCurrentRow(r + 1)

    def _sync_play(self, state):
        if state == QMediaPlayer.PlayingState:
            self.btn_play.setIcon(FluentIcon.PAUSE)
            self.btn_play.setText(tr("暂停", "Pause"))
        else:
            self.btn_play.setIcon(FluentIcon.PLAY)
            self.btn_play.setText(tr("播放", "Play"))

    def done(self, r):
        self._release_media()
        super().done(r)

    def closeEvent(self, e):
        self._release_media()
        super().closeEvent(e)

    def _release_media(self):
        try:
            self.player.shutdown()
        except RuntimeError:
            pass
