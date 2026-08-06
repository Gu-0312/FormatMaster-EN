"""image_panel — 图片转换面板（阶段2 迁移自 gui/panels/image_panel.py）。

JPG · PNG · BMP · GIF · TIFF · WEBP · ICO 格式互转，支持质量/缩放/旋转/
裁剪/灰度/文字水印。任务经 TaskManager 通用链路执行 core.image_converter
（PIL 实现，不依赖 FFmpeg）。
"""
import os

from qfluentwidgets import (FluentIcon, CaptionLabel, CheckBox, ComboBox, LineEdit)

from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow
from utils.config import SUPPORTED_IMAGE

# 预置值（与 tkinter 版 image_panel 一致）
QUALITY_VALUES = ["100（无损）", "95（高质量）", "85（中等）", "70（低质量）", "50（压缩）"]
SIZE_VALUES = ["原始大小", "50%", "25%", "200%"]
ROTATE_VALUES = ["0°", "90°", "180°", "270°"]
CROP_VALUES = ["原始比例", "裁剪为正方形"]
WATERMARK_POS_VALUES = ["右下角", "左下角", "右上角", "左上角", "居中"]

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff",
              ".webp", ".ico", ".tga"}


class ImagePanelPage(BaseQtPanel, TaskPanelMixin):
    """图片转换页。"""

    panel_key = "image"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("图片转换", "Image convert")))
        lay.addWidget(CaptionLabel(
            "JPG · PNG · BMP · GIF · TIFF · WEBP · ICO 格式互转"))

        self.file_card = FileListCard(tr("文件列表", "Files"), file_exts=IMAGE_EXTS)
        lay.addWidget(self.file_card)
        self.file_card.set_target_fmt("PNG")

        lay.addWidget(self._build_params_card())

        from gui_qt.components.form_widgets import FormSection
        out_card = FormSection(tr("输出目录", "Output folder"), FluentIcon.FOLDER)
        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        out_card.add_widget(self.out_row)
        lay.addWidget(out_card)

        self.action_bar = ActionBar(tr("开始转换", "Convert"))
        lay.addWidget(self.action_bar)

        self.cb_fmt.currentTextChanged.connect(self.file_card.set_target_fmt)
        self._wire_tasks()

    def _build_params_card(self):
        from gui_qt.components.form_widgets import FormSection, FormGrid

        sec = FormSection(tr("转换参数", "Convert settings"), FluentIcon.SETTING)
        grid = FormGrid(columns=2)

        def _combo(items, default):
            cb = ComboBox()
            cb.addItems(items)
            cb.setCurrentText(default)
            return cb

        self.cb_fmt = grid.add_field(
            "目标格式", _combo(list(SUPPORTED_IMAGE), "PNG"),
            hint="输出图片格式")
        self.cb_q = grid.add_field(
            "质量", _combo(QUALITY_VALUES, "95（高质量）"),
            hint="压缩质量，数值越低文件越小")
        self.cb_sz = grid.add_field(
            "缩放", _combo(SIZE_VALUES, "原始大小"))
        self.cb_rotate = grid.add_field(
            "旋转", _combo(ROTATE_VALUES, "0°"))
        self.cb_crop = grid.add_field(
            "裁剪", _combo(CROP_VALUES, "原始比例"))
        self.cb_wm_pos = grid.add_field(
            "水印位置", _combo(WATERMARK_POS_VALUES, "右下角"))

        self.wm_edit = grid.add_field(
            "水印文字", LineEdit(), colspan=1,
            hint="留空则不添加水印")
        self.wm_edit.setPlaceholderText("留空则不添加水印")

        self.cb_gray = CheckBox("转为黑白（灰度）")
        sec.add_widget(self.cb_gray)
        sec.add_form(grid)
        return sec

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "fmt": self.cb_fmt.currentText(),
            "quality": self.cb_q.currentText(),
            "size": self.cb_sz.currentText(),
            "watermark": self.wm_edit.text().strip(),
            "watermark_pos": self.cb_wm_pos.currentText(),
            "rotate": self.cb_rotate.currentText(),
            "crop": self.cb_crop.currentText(),
            "grayscale": self.cb_gray.isChecked(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return {
            "fmt": self.cb_fmt.currentText(),
            "quality": self.cb_q.currentText(),
            "size": self.cb_sz.currentText(),
            "rotate": self.cb_rotate.currentText(),
            "crop": self.cb_crop.currentText(),
            "grayscale": self.cb_gray.isChecked(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("fmt") in SUPPORTED_IMAGE:
            self.cb_fmt.setCurrentText(prefs["fmt"])
        if prefs.get("quality") in QUALITY_VALUES:
            self.cb_q.setCurrentText(prefs["quality"])
        if prefs.get("size") in SIZE_VALUES:
            self.cb_sz.setCurrentText(prefs["size"])
        if prefs.get("rotate") in ROTATE_VALUES:
            self.cb_rotate.setCurrentText(prefs["rotate"])
        if prefs.get("crop") in CROP_VALUES:
            self.cb_crop.setCurrentText(prefs["crop"])
        if "grayscale" in prefs:
            self.cb_gray.setChecked(bool(prefs["grayscale"]))
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        p = task.params
        quality = int(p.get("quality", "95（高质量）").split("（")[0])
        resize_factor = {"50%": 0.5, "25%": 0.25, "200%": 2.0}.get(
            p.get("size", "原始大小"), 1.0)
        rotate_val = int(p.get("rotate", "0°").replace("°", ""))
        return self.services.image_conv.convert(
            task.file_path, task.output_path, quality, None,
            p.get("watermark", ""), p.get("watermark_pos", "右下角"),
            rotate=rotate_val, crop_mode=p.get("crop", "原始比例"),
            grayscale=p.get("grayscale", False),
            resize_factor=resize_factor, progress_callback=prog)

    def _make_task(self, f):
        params = self.collect_params()
        fmt_ext = SUPPORTED_IMAGE[params["fmt"]]
        out_dir = self.out_row.resolve_dir(f)
        out_path = tm.make_output_path(f, out_dir, fmt_ext)
        return dict(
            name=f"图片转换 - {os.path.basename(f)}",
            task_type="image", file_path=f, output_path=out_path,
            params=params, runner=self._runner,
            canceller=self.services.image_conv.cancel,
            history_type="图片转换", history_target=params["fmt"],
            need_ffmpeg=False)

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return "请先添加要转换的图片文件"
