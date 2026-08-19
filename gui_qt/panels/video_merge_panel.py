# -*- coding: utf-8 -*-
"""video_merge_panel — 批量视频合并面板。

按列表顺序选择多个视频 → 合并为单个 MP4；列表支持上移/下移调整
顺序（FileListCard.reorder）。合并策略见 core.video_merge：
同编码/分辨率走 concat 流复制（快），否则回退重编码。
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (CaptionLabel, FluentIcon, PushButton,
                            SegmentedWidget)

from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.components import toast
from gui_qt.components.form_widgets import FormSection
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow
from utils.config import SUPPORTED_VIDEO

from core.video_merge import make_runner, merge_videos

VIDEO_EXTS = set(SUPPORTED_VIDEO.values()) - {".gif"}
AUDIO_EXTS = {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma", ".opus"}

MERGE_MODES = [
    ("video", tr("视频合并", "Merge videos")),
    ("audio", tr("音频拼接", "Join audio")),
]


class VideoMergePanelPage(BaseQtPanel):
    """视频合并页。"""

    panel_key = "video_merge"

    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("视频合并 / 音频拼接", "Merge / Join")))
        lay.addWidget(CaptionLabel(
            tr("按列表顺序合并多个视频，或拼接多个音频（支持上移/下移调整顺序）",
               "Merge videos or join audio clips in list order")))

        # 模式切换
        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_row.addWidget(CaptionLabel(tr("模式", "Mode")))
        self.sg_mode = SegmentedWidget()
        for key, label in MERGE_MODES:
            self.sg_mode.addItem(key, label)
        self.sg_mode.setCurrentItem("video")
        self.sg_mode.currentItemChanged.connect(
            lambda _k: self._mode_changed())
        mode_row.addWidget(self.sg_mode, 1)
        lay.addLayout(mode_row)

        self.file_card = FileListCard(tr("文件列表（按顺序合并）", "Files (merged in order)"),
                                      file_exts=VIDEO_EXTS | AUDIO_EXTS)
        lay.addWidget(self.file_card)
        self.file_card.set_target_fmt(tr("合并", "Merge"))

        # 顺序调整按钮行
        order_row = QHBoxLayout()
        order_row.setSpacing(8)
        self.btn_up = PushButton(FluentIcon.UP, tr("上移", "Move up"))
        self.btn_down = PushButton(FluentIcon.DOWN, tr("下移", "Move down"))
        self.btn_up.clicked.connect(lambda: self._move_selected(-1))
        self.btn_down.clicked.connect(lambda: self._move_selected(1))
        order_row.addWidget(self.btn_up)
        order_row.addWidget(self.btn_down)
        order_row.addStretch(1)
        order_row.addWidget(CaptionLabel(
            tr("列表从上到下即合并顺序", "Top to bottom is the merge order")))
        lay.addLayout(order_row)

        out_card = FormSection(tr("输出目录", "Output folder"), FluentIcon.FOLDER)
        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        out_card.add_widget(self.out_row)
        lay.addWidget(out_card)

        self.action_bar = ActionBar(tr("开始合并", "Merge"))
        lay.addWidget(self.action_bar)
        self.btn_go = self.action_bar.btn_go
        self.btn_cancel = self.action_bar.btn_cancel
        self.bar_total = self.action_bar.bar_total
        self.status_label = self.action_bar.status_label

        self.btn_go.clicked.connect(self._start)
        self.btn_cancel.clicked.connect(self._cancel_all)

        mgr = self.services.task_manager
        mgr.sig_progress.connect(self._on_progress)
        mgr.sig_state.connect(self._on_state)
        self._task_ids = set()
        # 注册可重建 runner（持久化恢复重试需要）
        mgr.register_runner("video_merge", make_runner)

    def _mode_changed(self):
        mode = self.sg_mode.currentRouteKey()
        if mode == "audio":
            self.file_card.set_target_fmt(tr("音频拼接", "Join audio"))
        else:
            self.file_card.set_target_fmt(tr("合并", "Merge"))

    # ── 顺序调整 ─────────────────────────────────
    def _move_selected(self, delta):
        """上移/下移选中的文件行。"""
        table = self.file_card.table
        row = table.currentRow()
        j = row + delta
        if row < 0 or j < 0 or j >= table.rowCount():
            return
        files = self.file_card.files()
        files[row], files[j] = files[j], files[row]
        self.file_card.reorder(files)
        table.setCurrentCell(j, 0)

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "mode": self.sg_mode.currentRouteKey(),
            "files": self.file_card.files(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return {
            "mode": self.sg_mode.currentRouteKey(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        mode = prefs.get("mode")
        if mode in dict(MERGE_MODES):
            self.sg_mode.setCurrentItem(str(mode))
            self._mode_changed()
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行 ─────────────────────────────────
    def _runner(self, task, prog):
        files = task.params.get("files") or []
        mode = task.params.get("mode", "video")
        if mode == "audio":
            from core.audio_tools import concat_audio
            return concat_audio(
                files, task.output_path, prog,
                cancel_check=lambda: task.state == tm.CANCELLED)
        return merge_videos(
            files, task.output_path, prog,
            cancel_check=lambda: task.state == tm.CANCELLED)

    def _start(self):
        files = self.file_card.files()
        mode = self.sg_mode.currentRouteKey()
        if len(files) < 2:
            toast.show_warning(self, tr("请至少添加 2 个文件", "Add at least 2 files"))
            return
        if not self.services.ffmpeg_ready():
            toast.show_error(self, tr("FFmpeg 未就绪，请稍后重试", "FFmpeg not ready"))
            return
        if self.out_row.mode() == OutputDirRow.MODE_CUSTOM and not self.out_row.path():
            toast.show_warning(self, tr("请先选择自定义输出目录", "Choose an output folder first"))
            return

        params = self.collect_params()
        self.save_prefs()
        out_dir = self.out_row.resolve_dir(files[0])
        out_ext = ".m4a" if mode == "audio" else ".mp4"
        out_name = tr("拼接结果", "joined") if mode == "audio" else tr("合并结果", "merged")
        out_path = tm.make_output_path(files[0], out_dir, out_ext,
                                       name=out_name)
        mgr = self.services.task_manager
        tid = mgr.add_task(
            name=f"{tr('合并', 'Merge')} - {len(files)} 个文件",
            task_type="video_merge", file_path=files[0], output_path=out_path,
            params=params, runner=self._runner,
            history_type=tr("合并", "Merge"),
            history_target=tr("合并", "Merge"),
            runner_key="video_merge")
        if tid is not None:
            self._task_ids.add(tid)
            self.btn_go.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self.bar_total.setValue(0)
            self.status_label.setText(
                tr("已提交合并任务（{} 个视频）", "Merge submitted ({} videos)").format(len(files)))
        else:
            toast.show_error(self, tr("任务提交失败", "Submit failed"))

    def _cancel_all(self):
        mgr = self.services.task_manager
        for tid in list(self._task_ids):
            mgr.cancel_task(tid)
        self.btn_cancel.setEnabled(False)

    # ── 进度/状态联动 ────────────────────────────
    def _on_progress(self, task_id, pct, msg, speed):
        if task_id not in self._task_ids:
            return
        task = self.services.task_manager.get_task(task_id)
        if task and task.state in (tm.SUCCESS, tm.FAILED, tm.CANCELLED):
            return
        if pct >= 0:
            self.bar_total.setValue(pct)
        self.status_label.setText(msg)

    def _on_state(self, task_id, state):
        if task_id not in self._task_ids:
            return
        task = self.services.task_manager.get_task(task_id)
        if state == tm.SUCCESS and task:
            self.status_label.setText(tr("合并完成", "Merge done"))
            toast.show_success(self, tr("合并完成：{}", "Merged: {}").format(
                os.path.basename(task.output_path)))
        elif state == tm.FAILED and task:
            self.status_label.setText(tr("合并失败", "Merge failed"))
            toast.show_error(self,
                             tr("合并失败：{}", "Merge failed: {}").format(
                                 task.error or tr("未知错误", "unknown error")))
        elif state == tm.CANCELLED:
            self.status_label.setText(tr("已取消", "Cancelled"))
        if state in (tm.SUCCESS, tm.FAILED, tm.CANCELLED):
            self._task_ids.discard(task_id)
            self.bar_total.setValue(0)
            self.btn_go.setEnabled(True)
            self.btn_cancel.setEnabled(False)
