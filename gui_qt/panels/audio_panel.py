"""audio_panel — 音频转换面板（阶段2 迁移自 gui/panels/audio_panel.py）。

复用 FileListCard / OutputDirRow 原语；任务经 TaskManager.add_task 通用链路
执行 core.audio_converter.AudioConverter，参数与 tkinter 版 collect_params 一致：
fmt / codec / bitrate / sample_rate / channels / volume。
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QVBoxLayout, QWidget
from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon,
                            Slider, SubtitleLabel)

from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.components import toast
from gui_qt.components import design_system as ds
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow
from utils.config import SUPPORTED_AUDIO, SUPPORTED_VIDEO

# 音频格式 → FFmpeg 编码器映射（与 tkinter 版 audio_panel.AUDIO_CODEC_MAP 一致）
AUDIO_CODEC_MAP = {
    "MP3": "libmp3lame", "AAC": "aac", "FLAC": "flac", "WAV": "pcm_s16le",
    "WMA": "wmav2", "OGG": "libvorbis", "M4A": "aac",
    "AMR": "libopencore_amrnb", "OPUS": "libopus",
}

BR_VALUES = ["128k", "192k", "256k", "320k"]
SR_VALUES = [tr("原始", "Original"), "22050", "44100", "48000", "96000"]
CH_VALUES = [tr("原始", "Original"), "单声道", "立体声"]
CH_MAP = {tr("原始", "Original"): None, "单声道": 1, "立体声": 2}


class AudioPanelPage(BaseQtPanel):
    """音频转换页。"""

    panel_key = "audio"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("音频转换 / 提取", "Audio convert / extract")))
        lay.addWidget(CaptionLabel(
            tr("MP3 · WAV · WMA · AAC · FLAC · OGG · M4A 等格式互转，也可直接拖入视频提取音频（如 MP4 → MP3）",
               "Interconvert audio formats, or drop a video to extract its audio (e.g. MP4 → MP3)")))

        exts = set(SUPPORTED_AUDIO.values()) | set(SUPPORTED_VIDEO.values())
        self.file_card = FileListCard(tr("文件列表", "Files"), file_exts=exts)
        lay.addWidget(self.file_card)
        self.file_card.set_target_fmt("MP3")

        lay.addWidget(self._build_params_card())

        from gui_qt.components.form_widgets import FormSection
        out_card = FormSection(tr("输出目录", "Output folder"), FluentIcon.FOLDER)
        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        out_card.add_widget(self.out_row)
        lay.addWidget(out_card)

        # 波形预览（pyqtgraph，后台解码不卡 UI）
        lay.addWidget(self._build_waveform_card())

        # 底部操作栏
        self.action_bar = ActionBar(tr("开始转换", "Convert"))
        lay.addWidget(self.action_bar)
        self.btn_go = self.action_bar.btn_go
        self.btn_cancel = self.action_bar.btn_cancel
        self.bar_total = self.action_bar.bar_total
        self.status_label = self.action_bar.status_label

        self.btn_go.clicked.connect(self._start)
        self.btn_cancel.clicked.connect(self._cancel_all)
        self.cb_fmt.currentTextChanged.connect(self.file_card.set_target_fmt)
        self._wave_worker = None

        mgr = self.services.task_manager
        mgr.sig_progress.connect(self._on_progress)
        mgr.sig_state.connect(self._on_state)
        self._task_rows = {}   # task_id -> (file_path, row)

    def _build_waveform_card(self):
        """波形预览折叠区：按钮 + pyqtgraph 波形（后台解码）。"""
        from PySide6.QtWidgets import QHBoxLayout
        from qfluentwidgets import PushButton
        from gui_qt.components.form_widgets import CollapsibleSection
        from gui_qt.components.audio_waveform import AudioWaveformWidget

        sec = CollapsibleSection(tr("波形预览", "Waveform preview"),
                                 hint=tr("查看音频音量波形（可选，不影响转换）",
                                         "View volume waveform (optional)"))
        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_wave = PushButton(tr("显示波形", "Show waveform"))
        self.btn_wave.clicked.connect(self._show_waveform)
        row.addWidget(self.btn_wave)
        self.lb_wave = CaptionLabel("")
        row.addWidget(self.lb_wave)
        row.addStretch(1)
        sec.add_widget(self._holder(row))
        self.waveform = AudioWaveformWidget()
        sec.add_widget(self.waveform)
        return sec

    @staticmethod
    def _holder(layout):
        w = QWidget()
        w.setLayout(layout)
        return w

    def _show_waveform(self):
        files = self.file_card.files()
        if not files:
            toast.show_warning(self, tr("请先添加音频/视频文件", "Add audio/video files first"))
            return
        fp = files[0]
        if self._wave_worker and self._wave_worker.isRunning():
            return
        self.lb_wave.setText(tr("正在解码…", "Decoding…"))
        from gui_qt.components.safe_worker import SafeWorker
        from PySide6.QtCore import Signal

        class _WaveWorker(SafeWorker):
            sig_done = Signal(str, object)

            def __init__(self, f, parent=None):
                super().__init__(parent)
                self._f = f

            def work(self):
                from gui_qt.components.audio_waveform import _decode_pcm, _bucket_peaks
                samples, dur = _decode_pcm(self._f)
                if samples is None or len(samples) == 0:
                    self.sig_done.emit(self._f, None)
                    return
                peaks = _bucket_peaks(samples, 2000)
                self.sig_done.emit(self._f, (peaks, dur))

        self._wave_worker = _WaveWorker(fp, self)
        self._wave_worker.sig_done.connect(self._on_wave_done)
        self._wave_worker.start()

    def _on_wave_done(self, fp, result):
        if result is None:
            self.lb_wave.setText(tr("解码失败（文件损坏或非音频）", "Decode failed"))
            return
        peaks, dur = result
        self.waveform.set_peaks(peaks, dur)
        self.lb_wave.setText(tr("已显示波形 · 时长 {}s", "Waveform · {}s").format(int(dur)))

    def _build_params_card(self):
        from gui_qt.components.form_widgets import FormSection, FormGrid

        sec = FormSection(tr("转换参数", "Convert settings"), FluentIcon.SETTING)
        grid = FormGrid(columns=2)

        def _combo(items, default):
            cb = ComboBox()
            cb.addItems(items)
            cb.setCurrentText(default)
            return cb

        self.cb_fmt = grid.add_field(
            tr("目标格式", "Target format"), _combo(list(SUPPORTED_AUDIO), "MP3"),
            hint=tr("输出音频格式", "Output audio format"))
        self.cb_br = grid.add_field(
            tr("比特率", "Bitrate"), _combo(BR_VALUES, "192k"),
            hint=tr("码率越高音质越好，文件也越大", "Higher bitrate = better audio, larger file"))
        self.cb_sr = grid.add_field(
            tr("采样率", "Sample rate"), _combo(SR_VALUES, tr("原始", "Original")))
        self.cb_ch = grid.add_field(
            tr("声道", "Channels"), _combo(CH_VALUES, tr("原始", "Original")))
        sec.add_form(grid)

        # 音量滑块（20%~200%，默认 100%）
        from PySide6.QtWidgets import QHBoxLayout, QWidget
        vol_box = QWidget()
        vol_row = QHBoxLayout(vol_box)
        vol_row.setSpacing(8)
        vol_lbl = CaptionLabel(tr("音量", "Volume"))
        vol_lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 600"
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
        sr = None if p.get("sample_rate", tr("原始", "Original")) == tr("原始", "Original") \
            else int(p["sample_rate"])
        ch = CH_MAP.get(p.get("channels", tr("原始", "Original")))
        return self.services.audio_conv.convert(
            task.file_path, task.output_path,
            codec=p.get("codec"), bitrate=p.get("bitrate", "192k"),
            sample_rate=sr, channels=ch,
            volume=p.get("volume", 100), progress_callback=prog)

    # ── 任务提交 ─────────────────────────────────
    def _start(self):
        files = self.file_card.files()
        if not files:
            toast.show_warning(self, tr("请先添加要转换的音频或视频文件", "Add audio or video files to convert first"))
            return
        if not self.services.ffmpeg_ready():
            toast.show_error(self, tr("FFmpeg 未就绪，请稍后重试", "FFmpeg not ready"))
            return
        if self.out_row.mode() == OutputDirRow.MODE_CUSTOM and not self.out_row.path():
            toast.show_warning(self, tr("请先选择自定义输出目录", "Choose an output folder first"))
            return

        params = self.collect_params()
        self.save_prefs()
        fmt_ext = SUPPORTED_AUDIO[params["fmt"]]
        mgr = self.services.task_manager
        conv = self.services.audio_conv
        added = 0
        used_out = set()  # 同批内已分配的输出路径（防同名不同源互相覆盖）
        for f in files:
            out_dir = self.out_row.resolve_dir(f)
            out_path = tm.make_output_path(f, out_dir, fmt_ext)
            base, e = os.path.splitext(out_path)
            n = 1
            while out_path.lower() in used_out:
                out_path = f"{base}_{n}{e}"
                n += 1
            used_out.add(out_path.lower())
            tid = mgr.add_task(
                name=f"{tr('音频转换', 'Audio Convert')} - {os.path.basename(f)}",
                task_type="audio", file_path=f, output_path=out_path,
                params=params, runner=self._runner, canceller=conv.cancel,
                history_type=tr("音频转换", "Audio Convert"), history_target=params["fmt"])
            if tid is not None:
                self._task_rows[tid] = (f, self.file_card.row_of_file(f))
                added += 1
        if added:
            self.btn_go.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self.bar_total.setValue(0)
            self.status_label.setText(tr("已提交 {} 个任务", "Submitted {} tasks").format(added))
        else:
            toast.show_error(self, tr("任务提交失败：FFmpeg 未就绪", "Submit failed: FFmpeg not ready"))

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
        if not row:
            return
        if row:
            _file, idx = row
            if state in (tm.SUCCESS, tm.FAILED, tm.CANCELLED):
                # 终态：移除行内进度条，改为显示状态文字（成功/失败/取消）
                self.file_card.set_row_progress(idx, -1,
                                                tm.state_text(state))
            self.file_card.set_row_state(idx, tm.state_text(state))
        task = self.services.task_manager.get_task(task_id)
        if state == tm.FAILED and task:
            # 失败即时提示（具体文件+原因）；成功统一走全局完成通知，
            # 避免与「全部转换完成」重复弹两条提示
            toast.show_error(self,
                             tr("转换失败：{}", "Failed: {}").format(os.path.basename(task.file_path))
                             + tr("（{}）", " ({})").format(task.error or tr("未知错误", "unknown error")))
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
