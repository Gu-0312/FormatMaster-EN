# -*- coding: utf-8 -*-
"""id_photo_panel — 证件照换底色面板。

把照片背景一键替换为红/蓝/白标准证件照底色（core.id_photo 色度键算法），
适合求职简历、证件办理等场景。
"""
import os

from qfluentwidgets import CheckBox, ComboBox, FluentIcon

from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".heic", ".heif"}
BG_VALUES = [tr("蓝底", "Blue"), tr("红底", "Red"), tr("白底", "White")]


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

        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        lay.addWidget(self.out_row)

        self.action_bar = ActionBar(tr("开始处理", "Start"))
        lay.addWidget(self.action_bar)

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
