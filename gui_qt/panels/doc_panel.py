"""doc_panel — 文档转换面板（阶段2 迁移自 gui/panels/doc_panel.py）。

PDF · Word · Excel · PPT · WPS · TXT · 图片 · Markdown · EPUB · RTF · ODT
互转。「检测格式」按钮按首个文件扩展名查 DOC_CONVERSION_MAP 填充目标格式；
任务经 TaskManager 通用链路执行 core.doc_converter（不依赖 FFmpeg）。
"""
import os

from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import (FluentIcon, CaptionLabel, ComboBox, PushButton)

from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.components import toast
from gui_qt.components.form_widgets import FormGrid, FormSection
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow
from utils.config import DOC_CONVERSION_MAP, DOC_READ_FORMATS

DOC_EXTS = set(DOC_READ_FORMATS.keys())
PLACEHOLDER = tr("请先添加文件", "Add files first")


class DocPanelPage(BaseQtPanel, TaskPanelMixin):
    """文档转换页。"""

    panel_key = "document"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("文档转换", "Document convert")))
        lay.addWidget(CaptionLabel(
            tr("PDF · Word · Excel · PPT · WPS · TXT · 图片 · Markdown · EPUB · RTF · ODT", "PDF · Word · Excel · PPT · WPS · TXT · Image · Markdown · EPUB · RTF · ODT")))

        self.file_card = FileListCard(tr("文件列表", "Files"), file_exts=DOC_EXTS)
        lay.addWidget(self.file_card)

        # 转换设置
        sec = FormSection(tr("转换设置", "Convert settings"), FluentIcon.SETTING)
        sec.add_widget(CaptionLabel(
            tr("添加文件后点击「检测格式」，系统将自动列出可转换的目标格式", "Click \"Detect format\" after adding files to list convertible targets")))

        grid = FormGrid(columns=1)
        self.cb_tgt = ComboBox()
        self.cb_tgt.addItems([PLACEHOLDER])
        self.cb_tgt.setCurrentIndex(0)
        self.cb_tgt.setMinimumWidth(220)
        self.cb_tgt = grid.add_field(
            tr("目标格式", "Target format"), self.cb_tgt,
            hint=tr("点击「检测格式」后自动列出可转换的目标格式", "Click \"Detect format\" to list convertible targets"))
        sec.add_form(grid)

        # 检测按钮 + 状态提示
        self.btn_detect = PushButton(tr("检测格式", "Detect format"))
        self.detect_label = CaptionLabel("")
        act_row = QHBoxLayout()
        act_row.setSpacing(8)
        act_row.addWidget(self.btn_detect)
        act_row.addWidget(self.detect_label)
        act_row.addStretch(1)
        sec.add_layout(act_row)
        lay.addWidget(sec)

        # 输出目录
        out_card = FormSection(tr("输出目录", "Output folder"), FluentIcon.FOLDER)
        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        out_card.add_widget(self.out_row)
        lay.addWidget(out_card)

        self.action_bar = ActionBar(tr("开始转换", "Convert"))
        lay.addWidget(self.action_bar)

        self.btn_detect.clicked.connect(self._detect)
        self.file_card.files_changed.connect(self._on_files_changed)
        self._wire_tasks()

    # ── 格式检测（对应 tkinter 版 main._detect）──
    def _detect(self):
        files = self.file_card.files()
        if not files:
            toast.show_info(self, tr("请先添加文档文件", "Add document files first"))
            return
        ext = os.path.splitext(files[0])[1].lower()
        src = DOC_READ_FORMATS.get(ext)
        if not src:
            toast.show_warning(self, tr("不支持的格式：{}", "Unsupported format: {}").format(ext))
            return
        tgts = DOC_CONVERSION_MAP.get(src, [])
        if not tgts:
            toast.show_info(self, f"暂不支持从 {src} 转换")
            return
        names = [f"{t}（{DOC_READ_FORMATS.get(t, t)}）" for t in tgts]
        self.cb_tgt.clear()
        self.cb_tgt.addItems(names)
        self.cb_tgt.setCurrentIndex(0)
        self.file_card.set_target_fmt(names[0].split("（")[0].lstrip(".").upper())
        self.detect_label.setText(tr("已识别 {} · {} 个文件", "Detected {} · {} files").format(src, len(files)))

    def _on_files_changed(self):
        # 文件变化后目标格式需重新检测（与 tkinter 版语义一致）
        self.cb_tgt.clear()
        self.cb_tgt.addItems([PLACEHOLDER])
        self.cb_tgt.setCurrentIndex(0)
        self.detect_label.setText("")
        self.file_card.set_target_fmt("")

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "target": self.cb_tgt.currentText(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        # 与 tkinter 版一致：不持久化 target（需重新检测）
        return {
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        return self.services.doc_conv.convert(
            task.file_path, task.output_path, prog)

    def _make_task(self, f):
        target = self.cb_tgt.currentText()
        if target == PLACEHOLDER:
            toast.show_warning(self, tr("请先点击「检测格式」选择目标格式", "Click \"Detect format\" to choose target format first"))
            return None
        ext = target.split("（")[0].strip()
        params = self.collect_params()
        out_dir = self.out_row.resolve_dir(f)
        out_path = tm.make_output_path(f, out_dir, ext)
        return dict(
            name=f"{tr('文档转换', 'Doc Convert')} - {os.path.basename(f)}",
            task_type="doc", file_path=f, output_path=out_path,
            params=params, runner=self._runner,
            canceller=self.services.doc_conv.cancel,
            history_type=tr("文档转换", "Document Convert"), history_target=ext.lstrip(".").upper(),
            need_ffmpeg=False)

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要转换的文档文件", "Add documents to convert first")
