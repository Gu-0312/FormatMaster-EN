"""ocr_panel — OCR 文字识别面板（合并版）。

从图片或 PDF 中识别文字，支持单文件和批量处理。
- 单文件模式：显示识别结果文本区，支持复制/导出
- 批量模式：每个输入生成一个同名 .txt 结果文件
"""
import os

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import (FluentIcon, CaptionLabel, ComboBox, PushButton,
                            SwitchButton, TextEdit)

from gui_qt.i18n import tr
from gui_qt.components import toast
from gui_qt.components.form_widgets import FormSection
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt import task_manager as tm
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

# 预置值
OCR_LANGS = ["chi_sim+eng", "chi_sim", "eng", "jpn", "kor",
             "chi_tra+eng", "chi_tra", "eng+chi_sim"]

OCR_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif", ".pdf"}


class OcrPanelPage(BaseQtPanel, TaskPanelMixin):
    """OCR 识别页（合并版，支持单文件和批量）。"""

    panel_key = "ocr"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("OCR 文字识别", "OCR")))
        lay.addWidget(CaptionLabel(
            tr("从图片或PDF中识别文字，支持单文件和批量处理",
               "OCR text from images or PDF, single file and batch")))

        self.file_card = FileListCard(tr("文件列表", "Files"), file_exts=OCR_EXTS)
        lay.addWidget(self.file_card)

        # 识别设置
        sec = FormSection(tr("识别设置", "OCR settings"), FluentIcon.FONT)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(CaptionLabel(tr("识别语言", "Language")))
        self.cb_lang = ComboBox()
        self.cb_lang.addItems(OCR_LANGS)
        self.cb_lang.setCurrentText("chi_sim+eng")
        row.addWidget(self.cb_lang)
        row.addWidget(CaptionLabel(
            tr("chi_sim=简体中文  eng=英文  jpn=日文  kor=韩文",
               "chi_sim=Chinese  eng=English  jpn=Japanese  kor=Korean")))
        row.addStretch(1)
        row.addWidget(CaptionLabel(tr("导出格式", "Export format")))
        self.cb_export = ComboBox()
        self.cb_export.addItems([tr("TXT 文本", "TXT"), tr("Word 文档", "Word")])
        self.cb_export.setCurrentIndex(0)
        row.addWidget(self.cb_export)
        sec.add_layout(row)
        lay.addWidget(sec)

        # 批量模式开关
        batch_row = QHBoxLayout()
        batch_row.setSpacing(8)
        self.sw_batch = SwitchButton(tr("批量模式", "Batch mode"))
        self.sw_batch.setToolTip(
            tr("批量模式：每个文件生成一个.txt结果文件；关闭：单文件模式，显示识别结果",
               "Batch: each file generates a .txt; Off: single file, show result"))
        self.sw_batch.checkedChanged.connect(self._on_batch_changed)
        batch_row.addWidget(self.sw_batch)
        batch_row.addStretch(1)
        lay.addLayout(batch_row)

        # 识别结果区（单文件模式显示）
        self.result_card = FormSection(tr("识别结果", "Result"), FluentIcon.INFO)
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addStretch(1)
        btn_copy = PushButton(tr("复制到剪贴板", "Copy to clipboard"))
        btn_copy.clicked.connect(self._copy_result)
        btn_export = PushButton(tr("导出 TXT", "Export TXT"))
        btn_export.clicked.connect(self._export_txt)
        head.addWidget(btn_copy)
        head.addWidget(btn_export)
        self.result_card.add_layout(head)
        self.txt_result = TextEdit()
        self.txt_result.setReadOnly(True)
        self.txt_result.setMinimumHeight(120)
        self.txt_result.setPlaceholderText(
            tr("识别完成后在此显示文字…", "Recognized text will show here…"))
        from gui_qt.components import design_system as _ds
        _ds.apply_text_edit_style(self.txt_result)
        self.result_card.add_widget(self.txt_result)
        lay.addWidget(self.result_card)

        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        lay.addWidget(self.out_row)

        self.action_bar = ActionBar(tr("开始识别", "OCR"))
        lay.addWidget(self.action_bar)

        self._wire_tasks()
        self._on_batch_changed(False)  # 初始化显示状态

    def _on_batch_changed(self, checked):
        """批量模式切换时更新UI。"""
        self.result_card.setVisible(not checked)

    # ── 结果操作 ─────────────────────────────────
    def _copy_result(self):
        text = self.txt_result.toPlainText().strip()
        if text:
            QGuiApplication.clipboard().setText(text)
            toast.show_success(self, tr("已复制到剪贴板", "Copied to clipboard"))

    def _export_txt(self):
        text = self.txt_result.toPlainText().strip()
        if not text:
            toast.show_warning(self, tr("暂无识别结果", "No recognized text yet"))
            return
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, tr("导出识别结果", "Export result"), "ocr_result.txt",
            tr("文本文件 (*.txt)", "Text files (*.txt)"))
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                toast.show_success(self, tr("已导出至：{}", "Exported to: {}")
                                   .format(os.path.basename(path)))
            except OSError as e:
                toast.show_error(self, tr("导出失败：{}", "Export failed: {}")
                                 .format(e))

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "lang": self.cb_lang.currentText(),
            "export_fmt": "docx" if self.cb_export.currentIndex() == 1 else "txt",
            "batch_mode": self.sw_batch.isChecked(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return self.collect_params()

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("lang") in OCR_LANGS:
            self.cb_lang.setCurrentText(prefs["lang"])
        if prefs.get("export_fmt") == "docx":
            self.cb_export.setCurrentIndex(1)
        if "batch_mode" in prefs:
            self.sw_batch.setChecked(bool(prefs["batch_mode"]))
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        from core.ocr_batch import ocr_file_to_txt
        return ocr_file_to_txt(task.file_path, task.output_path,
                               lang=task.params.get("lang", "chi_sim+eng"),
                               progress_cb=prog)

    def _make_task(self, f):
        params = self.collect_params()
        out_dir = self.out_row.resolve_dir(f)
        out_path = tm.make_output_path(f, out_dir, ".txt")
        return dict(
            name=f"{tr('OCR识别', 'OCR')} - {os.path.basename(f)}",
            task_type="ocr", file_path=f, output_path=out_path,
            params=params, runner=self._runner,
            history_type=tr("OCR 识别", "OCR"), history_target=params["lang"],
            need_ffmpeg=False)

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要识别的图片或PDF", "Add images or PDFs to recognize first")

    # ── 状态联动：成功后回填结果文本区 ──────────
    def _on_state(self, task_id, state):
        task = self.services.task_manager.get_task(task_id)
        if (task and task.task_type == "ocr" and state == tm.SUCCESS
                and os.path.isfile(task.output_path)
                and not task.params.get("batch_mode", False)):
            try:
                with open(task.output_path, "r", encoding="utf-8") as f:
                    self.txt_result.setPlainText(f.read())
            except OSError:
                pass
        super()._on_state(task_id, state)
