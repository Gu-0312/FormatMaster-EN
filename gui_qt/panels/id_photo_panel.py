# -*- coding: utf-8 -*-
"""id_photo_panel — 证件照换底色面板。

双引擎（AI 人像抠图 / 自适应色度键兜底）+ 实时预览：
添加照片并选择底色后，可实时预览换底效果，满意再批量处理。
"""
import os
import tempfile

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (QColorDialog, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, CheckBox, ComboBox, FluentIcon,
                            PushButton, Slider)

from core.id_photo import (PHOTO_SIZES, TRANSPARENT_KEY, size_to_px,
                           CARD_PRESETS, PAPER_SIZES, draw_head_guides,
                           layout_print, check_compliance)
from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".heic", ".heif"}
# 目标底色下拉（显示名 ↔ _BG_KEYS 键一一对应；偏好/任务存键，中英界面语义一致）
BG_VALUES = [tr("蓝底", "Blue"), tr("红底", "Red"), tr("白底", "White"),
             tr("灰底", "Gray"), tr("绿底", "Green"), tr("黑底", "Black"),
             tr("透明PNG", "Transparent PNG"), tr("自定义…", "Custom…")]
_BG_KEYS = ["蓝底", "红底", "白底", "灰底", "绿底", "黑底", "透明PNG", "自定义"]
# 证件照尺寸下拉项（显示名与 PHOTO_SIZES 键一一对应）
SIZE_VALUES = [tr("原尺寸", "Original"),
               tr("小1寸 (259×377)", "1-inch small (259×377)"),
               tr("1寸 (295×413)", "1-inch (295×413)"),
               tr("大1寸 (390×567)", "1-inch large (390×567)"),
               tr("小2寸 (413×531)", "2-inch small (413×531)"),
               tr("2寸 (413×579)", "2-inch (413×579)"),
               tr("大2寸 (413×626)", "2-inch large (413×626)"),
               tr("3寸 (550×840)", "3-inch (550×840)"),
               tr("美签照 (601×601)", "US Visa (601×601)"),
               tr("4寸 (898×1205)", "4-inch (898×1205)"),
               tr("5寸 (1051×1500)", "5-inch (1051×1500)"),
               tr("6寸 (1205×1795)", "6-inch (1205×1795)"),
               tr("自定义…", "Custom…")]
_SIZE_KEYS = ["原尺寸", "小1寸", "1寸", "大1寸", "小2寸", "2寸",
              "大2寸", "3寸", "美签照", "4寸", "5寸", "6寸", "自定义"]
# 证照预设（手动 + 各类型）
PRESET_VALUES = [tr("手动设置", "Manual")] + [tr(k, k) for k in CARD_PRESETS]
_PRESET_KEYS = ["__manual__"] + list(CARD_PRESETS.keys())
# 冲印相纸
PAPER_VALUES = [tr("6寸 (10.2×15.2cm)", "6-inch (10.2×15.2cm)"),
                tr("5寸 (8.9×12.7cm)", "5-inch (8.9×12.7cm)"),
                tr("4寸 (7.6×10.2cm)", "4-inch (7.6×10.2cm)")]
_PAPER_KEYS = ["6寸", "5寸", "4寸"]

# 预览临时输出（系统临时目录，每次覆盖；透明预览为 PNG）
_PREVIEW_OUT = os.path.join(tempfile.gettempdir(), "FormatMaster_idphoto_preview.png")


def _checker_composite(rgb, alpha):
    """棋盘格垫底合成（透明预览用，直观看到透明区域）。"""
    import numpy as _np
    h, w = alpha.shape[:2]
    yy, xx = _np.mgrid[:h, :w]
    cell = 16
    checker = _np.full((h, w, 3), 210, dtype=_np.uint8)
    checker[((yy // cell) + (xx // cell)) % 2 == 0] = 235
    a = alpha[..., None].astype(_np.float32) / 255.0
    return (rgb.astype(_np.float32) * a
            + checker.astype(_np.float32) * (1 - a)).astype(_np.uint8)


class _PreviewWorker(QThread):
    """后台跑一次换底生成预览图，信号回传结果。"""

    sig_done = Signal(bool, str)  # (成功, 预览图路径)

    def __init__(self, src, out, color, use_ai, size=None, offset=0.0,
                 show_guides=False, parent=None):
        super().__init__(parent)
        self._src, self._out = src, out
        self._color, self._use_ai = color, use_ai
        self._size, self._offset = size, offset
        self._show_guides = show_guides

    def run(self):
        try:
            from core.id_photo import change_background, draw_head_guides
            ok = change_background(
                self._src, self._out, self._color, None, self._use_ai,
                size=self._size, offset=self._offset)
            if ok and self._color == TRANSPARENT_KEY:
                self._apply_checker()
            if ok and self._show_guides and self._size is not None:
                try:
                    from PIL import Image
                    im = Image.open(self._out)
                    draw_head_guides(im).save(self._out)
                except Exception:  # noqa: BLE001 - 参考线失败不影响预览
                    pass
            self.sig_done.emit(bool(ok), self._out if ok else "")
        except Exception:  # noqa: BLE001 - 预览失败仅提示，不打断流程
            self.sig_done.emit(False, "")

    def _apply_checker(self):
        """透明预览：把透明区域叠成棋盘格再存回（显示透明效果）。"""
        try:
            from PIL import Image
            import numpy as _np
            img = Image.open(self._out).convert("RGBA")
            rgb = _np.asarray(img.convert("RGB"))
            alpha = _np.asarray(img)[..., 3]
            Image.fromarray(_checker_composite(rgb, alpha), "RGB").save(self._out)
        except Exception:  # noqa: BLE001 - 棋盘格失败则保留原透明图
            pass


class _CheckWorker(QThread):
    """后台跑合规自检，信号回传结果 dict（失败为 None）。"""

    sig_done = Signal(object)

    def __init__(self, path, size, offset, use_ai, parent=None):
        super().__init__(parent)
        self._path, self._size = path, size
        self._offset, self._use_ai = offset, use_ai

    def run(self):
        try:
            from core.id_photo import check_compliance
            result = check_compliance(self._path, self._size,
                                      self._offset, self._use_ai)
        except Exception:  # noqa: BLE001 - 自检失败仅提示
            result = None
        self.sig_done.emit(result)


class IdPhotoPanelPage(BaseQtPanel, TaskPanelMixin):
    """证件照换底色页。"""

    panel_key = "id_photo"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("证件照换底色", "ID photo background")))
        lay.addWidget(self.make_subtitle(
            tr("AI 抠出人像换任意底色或导出透明 PNG，适合证件照办理",
               "AI extracts the person; swap to any color or export a transparent PNG")))

        self.file_card = FileListCard(tr("照片列表", "Photos"), file_exts=PHOTO_EXTS)
        lay.addWidget(self.file_card)

        from gui_qt.components.form_widgets import (FormGrid, FormSection,
                                                    CollapsibleSection)
        card = FormSection(tr("换底设置", "Background settings"), FluentIcon.BRUSH)
        grid = FormGrid(columns=2)

        def _combo(items, default):
            cb = ComboBox()
            cb.addItems(items)
            cb.setCurrentText(default)
            return cb

        # 主参数（直接可见）：预设 / 底色 / 尺寸
        self.cb_preset = grid.add_field(
            tr("证照预设", "Card preset"), _combo(PRESET_VALUES, PRESET_VALUES[0]),
            hint=tr("选择证件类型自动套用尺寸与底色，也可手动调整",
                    "Pick a card type to auto-apply size & color; editable"))
        self.cb_bg = grid.add_field(
            tr("目标底色", "Target color"), _combo(BG_VALUES, tr("蓝底", "Blue")),
            hint=tr("多色可选，透明 PNG 保留 alpha 可叠加到任意画面",
                    "Multiple colors; transparent PNG keeps alpha for layering"))
        self.cb_size = grid.add_field(
            tr("证件照尺寸", "Photo size"), _combo(SIZE_VALUES, SIZE_VALUES[0]),
            hint=tr("小1寸=2.2×3.2cm、1寸=2.5×3.5cm、大1寸=3.3×4.8cm、"
                    "小2寸=3.5×4.5cm、2寸=3.5×4.9cm、大2寸=3.5×5.3cm、"
                    "3寸=4.7×7.1cm、美签照=5.1×5.1cm、4寸=7.6×10.2cm、"
                    "5寸=8.9×12.7cm、6寸=10.2×15.2cm（300dpi）",
                    "1in=2.5×3.5cm, 2in=3.5×4.9cm, 3in=4.7×7.1cm, "
                    "US Visa=5.1×5.1cm, 4in=7.6×10.2cm, 5in=8.9×12.7cm, "
                    "6in=10.2×15.2cm (300dpi)"))
        card.add_form(grid)
        self.cb_ai = CheckBox(
            tr("AI 人像抠图（推荐，干净不误伤衣服眼睛）",
               "AI portrait matting (recommended, clean result, won't damage clothes/eyes)"))
        self.cb_ai.setChecked(True)
        card.add_widget(self.cb_ai)

        # 高级设置（渐进式披露：默认折叠，进阶项）
        self.adv_collapse = CollapsibleSection(
            tr("高级设置", "Advanced"),
            hint=tr("自定义颜色/尺寸、裁剪位置、导出 DPI、命名（进阶选项）",
                    "Custom color/size, crop position, export DPI, naming (advanced)"))
        adv_grid = FormGrid(columns=1)

        # 自定义颜色（选中“自定义…”时显示）：任意选色
        color_row = QWidget()
        color_lay = QHBoxLayout(color_row)
        color_lay.setContentsMargins(0, 0, 0, 0)
        color_lay.setSpacing(8)
        self.btn_color = PushButton(tr("选择颜色…", "Pick color…"))
        self.lb_swatch = QLabel()
        self.lb_swatch.setFixedSize(28, 20)
        self.lb_swatch.setStyleSheet(
            "border:1px solid rgba(128,128,128,0.5); border-radius:3px;")
        color_lay.addWidget(self.btn_color)
        color_lay.addWidget(self.lb_swatch)
        color_lay.addStretch(1)
        self.color_row = color_row
        adv_grid.add_field(tr("自定义颜色", "Custom color"), color_row)
        color_row.setVisible(False)

        # 自定义尺寸输入（选中“自定义…”时显示）
        cust_row = QWidget()
        cust_lay = QHBoxLayout(cust_row)
        cust_lay.setContentsMargins(0, 0, 0, 0)
        cust_lay.setSpacing(8)
        self.le_cw = QLineEdit()
        self.le_cw.setPlaceholderText(tr("宽", "W"))
        self.le_cw.setFixedWidth(70)
        self.le_ch = QLineEdit()
        self.le_ch.setPlaceholderText(tr("高", "H"))
        self.le_ch.setFixedWidth(70)
        self.cb_unit = _combo([tr("像素", "px"), tr("厘米", "cm"), tr("英寸", "inch")],
                              tr("像素", "px"))
        self.cb_unit.setFixedWidth(90)
        cust_lay.addWidget(QLabel(tr("宽", "W")))
        cust_lay.addWidget(self.le_cw)
        cust_lay.addWidget(QLabel(tr("高", "H")))
        cust_lay.addWidget(self.le_ch)
        cust_lay.addWidget(QLabel(tr("单位", "Unit")))
        cust_lay.addWidget(self.cb_unit)
        cust_lay.addStretch(1)
        self.cust_row = cust_row
        adv_grid.add_field(tr("自定义尺寸", "Custom size"), cust_row)
        cust_row.setVisible(False)

        # 裁剪位置（仅选尺寸时有意义）：滑块 -20~20
        pos_row = QWidget()
        pos_lay = QHBoxLayout(pos_row)
        pos_lay.setContentsMargins(0, 0, 0, 0)
        pos_lay.setSpacing(10)
        self.sl_offset = Slider(Qt.Horizontal)
        self.sl_offset.setRange(-20, 20)
        self.sl_offset.setValue(0)
        self.sl_offset.setFixedWidth(180)
        self.lb_offset = CaptionLabel(tr("居中", "Center"))
        pos_lay.addWidget(self.sl_offset)
        pos_lay.addWidget(self.lb_offset)
        pos_lay.addStretch(1)
        adv_grid.add_field(
            tr("裁剪位置", "Crop position"), pos_row,
            hint=tr("偏上保留更多头顶，偏下保留更多下巴", "Shift up to keep more headroom, down for more chin"))

        # 导出 DPI 与 JPG 质量
        self.cb_dpi = _combo([tr("96 DPI", "96 DPI"), tr("150 DPI", "150 DPI"),
                              tr("300 DPI", "300 DPI"), tr("600 DPI", "600 DPI")],
                             tr("300 DPI", "300 DPI"))
        self.cb_quality = _combo([tr("80%", "80%"), tr("90%", "90%"),
                                  tr("95%", "95%"), tr("100%", "100%")],
                                 tr("95%", "95%"))
        dpi_row = QWidget()
        dpi_lay = QHBoxLayout(dpi_row)
        dpi_lay.setContentsMargins(0, 0, 0, 0)
        dpi_lay.setSpacing(8)
        dpi_lay.addWidget(self.cb_dpi)
        dpi_lay.addWidget(QLabel(tr("JPG 质量", "JPG quality")))
        dpi_lay.addWidget(self.cb_quality)
        dpi_lay.addStretch(1)
        adv_grid.add_field(tr("导出设置", "Export"), dpi_row)

        self.adv_collapse.add_layout(adv_grid)
        self.cb_named = CheckBox(
            tr("输出文件名添加 尺寸_底色 标记",
               "Append size_color tag to output filename"))
        self.cb_named.setChecked(False)
        self.adv_collapse.add_widget(self.cb_named)
        card.add_widget(self.adv_collapse)
        lay.addWidget(card)

        # ── 实时预览 ─────────────────────────────
        pv_card = FormSection(tr("实时预览", "Live preview"), FluentIcon.VIEW)
        self.pv_label = QLabel(tr("添加照片并选择底色，此处实时预览换底效果",
                                  "Add photos and pick a color to preview the result live"))
        self.pv_label.setAlignment(Qt.AlignCenter)
        self.pv_label.setMinimumHeight(280)
        self.pv_label.setWordWrap(True)
        self.pv_label.setStyleSheet(
            "border: 1px dashed rgba(128,128,128,0.45); border-radius: 8px;"
            "color: rgba(128,128,128,0.75); background: transparent; font-size: 13px;")
        pv_card.add_widget(self.pv_label)
        pv_head = QHBoxLayout()
        self.btn_preview = PushButton(FluentIcon.VIEW, tr("预览效果", "Preview"))
        self.btn_check = PushButton(tr("合规自检", "Compliance"))
        self.pv_status = CaptionLabel(
            tr("切换底色/AI 开关会自动刷新预览", "Switching color or AI toggles refreshes the preview"))
        pv_head.addWidget(self.btn_preview)
        pv_head.addWidget(self.btn_check)
        pv_head.addWidget(self.pv_status)
        pv_head.addStretch(1)
        pv_card.add_layout(pv_head)
        # 头部比例参考线（仅预览辅助）
        self.cb_guides = CheckBox(
            tr("显示头部比例参考线", "Show head-ratio guide"))
        self.cb_guides.setChecked(False)
        pv_card.add_widget(self.cb_guides)
        # 一键冲印排版
        print_row = QWidget()
        pl = QHBoxLayout(print_row)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(8)
        self.cb_print = CheckBox(tr("一键冲印排版", "Print layout"))
        self.cb_print.setChecked(False)
        self.cb_paper = _combo(PAPER_VALUES, PAPER_VALUES[0])
        self.cb_paper.setFixedWidth(180)
        pl.addWidget(self.cb_print)
        pl.addWidget(QLabel(tr("相纸", "Paper")))
        pl.addWidget(self.cb_paper)
        pl.addStretch(1)
        pv_card.add_widget(print_row)
        lay.addWidget(pv_card)

        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        lay.addWidget(self.out_row)

        self.action_bar = ActionBar(tr("开始处理", "Start"))
        lay.addWidget(self.action_bar)

        # ── 预览联动 ─────────────────────────────
        self._pv_worker = None
        self._custom_color = (219, 64, 64)      # 自定义底色默认（红）
        # 实时记忆由基类 BaseQtPanel._install_auto_prefs 统一提供（防抖自动保存）
        self.btn_preview.clicked.connect(lambda: self._preview_file())
        self.btn_check.clicked.connect(self._run_compliance)
        self.cb_bg.currentTextChanged.connect(lambda _: self._on_bg_changed())
        self.cb_ai.toggled.connect(lambda _: self._on_param_changed())
        self.cb_size.currentIndexChanged.connect(self._on_size_changed)
        self.cb_preset.currentIndexChanged.connect(self._on_preset_changed)
        self.cb_print.toggled.connect(lambda _: self._on_param_changed())
        self.cb_paper.currentIndexChanged.connect(lambda _: self._on_param_changed())
        self.cb_guides.toggled.connect(lambda _: self._on_param_changed())
        self.cb_dpi.currentIndexChanged.connect(lambda _: self._on_param_changed())
        self.cb_quality.currentIndexChanged.connect(lambda _: self._on_param_changed())
        self.btn_color.clicked.connect(self._pick_custom_color)
        self.le_cw.textChanged.connect(lambda _: self._on_param_changed())
        self.le_ch.textChanged.connect(lambda _: self._on_param_changed())
        self.cb_unit.currentIndexChanged.connect(lambda _: self._on_param_changed())
        self.sl_offset.valueChanged.connect(self._update_offset_label)
        self.sl_offset.valueChanged.connect(lambda _: self._on_param_changed())
        self.file_card.files_changed.connect(lambda: self._preview_file())
        self.file_card.file_double_clicked.connect(self._preview_file)
        # 初始状态：原尺寸时裁剪位置滑块禁用、自定义行隐藏
        self._on_size_changed(self.cb_size.currentIndex())
        self._on_bg_changed()

        self.services.task_manager.register_runner(
            "id_photo", lambda task: self._runner)
        self._wire_tasks()

    # ── 参数/偏好 ────────────────────────────────
    def _on_param_changed(self):
        """任一参数变化：触发自动保存（基类防抖） + 刷新预览。"""
        self._schedule_prefs_save()
        self._preview_file()

    def _bg_key(self):
        idx = self.cb_bg.currentIndex()
        key = _BG_KEYS[idx] if 0 <= idx < len(_BG_KEYS) else "蓝底"
        if key == "自定义":
            return self._custom_rgb()
        return key

    def _custom_rgb(self) -> tuple:
        r, g, b = self._custom_color
        return (int(r), int(g), int(b))

    def _set_swatch(self):
        r, g, b = self._custom_rgb()
        self.lb_swatch.setStyleSheet(
            f"background: rgb({r},{g},{b});"
            " border:1px solid rgba(128,128,128,0.5); border-radius:3px;")

    def _on_bg_changed(self):
        idx = self.cb_bg.currentIndex()
        key = _BG_KEYS[idx] if 0 <= idx < len(_BG_KEYS) else "蓝底"
        self.color_row.setVisible(key == "自定义")
        if key == "自定义":
            self.adv_collapse.set_expanded(True)  # 需输入颜色，自动展开高级区
        self._set_swatch()
        self._schedule_prefs_save()
        self._preview_file()

    def _pick_custom_color(self):
        r, g, b = self._custom_rgb()
        c = QColorDialog.getColor(
            QColor(r, g, b), self, tr("选择自定义底色", "Pick custom color"))
        if c.isValid():
            self._custom_color = (c.red(), c.green(), c.blue())
            self._set_swatch()
            self._schedule_prefs_save()
            self._preview_file()

    def collect_params(self) -> dict:
        custom = None
        if self._size_key() == "自定义":
            unit = ("px", "cm", "inch")[self.cb_unit.currentIndex()]
            custom = size_to_px(self.le_cw.text(), self.le_ch.text(), unit)
        return {
            "bg": self._bg_key(),
            "use_ai": self.cb_ai.isChecked(),
            "named": self.cb_named.isChecked(),
            "size_key": self._size_key(),
            "custom_size": custom,
            "offset": self.sl_offset.value() / 100.0,
            "show_guides": self.cb_guides.isChecked(),
            "do_print": self.cb_print.isChecked(),
            "paper": _PAPER_KEYS[self.cb_paper.currentIndex()],
            "dpi": int(self.cb_dpi.currentText().split()[0]),
            "quality": int(self.cb_quality.currentText().rstrip("%")),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return self.collect_params()

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        bg = prefs.get("bg")
        if isinstance(bg, (tuple, list)) and len(bg) == 3:
            self._custom_color = tuple(int(c) for c in bg)
            self.cb_bg.setCurrentIndex(_BG_KEYS.index("自定义"))
        elif bg in _BG_KEYS:
            self.cb_bg.setCurrentIndex(_BG_KEYS.index(str(bg)))
        if "use_ai" in prefs:
            self.cb_ai.setChecked(bool(prefs["use_ai"]))
        if "named" in prefs:
            self.cb_named.setChecked(bool(prefs["named"]))
        if prefs.get("size_key") in _SIZE_KEYS:
            self.cb_size.setCurrentIndex(_SIZE_KEYS.index(str(prefs["size_key"])))
        if "offset" in prefs:
            self.sl_offset.setValue(int(round(float(prefs["offset"]) * 100)))
        if "show_guides" in prefs:
            self.cb_guides.setChecked(bool(prefs["show_guides"]))
        if "do_print" in prefs:
            self.cb_print.setChecked(bool(prefs["do_print"]))
        if prefs.get("paper") in _PAPER_KEYS:
            self.cb_paper.setCurrentIndex(_PAPER_KEYS.index(prefs["paper"]))
        if "dpi" in prefs:
            for i, t in enumerate(["96 DPI", "150 DPI", "300 DPI", "600 DPI"]):
                if t.startswith(str(prefs["dpi"])):
                    self.cb_dpi.setCurrentIndex(i)
                    break
        if "quality" in prefs:
            idx = self.cb_quality.findText(str(prefs["quality"]) + "%")
            if idx >= 0:
                self.cb_quality.setCurrentIndex(idx)
        if prefs.get("custom_size"):
            try:
                cw, ch = prefs["custom_size"]
                self.le_cw.setText(str(int(cw)))
                self.le_ch.setText(str(int(ch)))
            except Exception:  # noqa: BLE001
                pass
        # 应用尺寸/底色后同步自定义行可见性
        self._on_size_changed(self.cb_size.currentIndex())
        self._on_bg_changed()
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 实时预览 ─────────────────────────────────
    def _size_key(self) -> str:
        idx = self.cb_size.currentIndex()
        return _SIZE_KEYS[idx] if 0 <= idx < len(_SIZE_KEYS) else "原尺寸"

    def _update_offset_label(self, v: int):
        if v > 0:
            self.lb_offset.setText(tr(f"偏上 {v}%", f"Up {v}%"))
        elif v < 0:
            self.lb_offset.setText(tr(f"偏下 {-v}%", f"Down {-v}%"))
        else:
            self.lb_offset.setText(tr("居中", "Center"))

    def _on_size_changed(self, idx: int):
        is_custom = 0 <= idx < len(_SIZE_KEYS) and _SIZE_KEYS[idx] == "自定义"
        self.cust_row.setVisible(is_custom)
        if is_custom:
            self.adv_collapse.set_expanded(True)  # 需输入尺寸，自动展开高级区
        self.sl_offset.setEnabled(idx != 0)
        self._schedule_prefs_save()
        self._preview_file()

    def _on_preset_changed(self, idx: int):
        if 0 <= idx < len(_PRESET_KEYS):
            key = _PRESET_KEYS[idx]
            if key in CARD_PRESETS:
                p = CARD_PRESETS[key]
                if p["size"] in _SIZE_KEYS:
                    self.cb_size.setCurrentIndex(_SIZE_KEYS.index(p["size"]))
                if p["bg"] in _BG_KEYS:
                    self.cb_bg.setCurrentIndex(_BG_KEYS.index(p["bg"]))
                self._on_size_changed(self.cb_size.currentIndex())
        self._schedule_prefs_save()
        self._preview_file()

    def _preview_file(self, path=None):
        """预览指定文件；缺省取当前选中行，再取列表第一张。"""
        if self._pv_worker and self._pv_worker.isRunning():
            return  # 正在预览时忽略新请求（0.2~3s 很短）
        if not path:
            files = self.file_card.files()
            if not files:
                self._pv_status_text(tr("请先添加照片", "Add photos first"))
                return
            rows = sorted({i.row() for i in self.file_card.table.selectedIndexes()})
            path = files[rows[0]] if rows and rows[0] < len(files) else files[0]
        if not os.path.isfile(path):
            return
        self.btn_preview.setEnabled(False)
        self._pv_status_text(tr("预览中…", "Previewing…"))
        size = PHOTO_SIZES.get(self._size_key())
        if size is None and self._size_key() == "自定义":
            unit = ("px", "cm", "inch")[self.cb_unit.currentIndex()]
            size = size_to_px(self.le_cw.text(), self.le_ch.text(), unit)
        self._pv_worker = _PreviewWorker(
            path, _PREVIEW_OUT,
            self._bg_key(), self.cb_ai.isChecked(),
            size=size, offset=self.sl_offset.value() / 100.0,
            show_guides=self.cb_guides.isChecked())
        self._pv_worker.sig_done.connect(self._on_preview_done)
        self._pv_worker.start()

    def _on_preview_done(self, ok, path):
        self.btn_preview.setEnabled(True)
        if ok and path and os.path.isfile(path):
            pix = QPixmap(path)
            if not pix.isNull():
                w = max(self.pv_label.width() - 24, 120)
                h = max(self.pv_label.height() - 24, 120)
                self.pv_label.setPixmap(
                    pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.pv_label.setStyleSheet(
                    "border: 1px solid rgba(128,128,128,0.25); border-radius: 8px;"
                    "background: transparent;")
                self._pv_status_text(tr("预览完成", "Preview ready"))
                return
        self.pv_label.clear()
        self.pv_label.setText(tr("预览失败：图片无法处理", "Preview failed: cannot process image"))
        self.pv_label.setStyleSheet(
            "border: 1px dashed rgba(128,128,128,0.45); border-radius: 8px;"
            "color: rgba(128,128,128,0.75); background: transparent; font-size: 13px;")
        self._pv_status_text("")

    def _pv_status_text(self, text):
        self.pv_status.setText(text)

    # ── 合规自检 ─────────────────────────────────
    def _run_compliance(self):
        files = self.file_card.files()
        if not files:
            self._pv_status_text(tr("请先添加照片", "Add photos first"))
            return
        rows = sorted({i.row() for i in self.file_card.table.selectedIndexes()})
        path = files[rows[0]] if rows and rows[0] < len(files) else files[0]
        if not os.path.isfile(path):
            return
        size = PHOTO_SIZES.get(self._size_key())
        if size is None and self._size_key() == "自定义":
            unit = ("px", "cm", "inch")[self.cb_unit.currentIndex()]
            size = size_to_px(self.le_cw.text(), self.le_ch.text(), unit)
        self.btn_check.setEnabled(False)
        self._pv_status_text(tr("合规自检中…", "Checking…"))
        self._check_worker = _CheckWorker(
            path, size, self.sl_offset.value() / 100.0, self.cb_ai.isChecked())
        self._check_worker.sig_done.connect(self._on_compliance_done)
        self._check_worker.start()

    def _on_compliance_done(self, result):
        self.btn_check.setEnabled(True)
        if not result:
            self._pv_status_text(tr("自检失败：无法处理该图片", "Check failed"))
            return
        lines = [
            tr("头部距上边 {}%", "Head top {}%").format(result["head_top_pct"]),
            tr("人像高度占 {}%", "Person height {}%").format(result["person_h_pct"]),
            tr("人像宽度占 {}%", "Person width {}%").format(result["person_w_pct"]),
        ]
        if result["ok"]:
            msg = (tr("✅ 合规：头部位置与人像占比符合常见证件照标准",
                      "Compliant: head position & person ratio meet common standards")
                   + "\n" + "\n".join(lines))
        else:
            msg = (tr("⚠️ 建议调整：", "Needs adjustment")
                   + "\n" + "\n".join(result["issues"]) + "\n\n"
                   + "\n".join(lines))
        QMessageBox.information(self, tr("合规自检", "Compliance"), msg)

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        from core.id_photo import change_background, layout_print
        from PIL import Image
        params = task.params
        bg = params.get("bg", "蓝底")
        offset = params.get("offset", 0.0)
        dpi = int(params.get("dpi", 300) or 300)
        quality = int(params.get("quality", 95) or 95)
        size = PHOTO_SIZES.get(params.get("size_key", "原尺寸"))
        if size is None and params.get("size_key") == "自定义":
            size = params.get("custom_size")
        ok = change_background(task.file_path, task.output_path, bg, prog,
                               use_ai=params.get("use_ai", True),
                               size=size, offset=offset,
                               dpi=dpi, quality=quality)
        if ok and params.get("do_print"):
            try:
                single = Image.open(task.output_path).convert("RGB")
                paper = PAPER_SIZES.get(params.get("paper", "6寸"),
                                        PAPER_SIZES["6寸"])
                layout_print(single, paper, dpi=dpi).save(
                    task.output_path, quality=quality, dpi=(dpi, dpi))
            except Exception:  # noqa: BLE001 - 排版失败不影响单张
                pass
        return ok

    def _make_task(self, f):
        params = self.collect_params()
        out_dir = self.out_row.resolve_dir(f)
        ext = ".png" if params["bg"] == TRANSPARENT_KEY else ".jpg"
        nm = None
        if params.get("named"):
            size_tag = params.get("size_key", "原尺寸")
            bg = params["bg"]
            if isinstance(bg, (tuple, list)):
                r, g, b = (int(x) for x in bg)
                bg_tag = f"RGB{r}{g}{b}"
            elif bg == TRANSPARENT_KEY:
                bg_tag = "透明"
            else:
                bg_tag = bg
            nm = os.path.splitext(os.path.basename(f))[0] + f"_{size_tag}_{bg_tag}"
        out_path = tm.make_output_path(f, out_dir, ext, name=nm)
        bg = params["bg"]
        if isinstance(bg, (tuple, list)):
            r, g, b = (int(x) for x in bg)
            target_label = f"自定义 ({r},{g},{b})"
        else:
            target_label = bg
        return dict(
            name=f"{tr('证件照换底色', 'ID photo')} - {os.path.basename(f)}",
            task_type="id_photo", file_path=f, output_path=out_path,
            params=params, runner=self._runner, runner_key="id_photo",
            history_type=tr("证件照换底色", "ID photo"), history_target=target_label,
            need_ffmpeg=False)

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要处理的照片文件", "Add photos to process first")
