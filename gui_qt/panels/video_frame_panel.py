# -*- coding: utf-8 -*-
"""video_frame_panel — 视频抽帧 / 缩略图墙面板（合并版）。

两种输出模式（SegmentedWidget 切换）：
- 单张序列：按固定时间间隔批量截取关键帧（extract_frames，FFmpeg fps 滤镜）
- 缩略图墙：提取多帧生成 N×M 网格图（generate_thumbnail_sheet）
"""
import os

from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import (ComboBox, FluentIcon, PushButton, SegmentedWidget)

from gui_qt.i18n import tr
from gui_qt import task_manager as tm
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".wmv", ".mov", ".flv", ".webm", ".ts",
              ".m4v", ".mpg", ".mpeg", ".3gp"}

INTERVAL_VALUES = ["0.5", "1", "2", "3", "5", "10", "30", "60"]
FORMAT_VALUES = ["PNG", "JPG"]
COLS_VALUES = ["2", "3", "4", "5", "6", "8"]
ROWS_VALUES = ["2", "3", "4", "5", "6", "8"]
WIDTH_VALUES = ["800", "1200", "1600", "2000", "2400"]


class VideoFramePanelPage(BaseQtPanel, TaskPanelMixin):
    """视频抽帧 / 缩略图墙页。"""

    panel_key = "frame_extract"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("视频抽帧 / 缩略图", "Extract frames / Thumbnails")))
        lay.addWidget(self.make_subtitle(
            tr("按间隔批量截取关键帧，或生成 N×M 缩略图墙，用于封面、预览与场景截图",
               "Extract key frames at intervals, or build an N×M thumbnail sheet")))

        self.file_card = FileListCard(tr("视频列表", "Video list"), file_exts=VIDEO_EXTS)
        lay.addWidget(self.file_card)

        # 输出模式：单张序列 / 缩略图墙
        self.sg_mode = SegmentedWidget(self)
        self.sg_mode.addItem("frames", tr("单张序列", "Frame sequence"))
        self.sg_mode.addItem("sheet", tr("缩略图墙", "Thumbnail sheet"))
        self.sg_mode.setCurrentItem("frames")
        self.sg_mode.currentItemChanged.connect(self._on_mode_changed)
        self.sg_mode.setFixedHeight(32)
        lay.addWidget(self.sg_mode)
        self._mode = "frames"

        from gui_qt.components.form_widgets import FormGrid, FormSection

        def _combo(items, default):
            cb = ComboBox()
            cb.addItems(items)
            cb.setCurrentText(default)
            return cb

        # 单张序列设置
        self.card_frames = FormSection(tr("抽帧设置", "Frame settings"), FluentIcon.CAMERA)
        grid = FormGrid(columns=2)
        self.cb_interval = grid.add_field(
            tr("间隔（秒）", "Interval (sec)"), _combo(INTERVAL_VALUES, "1"),
            hint=tr("每隔多少秒截取一帧", "Capture one frame every N seconds"))
        self.cb_fmt = grid.add_field(
            tr("输出格式", "Output format"), _combo(FORMAT_VALUES, "PNG"),
            hint=tr("JPG 体积更小，PNG 画质无损", "JPG smaller, PNG lossless"))
        self.card_frames.add_form(grid)
        lay.addWidget(self.card_frames)

        # 缩略图墙设置（默认隐藏）
        self.card_sheet = FormSection(tr("缩略图布局", "Thumbnail layout"), FluentIcon.LAYOUT)
        grid2 = FormGrid(columns=3)
        self.cb_cols = grid2.add_field(
            tr("列数", "Columns"), _combo(COLS_VALUES, "4"),
            hint=tr("缩略图网格的列数", "Thumbnail grid columns"))
        self.cb_rows = grid2.add_field(
            tr("行数", "Rows"), _combo(ROWS_VALUES, "4"),
            hint=tr("缩略图网格的行数", "Thumbnail grid rows"))
        self.cb_width = grid2.add_field(
            tr("输出宽度", "Output width"), _combo(WIDTH_VALUES, "1600"),
            hint=tr("输出图片的宽度（像素）", "Output image width (px)"))
        self.card_sheet.add_form(grid2)
        lay.addWidget(self.card_sheet)
        self.card_sheet.setVisible(False)

        # 取景器入口：预览 + 时间轴定位，一键导出单帧
        picker_row = QWidget()
        h = QHBoxLayout(picker_row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        self.btn_picker = PushButton(
            FluentIcon.CAMERA, tr("打开取景器", "Open Frame Picker"))
        self.btn_picker.setToolTip(
            tr("在独立窗口中预览视频、拖动时间轴定位，一键导出当前帧",
               "Preview video, drag the timeline, export any frame"))
        self.btn_picker.clicked.connect(self._open_picker)
        h.addWidget(self.btn_picker)
        h.addStretch(1)
        lay.addWidget(picker_row)

        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        lay.addWidget(self.out_row)

        self.action_bar = ActionBar(tr("开始生成", "Generate"))
        lay.addWidget(self.action_bar)

        # 注册 runner 工厂：持久化恢复的任务可在此面板上下文重建执行器
        self.services.task_manager.register_runner(
            "frame_extract", lambda task: self._runner)
        self._wire_tasks()

    def _on_mode_changed(self, key):
        self._mode = key
        self.card_frames.setVisible(key == "frames")
        self.card_sheet.setVisible(key == "sheet")

    # ── 取景器 ──────────────────────────────────
    def _open_picker(self):
        """打开独立取景器（手动选帧导出）。"""
        files = self.file_card.files()
        if not files:
            from gui_qt.components import toast
            toast.show_warning(self, tr("请先添加要抽帧的视频",
                                        "Add a video first"))
            return
        from gui_qt.components.frame_picker import FramePickerDialog
        dlg = FramePickerDialog(
            files[0], out_dir=self.out_row.resolve_dir(files[0]), parent=self)
        dlg.exec()

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "mode": self._mode,
            "interval": self.cb_interval.currentText(),
            "fmt": self.cb_fmt.currentText(),
            "cols": self.cb_cols.currentText(),
            "rows": self.cb_rows.currentText(),
            "width": self.cb_width.currentText(),
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
        if prefs.get("cols") in COLS_VALUES:
            self.cb_cols.setCurrentText(str(prefs["cols"]))
        if prefs.get("rows") in ROWS_VALUES:
            self.cb_rows.setCurrentText(str(prefs["rows"]))
        if prefs.get("width") in WIDTH_VALUES:
            self.cb_width.setCurrentText(str(prefs["width"]))
        if prefs.get("mode") in ("frames", "sheet"):
            self.sg_mode.setCurrentItem(prefs["mode"])
            self._on_mode_changed(prefs["mode"])
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        p = task.params
        if p.get("mode") == "sheet":
            from core.thumbnail_sheet import generate_thumbnail_sheet
            return generate_thumbnail_sheet(
                task.file_path, task.output_path,
                int(p.get("cols", 4)), int(p.get("rows", 4)),
                int(p.get("width", 1600)), prog)
        from core.video_frame_extract import extract_frames
        out_dir = os.path.dirname(task.output_path)
        ok, _n = extract_frames(
            task.file_path, out_dir,
            float(p.get("interval", 1) or 1), p.get("fmt", "PNG"), prog)
        return ok

    def _make_task(self, f):
        params = self.collect_params()
        out_dir = self.out_row.resolve_dir(f)
        if params["mode"] == "sheet":
            nm = os.path.splitext(os.path.basename(f))[0]
            # 统一走 make_output_path：应用冲突策略 + 源目同路径保护
            out_path = tm.make_output_path(f, out_dir, ".png",
                                           name=nm + "_thumbnails")
            return dict(
                name=f"{tr('视频缩略图', 'Video thumbnails')} - {os.path.basename(f)}",
                task_type="frame_extract", file_path=f,
                output_path=out_path, params=params,
                runner=self._runner, runner_key="frame_extract",
                history_type=tr("视频缩略图", "Video thumbnails"),
                history_target=f"{params['cols']}×{params['rows']}",
                need_ffmpeg=True)
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
