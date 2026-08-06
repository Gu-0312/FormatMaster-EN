"""crop_panel — 图像预设裁剪面板（阶段2 迁移自 gui/panels/crop_panel.py）。

按社交媒体尺寸批量裁剪图片。整批文件作为单个任务执行
core.image_cropper.batch_crop（PIL 实现，不依赖 FFmpeg），输出为目录。
"""
import os

from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon)

import core.image_cropper as ic
from gui_qt.i18n import tr
from gui_qt.components import toast
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

# 预置值（与 tkinter 版 crop_panel 一致）
MODE_VALUES = [tr("cover（裁剪填充）", "cover (crop fill)"), "fit（等比适应）"]
DEFAULT_PRESET = tr("1:1 正方形 (1080×1080)", "1:1 Square (1080×1080)")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


class CropPanelPage(BaseQtPanel, TaskPanelMixin):
    """图像预设裁剪页。"""

    panel_key = "video_edit"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("封面裁剪", "Crop cover")))
        lay.addWidget(CaptionLabel(tr("按社交媒体尺寸批量裁剪图片", "Batch crop images to social media sizes")))

        self.file_card = FileListCard(tr("文件列表", "Files"), file_exts=IMAGE_EXTS)
        lay.addWidget(self.file_card)

        from gui_qt.components.form_widgets import FormSection
        card = FormSection(tr("裁剪设置", "Crop settings"), FluentIcon.CUT)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(CaptionLabel(tr("预设尺寸", "Preset size")))
        self.cb_preset = ComboBox()
        self.cb_preset.addItems(list(ic.PRESETS.keys()))
        self.cb_preset.setCurrentText(DEFAULT_PRESET)
        self.cb_preset.setMinimumWidth(240)
        row1.addWidget(self.cb_preset)
        row1.addStretch(1)
        card.add_layout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(CaptionLabel(tr("裁剪模式", "Crop mode")))
        self.cb_mode = ComboBox()
        self.cb_mode.addItems(MODE_VALUES)
        self.cb_mode.setCurrentIndex(0)
        self.cb_mode.setMinimumWidth(180)
        row2.addWidget(self.cb_mode)
        row2.addStretch(1)
        card.add_layout(row2)
        lay.addWidget(card)

        out_card = FormSection(tr("输出目录", "Output folder"), FluentIcon.FOLDER)
        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        out_card.add_widget(self.out_row)
        lay.addWidget(out_card)

        self.action_bar = ActionBar(tr("开始裁剪", "Trim"))
        lay.addWidget(self.action_bar)

        self._wire_tasks()

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        mode_raw = self.cb_mode.currentText()
        return {
            "preset": self.cb_preset.currentText(),
            # 简化模式名（与 _run_task_general 的 crop 分支读取键一致）
            "crop_mode": "cover" if "cover" in mode_raw else "fit",
        }

    def collect_prefs(self) -> dict:
        return {
            "preset": self.cb_preset.currentText(),
            # mode 为原始字符串，用于恢复 ComboBox 选择
            "mode": self.cb_mode.currentText(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("preset") in ic.PRESETS:
            self.cb_preset.setCurrentText(prefs["preset"])
        if prefs.get("mode") in MODE_VALUES:
            self.cb_mode.setCurrentText(prefs["mode"])
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        p = task.params
        sz = ic.PRESETS.get(p.get("preset", ""))
        if not sz:
            task.error = tr("未知预设：{}", "Unknown preset: {}").format(p.get('preset', ''))
            return False
        files_all = p.get("files") or [task.file_path]
        cnt = ic.batch_crop(files_all, task.output_path, sz,
                            p.get("crop_mode", "cover"), prog)
        return cnt > 0

    # ── 任务提交（整批单任务，输出为目录）──────────
    def _start(self):
        files = self.file_card.files()
        if not files:
            toast.show_warning(self, tr("请先添加要裁剪的图片", "Add images to crop first"))
            return
        if self.out_row.mode() == OutputDirRow.MODE_CUSTOM and not self.out_row.path():
            toast.show_warning(self, tr("请先选择自定义输出目录", "Choose an output folder first"))
            return

        params = self.collect_params()
        out_dir = self.out_row.resolve_dir(files[0])
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError:
            toast.show_error(self, tr("无法创建输出目录：{}", "Cannot create output folder: {}").format(out_dir))
            return

        self.save_prefs()
        params["files"] = list(files)
        mgr = self.services.task_manager
        tid = mgr.add_task(
            name=tr("图像裁剪 - {}个文件", "Image Crop - {} files").format(len(files)),
            task_type="crop", file_path=files[0], output_path=out_dir,
            params=params, runner=self._runner,
            history_type=tr("图像裁剪", "Image Crop"), history_target=params["preset"],
            need_ffmpeg=False)
        if tid is not None:
            self._task_rows[tid] = (files[0], -1)
            self.action_bar.set_running(True)
            self.action_bar.set_status(tr("已提交裁剪任务", "Crop task submitted"))
        else:
            toast.show_error(self, tr("任务提交失败", "Submit failed"))

    def _empty_hint(self):
        return tr("请先添加要裁剪的图片", "Add images to crop first")
