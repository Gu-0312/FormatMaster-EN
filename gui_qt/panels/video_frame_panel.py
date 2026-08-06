# -*- coding: utf-8 -*-
"""video_frame_panel — 视频抽帧 / 场景截图面板。

按固定时间间隔批量截取视频关键帧（core.video_frame_extract，FFmpeg fps 滤镜），
输出到所选目录，文件名 frame_00001.png 依次编号。
"""
import os

from qfluentwidgets import (ComboBox, FluentIcon)

from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".wmv", ".mov", ".flv", ".webm", ".ts",
              ".m4v", ".mpg", ".mpeg", ".3gp"}

INTERVAL_VALUES = ["0.5", "1", "2", "3", "5", "10", "30", "60"]
FORMAT_VALUES = ["PNG", "JPG"]


class VideoFramePanelPage(BaseQtPanel, TaskPanelMixin):
    """视频抽帧 / 场景截图页。"""

    panel_key = "frame_extract"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("视频抽帧", "Extract frames")))
        lay.addWidget(self.make_subtitle(
            tr("按固定时间间隔批量截取视频关键帧，用于封面、预览与场景截图",
               "Extract key frames at fixed intervals for covers, previews and scene shots")))

        self.file_card = FileListCard(tr("视频列表", "Video list"), file_exts=VIDEO_EXTS)
        lay.addWidget(self.file_card)

        from gui_qt.components.form_widgets import FormGrid, FormSection
        card = FormSection(tr("抽帧设置", "Frame settings"), FluentIcon.CAMERA)
        grid = FormGrid(columns=2)

        def _combo(items, default):
            cb = ComboBox()
            cb.addItems(items)
            cb.setCurrentText(default)
            return cb

        self.cb_interval = grid.add_field(
            tr("间隔（秒）", "Interval (sec)"), _combo(INTERVAL_VALUES, "1"),
            hint=tr("每隔多少秒截取一帧", "Capture one frame every N seconds"))
        self.cb_fmt = grid.add_field(
            tr("输出格式", "Output format"), _combo(FORMAT_VALUES, "PNG"),
            hint=tr("JPG 体积更小，PNG 画质无损", "JPG smaller, PNG lossless"))
        card.add_form(grid)
        lay.addWidget(card)

        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        lay.addWidget(self.out_row)

        self.action_bar = ActionBar(tr("开始抽帧", "Extract"))
        lay.addWidget(self.action_bar)

        # 注册 runner 工厂：持久化恢复的任务可在此面板上下文重建执行器
        self.services.task_manager.register_runner(
            "frame_extract", lambda task: self._runner)
        self._wire_tasks()

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "interval": self.cb_interval.currentText(),
            "fmt": self.cb_fmt.currentText(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return self.collect_params()

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("interval") in INTERVAL_VALUES:
            self.cb_interval.setCurrentText(str(prefs["interval"]))
        if prefs.get("fmt") in FORMAT_VALUES:
            self.cb_fmt.setCurrentText(str(prefs["fmt"]))
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        from core.video_frame_extract import extract_frames
        p = task.params
        out_dir = os.path.dirname(task.output_path)
        ok, _n = extract_frames(
            task.file_path, out_dir,
            float(p.get("interval", 1) or 1), p.get("fmt", "PNG"), prog)
        return ok

    def _make_task(self, f):
        params = self.collect_params()
        out_dir = self.out_row.resolve_dir(f)
        return dict(
            name=f"{tr('视频抽帧', 'Extract frames')} - {os.path.basename(f)}",
            task_type="frame_extract", file_path=f,
            output_path=os.path.join(out_dir, "frame_%05d.png"),
            params=params, runner=self._runner, runner_key="frame_extract",
            history_type=tr("视频抽帧", "Extract frames"),
            history_target=f"每{params['interval']}秒",
            need_ffmpeg=True)

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要抽帧的视频文件", "Add videos to extract frames first")
