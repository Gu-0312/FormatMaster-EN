"""audio_panel — 音频转换面板（阶段2 迁移自 gui/panels/audio_panel.py）。

复用 FileListCard / OutputDirRow 原语；任务经 TaskManager.add_task 通用链路
执行 core.audio_converter.AudioConverter，参数与 tkinter 版 collect_params 一致：
fmt / codec / bitrate / sample_rate / channels / volume。
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QVBoxLayout
from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon,
                            Slider, SubtitleLabel)

from gui_qt import task_manager as tm
from gui_qt.components import toast
from gui_qt.components import design_system as ds
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow
from utils.config import SUPPORTED_AUDIO

# 音频格式 → FFmpeg 编码器映射（与 tkinter 版 audio_panel.AUDIO_CODEC_MAP 一致）
AUDIO_CODEC_MAP = {
    "MP3": "libmp3lame", "AAC": "aac", "FLAC": "flac", "WAV": "pcm_s16le",
    "WMA": "wmav2", "OGG": "libvorbis", "M4A": "aac",
    "AMR": "libopencore_amrnb", "OPUS": "libopus",
}

BR_VALUES = ["128k", "192k", "256k", "320k"]
SR_VALUES = ["原始", "22050", "44100", "48000", "96000"]
CH_VALUES = ["原始", "单声道", "立体声"]
CH_MAP = {"原始": None, "单声道": 1, "立体声": 2}


class AudioPanelPage(BaseQtPanel):
    """音频转换页。"""

    panel_key = "audio"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title("音频转换"))
        lay.addWidget(CaptionLabel(
            "MP3 · WAV · WMA · AAC · FLAC · OGG · M4A 等格式互转"))

        exts = set(SUPPORTED_AUDIO.values())
        self.file_card = FileListCard("文件列表", file_exts=exts)
        lay.addWidget(self.file_card)
        self.file_card.set_target_fmt("MP3")

        lay.addWidget(self._build_params_card())

        from gui_qt.components.form_widgets import FormSection
        out_card = FormSection("输出目录", FluentIcon.FOLDER)
        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        out_card.add_widget(self.out_row)
        lay.addWidget(out_card)

        # 底部操作栏
        self.action_bar = ActionBar("开始转换")
        lay.addWidget(self.action_bar)
        self.btn_go = self.action_bar.btn_go
        self.btn_cancel = self.action_bar.btn_cancel
        self.bar_total = self.action_bar.bar_total
        self.status_label = self.action_bar.status_label

        self.btn_go.clicked.connect(self._start)
        self.btn_cancel.clicked.connect(self._cancel_all)
        self.cb_fmt.currentTextChanged.connect(self.file_card.set_target_fmt)

        mgr = self.services.task_manager
        mgr.sig_progress.connect(self._on_progress)
        mgr.sig_state.connect(self._on_state)
        self._task_rows = {}   # task_id -> (file_path, row)

    def _build_params_card(self):
        from gui_qt.components.form_widgets import FormSection, FormGrid

        sec = FormSection("转换参数", FluentIcon.SETTING)
        grid = FormGrid(columns=2)

        def _combo(items, default):
            cb = ComboBox()
            cb.addItems(items)
            cb.setCurrentText(default)
            return cb

        self.cb_fmt = grid.add_field(
            "目标格式", _combo(list(SUPPORTED_AUDIO), "MP3"),
            hint="输出音频格式")
        self.cb_br = grid.add_field(
            "比特率", _combo(BR_VALUES, "192k"),
            hint="码率越高音质越好，文件也越大")
        self.cb_sr = grid.add_field(
            "采样率", _combo(SR_VALUES, "原始"))
        self.cb_ch = grid.add_field(
            "声道", _combo(CH_VALUES, "原始"))
        sec.add_form(grid)

        # 音量滑块（20%~200%，默认 100%）
        from PySide6.QtWidgets import QHBoxLayout, QWidget
        vol_box = QWidget()
        vol_row = QHBoxLayout(vol_box)
        vol_row.setSpacing(8)
        vol_lbl = CaptionLabel("音量")
        vol_lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {ds.ink_sec()};"
            "border: none; background: transparent;")
        vol_row.addWidget(vol_lbl)
        self.vol_slider = Slider(Qt.Horizontal)
        self.vol_slider.setRange(20, 200)
        self.vol_slider.setValue(100)
        self.vol_label = CaptionLabel("100%")
        self.vol_slider.valueChanged.connect(
            lambda v: self.vol_label.setText(f"{v}%"))
        vol_row.addWidget(self.vol_slider, 1)
        vol_row.addWidget(self.vol_label)
        sec.add_widget(vol_box)
        return sec

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        fmt = self.cb_fmt.currentText()
        return {
            "fmt": fmt,
            "codec": AUDIO_CODEC_MAP.get(fmt),
            "bitrate": self.cb_br.currentText(),
            "sample_rate": self.cb_sr.currentText(),
            "channels": self.cb_ch.currentText(),
            "volume": self.vol_slider.value(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return {
            "fmt": self.cb_fmt.currentText(),
            "br": self.cb_br.currentText(),
            "sr": self.cb_sr.currentText(),
            "ch": self.cb_ch.currentText(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("fmt") in SUPPORTED_AUDIO:
            self.cb_fmt.setCurrentText(prefs["fmt"])
        if prefs.get("br") in BR_VALUES:
            self.cb_br.setCurrentText(prefs["br"])
        if prefs.get("sr") in SR_VALUES:
            self.cb_sr.setCurrentText(prefs["sr"])
        if prefs.get("ch") in CH_VALUES:
            self.cb_ch.setCurrentText(prefs["ch"])
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器（TaskManager 通用链路）────────
    def _runner(self, task, prog):
        p = task.params
        sr = None if p.get("sample_rate", "原始") == "原始" \
            else int(p["sample_rate"])
        ch = CH_MAP.get(p.get("channels", "原始"))
        return self.services.audio_conv.convert(
            task.file_path, task.output_path,
            codec=p.get("codec"), bitrate=p.get("bitrate", "192k"),
            sample_rate=sr, channels=ch,
            volume=p.get("volume", 100), progress_callback=prog)

    # ── 任务提交 ─────────────────────────────────
    def _start(self):
        files = self.file_card.files()
        if not files:
            toast.show_warning(self, "请先添加要转换的音频文件")
            return
        if not self.services.ffmpeg_ready():
            toast.show_error(self, "FFmpeg 未就绪，请稍后重试")
            return
        if self.out_row.mode() == OutputDirRow.MODE_CUSTOM and not self.out_row.path():
            toast.show_warning(self, "请先选择自定义输出目录")
            return

        params = self.collect_params()
        self.save_prefs()
        fmt_ext = SUPPORTED_AUDIO[params["fmt"]]
        mgr = self.services.task_manager
        conv = self.services.audio_conv
        added = 0
        for f in files:
            out_dir = self.out_row.resolve_dir(f)
            out_path = tm.make_output_path(f, out_dir, fmt_ext)
            tid = mgr.add_task(
                name=f"音频转换 - {os.path.basename(f)}",
                task_type="audio", file_path=f, output_path=out_path,
                params=params, runner=self._runner, canceller=conv.cancel,
                history_type="音频转换", history_target=params["fmt"])
            if tid is not None:
                self._task_rows[tid] = (f, self.file_card.row_of_file(f))
                added += 1
        if added:
            self.btn_go.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self.bar_total.setValue(0)
            self.status_label.setText(f"已提交 {added} 个任务")
        else:
            toast.show_error(self, "任务提交失败：FFmpeg 未就绪")

    def _cancel_all(self):
        mgr = self.services.task_manager
        for tid in list(self._task_rows):
            mgr.cancel_task(tid)
        self.btn_cancel.setEnabled(False)

    # ── 进度/状态联动 ────────────────────────────
    def _on_progress(self, task_id, pct, msg, speed):
        row = self._task_rows.get(task_id)
        if not row:
            return
        _file, idx = row
        task = self.services.task_manager.get_task(task_id)
        if task and task.state in (tm.SUCCESS, tm.FAILED, tm.CANCELLED):
            return
        self.file_card.set_row_progress(idx, pct)
        self.status_label.setText(msg)
        self._update_total()

    def _on_state(self, task_id, state):
        row = self._task_rows.get(task_id)
        if row:
            _file, idx = row
            if state in (tm.SUCCESS, tm.FAILED, tm.CANCELLED):
                # 终态：移除行内进度条，改为显示状态文字（成功/失败/取消）
                self.file_card.set_row_progress(idx, -1,
                                                tm.state_text(state))
            self.file_card.set_row_state(idx, tm.state_text(state))
        task = self.services.task_manager.get_task(task_id)
        if state == tm.SUCCESS and task:
            toast.show_success(self, f"转换完成：{os.path.basename(task.file_path)}")
        elif state == tm.FAILED and task:
            toast.show_error(self,
                             f"转换失败：{os.path.basename(task.file_path)}"
                             f"（{task.error or '未知错误'}）")
        if state in (tm.SUCCESS, tm.FAILED, tm.CANCELLED):
            self._task_rows.pop(task_id, None)
            self._update_total()
        active = [self.services.task_manager.get_task(t)
                  for t in self._task_rows]
        if not any(t and t.state in (tm.WAITING, tm.RUNNING, tm.PAUSED)
                   for t in active):
            self.btn_go.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self.bar_total.setValue(0)  # 全部结束：总进度条重置归零

    def _update_total(self):
        tasks = [self.services.task_manager.get_task(t) for t in self._task_rows]
        tasks = [t for t in tasks if t]
        if not tasks:
            return
        self.bar_total.setValue(sum(t.progress for t in tasks) // len(tasks))
