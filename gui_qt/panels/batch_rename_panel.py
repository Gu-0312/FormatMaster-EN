"""batch_rename_panel — 批量重命名面板。

基于 core/tools.batch_rename（模板占位符 {n}/{name}/{ext}/{date}/{time}/{folder}）。
即时执行（非队列任务），完成后刷新文件列表。
"""
import os

from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import (CaptionLabel, FluentIcon, LineEdit, PrimaryPushButton)

from gui_qt.components import toast
from gui_qt.i18n import tr
from gui_qt.components.form_widgets import FormGrid, FormSection
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.widgets import FileListCard


class BatchRenamePanelPage(BaseQtPanel):
    """批量重命名页。"""

    panel_key = "batch_rename"

    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("批量重命名", "Batch Rename")))
        lay.addWidget(CaptionLabel(
            "占位符：{n} 序号 · {name} 原名 · {ext} 扩展名 · "
            "{date} 日期 · {time} 时间 · {folder} 文件夹"))

        self.file_card = FileListCard(tr("文件列表", "Files"), file_exts=None)
        lay.addWidget(self.file_card)

        lay.addWidget(self._build_params_card())

        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_go = PrimaryPushButton(FluentIcon.EDIT, tr("开始重命名", "Rename"))
        self.btn_go.clicked.connect(self._run)
        row.addWidget(self.btn_go)
        lay.addLayout(row)

    def _build_params_card(self):
        sec = FormSection(tr("重命名规则", "Rename Rule"), FluentIcon.EDIT)
        g = FormGrid(columns=2)
        self.ed_pattern = LineEdit()
        self.ed_pattern.setText("文件_{n:03d}")
        g.add_field(tr("命名模板", "Name template"), self.ed_pattern,
                    hint="示例：照片_{n:03d} → 照片_001")
        self.ed_start = LineEdit()
        self.ed_start.setText("1")
        g.add_field(tr("开始序号", "Start number"), self.ed_start, hint="{n}")
        self.ed_search = LineEdit()
        self.ed_search.setPlaceholderText("留空跳过")
        g.add_field(tr("查找文本", "Find text"), self.ed_search)
        self.ed_replace = LineEdit()
        self.ed_replace.setPlaceholderText("留空表示删除")
        g.add_field(tr("替换为", "Replace with"), self.ed_replace)
        sec.add_form(g)
        return sec

    def _run(self):
        files = self.file_card.files()
        if not files:
            toast.show_warning(self, tr("请先添加要重命名的文件", "Add files first"))
            return
        pattern = self.ed_pattern.text().strip()
        if not pattern:
            toast.show_warning(self, "请填写命名模板")
            return
        try:
            start = int(self.ed_start.text() or "1")
        except ValueError:
            start = 1
        search = self.ed_search.text()
        replace = self.ed_replace.text()

        from core.tools import batch_rename
        ok = batch_rename(files, pattern, start_num=start,
                          search_text=search, replace_text=replace)
        if ok:
            toast.show_success(self, f"已重命名 {len(files)} 个文件")
        else:
            toast.show_error(self, "重命名失败：请检查模板与文件名冲突")
        # 刷新列表（重命名后路径已变）
        self.file_card.clear_files()
