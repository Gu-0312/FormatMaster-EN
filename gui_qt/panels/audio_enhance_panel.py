# -*- coding: utf-8 -*-
"""audio_enhance_panel — 音频降噪 / 响度归一化面板。

基于 FFmpeg afftdn（降噪）与 loudnorm（EBU R128 响度归一）滤镜，
适合录播课、播客、录音的后期处理（core.audio_tools）。
"""
import os

from qfluentwidgets import ComboBox, FluentIcon

from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

AUDIO_EXTS = {".mp3", ".wav", ".wma", ".aac", ".flac", ".ogg", ".m4a", ".amr", ".opus"}
MODE_VALUES = [
    tr("降噪", "Denoise"),
    tr("响度归一化", "Normalize loudness"),
    tr("降噪 + 响度归一", "Denoise + Normalize"),
]
STRENGTH_VALUES = ["10", "20", "25", "30", "40"]


class AudioEnhancePanelPage(BaseQtPanel, TaskPanelMixin):
    """音频降噪 / 响度归一化页。"""

    panel_key = "audio_enhance"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("音频增强", "Audio enhance")))
        lay.addWidget(self.make_subtitle(
            tr("降噪与响度归一化，适合录音、播客、录播课后期",
               "Denoise and loudness normalization for recordings, podcasts and lectures")))

        self.file_card = FileListCard(tr("音频列表", "Audio files"), file_exts=AUDIO_EXTS)
        lay.addWidget(self.file_card)

        from gui_qt.components.form_widgets import FormGrid, FormSection
        card = FormSection(tr("增强设置", "Enhance settings"), FluentIcon.SPEAKERS)
        grid = FormGrid(columns=2)

        def _combo(items, default):
            cb = ComboBox()
            cb.addItems(items)
            cb.setCurrentText(default)
            return cb

        self.cb_mode = grid.add_field(
            tr("处理模式", "Mode"), _combo(MODE_VALUES, MODE_VALUES[0]),
            hint=tr("降噪去除环境底噪，响度归一统一音量", "Denoise removes background hiss, normalize evens out volume"))
        self.cb_strength = grid.add_field(
            tr("降噪强度", "Denoise strength"), _combo(STRENGTH_VALUES, "25"),
            hint=tr("越大降噪越强，过大会损伤人声（仅降噪模式）", "Higher removes more noise but may hurt voice (denoise only)"))
        card.add_form(grid)
        lay.addWidget(card)

        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        lay.addWidget(self.out_row)

        self.action_bar = ActionBar(tr("开始处理", "Start"))
        lay.addWidget(self.action_bar)

        self.services.task_manager.register_runner(
            "audio_enhance", lambda task: self._runner)
        self._wire_tasks()

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "mode": self.cb_mode.currentText(),
            "strength": self.cb_strength.currentText(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return self.collect_params()

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("mode") in MODE_VALUES:
            self.cb_mode.setCurrentText(str(prefs["mode"]))
        if prefs.get("strength") in STRENGTH_VALUES:
            self.cb_strength.setCurrentText(str(prefs["strength"]))
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        from core.audio_tools import enhance
        p = task.params
        mode = p.get("mode", MODE_VALUES[0])
        mode_key = "normalize" if mode == MODE_VALUES[1] else (
            "both" if mode == MODE_VALUES[2] else "denoise")
        return enhance(task.file_path, task.output_path, mode_key,
                       int(p.get("strength", 25) or 25), -14, prog)

    def _make_task(self, f):
        params = self.collect_params()
        out_dir = self.out_row.resolve_dir(f)
        out_path = tm.make_output_path(f, out_dir, ".m4a")
        return dict(
            name=f"{tr('音频增强', 'Audio enhance')} - {os.path.basename(f)}",
            task_type="audio_enhance", file_path=f, output_path=out_path,
            params=params, runner=self._runner, runner_key="audio_enhance",
            canceller=None,
            history_type=tr("音频增强", "Audio enhance"), history_target=params["mode"],
            need_ffmpeg=True)

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要处理的音频文件", "Add audio files to process first")
