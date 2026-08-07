# -*- coding: utf-8 -*-
"""cutout_panel — 抠图换背景面板。

AI 人像抠图（MODNet，复用证件照引擎）：一键把人像从照片中抠出，
输出透明 PNG 或贴到纯色背景；带实时预览。
"""
import os
import tempfile

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget
from qfluentwidgets import CaptionLabel, CheckBox, ComboBox, FluentIcon, PushButton, Slider

from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".heic", ".heif"}
# 输出模式下拉（显示名 ↔ 背景色键，一一对应；None=透明 PNG）
MODE_VALUES = [tr("透明 PNG", "Transparent PNG"), tr("白底", "White"),
               tr("蓝底", "Blue"), tr("红底", "Red"),
               tr("灰底", "Gray"), tr("绿底", "Green"), tr("黑底", "Black")]
MODE_BG_KEYS = [None, "白底", "蓝底", "红底", "灰底", "绿底", "黑底"]

_PREVIEW_OUT = os.path.join(tempfile.gettempdir(), "FormatMaster_cutout_preview.png")


def _checker_composite(rgb, alpha):
    """棋盘格垫底合成（预览透明效果用，直观看到透明区域）。"""
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
    """后台跑一次抠图生成预览图（透明模式叠加棋盘格）。"""

    sig_done = Signal(bool, str)

    def __init__(self, src, out, bg, use_ai, parent=None):
        super().__init__(parent)
        self._src, self._out = src, out
        self._bg, self._use_ai = bg, use_ai

    def run(self):
        try:
            from core.id_photo import cutout_portrait
            ok = cutout_portrait(
                self._src, self._out, self._bg, None, self._use_ai)
            if ok and self._bg is None:
                self._apply_checker()
            self.sig_done.emit(bool(ok), self._out if ok else "")
        except Exception:  # noqa: BLE001 - 预览失败仅提示
            self.sig_done.emit(False, "")

    def _apply_checker(self):
        """透明预览：把透明区域叠成棋盘格再存回（显示透明效果）。"""
        try:
            from PIL import Image
            import numpy as _np
            img = Image.open(self._out).convert("RGBA")
            rgb = _np.asarray(img.convert("RGB"))
            alpha = _np.asarray(img)[..., 3]
            compos = _checker_composite(rgb, alpha)
            Image.fromarray(compos, "RGB").save(self._out)
        except Exception:  # noqa: BLE001 - 棋盘格失败则保留原透明图
            pass


class CutoutPanelPage(BaseQtPanel, TaskPanelMixin):
    """抠图换背景页。"""

    panel_key = "cutout"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("抠图换背景", "Cutout & background")))
        lay.addWidget(self.make_subtitle(
            tr("AI 一键抠出人像，生成透明 PNG 或替换纯色背景",
               "AI cutout: extract the person and export transparent PNG or swap to a solid background")))

        self.file_card = FileListCard(tr("照片列表", "Photos"), file_exts=PHOTO_EXTS)
        lay.addWidget(self.file_card)

        from gui_qt.components.form_widgets import FormGrid, FormSection
        card = FormSection(tr("抠图设置", "Cutout settings"), FluentIcon.CUT)
        grid = FormGrid(columns=2)

        def _combo(items, default):
            cb = ComboBox()
            cb.addItems(items)
            cb.setCurrentText(default)
            return cb

        self.cb_mode = grid.add_field(
            tr("输出模式", "Output mode"), _combo(MODE_VALUES, MODE_VALUES[0]),
            hint=tr("透明 PNG 带 alpha 通道，可叠加到任意画面；也可直接贴纯色背景",
                    "Transparent PNG keeps alpha for layering; or swap to a solid color"))
        card.add_form(grid)
        self.cb_ai = CheckBox(
            tr("AI 人像抠图（推荐，边缘干净）",
               "AI portrait matting (recommended, clean edges)"))
        self.cb_ai.setChecked(True)
        card.add_widget(self.cb_ai)
        lay.addWidget(card)

        # ── 实时预览 ─────────────────────────────
        pv_card = FormSection(tr("实时预览", "Live preview"), FluentIcon.VIEW)
        self.pv_label = QLabel(tr("添加照片并选择模式，此处实时预览抠图效果",
                                  "Add photos and pick a mode to preview the cutout live"))
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
            tr("切换模式/AI 开关会自动刷新预览", "Switching mode or AI toggles refreshes the preview"))
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
        self.cb_mode.currentIndexChanged.connect(lambda _: self._preview_file())
        self.cb_ai.toggled.connect(lambda _: self._preview_file())
        self.file_card.files_changed.connect(lambda: self._preview_file())
        self.file_card.file_double_clicked.connect(self._preview_file)

        self.services.task_manager.register_runner(
            "cutout", lambda task: self._runner)
        self._wire_tasks()

    # ── 参数/偏好 ────────────────────────────────
    def _mode_bg(self):
        idx = self.cb_mode.currentIndex()
        return MODE_BG_KEYS[idx] if 0 <= idx < len(MODE_BG_KEYS) else None

    def _is_transparent(self):
        return self._mode_bg() is None

    def collect_params(self) -> dict:
        return {
            "bg": self._mode_bg(),
            "use_ai": self.cb_ai.isChecked(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return self.collect_params()

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        bg = prefs.get("bg")
        idx = MODE_BG_KEYS.index(bg) if bg in MODE_BG_KEYS else 0
        self.cb_mode.setCurrentIndex(idx)
        if "use_ai" in prefs:
            self.cb_ai.setChecked(bool(prefs["use_ai"]))
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 实时预览 ─────────────────────────────────
    def _preview_file(self, path=None):
        if self._pv_worker and self._pv_worker.isRunning():
            return
        if not path:
            files = self.file_card.files()
            if not files:
                self.pv_status.setText(tr("请先添加照片", "Add photos first"))
                return
            rows = sorted({i.row() for i in self.file_card.table.selectedIndexes()})
            path = files[rows[0]] if rows and rows[0] < len(files) else files[0]
        if not os.path.isfile(path):
            return
        self.btn_preview.setEnabled(False)
        self.pv_status.setText(tr("预览中…", "Previewing…"))
        self._pv_worker = _PreviewWorker(
            path, _PREVIEW_OUT, self._mode_bg(), self.cb_ai.isChecked())
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
                self.pv_status.setText(tr("预览完成", "Preview ready"))
                return
        self.pv_label.clear()
        self.pv_label.setText(tr("预览失败：图片无法处理", "Preview failed: cannot process image"))
        self.pv_label.setStyleSheet(
            "border: 1px dashed rgba(128,128,128,0.45); border-radius: 8px;"
            "color: rgba(128,128,128,0.75); background: transparent; font-size: 13px;")
        self.pv_status.setText("")

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        from core.id_photo import cutout_portrait
        return cutout_portrait(
            task.file_path, task.output_path,
            task.params.get("bg"), prog,
            use_ai=task.params.get("use_ai", True))

    def _make_task(self, f):
        params = self.collect_params()
        out_dir = self.out_row.resolve_dir(f)
        ext = ".png" if self._is_transparent() else ".jpg"
        out_path = tm.make_output_path(f, out_dir, ext)
        return dict(
            name=f"{tr('抠图换背景', 'Cutout')} - {os.path.basename(f)}",
            task_type="cutout", file_path=f, output_path=out_path,
            params=params, runner=self._runner, runner_key="cutout",
            history_type=tr("抠图换背景", "Cutout"),
            history_target=self.cb_mode.currentText(),
            need_ffmpeg=False)

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要处理的照片文件", "Add photos to process first")
