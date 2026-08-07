# -*- coding: utf-8 -*-
"""id_photo_panel — 证件照换底色面板。

双引擎（AI 人像抠图 / 自适应色度键兜底）+ 实时预览：
添加照片并选择底色后，可实时预览换底效果，满意再批量处理。
"""
import os
import tempfile

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget
from qfluentwidgets import CaptionLabel, CheckBox, ComboBox, FluentIcon, PushButton, Slider

from core.id_photo import PHOTO_SIZES, TRANSPARENT_KEY
from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".heic", ".heif"}
# 目标底色下拉（显示名 ↔ _BG_KEYS 键一一对应；偏好/任务存键，中英界面语义一致）
BG_VALUES = [tr("蓝底", "Blue"), tr("红底", "Red"), tr("白底", "White"),
             tr("灰底", "Gray"), tr("绿底", "Green"), tr("黑底", "Black"),
             tr("透明PNG", "Transparent PNG")]
_BG_KEYS = ["蓝底", "红底", "白底", "灰底", "绿底", "黑底", "透明PNG"]
# 证件照尺寸下拉项（显示名与 PHOTO_SIZES 键一一对应）
SIZE_VALUES = [tr("原尺寸", "Original"),
               tr("1寸 (295×413)", "1-inch (295×413)"),
               tr("小1寸 (259×377)", "1-inch small (259×377)"),
               tr("大1寸 (390×567)", "1-inch large (390×567)"),
               tr("2寸 (413×579)", "2-inch (413×579)"),
               tr("3寸 (550×840)", "3-inch (550×840)")]
_SIZE_KEYS = ["原尺寸", "1寸", "小1寸", "大1寸", "2寸", "3寸"]

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

    def __init__(self, src, out, color, use_ai, size=None, offset=0.0, parent=None):
        super().__init__(parent)
        self._src, self._out = src, out
        self._color, self._use_ai = color, use_ai
        self._size, self._offset = size, offset

    def run(self):
        try:
            from core.id_photo import change_background
            ok = change_background(
                self._src, self._out, self._color, None, self._use_ai,
                size=self._size, offset=self._offset)
            if ok and self._color == TRANSPARENT_KEY:
                self._apply_checker()
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

        from gui_qt.components.form_widgets import FormGrid, FormSection
        card = FormSection(tr("换底设置", "Background settings"), FluentIcon.BRUSH)
        grid = FormGrid(columns=2)

        def _combo(items, default):
            cb = ComboBox()
            cb.addItems(items)
            cb.setCurrentText(default)
            return cb

        self.cb_bg = grid.add_field(
            tr("目标底色", "Target color"), _combo(BG_VALUES, tr("蓝底", "Blue")),
            hint=tr("多色可选，透明 PNG 保留 alpha 可叠加到任意画面",
                    "Multiple colors; transparent PNG keeps alpha for layering"))
        self.cb_size = grid.add_field(
            tr("证件照尺寸", "Photo size"), _combo(SIZE_VALUES, SIZE_VALUES[0]),
            hint=tr("1寸=2.5×3.5cm、2寸=3.5×5.3cm、3寸=5.5×8.4cm（300dpi）",
                    "1in=2.5×3.5cm, 2in=3.5×5.3cm, 3in=5.5×8.4cm (300dpi)"))
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
        grid.add_field(
            tr("裁剪位置", "Crop position"), pos_row,
            hint=tr("偏上保留更多头顶，偏下保留更多下巴", "Shift up to keep more headroom, down for more chin"),
            colspan=2)
        card.add_form(grid)
        self.cb_ai = CheckBox(
            tr("AI 人像抠图（推荐，干净不误伤衣服眼睛）",
               "AI portrait matting (recommended, clean result, won't damage clothes/eyes)"))
        self.cb_ai.setChecked(True)
        card.add_widget(self.cb_ai)
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
        self.pv_status = CaptionLabel(
            tr("切换底色/AI 开关会自动刷新预览", "Switching color or AI toggles refreshes the preview"))
        pv_head.addWidget(self.btn_preview)
        pv_head.addWidget(self.pv_status)
        pv_head.addStretch(1)
        pv_card.add_layout(pv_head)
        lay.addWidget(pv_card)

        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        lay.addWidget(self.out_row)

        self.action_bar = ActionBar(tr("开始处理", "Start"))
        lay.addWidget(self.action_bar)

        # ── 预览联动 ─────────────────────────────
        self._pv_worker = None
        self.btn_preview.clicked.connect(lambda: self._preview_file())
        self.cb_bg.currentTextChanged.connect(lambda _: self._preview_file())
        self.cb_ai.toggled.connect(lambda _: self._preview_file())
        self.cb_size.currentIndexChanged.connect(self._on_size_changed)
        self.sl_offset.valueChanged.connect(self._update_offset_label)
        self.sl_offset.valueChanged.connect(lambda _: self._preview_file())
        self.file_card.files_changed.connect(lambda: self._preview_file())
        self.file_card.file_double_clicked.connect(self._preview_file)
        # 初始状态：原尺寸时裁剪位置滑块禁用
        self.sl_offset.setEnabled(self.cb_size.currentIndex() != 0)

        self.services.task_manager.register_runner(
            "id_photo", lambda task: self._runner)
        self._wire_tasks()

    # ── 参数/偏好 ────────────────────────────────
    def _bg_key(self) -> str:
        idx = self.cb_bg.currentIndex()
        return _BG_KEYS[idx] if 0 <= idx < len(_BG_KEYS) else "蓝底"

    def collect_params(self) -> dict:
        return {
            "bg": self._bg_key(),
            "use_ai": self.cb_ai.isChecked(),
            "size_key": self._size_key(),
            "offset": self.sl_offset.value() / 100.0,
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return self.collect_params()

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("bg") in _BG_KEYS:
            self.cb_bg.setCurrentIndex(_BG_KEYS.index(str(prefs["bg"])))
        if "use_ai" in prefs:
            self.cb_ai.setChecked(bool(prefs["use_ai"]))
        if prefs.get("size_key") in _SIZE_KEYS:
            self.cb_size.setCurrentIndex(_SIZE_KEYS.index(str(prefs["size_key"])))
        if "offset" in prefs:
            self.sl_offset.setValue(int(round(float(prefs["offset"]) * 100)))
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
        # 原尺寸无需裁剪位置
        self.sl_offset.setEnabled(idx != 0)
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
        self._pv_worker = _PreviewWorker(
            path, _PREVIEW_OUT,
            self._bg_key(), self.cb_ai.isChecked(),
            size=PHOTO_SIZES.get(self._size_key()),
            offset=self.sl_offset.value() / 100.0)
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

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        from core.id_photo import change_background
        return change_background(
            task.file_path, task.output_path,
            task.params.get("bg", "蓝底"), prog,
            use_ai=task.params.get("use_ai", True),
            size=PHOTO_SIZES.get(task.params.get("size_key", "原尺寸")),
            offset=task.params.get("offset", 0.0))

    def _make_task(self, f):
        params = self.collect_params()
        out_dir = self.out_row.resolve_dir(f)
        ext = ".png" if params["bg"] == TRANSPARENT_KEY else ".jpg"
        out_path = tm.make_output_path(f, out_dir, ext)
        return dict(
            name=f"{tr('证件照换底色', 'ID photo')} - {os.path.basename(f)}",
            task_type="id_photo", file_path=f, output_path=out_path,
            params=params, runner=self._runner, runner_key="id_photo",
            history_type=tr("证件照换底色", "ID photo"), history_target=params["bg"],
            need_ffmpeg=False)

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要处理的照片文件", "Add photos to process first")
