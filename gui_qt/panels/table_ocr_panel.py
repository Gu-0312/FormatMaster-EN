"""table_ocr_panel — 表格识别面板（图片 → CSV / Excel）。

基于 core.table_recognizer（RapidOCR 文字 + 位置聚类成表）。
"""
import os

from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon)

from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.components.form_widgets import FormGrid, FormSection
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}


class TableOcrPanelPage(BaseQtPanel, TaskPanelMixin):
    """表格识别页。"""

    panel_key = "table_ocr"

    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("表格识别", "Table OCR")))
        lay.addWidget(CaptionLabel(
            tr("识别图片中的表格结构并输出为 CSV / Excel（本地 RapidOCR）", "Recognize tables in images and export CSV / Excel (local RapidOCR)")))

        self.file_card = FileListCard(tr("文件列表", "Files"), file_exts=IMAGE_EXTS)
        lay.addWidget(self.file_card)
        self.file_card.set_target_fmt(tr("表格识别", "Table OCR"))

        lay.addWidget(self._build_params_card())

        from gui_qt.components.form_widgets import FormSection
        out_card = FormSection(tr("输出目录", "Output folder"), FluentIcon.FOLDER)
        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        out_card.add_widget(self.out_row)
        lay.addWidget(out_card)

        self.action_bar = ActionBar(tr("开始识别", "OCR"))
        lay.addWidget(self.action_bar)

        self._wire_tasks()

    def _build_params_card(self):
        sec = FormSection(tr("识别设置", "OCR Settings"), FluentIcon.SETTING)
        g = FormGrid(columns=1)
        self.cb_fmt = ComboBox()
        self.cb_fmt.addItems(["CSV", "Excel (XLSX)"])
        self.cb_fmt.setCurrentText("CSV")
        self.cb_fmt.currentTextChanged.connect(self._on_fmt_changed)
        g.add_field(tr("输出格式", "Output format"), self.cb_fmt)
        self.cb_chart = ComboBox()
        self.cb_chart.addItems([tr("不生成图表", "No chart"),
                                tr("柱状图", "Bar chart"),
                                tr("折线图", "Line chart"),
                                tr("饼图", "Pie chart")])
        self.cb_chart.setCurrentText(tr("不生成图表", "No chart"))
        self.cb_chart.setEnabled(False)
        g.add_field(tr("生成图表(仅Excel)", "Chart (Excel only)"), self.cb_chart,
                    hint=tr("首行为表头、首列为分类、其余为数值", "Header = row 1, categories = col 1"))
        sec.add_form(g)
        return sec

    def _on_fmt_changed(self, text):
        """图表仅 Excel 模式可用。"""
        self.cb_chart.setEnabled(text.startswith("Excel"))

    def _start(self):
        self._submit_files()

    def _empty_hint(self) -> str:
        return tr("请先添加要识别的图片", "Add images to recognize first")

    def _make_task(self, f: str) -> dict:
        ext = ".xlsx" if self.cb_fmt.currentText().startswith("Excel") else ".csv"
        chart_map = {tr("柱状图", "Bar chart"): "bar",
                     tr("折线图", "Line chart"): "line",
                     tr("饼图", "Pie chart"): "pie"}
        params = {"chart_type": chart_map.get(self.cb_chart.currentText(), None)}
        out = tm.make_output_path(f, self.out_row.path(), ext)
        return dict(name=tr("表格识别", "Table OCR"), task_type="table_ocr",
                    file_path=f, output_path=out, params=params,
                    runner=self._runner,
                    history_type=tr("表格识别", "Table OCR"), history_target=ext[1:].upper(),
                    need_ffmpeg=False)

    def _runner(self, task, prog):
        from core import table_recognizer
        return table_recognizer.recognize_table(
            task.file_path, task.output_path, progress_cb=prog,
            chart_type=task.params.get("chart_type"))

    def collect_prefs(self) -> dict:
        """记忆输出格式/图表选择，重进面板自动恢复。"""
        return {"fmt": self.cb_fmt.currentIndex(),
                "chart": self.cb_chart.currentIndex()}

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        for k in ("fmt", "chart"):
            idx = prefs.get(k)
            cb = getattr(self, f"cb_{k}")
            if isinstance(idx, int) and 0 <= idx < cb.count():
                cb.setCurrentIndex(idx)

