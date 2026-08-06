"""ocr_panel — OCR 文字识别面板（阶段2 迁移自 gui/panels/ocr_panel.py）。

从图片或 PDF 中识别文字，支持批量处理。任务经 TaskManager 通用链路
执行 core.ocr_tool.ocr_image（rapidocr，不依赖 FFmpeg），识别结果
写入同名 .txt 并回填到结果文本区。
"""
import os

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import (FluentIcon, CaptionLabel, ComboBox, PushButton,
                            TextEdit)

from gui_qt.i18n import tr
from gui_qt.components import toast
from gui_qt.components.form_widgets import FormSection
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt import task_manager as tm
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

# 预置值（与 tkinter 版 ocr_panel 一致）
OCR_LANGS = ["chi_sim+eng", "chi_sim", "eng", "jpn", "kor",
             "chi_tra+eng", "chi_tra", "eng+chi_sim"]

OCR_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".pdf"}


class OcrPanelPage(BaseQtPanel, TaskPanelMixin):
    """OCR 识别页。"""

    panel_key = "ocr"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("OCR 文字识别", "OCR")))
        lay.addWidget(CaptionLabel(tr("从图片或PDF中识别文字，支持批量处理", "OCR text from images or PDF, batch supported")))

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
        row.addWidget(CaptionLabel(tr("chi_sim=简体中文  eng=英文  jpn=日文  kor=韩文", "chi_sim=Chinese  eng=English  jpn=Japanese  kor=Korean")))
        row.addStretch(1)
        sec.add_layout(row)
        lay.addWidget(sec)

        # 识别结果区
        res_card = FormSection(tr("识别结果", "Result"), FluentIcon.INFO)
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addStretch(1)
        btn_copy = PushButton(tr("复制到剪贴板", "Copy to clipboard"))
        btn_copy.clicked.connect(self._copy_result)
        btn_export = PushButton(tr("导出 TXT", "Export TXT"))
        btn_export.clicked.connect(self._export_txt)
        head.addWidget(btn_copy)
        head.addWidget(btn_export)
        res_card.add_layout(head)
        self.txt_result = TextEdit()
        self.txt_result.setReadOnly(True)
        self.txt_result.setMinimumHeight(120)
        self.txt_result.setPlaceholderText(tr("识别完成后在此显示文字…", "Recognized text will show here…"))
        from gui_qt.components import design_system as _ds
        _ds.apply_text_edit_style(self.txt_result)
        res_card.add_widget(self.txt_result)
        lay.addWidget(res_card)

        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        lay.addWidget(self.out_row)

        self.action_bar = ActionBar(tr("开始识别", "OCR"))
        lay.addWidget(self.action_bar)

        self._wire_tasks()

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
            self, tr("导出识别结果", "Export result"), "ocr_result.txt", tr("文本文件 (*.txt)", "Text files (*.txt)"))
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                toast.show_success(self, tr("已导出至：{}", "Exported to: {}").format(os.path.basename(path)))
            except OSError as e:
                toast.show_error(self, tr("导出失败：{}", "Export failed: {}").format(e))

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "lang": self.cb_lang.currentText(),
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
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        from core.ocr_tool import ocr_image
        text = ocr_image(task.file_path, task.params.get("lang", "chi_sim+eng"), prog)
        if not text:
            task.error = tr("未识别到文字", "No text recognized")
            return False
        try:
            with open(task.output_path, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError:
            task.error = tr("结果保存失败", "Failed to save result")
            return False
        return True

    def _make_task(self, f):
        params = self.collect_params()
        nm = os.path.splitext(os.path.basename(f))[0]
        out_dir = self.out_row.resolve_dir(f)
        out_path = os.path.join(out_dir, nm + ".txt")
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
                and os.path.isfile(task.output_path)):
            try:
                with open(task.output_path, "r", encoding="utf-8") as f:
                    self.txt_result.setPlainText(f.read())
            except OSError:
                pass
        super()._on_state(task_id, state)
