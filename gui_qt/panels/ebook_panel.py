# -*- coding: utf-8 -*-
"""ebook_panel — 电子书互转面板。

EPUB / MOBI / PRC / AZW / AZW3 / TXT / HTML 互转（core.ebook_converter）。
MOBI/AZW3 目标格式需要系统安装 Calibre（自动探测 ebook-convert）；
EPUB/TXT/HTML 互转完全离线、零依赖。
"""
import os

from qfluentwidgets import CaptionLabel, ComboBox, FluentIcon

from core.ebook_converter import SRC_EXTS, convert_ebook
from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

DST_VALUES = ["EPUB", "MOBI", "AZW3", "TXT", "HTML"]
# 目标扩展名映射（HTML 源允许 .htm）
_DST_EXT = {"EPUB": ".epub", "MOBI": ".mobi", "AZW3": ".azw3",
            "TXT": ".txt", "HTML": ".html"}


class EbookPanelPage(BaseQtPanel, TaskPanelMixin):
    """电子书互转页。"""

    panel_key = "ebook"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("电子书互转", "Ebook convert")))
        lay.addWidget(self.make_subtitle(
            tr("EPUB / MOBI / TXT / HTML 互转；转 MOBI/AZW3 需安装 Calibre",
               "EPUB / MOBI / TXT / HTML convert; MOBI/AZW3 needs Calibre")))

        self.file_card = FileListCard(tr("文件列表", "Files"), file_exts=SRC_EXTS)
        lay.addWidget(self.file_card)

        from gui_qt.components.form_widgets import FormSection, FormGrid
        sec = FormSection(tr("转换设置", "Convert settings"), FluentIcon.MOVIE)
        grid = FormGrid(columns=1)
        self.cb_dst = ComboBox()
        self.cb_dst.addItems(DST_VALUES)
        self.cb_dst.setCurrentText("EPUB")
        grid.add_field(tr("目标格式", "Target format"), self.cb_dst,
                       hint=tr("EPUB/TXT/HTML 离线转换；MOBI/AZW3 自动调用 Calibre",
                               "EPUB/TXT/HTML offline; MOBI/AZW3 via Calibre"))
        sec.add_form(grid)
        lay.addWidget(sec)

        out_card = FormSection(tr("输出目录", "Output folder"), FluentIcon.FOLDER)
        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        out_card.add_widget(self.out_row)
        lay.addWidget(out_card)

        self.action_bar = ActionBar(tr("开始转换", "Convert"))
        lay.addWidget(self.action_bar)

        self._wire_tasks()

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "target": self.cb_dst.currentText(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return self.collect_params()

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("target") in DST_VALUES:
            self.cb_dst.setCurrentText(prefs["target"])
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        p = task.params
        dst_ext = _DST_EXT.get(p.get("target", "EPUB"), ".epub")
        # 目标文件名：同名不同扩展名（mobi→epub 等）
        out = task.output_path
        ok, msg = convert_ebook(task.file_path, out, prog)
        if not ok:
            task.error = msg or tr("转换失败", "Convert failed")
            return False
        return True

    def _make_task(self, f):
        params = self.collect_params()
        dst_ext = _DST_EXT.get(params.get("target", "EPUB"), ".epub")
        out_dir = self.out_row.resolve_dir(f)
        out_path = tm.make_output_path(f, out_dir, dst_ext)
        return dict(
            name=f"{tr('电子书转换', 'Ebook convert')} - {os.path.basename(f)}",
            task_type="ebook", file_path=f, output_path=out_path,
            params=params, runner=self._runner,
            history_type=tr("电子书互转", "Ebook convert"),
            history_target=params.get("target", "EPUB"),
            need_ffmpeg=False)

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要转换的电子书文件", "Add ebook files first")
