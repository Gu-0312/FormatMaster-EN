# -*- coding: utf-8 -*-
"""video_compress_panel — 视频压缩面板。

HEVC（libx265）恒定质量重编码 + 可选分辨率缩放，把大视频压小；
复用 TaskManager 通用任务链路与 FFmpegProgressReader 进度。
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QVBoxLayout
from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon,
                            SubtitleLabel)

from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.components import toast
from gui_qt.components import design_system as ds
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow
from utils.config import SUPPORTED_VIDEO
from core.video_compress import CRF_PRESETS, RES_VALUES

VIDEO_EXTS = set(SUPPORTED_VIDEO.values()) - {".gif"}

# 下拉显示名（与 CRF_PRESETS / RES_VALUES 键一一对应）
QUALITY_VALUES = [tr("高质量（体积大）", "High (larger)"),
                  tr("平衡（推荐）", "Balanced (recommended)"),
                  tr("小体积（质量稍降）", "Small (lower quality)")]
QUALITY_KEYS = ["高质量", "平衡", "小体积"]
RES_DISPLAY = [tr("原分辨率", "Original"), "1080p", "720p", "480p"]
RES_KEYS = ["原分辨率", "1080p", "720p", "480p"]
CODEC_VALUES = [tr("HEVC H.265（推荐，更小）", "HEVC H.265 (recommended, smaller)"),
                tr("H.264（兼容性更好）", "H.264 (better compatibility)")]
CODEC_KEYS = ["libx265", "libx264"]


class VideoCompressPanelPage(BaseQtPanel):
    """视频压缩页。"""

    panel_key = "video_compress"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("视频压缩", "Video compress")))
        lay.addWidget(CaptionLabel(
            tr("HEVC 重编码压缩视频体积，适合微信/网盘传视频",
               "Re-encode with HEVC to shrink video size for sharing")))

        self.file_card = FileListCard(tr("文件列表", "Files"), file_exts=VIDEO_EXTS)
        lay.addWidget(self.file_card)
        self.file_card.set_target_fmt(tr("压缩", "Compress"))

        lay.addWidget(self._build_params_card())

        from gui_qt.components.form_widgets import FormSection
        out_card = FormSection(tr("输出目录", "Output folder"), FluentIcon.FOLDER)
        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        out_card.add_widget(self.out_row)
        lay.addWidget(out_card)

        self.action_bar = ActionBar(tr("开始压缩", "Compress"))
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
        self._task_rows = {}  # task_id -> (file_path, row)

    def _build_params_card(self):
        from gui_qt.components.form_widgets import FormSection, FormGrid

        sec = FormSection(tr("压缩参数", "Compress settings"), FluentIcon.SETTING)
        grid = FormGrid(columns=2)

        def _combo(items, default):
            cb = ComboBox()
            cb.addItems(items)
            cb.setCurrentText(default)
            return cb

        self.cb_quality = grid.add_field(
            tr("压缩等级", "Quality"), _combo(QUALITY_VALUES, QUALITY_VALUES[1]),
            hint=tr("平衡推荐；小体积压缩率最高，画质略降",
                    "Balanced recommended; small gives the highest compression"))
        self.cb_res = grid.add_field(
            tr("目标分辨率", "Resolution"), _combo(RES_DISPLAY, RES_DISPLAY[0]),
            hint=tr("1080p/720p 可进一步减小体积（不放大原视频）",
                    "Downscale to 1080p/720p for smaller files (never upscales)"))
        self.cb_codec = grid.add_field(
            tr("编码器", "Codec"), _combo(CODEC_VALUES, CODEC_VALUES[0]),
            hint=tr("HEVC 体积更小；H.264 老设备兼容性更好",
                    "HEVC is smaller; H.264 works on more devices"))
        sec.add_form(grid)
        return sec

    # ── 参数/偏好 ────────────────────────────────
    def _key(self, display_list, key_list, current):
        idx = display_list.index(current) if current in display_list else 0
        return key_list[idx]

    def collect_params(self) -> dict:
        return {
            "crf": CRF_PRESETS[self._key(QUALITY_VALUES, QUALITY_KEYS,
                                         self.cb_quality.currentText())],
            "max_height": RES_VALUES[self._key(RES_DISPLAY, RES_KEYS,
                                               self.cb_res.currentText())],
            "codec": self._key(CODEC_VALUES, CODEC_KEYS,
                               self.cb_codec.currentText()),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return {
            "quality": self.cb_quality.currentText(),
            "res": self.cb_res.currentText(),
            "codec": self.cb_codec.currentText(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("quality") in QUALITY_VALUES:
            self.cb_quality.setCurrentText(prefs["quality"])
        if prefs.get("res") in RES_DISPLAY:
            self.cb_res.setCurrentText(prefs["res"])
        if prefs.get("codec") in CODEC_VALUES:
            self.cb_codec.setCurrentText(prefs["codec"])
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        p = task.params
        return self.services.video_compressor.compress(
            task.file_path, task.output_path,
            crf=p.get("crf", 28),
            max_height=p.get("max_height"),
            codec=p.get("codec", "libx265"),
            progress_callback=prog)

    # ── 任务提交 ─────────────────────────────────
    def _start(self):
        files = self.file_card.files()
        if not files:
            toast.show_warning(self, tr("请先添加要压缩的视频文件", "Add videos to compress first"))
            return
        if not self.services.ffmpeg_ready():
            toast.show_error(self, tr("FFmpeg 未就绪，请稍后重试", "FFmpeg not ready"))
            return
        if self.out_row.mode() == OutputDirRow.MODE_CUSTOM and not self.out_row.path():
            toast.show_warning(self, tr("请先选择自定义输出目录", "Choose an output folder first"))
            return

        params = self.collect_params()
        self.save_prefs()
        mgr = self.services.task_manager
        comp = self.services.video_compressor
        added = 0
        used_out = set()  # 同批输出去重（同名视频不同源）
        for f in files:
            out_dir = self.out_row.resolve_dir(f)
            out_path = tm.make_output_path(f, out_dir, ".mp4")
            base, e = os.path.splitext(out_path)
            n = 1
            while out_path.lower() in used_out:
                out_path = f"{base}_{n}{e}"
                n += 1
            used_out.add(out_path.lower())
            tid = mgr.add_task(
                name=f"{tr('视频压缩', 'Video Compress')} - {os.path.basename(f)}",
                task_type="video_compress", file_path=f, output_path=out_path,
                params=params, runner=self._runner, canceller=comp.cancel,
                history_type=tr("视频压缩", "Video Compress"),
                history_target=self.cb_quality.currentText())
            if tid is not None:
                self._task_rows[tid] = (f, self.file_card.row_of_file(f))
                added += 1
        if added:
            self.btn_go.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self.bar_total.setValue(0)
            self.status_label.setText(tr("已提交 {} 个任务", "Submitted {} tasks").format(added))
        else:
            toast.show_error(self, tr("任务提交失败：FFmpeg 未就绪", "Submit failed: FFmpeg not ready"))

    def _cancel_all(self):
        mgr = self.services.task_manager
        for tid in list(self._task_rows):
            mgr.cancel_task(tid)
        self.btn_cancel.setEnabled(False)

    # ── 进度/状态联动 ────────────────────────────
    def _on_progress(self, task_id, pct, msg, speed):
        row = self._task_rows.get(task_id)
        if not row:
            return
        _file, idx = row
        task = self.services.task_manager.get_task(task_id)
        if task and task.state in (tm.SUCCESS, tm.FAILED, tm.CANCELLED):
            return
        self.file_card.set_row_progress(idx, pct)
        self.status_label.setText(msg)
        self._update_total()

    def _on_state(self, task_id, state):
        row = self._task_rows.get(task_id)
        if row:
            _file, idx = row
            if state in (tm.SUCCESS, tm.FAILED, tm.CANCELLED):
                self.file_card.set_row_progress(idx, -1, tm.state_text(state))
            self.file_card.set_row_state(idx, tm.state_text(state))
        task = self.services.task_manager.get_task(task_id)
        if state == tm.SUCCESS and task:
            toast.show_success(self, tr("压缩完成：{}", "Compressed: {}").format(
                os.path.basename(task.file_path)))
        elif state == tm.FAILED and task:
            toast.show_error(self,
                             tr("压缩失败：{}", "Failed: {}").format(os.path.basename(task.file_path))
                             + tr("（{}）", " ({})").format(task.error or tr("未知错误", "unknown error")))
        if state in (tm.SUCCESS, tm.FAILED, tm.CANCELLED):
            self._task_rows.pop(task_id, None)
            self._update_total()
        active = [self.services.task_manager.get_task(t) for t in self._task_rows]
        if not any(t and t.state in (tm.WAITING, tm.RUNNING, tm.PAUSED) for t in active):
            self.btn_go.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self.bar_total.setValue(0)

    def _update_total(self):
        tasks = [self.services.task_manager.get_task(t) for t in self._task_rows]
        tasks = [t for t in tasks if t]
        if not tasks:
            return
        self.bar_total.setValue(sum(t.progress for t in tasks) // len(tasks))
