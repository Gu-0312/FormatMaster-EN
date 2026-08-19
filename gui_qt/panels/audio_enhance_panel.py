# -*- coding: utf-8 -*-
"""audio_enhance_panel — 音频增强面板（降噪/响度/人声伴奏提取/EQ/压限）。

基于 FFmpeg 滤镜（core.audio_tools）：
- 降噪 afftdn、响度 loudnorm（EBU R128）
- 人声/伴奏提取 pan（中置声道原理，非 AI）
- 三段均衡器 equalizer、动态压限 acompressor+alimiter
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon,
                            SegmentedWidget, Slider)

from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow
from gui_qt.components.form_widgets import FormGrid, FormSection

AUDIO_EXTS = {".mp3", ".wav", ".wma", ".aac", ".flac", ".ogg", ".m4a", ".amr", ".opus"}
STRENGTH_VALUES = ["10", "20", "25", "30", "40"]

MODES = [
    ("denoise", tr("降噪", "Denoise")),
    ("normalize", tr("响度归一化", "Normalize loudness")),
    ("both", tr("降噪+响度", "Denoise + Normalize")),
    ("vocal", tr("人声提取", "Extract vocal")),
    ("music", tr("伴奏提取", "Extract music")),
    ("equalizer", tr("均衡器", "Equalizer")),
    ("compress", tr("动态压限", "Compress")),
]


class _SliderRow(QWidget):
    """滑块 + 数值标签行。"""

    def __init__(self, label, lo, hi, default, step=1, fmt="{:.0f}", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.lb = CaptionLabel(label)
        self.sl = Slider(Qt.Horizontal)
        self.sl.setRange(lo * 10, hi * 10)
        self.sl.setValue(int(default * 10))
        self.sl.setSingleStep(int(step * 10))
        self.lb_val = CaptionLabel(fmt.format(default))
        self._fmt = fmt
        self.sl.valueChanged.connect(
            lambda v: self.lb_val.setText(fmt.format(v / 10.0)))
        lay.addWidget(self.lb)
        lay.addWidget(self.sl, 1)
        lay.addWidget(self.lb_val)

    def value(self):
        return self.sl.value() / 10.0


class AudioEnhancePanelPage(BaseQtPanel, TaskPanelMixin):
    """音频增强页。"""

    panel_key = "audio_enhance"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("音频增强", "Audio enhance")))
        lay.addWidget(self.make_subtitle(
            tr("降噪 · 响度 · 人声/伴奏提取 · 均衡器 · 压限",
               "Denoise · Loudness · Vocal/Music · EQ · Compress")))

        self.file_card = FileListCard(tr("音频列表", "Audio files"), file_exts=AUDIO_EXTS)
        lay.addWidget(self.file_card)

        card = FormSection(tr("增强设置", "Enhance settings"), FluentIcon.SPEAKERS)
        # 模式分段选择
        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_row.addWidget(CaptionLabel(tr("处理模式", "Mode")))
        self.sg_mode = SegmentedWidget()
        for key, label in MODES:
            self.sg_mode.addItem(key, label)
        self.sg_mode.setCurrentItem("denoise")
        self.sg_mode.currentItemChanged.connect(
            lambda _k: self._mode_changed())
        mode_row.addWidget(self.sg_mode, 1)
        card.add_layout(mode_row)

        # 降噪强度（denoise / both）
        self.w_strength = QWidget()
        srow = QHBoxLayout(self.w_strength)
        srow.setContentsMargins(0, 0, 0, 0)
        srow.setSpacing(8)
        self.cb_strength = ComboBox()
        self.cb_strength.addItems(STRENGTH_VALUES)
        self.cb_strength.setCurrentText("25")
        srow.addWidget(CaptionLabel(tr("降噪强度", "Denoise strength")))
        srow.addWidget(self.cb_strength)
        srow.addStretch(1)
        card.add_widget(self.w_strength)

        # 均衡器三频段
        self.w_eq = QWidget()
        veq = QVBoxLayout(self.w_eq)
        veq.setContentsMargins(0, 0, 0, 0)
        veq.setSpacing(6)
        self.sl_low = _SliderRow(tr("低频 (200Hz)", "Low (200Hz)"), -12, 12, 0)
        self.sl_mid = _SliderRow(tr("中频 (1kHz)", "Mid (1kHz)"), -12, 12, 0)
        self.sl_high = _SliderRow(tr("高频 (5kHz)", "High (5kHz)"), -12, 12, 0)
        veq.addWidget(self.sl_low)
        veq.addWidget(self.sl_mid)
        veq.addWidget(self.sl_high)
        card.add_widget(self.w_eq)

        # 压限参数
        self.w_comp = QWidget()
        vco = QVBoxLayout(self.w_comp)
        vco.setContentsMargins(0, 0, 0, 0)
        vco.setSpacing(6)
        self.sl_thr = _SliderRow(tr("阈值 dB", "Threshold dB"), -50, -5, -20)
        self.sl_ratio = _SliderRow(tr("压缩比", "Ratio"), 1, 20, 4)
        vco.addWidget(self.sl_thr)
        vco.addWidget(self.sl_ratio)
        card.add_widget(self.w_comp)

        # 人声/伴奏/响度提示
        self.w_hint = QWidget()
        hrow = QHBoxLayout(self.w_hint)
        hrow.setContentsMargins(0, 0, 0, 0)
        self.lb_hint = CaptionLabel("")
        self.lb_hint.setWordWrap(True)
        hrow.addWidget(self.lb_hint)
        card.add_widget(self.w_hint)

        lay.addWidget(card)

        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        lay.addWidget(self.out_row)

        self.action_bar = ActionBar(tr("开始处理", "Start"))
        lay.addWidget(self.action_bar)

        self.services.task_manager.register_runner(
            "audio_enhance", lambda task: self._runner)
        self._wire_tasks()
        self._mode_changed()

    def _mode_changed(self):
        mode = self.sg_mode.currentRouteKey()
        self.w_strength.setVisible(mode in ("denoise", "both"))
        self.w_eq.setVisible(mode == "equalizer")
        self.w_comp.setVisible(mode == "compress")
        hints = {
            "vocal": tr("基于中置声道原理提取人声（非 AI 算法，纯伴奏段会有残留）",
                        "Center-channel vocal extraction (non-AI; music-only parts may bleed)"),
            "music": tr("消除中置人声得到伴奏版（相位抵消法）",
                        "Remove center vocal to get instrumental (phase-cancellation)"),
            "normalize": tr("统一到 -14 LUFS（流媒体常用响度）", "Normalize to -14 LUFS"),
        }
        self.w_hint.setVisible(mode in hints)
        self.lb_hint.setText(hints.get(mode, ""))

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "mode": self.sg_mode.currentRouteKey(),
            "strength": self.cb_strength.currentText(),
            "eq_low": self.sl_low.value(),
            "eq_mid": self.sl_mid.value(),
            "eq_high": self.sl_high.value(),
            "comp_thr": self.sl_thr.value(),
            "comp_ratio": self.sl_ratio.value(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return self.collect_params()

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        mode = prefs.get("mode")
        if mode in dict(MODES):
            self.sg_mode.setCurrentItem(str(mode))
            self._mode_changed()
        if prefs.get("strength") in STRENGTH_VALUES:
            self.cb_strength.setCurrentText(str(prefs["strength"]))
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        from core import audio_tools
        p = task.params
        mode = p.get("mode", "denoise")
        if mode == "normalize":
            return audio_tools.normalize(task.file_path, task.output_path,
                                         -14, prog)
        if mode == "both":
            return audio_tools.enhance(task.file_path, task.output_path,
                                       "both", int(p.get("strength", 25) or 25),
                                       -14, prog)
        if mode == "vocal":
            return audio_tools.extract_vocal(task.file_path, task.output_path,
                                             prog)
        if mode == "music":
            return audio_tools.extract_music(task.file_path, task.output_path,
                                             prog)
        if mode == "equalizer":
            return audio_tools.audio_equalizer(
                task.file_path, task.output_path,
                low=p.get("eq_low", 0), mid=p.get("eq_mid", 0),
                high=p.get("eq_high", 0), progress_cb=prog)
        if mode == "compress":
            return audio_tools.audio_compress(
                task.file_path, task.output_path,
                threshold=p.get("comp_thr", -20), ratio=p.get("comp_ratio", 4),
                progress_cb=prog)
        return audio_tools.denoise(task.file_path, task.output_path,
                                   int(p.get("strength", 25) or 25), prog)

    def _make_task(self, f):
        params = self.collect_params()
        out_dir = self.out_row.resolve_dir(f)
        mode = params["mode"]
        out_ext = ".m4a"
        out_path = tm.make_output_path(f, out_dir, out_ext)
        labels = dict(MODES)
        return dict(
            name=f"{tr('音频增强', 'Audio enhance')} - {os.path.basename(f)}",
            task_type="audio_enhance", file_path=f, output_path=out_path,
            params=params, runner=self._runner, runner_key="audio_enhance",
            canceller=None,
            history_type=tr("音频增强", "Audio enhance"),
            history_target=labels.get(mode, mode),
            need_ffmpeg=True)

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要处理的音频文件", "Add audio files to process first")
