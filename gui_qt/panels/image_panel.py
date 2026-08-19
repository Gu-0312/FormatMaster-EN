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
QUALITY_VALUES = [tr("100（无损）", "100 (lossless)"), tr("95（高质量）", "95 (high)"), tr("85（中等）", "85 (medium)"), tr("70（低质量）", "70 (low)"), tr("50（压缩）", "50 (small)")]
SIZE_VALUES = [tr("原始大小", "Original size"), "50%", "25%", "200%"]
ROTATE_VALUES = ["0°", "90°", "180°", "270°"]
CROP_VALUES = [tr("原始比例", "Original ratio"), tr("裁剪为正方形", "Crop to square")]
WATERMARK_POS_VALUES = [tr("右下角", "Bottom right"), tr("左下角", "Bottom left"), tr("右上角", "Top right"), tr("左上角", "Top left"), tr("居中", "Center")]
EFFECT_VALUES = [tr("无特效", "None"), tr("水平翻转", "Flip horizontal"),
                 tr("垂直翻转", "Flip vertical"), tr("反色", "Invert"),
                 tr("浮雕", "Emboss"), tr("边缘检测", "Edges"),
                 tr("锐化", "Sharpen")]

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff",
              ".webp", ".ico", ".tga", ".heic", ".heif"}


class ImagePanelPage(BaseQtPanel, TaskPanelMixin):
    """图片转换页。"""

    panel_key = "image"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("图片转换", "Image convert")))
        lay.addWidget(CaptionLabel(
            tr("JPG · PNG · BMP · GIF · TIFF · WEBP · ICO 格式互转", "JPG · PNG · BMP · GIF · TIFF · WEBP · ICO interconvert")))

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
        from gui_qt.components.form_widgets import (FormSection, FormGrid,
                                                    CollapsibleSection)

        sec = FormSection(tr("转换参数", "Convert settings"), FluentIcon.SETTING)

        def _combo(items, default):
            cb = ComboBox()
            cb.addItems(items)
            cb.setCurrentText(default)
            return cb

        # 主参数（直接可见）
        main_grid = FormGrid(columns=2)
        self.cb_fmt = main_grid.add_field(
            tr("目标格式", "Target format"), _combo(list(SUPPORTED_IMAGE), "PNG"),
            hint=tr("输出图片格式", "Output image format"))
        self.cb_q = main_grid.add_field(
            tr("质量", "Quality"), _combo(QUALITY_VALUES, tr("95（高质量）", "95 (high)")),
            hint=tr("压缩质量，数值越低文件越小", "Compress quality, lower = smaller file"))
        self.cb_sz = main_grid.add_field(
            tr("缩放", "Scale"), _combo(SIZE_VALUES, tr("原始大小", "Original size")))
        sec.add_form(main_grid)

        # 高级设置（渐进式披露：默认折叠）
        adv = CollapsibleSection(
            tr("高级设置", "Advanced"),
            hint=tr("旋转 / 裁剪 / 水印 / 灰度 / 隐私（通常无需调整）",
                    "Rotate / crop / watermark / grayscale / privacy (usually leave as-is)"))
        adv_grid = FormGrid(columns=2)
        self.cb_rotate = adv_grid.add_field(
            tr("旋转", "Rotate"), _combo(ROTATE_VALUES, "0°"))
        self.cb_crop = adv_grid.add_field(
            tr("裁剪", "Crop"), _combo(CROP_VALUES, tr("原始比例", "Original ratio")))
        self.cb_wm_pos = adv_grid.add_field(
            tr("水印位置", "Watermark position"), _combo(WATERMARK_POS_VALUES, tr("右下角", "Bottom right")))
        self.wm_edit = adv_grid.add_field(
            tr("水印文字", "Watermark text"), LineEdit(), colspan=1,
            hint=tr("留空则不添加水印", "blank = no watermark"))
        self.wm_edit.setPlaceholderText(tr("留空则不添加水印", "blank = no watermark"))
        adv.add_layout(adv_grid)

        self.cb_gray = CheckBox(tr("转为黑白（灰度）", "Convert to grayscale"))
        adv.add_widget(self.cb_gray)
        self.cb_strip = CheckBox(tr("清除 EXIF 隐私信息（拍摄设备/GPS）", "Strip EXIF privacy data (camera/GPS)"))
        adv.add_widget(self.cb_strip)

        # 增强与特效（2026-08-15 合并）
        adv.add_widget(CaptionLabel(tr("增强与特效", "Enhance & effects")))
        fx_grid = FormGrid(columns=2)
        from PySide6.QtWidgets import QDoubleSpinBox
        self.sp_contrast = QDoubleSpinBox()
        self.sp_contrast.setRange(0.5, 2.0); self.sp_contrast.setSingleStep(0.1); self.sp_contrast.setValue(1.0)
        self.sp_saturation = QDoubleSpinBox()
        self.sp_saturation.setRange(0.0, 3.0); self.sp_saturation.setSingleStep(0.1); self.sp_saturation.setValue(1.0)
        self.sp_sharpness = QDoubleSpinBox()
        self.sp_sharpness.setRange(0.0, 5.0); self.sp_sharpness.setSingleStep(0.1); self.sp_sharpness.setValue(1.0)
        fx_grid.add_field(tr("对比度", "Contrast"), self.sp_contrast,
                          hint=tr("1.0 为原样，>1 增强", "1.0 = original, >1 = stronger"))
        fx_grid.add_field(tr("饱和度", "Saturation"), self.sp_saturation,
                          hint=tr("1.0 为原样，0 为黑白", "1.0 = original, 0 = grayscale"))
        fx_grid.add_field(tr("锐度", "Sharpness"), self.sp_sharpness,
                          hint=tr("1.0 为原样，>1 更锐利", "1.0 = original, >1 = sharper"))
        self.cb_effect = fx_grid.add_field(
            tr("特效", "Effect"), _combo(EFFECT_VALUES, tr("无特效", "None")),
            hint=tr("翻转 / 反色 / 浮雕 / 边缘检测 / 锐化", "Flip / invert / emboss / edges / sharpen"))
        adv.add_layout(fx_grid)

        sec.add_widget(adv)
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
            "strip_exif": self.cb_strip.isChecked(),
            "contrast": self.sp_contrast.value(),
            "saturation": self.sp_saturation.value(),
            "sharpness": self.sp_sharpness.value(),
            "effect": self.cb_effect.currentText(),
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
            "strip_exif": self.cb_strip.isChecked(),
            "contrast": self.sp_contrast.value(),
            "saturation": self.sp_saturation.value(),
            "sharpness": self.sp_sharpness.value(),
            "effect": self.cb_effect.currentText(),
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
        if "strip_exif" in prefs:
            self.cb_strip.setChecked(bool(prefs["strip_exif"]))
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        p = task.params
        quality = int(p.get("quality", tr("95（高质量）", "95 (high)")).split("（")[0])
        resize_factor = {"50%": 0.5, "25%": 0.25, "200%": 2.0}.get(
            p.get("size", tr("原始大小", "Original size")), 1.0)
        rotate_val = int(p.get("rotate", "0°").replace("°", ""))
        return self.services.image_conv.convert(
            task.file_path, task.output_path, quality, None,
            p.get("watermark", ""), p.get("watermark_pos", tr("右下角", "Bottom right")),
            rotate=rotate_val, crop_mode=p.get("crop", tr("原始比例", "Original ratio")),
            grayscale=p.get("grayscale", False),
            strip_exif=p.get("strip_exif", False),
            resize_factor=resize_factor, progress_callback=prog,
            contrast=p.get("contrast", 1.0),
            saturation=p.get("saturation", 1.0),
            sharpness=p.get("sharpness", 1.0),
            effect=self._resolve_effect(p.get("effect", "")))

    @staticmethod
    def _resolve_effect(text):
        """特效中文名 → core 特效 key。"""
        mapping = {tr("水平翻转", "Flip horizontal"): "hflip",
                   tr("垂直翻转", "Flip vertical"): "vflip",
                   tr("反色", "Invert"): "invert",
                   tr("浮雕", "Emboss"): "emboss",
                   tr("边缘检测", "Edges"): "edges",
                   tr("锐化", "Sharpen"): "sharpen"}
        return mapping.get(text or "", "")

    def _make_task(self, f):
        params = self.collect_params()
        fmt_ext = SUPPORTED_IMAGE[params["fmt"]]
        out_dir = self.out_row.resolve_dir(f)
        out_path = tm.make_output_path(f, out_dir, fmt_ext)
        return dict(
            name=f"{tr('图片转换', 'Image Convert')} - {os.path.basename(f)}",
            task_type="image", file_path=f, output_path=out_path,
            params=params, runner=self._runner,
            canceller=self.services.image_conv.cancel,
            history_type=tr("图片转换", "Image Convert"), history_target=params["fmt"],
            need_ffmpeg=False)

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要转换的图片文件", "Add images to convert first")
