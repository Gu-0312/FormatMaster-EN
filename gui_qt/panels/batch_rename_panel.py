# -*- coding: utf-8 -*-
"""batch_rename_panel — 批量重命名面板。

基于 core/tools.build_rename_plan（模板占位符 {n}/{name}/{ext}/{date}/
{time}/{folder} + 查找替换 + 正则替换 + 大小写转换）。
支持「重命名预览」：执行前先看新旧文件名对照。
即时执行（非队列任务），完成后刷新文件列表。
"""
import os

from PySide6.QtWidgets import (QHBoxLayout, QTableWidget, QTableWidgetItem)
from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon, LineEdit,
                            PrimaryPushButton, PushButton)

from gui_qt.components import toast
from gui_qt.i18n import tr
from gui_qt.components.form_widgets import FormGrid, FormSection
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.widgets import FileListCard

CASE_VALUES = [tr("不转换", "Keep"), tr("大写", "UPPER"),
               tr("小写", "lower"), tr("首字母大写", "Title")]


class BatchRenamePanelPage(BaseQtPanel):
    """批量重命名页。"""

    panel_key = "batch_rename"

    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("批量重命名", "Batch Rename")))
        lay.addWidget(CaptionLabel(
            tr("占位符：{n} 序号 · {name} 原名 · {ext} 扩展名 · ", "Placeholders: {n} number · {name} original · {ext} ext · ")
            + tr("{date} 日期 · {time} 时间 · {folder} 文件夹", "{date} date · {time} time · {folder} folder")))

        self.file_card = FileListCard(tr("文件列表", "Files"), file_exts=None)
        lay.addWidget(self.file_card)

        lay.addWidget(self._build_params_card())

        # 预览表格（新旧文件名对照）
        self.preview_table = QTableWidget(0, 2, self)
        self.preview_table.setHorizontalHeaderLabels(
            [tr("原文件名", "Original"), tr("新文件名", "New")])
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        self.preview_table.setColumnWidth(0, 300)
        self.preview_table.setMaximumHeight(220)
        self.preview_table.verticalHeader().setVisible(False)
        self.preview_table.setAlternatingRowColors(True)
        lay.addWidget(self.preview_table)

        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_preview = PushButton(
            FluentIcon.SEARCH, tr("重命名预览", "Preview"))
        self.btn_preview.clicked.connect(self._preview)
        row.addWidget(self.btn_preview)
        self.btn_go = PrimaryPushButton(FluentIcon.EDIT, tr("开始重命名", "Rename"))
        self.btn_go.clicked.connect(self._run)
        row.addWidget(self.btn_go)
        lay.addLayout(row)

    def _build_params_card(self):
        sec = FormSection(tr("重命名规则", "Rename Rule"), FluentIcon.EDIT)
        g = FormGrid(columns=2)
        self.ed_pattern = LineEdit()
        self.ed_pattern.setText(tr("文件_{n:03d}", "File_{n:03d}"))
        g.add_field(tr("命名模板", "Name template"), self.ed_pattern,
                    hint=tr("示例：照片_{n:03d} → 照片_001", "Example: Photo_{n:03d} → Photo_001"))
        self.ed_start = LineEdit()
        self.ed_start.setText("1")
        g.add_field(tr("开始序号", "Start number"), self.ed_start, hint="{n}")
        self.ed_search = LineEdit()
        self.ed_search.setPlaceholderText(tr("留空跳过", "blank to skip"))
        g.add_field(tr("查找文本", "Find text"), self.ed_search)
        self.ed_replace = LineEdit()
        self.ed_replace.setPlaceholderText(tr("留空表示删除", "blank = delete"))
        g.add_field(tr("替换为", "Replace with"), self.ed_replace)
        self.ed_regex = LineEdit()
        self.ed_regex.setPlaceholderText(tr(r"如 \s+ 或 ^IMG_", r"e.g. \s+ or ^IMG_"))
        g.add_field(tr("正则查找", "Regex find"), self.ed_regex,
                    hint=tr("按正则匹配替换（在查找替换之后执行）", "Applied after find/replace"))
        self.ed_regex_rep = LineEdit()
        self.ed_regex_rep.setPlaceholderText(tr("留空表示删除", "blank = delete"))
        g.add_field(tr("正则替换为", "Regex replace"), self.ed_regex_rep)
        self.cb_case = ComboBox()
        self.cb_case.addItems(CASE_VALUES)
        g.add_field(tr("大小写", "Case"), self.cb_case)
        sec.add_form(g)
        return sec

    def _rule_args(self):
        """收集当前规则参数（不含文件列表）。"""
        try:
            start = int(self.ed_start.text() or "1")
        except ValueError:
            start = 1
        case_map = {CASE_VALUES[0]: "none", CASE_VALUES[1]: "upper",
                    CASE_VALUES[2]: "lower", CASE_VALUES[3]: "title"}
        return dict(
            start_num=start,
            search_text=self.ed_search.text(),
            replace_text=self.ed_replace.text(),
            case=case_map.get(self.cb_case.currentText(), "none"),
            regex_pattern=self.ed_regex.text(),
            regex_replace=self.ed_regex_rep.text())

    def _plan(self):
        """计算重命名方案；返回 (plan, None) 或 (None, 错误消息)。"""
        files = self.file_card.files()
        if not files:
            return None, tr("请先添加要重命名的文件", "Add files first")
        pattern = self.ed_pattern.text().strip()
        if not pattern:
            return None, tr("请填写命名模板", "Fill in the name template")
        from core.tools import build_rename_plan
        try:
            plan = build_rename_plan(files, pattern, **_rule_args(self))
        except Exception as exc:  # noqa: BLE001 - 正则非法等
            return None, tr("规则错误：{}", "Rule error: {}").format(exc)
        return plan, None

    def _preview(self):
        plan, err = self._plan()
        if err:
            toast.show_warning(self, err)
            return
        self.preview_table.setRowCount(0)
        changed = 0
        for i, (src, new_name, _new_path) in enumerate(plan):
            old = os.path.basename(src)
            if new_name != old:
                changed += 1
            self.preview_table.insertRow(i)
            self.preview_table.setItem(i, 0, QTableWidgetItem(old))
            self.preview_table.setItem(i, 1, QTableWidgetItem(new_name))
        toast.show_info(
            self, tr("预览：{} 个文件将改名（共 {} 个）",
                     "Preview: {} will be renamed (of {})")
            .format(changed, len(plan)))

    def _run(self):
        plan, err = self._plan()
        if err:
            toast.show_warning(self, err)
            return
        from core.tools import batch_rename
        ok = batch_rename(
            [src for src, _n, _p in plan],
            self.ed_pattern.text().strip(), **_rule_args(self))
        if ok:
            toast.show_success(self, tr("已重命名 {} 个文件", "Renamed {} files").format(len(ok)))
        else:
            toast.show_error(self, tr("重命名失败：请检查模板与文件名冲突", "Rename failed: check template or filename conflicts"))
        self.preview_table.setRowCount(0)
        # 刷新列表（重命名后路径已变）
        self.file_card.clear_files()

    def collect_prefs(self) -> dict:
        """记忆命名模板/序号/查找替换/正则/大小写，重进面板自动恢复。"""
        return {"pattern": self.ed_pattern.text(),
                "start": self.ed_start.text(),
                "search": self.ed_search.text(),
                "replace": self.ed_replace.text(),
                "regex": self.ed_regex.text(),
                "regex_rep": self.ed_regex_rep.text(),
                "case": self.cb_case.currentIndex()}

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        for k in ("pattern", "start", "search", "replace", "regex", "regex_rep"):
            v = prefs.get(k)
            if v is not None:
                getattr(self, f"ed_{k}").setText(v)
        ci = prefs.get("case")
        if isinstance(ci, int) and 0 <= ci < len(CASE_VALUES):
            self.cb_case.setCurrentIndex(ci)
