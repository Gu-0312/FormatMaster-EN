# -*- coding: utf-8 -*-
"""audio_norm_panel — 批量音频标准化面板。

对多个音频统一响度（EBU R128 loudnorm，两遍测量应用），
可选目标采样率/声道。任务经 TaskManager 通用链路批量执行。
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon)

from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.components import toast
from gui_qt.components.form_widgets import FormGrid, FormSection
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow
from utils.config import SUPPORTED_AUDIO

from core.audio_norm import make_runner, normalize_audio

AUDIO_EXTS = set(SUPPORTED_AUDIO.values())

# 目标响度（显示名 → 值）
LUFS_VALUES = [tr("-14 LUFS（推荐，流媒体常用）", "-14 LUFS (recommended)"),
               "-16 LUFS", "-18 LUFS", "-23 LUFS（广播标准）"]
LUFS_KEYS = [-14, -16, -18, -23]

# 采样率（显示名 → None/数值）
SR_VALUES = [tr("保持原始", "Original"), "44100 Hz", "48000 Hz"]
SR_KEYS = [None, 44100, 48000]

# 声道（显示名 → None/数值）
CH_VALUES = [tr("保持原始", "Original"),
             tr("单声道", "Mono"),
             tr("立体声", "Stereo")]
CH_KEYS = [None, 1, 2]


class AudioNormPanelPage(BaseQtPanel, TaskPanelMixin):
    """音频标准化页。"""

    panel_key = "audio_norm"
    need_ffmpeg = True

    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("音频标准化", "Audio Normalize")))
        lay.addWidget(CaptionLabel(
            tr("统一多个音频的响度到目标 LUFS（EBU R128），可选目标采样率与声道",
               "Normalize loudness to target LUFS (EBU R128)")))

        self.file_card = FileListCard(tr("音频列表", "Audio files"),
                                      file_exts=AUDIO_EXTS)
        lay.addWidget(self.file_card)
        self.file_card.set_target_fmt(tr("标准化", "Normalize"))

        sec = FormSection(tr("标准化参数", "Normalize settings"), FluentIcon.SETTING)
        grid = FormGrid(columns=3)

        def _combo(items, default):
            cb = ComboBox()
            cb.addItems(items)
            cb.setCurrentText(default)
            return cb

        self.cb_lufs = grid.add_field(
            tr("目标响度", "Target LUFS"),
            _combo(LUFS_VALUES, LUFS_VALUES[0]),
            hint=tr("流媒体平台通常 -14 LUFS；广播标准 -23 LUFS",
                    "Streaming platforms usually use -14 LUFS"))
        self.cb_sr = grid.add_field(
            tr("采样率", "Sample rate"), _combo(SR_VALUES, SR_VALUES[0]),
            hint=tr("44100/48000 Hz 为 CD/视频常见采样率",
                    "44100/48000 Hz are common for CD/video"))
        self.cb_ch = grid.add_field(
            tr("声道", "Channels"), _combo(CH_VALUES, CH_VALUES[0]),
            hint=tr("单声道可减小体积；立体声兼容性更好",
                    "Mono is smaller; stereo is more compatible"))
        sec.add_form(grid)
        lay.addWidget(sec)

        out_card = FormSection(tr("输出目录", "Output folder"), FluentIcon.FOLDER)
        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        out_card.add_widget(self.out_row)
        lay.addWidget(out_card)

        self.action_bar = ActionBar(tr("开始标准化", "Normalize"))
        lay.addWidget(self.action_bar)
        self._wire_tasks()

        mgr = self.services.task_manager
        mgr.register_runner("audio_norm", make_runner)

    # ── 参数/偏好 ────────────────────────────────
    def _key(self, display_list, key_list, current):
        idx = display_list.index(current) if current in display_list else 0
        return key_list[idx]

    def collect_params(self) -> dict:
        return {
            "target_lufs": self._key(LUFS_VALUES, LUFS_KEYS,
                                     self.cb_lufs.currentText()),
            "sample_rate": self._key(SR_VALUES, SR_KEYS,
                                     self.cb_sr.currentText()),
            "channels": self._key(CH_VALUES, CH_KEYS,
                                  self.cb_ch.currentText()),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return {
            "lufs": self.cb_lufs.currentText(),
            "sr": self.cb_sr.currentText(),
            "ch": self.cb_ch.currentText(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("lufs") in LUFS_VALUES:
            self.cb_lufs.setCurrentText(prefs["lufs"])
        if prefs.get("sr") in SR_VALUES:
            self.cb_sr.setCurrentText(prefs["sr"])
        if prefs.get("ch") in CH_VALUES:
            self.cb_ch.setCurrentText(prefs["ch"])
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务 ─────────────────────────────────────
    def _runner(self, task, prog):
        p = task.params
        return normalize_audio(
            task.file_path, task.output_path,
            target_lufs=p.get("target_lufs", -14),
            sample_rate=p.get("sample_rate"),
            channels=p.get("channels"),
            progress_cb=prog,
            cancel_check=lambda: task.state == tm.CANCELLED)

    def _make_task(self, f):
        params = self.collect_params()
        out_dir = self.out_row.resolve_dir(f)
        src_ext = os.path.splitext(f)[1].lower()
        # 输出保持源格式（wav/flac 无损保留，其余按原格式输出）
        out_path = tm.make_output_path(f, out_dir, src_ext)
        return dict(
            name=f"{tr('音频标准化', 'Audio Normalize')} - {os.path.basename(f)}",
            task_type="audio_norm", file_path=f, output_path=out_path,
            params=params, runner=self._runner,
            history_type=tr("音频标准化", "Audio Normalize"),
            history_target=f"{params.get('target_lufs', -14)} LUFS",
            runner_key="audio_norm")

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要标准化的音频文件", "Add audio files to normalize first")
