# -*- coding: utf-8 -*-
"""id_photo_panel — 证件照换底色面板。

双引擎（AI 人像抠图 / 自适应色度键兜底）+ 实时预览：
添加照片并选择底色后，可实时预览换底效果，满意再批量处理。
"""
import os
import tempfile

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel
from qfluentwidgets import CaptionLabel, CheckBox, ComboBox, FluentIcon, PushButton

from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".heic", ".heif"}
BG_VALUES = [tr("蓝底", "Blue"), tr("红底", "Red"), tr("白底", "White")]

# 预览临时输出（系统临时目录，每次覆盖）
_PREVIEW_OUT = os.path.join(tempfile.gettempdir(), "FormatMaster_idphoto_preview.jpg")


class _PreviewWorker(QThread):
    """后台跑一次换底生成预览图，信号回传结果。"""

    sig_done = Signal(bool, str)  # (成功, 预览图路径)

    def __init__(self, src, out, color, use_ai, parent=None):
        super().__init__(parent)
        self._src, self._out = src, out
        self._color, self._use_ai = color, use_ai

    def run(self):
        try:
            from core.id_photo import change_background
            ok = change_background(
                self._src, self._out, self._color, None, self._use_ai)
            self.sig_done.emit(bool(ok), self._out if ok else "")
        except Exception:  # noqa: BLE001 - 预览失败仅提示，不打断流程
            self.sig_done.emit(False, "")


class IdPhotoPanelPage(BaseQtPanel, TaskPanelMixin):
    """证件照换底色页。"""

    panel_key = "id_photo"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("证件照换底色", "ID photo background")))
        lay.addWidget(self.make_subtitle(
            tr("一键把照片背景替换为红/蓝/白标准底色，适合证件照办理",
               "Swap photo background to standard red/blue/white for ID photos")))

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
            hint=tr("蓝底/红底/白底为证件照标准底色", "Blue/red/white are standard ID photo colors"))
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
        self.file_card.files_changed.connect(lambda: self._preview_file())
        self.file_card.file_double_clicked.connect(self._preview_file)

        self.services.task_manager.register_runner(
            "id_photo", lambda task: self._runner)
        self._wire_tasks()

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "bg": self.cb_bg.currentText(),
            "use_ai": self.cb_ai.isChecked(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return self.collect_params()

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("bg") in BG_VALUES:
            self.cb_bg.setCurrentText(str(prefs["bg"]))
        if "use_ai" in prefs:
            self.cb_ai.setChecked(bool(prefs["use_ai"]))
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 实时预览 ─────────────────────────────────
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
            self.cb_bg.currentText(), self.cb_ai.isChecked())
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
            task.params.get("bg", tr("蓝底", "Blue")), prog,
            use_ai=task.params.get("use_ai", True))

    def _make_task(self, f):
        params = self.collect_params()
        out_dir = self.out_row.resolve_dir(f)
        out_path = tm.make_output_path(f, out_dir, ".jpg")
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
