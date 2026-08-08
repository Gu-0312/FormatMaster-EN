# -*- coding: utf-8 -*-
"""image_merge_panel — 图片拼接 / 合成 PDF 相册面板。

纵向/横向拼接多图成一张长图，或把多张图片一键合成 PDF 相册
（core.image_album，纯 PIL 实现）。
"""
import os

from qfluentwidgets import ComboBox, FluentIcon

from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

ALBUM_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp", ".heic", ".heif"}
MODE_VALUES = [
    tr("纵向拼接（长图）", "Vertical (long image)"),
    tr("横向拼接", "Horizontal"),
    tr("合成 PDF（A4）", "PDF album (A4)"),
    tr("合成 PDF（原尺寸）", "PDF album (original size)"),
]
GAP_VALUES = ["0", "10", "20", "40"]


class ImageMergePanelPage(BaseQtPanel, TaskPanelMixin):
    """图片拼接 / PDF 相册页。"""

    panel_key = "image_merge"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("图片拼接 / PDF 相册", "Image merge / PDF album")))
        lay.addWidget(self.make_subtitle(
            tr("多图拼成长图，或一键合成 PDF 相册", "Merge multiple images into one long image or a PDF album")))

        self.file_card = FileListCard(tr("图片列表", "Images"), file_exts=ALBUM_EXTS)
        lay.addWidget(self.file_card)

        from gui_qt.components.form_widgets import FormGrid, FormSection
        card = FormSection(tr("拼接设置", "Merge settings"), FluentIcon.ALBUM)
        grid = FormGrid(columns=2)

        def _combo(items, default):
            cb = ComboBox()
            cb.addItems(items)
            cb.setCurrentText(default)
            return cb

        self.cb_mode = grid.add_field(
            tr("模式", "Mode"), _combo(MODE_VALUES, MODE_VALUES[0]),
            hint=tr("拼图或合成 PDF 相册", "Merge or PDF album"))
        self.cb_gap = grid.add_field(
            tr("间距（px）", "Gap (px)"), _combo(GAP_VALUES, "10"),
            hint=tr("拼接时图片之间的空隙（仅拼图模式）", "Gap between images (merge modes only)"))
        card.add_form(grid)
        lay.addWidget(card)

        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        lay.addWidget(self.out_row)

        # 拼版预览：多行缩略图，可拖动图片换位（实时同步文件顺序）
        from gui_qt.components.visual_widgets import FrameGrid
        self.merge_grid = FrameGrid()
        self.merge_grid.set_cell_size(120, 84)
        lay.addWidget(self.merge_grid)
        self.file_card.files_changed.connect(self._refresh_grid)
        self.merge_grid.order_changed.connect(self._on_grid_reorder)

        self.action_bar = ActionBar(tr("开始处理", "Start"))
        lay.addWidget(self.action_bar)

        self.services.task_manager.register_runner(
            "image_merge", lambda task: self._runner)
        self._wire_tasks()

    def _refresh_grid(self):
        """文件变化 → 刷新拼版预览网格。"""
        self.merge_grid.set_images(self.file_card.files())

    def _on_grid_reorder(self, new_order):
        """拖拽换位 → 同步文件列表顺序（拼接按此顺序输出）。"""
        self.file_card.reorder(new_order)

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "mode": self.cb_mode.currentText(),
            "gap": self.cb_gap.currentText(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return self.collect_params()

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("mode") in MODE_VALUES:
            self.cb_mode.setCurrentText(str(prefs["mode"]))
        if prefs.get("gap") in GAP_VALUES:
            self.cb_gap.setCurrentText(str(prefs["gap"]))
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        from core.image_album import (merge_vertical, merge_horizontal, to_pdf)
        p = task.params
        all_files = p.get("all_files") or [task.file_path]
        mode = p.get("mode", MODE_VALUES[0])
        if mode in (MODE_VALUES[2], MODE_VALUES[3]):
            page_mode = "A4" if mode == MODE_VALUES[2] else "original"
            return to_pdf(all_files, task.output_path, page_mode, prog)
        gap = int(p.get("gap", 10) or 0)
        if mode == MODE_VALUES[1]:
            return merge_horizontal(all_files, task.output_path, gap, prog)
        return merge_vertical(all_files, task.output_path, gap, prog)

    def _make_task(self, f):
        """单文件入口（持久化恢复用）：退化为单文件拼接。"""
        params = self.collect_params()
        params["all_files"] = [f]
        mode = params["mode"]
        out_dir = self.out_row.resolve_dir(f)
        if mode in (MODE_VALUES[2], MODE_VALUES[3]):
            out_ext = ".pdf"
            hist_target = tr("PDF 相册", "PDF album")
        else:
            out_ext = ".jpg"
            hist_target = tr("拼图", "Merge")
        out_path = tm.make_output_path(f, out_dir, out_ext)
        return dict(
            name=f"{tr('图片拼接', 'Image merge')} - {os.path.basename(f)}",
            task_type="image_merge", file_path=f, output_path=out_path,
            params=params, runner=self._runner, runner_key="image_merge",
            history_type=tr("图片拼接", "Image merge"), history_target=hist_target,
            need_ffmpeg=False)

    def _submit_files(self):
        """多合一提交：整批文件作为一个任务（拼接/相册需要全部文件）。"""
        from gui_qt.components import toast
        files = self.file_card.files()
        if not files:
            toast.show_warning(self, self._empty_hint())
            return False
        if self.out_row.mode() == OutputDirRow.MODE_CUSTOM and not self.out_row.path():
            toast.show_warning(self, tr("请先选择自定义输出目录", "Choose an output folder first"))
            return False

        self.save_prefs()
        mgr = self.services.task_manager
        max_retries = int(self.services.get_pref("max_retries", 0) or 0)
        params = self.collect_params()
        params["all_files"] = list(files)
        mode = params["mode"]
        out_dir = self.out_row.resolve_dir(files[0])
        out_ext = ".pdf" if mode in (MODE_VALUES[2], MODE_VALUES[3]) else ".jpg"
        base = os.path.splitext(os.path.basename(files[0]))[0]
        out_name = base + out_ext if len(files) == 1 else base + "_merged" + out_ext
        out_path = os.path.join(out_dir, out_name)
        kwargs = dict(
            name=f"{tr('图片拼接', 'Image merge')} - {len(files)} 张",
            task_type="image_merge", file_path=files[0], output_path=out_path,
            params=params, runner=self._runner, runner_key="image_merge",
            history_type=tr("图片拼接", "Image merge"),
            history_target=tr("{} 张", "{} images").format(len(files)),
            need_ffmpeg=False)
        kwargs.setdefault("max_retries", max_retries)
        tid = mgr.add_task(**kwargs)
        if tid is not None:
            self._task_rows[tid] = (files[0], self.file_card.row_of_file(files[0]))
            self.action_bar.set_running(True)
            self.action_bar.set_status(
                tr("已提交任务（{} 张图片）", "Submitted ({} images)").format(len(files)))
            return True
        toast.show_error(self, tr("任务提交失败", "Submit failed"))
        return False

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要处理的图片文件", "Add images to process first")
