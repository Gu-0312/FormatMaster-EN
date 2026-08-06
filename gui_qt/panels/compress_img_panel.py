"""compress_img_panel — 图片压缩面板（阶段2 迁移自 gui/panels/compress_img_panel.py）。

批量压缩图片体积，保持格式不变，支持限制最大分辨率。
任务经 TaskManager 通用链路执行 core.tools.image_compress（不依赖 FFmpeg）。
"""
import os

from qfluentwidgets import CaptionLabel, ComboBox, FluentIcon

from core.tools import image_compress
from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

# 预置值（与 tkinter 版 compress_img_panel 一致）
QUALITY_VALUES = ["95", "85", "75", "60", "50", "40", "30"]
SIZE_VALUES = [tr("不限制", "No limit"), "1920x1080", "1280x720", "800x600"]

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"}


class CompressImgPanelPage(BaseQtPanel, TaskPanelMixin):
    """图片压缩页。"""

    panel_key = "image_compress"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("图片压缩", "Image compress")))
        lay.addWidget(CaptionLabel(
            tr("批量压缩图片体积，保持格式不变，支持限制最大分辨率", "Batch compress images keeping format, with optional max resolution")))

        self.file_card = FileListCard(tr("文件列表", "Files"), file_exts=IMAGE_EXTS)
        lay.addWidget(self.file_card)

        from gui_qt.components.form_widgets import FormSection, FormGrid
        sec = FormSection(tr("压缩设置", "Compress settings"), FluentIcon.ZIP_FOLDER)
        grid = FormGrid(columns=2)

        self.cb_q = grid.add_field(
            tr("输出质量", "Output quality"), self._combo(QUALITY_VALUES, "75"),
            hint=tr("压缩后图片质量，数值越低体积越小", "Output quality, lower = smaller file"))
        self.cb_sz = grid.add_field(
            tr("最大分辨率", "Max resolution"), self._combo(SIZE_VALUES, tr("不限制", "No limit")),
            hint=tr("限制输出图片的最大分辨率", "Limit max output resolution"))
        sec.add_form(grid)
        lay.addWidget(sec)

        out_card = FormSection(tr("输出目录", "Output folder"), FluentIcon.FOLDER)
        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        out_card.add_widget(self.out_row)
        lay.addWidget(out_card)

        self.action_bar = ActionBar(tr("开始压缩", "Compress"))
        lay.addWidget(self.action_bar)

        self._wire_tasks()

    def _combo(self, items, default):
        cb = ComboBox()
        cb.addItems(items)
        cb.setCurrentText(default)
        return cb

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "quality": self.cb_q.currentText(),
            "size": self.cb_sz.currentText(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return {
            "quality": self.cb_q.currentText(),
            "size": self.cb_sz.currentText(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("quality") in QUALITY_VALUES:
            self.cb_q.setCurrentText(prefs["quality"])
        if prefs.get("size") in SIZE_VALUES:
            self.cb_sz.setCurrentText(prefs["size"])
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        p = task.params
        q = int(p.get("quality", "75"))
        sz_str = p.get("size", tr("不限制", "No limit"))
        max_sz = None
        if sz_str != tr("不限制", "No limit"):
            w, h = sz_str.split("x")
            max_sz = (int(w), int(h))
        return image_compress(task.file_path, task.output_path,
                              q, max_sz, prog)

    def _make_task(self, f):
        params = self.collect_params()
        nm = os.path.splitext(os.path.basename(f))[0]
        ext = os.path.splitext(f)[1]
        out_dir = self.out_row.resolve_dir(f)
        out_path = os.path.join(out_dir, nm + "_compressed" + ext)
        return dict(
            name=f"{tr('图片压缩', 'Image Compress')} - {os.path.basename(f)}",
            task_type="compress_img", file_path=f, output_path=out_path,
            params=params, runner=self._runner,
            history_type=tr("图片压缩", "Image Compress"), history_target=params["quality"],
            need_ffmpeg=False)

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要压缩的图片", "Add images to compress first")
