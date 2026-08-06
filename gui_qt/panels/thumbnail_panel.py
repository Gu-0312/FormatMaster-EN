"""thumbnail_panel — 视频缩略图墙面板（阶段2 迁移自 gui/panels/thumbnail_panel.py）。

从视频中按时间间隔提取多帧，生成 N×M 网格缩略图（core.thumbnail_sheet，
依赖 FFmpeg + Pillow）。输出为 `<源文件名>_thumbnails.png`。
"""
import os

from qfluentwidgets import (FluentIcon, CaptionLabel, ComboBox)

from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

# 预置值（与 tkinter 版 thumbnail_panel 一致）
COLS_VALUES = ["2", "3", "4", "5", "6", "8"]
ROWS_VALUES = ["2", "3", "4", "5", "6", "8"]
WIDTH_VALUES = ["800", "1200", "1600", "2000", "2400"]

VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".wmv", ".mov", ".flv", ".webm", ".ts"}


class ThumbnailPanelPage(BaseQtPanel, TaskPanelMixin):
    """视频缩略图墙页。"""

    panel_key = "thumbnails"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title("视频缩略图"))
        lay.addWidget(CaptionLabel("从视频中提取多帧画面，生成网格缩略图墙"))

        self.file_card = FileListCard("视频列表", file_exts=VIDEO_EXTS)
        lay.addWidget(self.file_card)

        # 布局设置
        from gui_qt.components.form_widgets import FormSection, FormGrid
        card = FormSection("布局设置", FluentIcon.LAYOUT)
        grid = FormGrid(columns=3)

        def _combo(items, default):
            cb = ComboBox()
            cb.addItems(items)
            cb.setCurrentText(default)
            return cb

        self.cb_cols = grid.add_field(
            "列数", _combo(COLS_VALUES, "4"),
            hint="缩略图网格的列数")
        self.cb_rows = grid.add_field(
            "行数", _combo(ROWS_VALUES, "4"),
            hint="缩略图网格的行数")
        self.cb_width = grid.add_field(
            "输出宽度", _combo(WIDTH_VALUES, "1600"),
            hint="输出图片的宽度（像素）")
        card.add_form(grid)
        lay.addWidget(card)

        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        lay.addWidget(self.out_row)

        self.action_bar = ActionBar("开始生成")
        lay.addWidget(self.action_bar)

        self._wire_tasks()

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
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
        if prefs.get("cols") in COLS_VALUES:
            self.cb_cols.setCurrentText(str(prefs["cols"]))
        if prefs.get("rows") in ROWS_VALUES:
            self.cb_rows.setCurrentText(str(prefs["rows"]))
        if prefs.get("width") in WIDTH_VALUES:
            self.cb_width.setCurrentText(str(prefs["width"]))
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        from core.thumbnail_sheet import generate_thumbnail_sheet
        p = task.params
        return generate_thumbnail_sheet(
            task.file_path, task.output_path,
            int(p.get("cols", 4)), int(p.get("rows", 4)),
            int(p.get("width", 1600)), prog)

    def _make_task(self, f):
        params = self.collect_params()
        nm = os.path.splitext(os.path.basename(f))[0]
        out_dir = self.out_row.resolve_dir(f)
        out_path = os.path.join(out_dir, nm + "_thumbnails.png")
        return dict(
            name=f"缩略图墙 - {os.path.basename(f)}",
            task_type="thumbnail", file_path=f, output_path=out_path,
            params=params, runner=self._runner,
            history_type="视频缩略图",
            history_target=f"{params['cols']}x{params['rows']}",
            need_ffmpeg=True)

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return "请先添加要生成缩略图墙的视频"
