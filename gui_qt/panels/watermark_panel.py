"""watermark_panel — 图片水印面板（阶段2 迁移自 gui/panels/watermark_panel.py）。

批量给图片添加文字或图片水印，支持透明度、旋转、位置。
任务经 TaskManager 通用链路执行 core.watermark_tool.process_watermark
（PIL 实现，不依赖 FFmpeg）。
"""
import os

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (FluentIcon, CaptionLabel, ComboBox, LineEdit,
                            PushButton, RadioButton)

from core.watermark_tool import process_watermark
from gui_qt.i18n import tr
from gui_qt.components import toast
from gui_qt.components.form_widgets import FormSection
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

# 预置值（与 tkinter 版 watermark_panel 一致）
FONT_SIZES = ["16", "24", "32", "48", "64", "96", "128"]
COLORS = ["#FFFFFF", "#000000", "#FF0000", "#00FF00", "#0000FF",
          "#FFFF00", "#FF00FF", "#00FFFF", "#CCCCCC", "#666666",
          "#FF6600", "#990099"]
OPACITIES = ["0.1", "0.2", "0.3", "0.5", "0.7", "0.8", "0.9", "1.0"]
ROTATIONS = ["0", "15", "30", "45", "60", "90", "180", "270", "315"]
POSITIONS = [tr("左上角", "Top left"), tr("右上角", "Top right"), tr("左下角", "Bottom left"), tr("右下角", "Bottom right"), tr("居中", "Center")]
SCALES = ["0.05", "0.1", "0.15", "0.2", "0.3", "0.5", "0.8", "1.0"]

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"}


class WatermarkPanelPage(BaseQtPanel, TaskPanelMixin):
    """图片水印页。"""

    panel_key = "watermark"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("图片水印", "Image watermark")))
        lay.addWidget(CaptionLabel(
            tr("批量给图片添加文字或图片水印，支持透明度、旋转、位置", "Add text or image watermarks in batch, with opacity/rotation/position")))

        self.file_card = FileListCard(tr("文件列表", "Files"), file_exts=IMAGE_EXTS)
        lay.addWidget(self.file_card)

        lay.addWidget(self._build_settings_card())

        # 输出目录
        out_card = FormSection(tr("输出目录", "Output folder"), FluentIcon.FOLDER)
        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        out_card.add_widget(self.out_row)
        lay.addWidget(out_card)

        self.action_bar = ActionBar(tr("开始加水印", "Add watermark"))
        lay.addWidget(self.action_bar)

        self.rb_text.setChecked(True)
        self._mode_changed()
        self._wire_tasks()

    def _build_settings_card(self):
        sec = FormSection(tr("水印设置", "Watermark settings"), FluentIcon.PENCIL_INK)

        # 水印类型切换
        type_row = QHBoxLayout()
        type_row.setSpacing(16)
        type_row.addWidget(CaptionLabel(tr("水印类型", "Watermark type")))
        self.rb_text = RadioButton(tr("文字水印", "Text watermark"))
        self.rb_image = RadioButton(tr("图片水印", "Image Watermark"))
        self.rb_text.clicked.connect(self._mode_changed)
        self.rb_image.clicked.connect(self._mode_changed)
        type_row.addWidget(self.rb_text)
        type_row.addWidget(self.rb_image)
        type_row.addStretch(1)
        sec.add_layout(type_row)

        self.sec_text = self._build_text_section()
        self.sec_image = self._build_image_section()
        sec.add_widget(self.sec_text)
        sec.add_widget(self.sec_image)
        return sec

    def _row_widget(self, builder):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        builder(h)
        h.addStretch(1)
        return w

    def _build_text_section(self):
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(8)

        vl.addWidget(CaptionLabel(tr("水印文字", "Watermark text")))
        self.ed_text = LineEdit()
        self.ed_text.setText(tr("水印", "Watermark"))
        vl.addWidget(self.ed_text)

        def build(h):
            h.addWidget(CaptionLabel(tr("字号", "Font size")))
            self.cb_font_size = ComboBox()
            self.cb_font_size.addItems(FONT_SIZES)
            self.cb_font_size.setCurrentText("48")
            h.addWidget(self.cb_font_size)
            h.addWidget(CaptionLabel(tr("颜色", "Color")))
            self.cb_color = ComboBox()
            self.cb_color.addItems(COLORS)
            self.cb_color.setCurrentText("#FFFFFF")
            h.addWidget(self.cb_color)
            h.addWidget(CaptionLabel(tr("透明度", "Opacity")))
            self.cb_opacity = ComboBox()
            self.cb_opacity.addItems(OPACITIES)
            self.cb_opacity.setCurrentText("0.8")
            h.addWidget(self.cb_opacity)
            h.addWidget(CaptionLabel(tr("旋转角度", "Rotation")))
            self.cb_rotation = ComboBox()
            self.cb_rotation.addItems(ROTATIONS)
            self.cb_rotation.setCurrentText("0")
            h.addWidget(self.cb_rotation)
            h.addWidget(CaptionLabel(tr("位置", "Position")))
            self.cb_position = ComboBox()
            self.cb_position.addItems(POSITIONS)
            self.cb_position.setCurrentText(tr("右下角", "Bottom right"))
            h.addWidget(self.cb_position)
        vl.addWidget(self._row_widget(build))
        return w

    def _build_image_section(self):
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(8)

        pick_row = QHBoxLayout()
        pick_row.setSpacing(8)
        pick_row.addWidget(CaptionLabel(tr("水印图片", "Watermark image")))
        self.ed_wm_path = LineEdit()
        self.ed_wm_path.setPlaceholderText(tr("未选择", "Not selected"))
        self.ed_wm_path.setReadOnly(True)
        pick_row.addWidget(self.ed_wm_path, 1)
        btn_pick = PushButton(tr("选择", "Pick"))
        btn_pick.clicked.connect(self._pick_wm_image)
        pick_row.addWidget(btn_pick)
        vl.addLayout(pick_row)

        def build(h):
            h.addWidget(CaptionLabel(tr("缩放比例", "Scale")))
            self.cb_scale = ComboBox()
            self.cb_scale.addItems(SCALES)
            self.cb_scale.setCurrentText("0.2")
            h.addWidget(self.cb_scale)
            h.addWidget(CaptionLabel(tr("透明度", "Opacity")))
            self.cb_opacity_img = ComboBox()
            self.cb_opacity_img.addItems(OPACITIES)
            self.cb_opacity_img.setCurrentText("0.8")
            h.addWidget(self.cb_opacity_img)
            h.addWidget(CaptionLabel(tr("旋转角度", "Rotation")))
            self.cb_rotation_img = ComboBox()
            self.cb_rotation_img.addItems(ROTATIONS)
            self.cb_rotation_img.setCurrentText("0")
            h.addWidget(self.cb_rotation_img)
            h.addWidget(CaptionLabel(tr("位置", "Position")))
            self.cb_position_img = ComboBox()
            self.cb_position_img.addItems(POSITIONS)
            self.cb_position_img.setCurrentText(tr("右下角", "Bottom right"))
            h.addWidget(self.cb_position_img)
        vl.addWidget(self._row_widget(build))
        return w

    def _mode_changed(self):
        is_text = self.rb_text.isChecked()
        self.sec_text.setVisible(is_text)
        self.sec_image.setVisible(not is_text)

    def _pick_wm_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("选择水印图片", "Pick watermark image"), "",
            tr("PNG图片 (*.png);;所有图片 (*.png *.jpg *.bmp);;所有文件 (*)", "PNG images (*.png);;All images (*.png *.jpg *.bmp);;All files (*)"))
        if path:
            self.ed_wm_path.setText(path)

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        is_text = self.rb_text.isChecked()
        return {
            "wm_type": "text" if is_text else "image",
            "text": self.ed_text.text(),
            "font_size": int(self.cb_font_size.currentText()),
            "color": self.cb_color.currentText(),
            "opacity": float(self.cb_opacity.currentText() if is_text
                             else self.cb_opacity_img.currentText()),
            "rotation": int(self.cb_rotation.currentText() if is_text
                            else self.cb_rotation_img.currentText()),
            "position": self.cb_position.currentText() if is_text
            else self.cb_position_img.currentText(),
            "wm_image_path": self.ed_wm_path.text().strip(),
            "scale": float(self.cb_scale.currentText()),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return {
            "wm_type": "text" if self.rb_text.isChecked() else "image",
            "text": self.ed_text.text(),
            "font_size": self.cb_font_size.currentText(),
            "color": self.cb_color.currentText(),
            "opacity": self.cb_opacity.currentText(),
            "rotation": self.cb_rotation.currentText(),
            "position": self.cb_position.currentText(),
            "scale": self.cb_scale.currentText(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("wm_type") == "image":
            self.rb_image.setChecked(True)
        elif prefs.get("wm_type") == "text":
            self.rb_text.setChecked(True)
        self._mode_changed()
        if prefs.get("text"):
            self.ed_text.setText(prefs["text"])
        if prefs.get("font_size") in FONT_SIZES:
            self.cb_font_size.setCurrentText(prefs["font_size"])
        if prefs.get("color") in COLORS:
            self.cb_color.setCurrentText(prefs["color"])
        if prefs.get("opacity") in OPACITIES:
            self.cb_opacity.setCurrentText(prefs["opacity"])
        if prefs.get("rotation") in ROTATIONS:
            self.cb_rotation.setCurrentText(prefs["rotation"])
        if prefs.get("position") in POSITIONS:
            self.cb_position.setCurrentText(prefs["position"])
        if prefs.get("scale") in SCALES:
            self.cb_scale.setCurrentText(prefs["scale"])
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        p = task.params
        return process_watermark(
            task.file_path, task.output_path,
            wm_type=p.get("wm_type", "text"),
            text=p.get("text", ""),
            font_size=p.get("font_size", 48),
            color=p.get("color", "#FFFFFF"),
            opacity=p.get("opacity", 0.8),
            rotation=p.get("rotation", 0),
            position=p.get("position", tr("右下角", "Bottom right")),
            wm_image_path=p.get("wm_image_path", ""),
            scale=p.get("scale", 0.2),
            progress_cb=prog)

    def _make_task(self, f):
        params = self.collect_params()
        if params["wm_type"] == "text" and not params["text"].strip():
            toast.show_warning(self, tr("水印文字不能为空", "Watermark text cannot be empty"))
            return None
        if params["wm_type"] == "image":
            if not params["wm_image_path"]:
                toast.show_warning(self, tr("请先选择水印图片", "Pick a watermark image first"))
                return None
            if not os.path.isfile(params["wm_image_path"]):
                toast.show_error(self, tr("水印图片不存在", "Watermark image does not exist"))
                return None
        nm = os.path.splitext(os.path.basename(f))[0]
        ext = os.path.splitext(f)[1]
        out_dir = self.out_row.resolve_dir(f)
        out_path = os.path.join(out_dir, nm + "_watermark" + ext)
        return dict(
            name=f"{tr('图片水印', 'Image Watermark')} - {os.path.basename(f)}",
            task_type="watermark", file_path=f, output_path=out_path,
            params=params, runner=self._runner,
            history_type=tr("图片水印", "Image Watermark"), history_target=tr("水印", "Watermark"),
            need_ffmpeg=False)

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要加水印的图片", "Add images to watermark first")
