"""audio_trim_panel — 音频剪辑面板（阶段2 迁移自 gui/panels/audio_trim_panel.py）。

波形预览 + 起止时间选择 + 淡入淡出。波形加载在后台线程执行
（core.audio_trimmer 走 ffprobe/ffmpeg），裁剪任务经 TaskManager 执行。
"""
import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import (FluentIcon, CaptionLabel, ComboBox, LineEdit,
                            PushButton)

from gui_qt.components.form_widgets import FormSection, FormGrid
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

FADE_VALUES = ["0", "0.5", "1.0", "2.0", "3.0", "5.0"]

AUDIO_EXTS = {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a",
              ".wma", ".opus"}


def parse_time(s):
    """「HH:MM:SS / MM:SS / 秒数」→ float 秒（与 tkinter 版一致）。"""
    try:
        parts = (s or "").strip().split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(s)
    except Exception:
        return 0.0


class _WaveWorker(QThread):
    """后台读取音频信息与波形振幅数据，避免阻塞 UI 线程。"""

    sig_done = Signal(str, object, list)  # (文件路径, info, 波形数据)

    def __init__(self, fp, points=300, parent=None):
        super().__init__(parent)
        self._fp = fp
        self._points = points

    def run(self):
        from core.audio_trimmer import get_audio_info, get_waveform_data
        try:
            info = get_audio_info(self._fp)
        except Exception:
            info = None
        try:
            data = get_waveform_data(self._fp, self._points)
        except Exception:
            data = []
        self.sig_done.emit(self._fp, info, data)


class WaveformWidget(QWidget):
    """振幅条形波形图；左键设置开始时间，Shift+左键设置结束时间。"""

    time_picked = Signal(float, bool)  # (秒, 是否为结束点)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = []
        self.duration = 0.0
        self.start_sec = 0.0
        self.end_sec = 0.0
        self.setFixedHeight(120)

    def set_wave(self, data, duration):
        self.data = list(data or [])
        self.duration = float(duration or 0.0)
        self.update()

    def set_marks(self, start_sec, end_sec):
        self.start_sec = start_sec
        self.end_sec = end_sec
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        mid = h // 2
        if not self.data:
            p.setPen(QColor(128, 128, 128))
            p.drawText(self.rect(), Qt.AlignCenter, "（点击「刷新波形」加载）")
            return
        n = len(self.data)
        bar_w = max(1.0, w / n)
        pen = QPen(QColor(96, 140, 255), max(1, int(bar_w)))
        p.setPen(pen)
        for i, val in enumerate(self.data):
            x = int(i * bar_w)
            bar_h = max(1, int(val * (mid - 4)))
            p.drawLine(x, mid - bar_h, x, mid + bar_h)
        if self.duration > 0:
            x1 = int(self.start_sec / self.duration * w)
            x2 = int(self.end_sec / self.duration * w)
            p.setPen(QPen(QColor(80, 200, 120), 2))
            p.drawLine(x1, 0, x1, h)
            p.setPen(QPen(QColor(230, 90, 90), 2))
            p.drawLine(x2, 0, x2, h)

    def mousePressEvent(self, e):
        if self.duration <= 0 or e.button() != Qt.LeftButton:
            return
        sec = max(0.0, min(e.position().x() / max(self.width(), 1)
                           * self.duration, self.duration))
        is_end = bool(e.modifiers() & Qt.ShiftModifier)
        self.time_picked.emit(round(sec, 2), is_end)


class AudioTrimPanelPage(BaseQtPanel, TaskPanelMixin):
    """音频剪辑页。"""

    panel_key = "audio_edit"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title("音频裁剪"))
        lay.addWidget(CaptionLabel(
            "选择音频文件，点击波形图选择起止位置进行裁剪，支持淡入淡出"))

        self.file_card = FileListCard("文件列表", file_exts=AUDIO_EXTS)
        lay.addWidget(self.file_card)
        self.file_card.files_changed.connect(self._on_files_changed)

        card = FormSection("裁剪设置", FluentIcon.CUT)

        # 文件信息行
        info_wrap = QWidget()
        info_row = QHBoxLayout(info_wrap)
        info_row.setContentsMargins(0, 0, 0, 0)
        info_row.setSpacing(8)
        self.lb_file = CaptionLabel("未选择音频文件")
        info_row.addWidget(self.lb_file)
        info_row.addStretch(1)
        self.lb_info = CaptionLabel("")
        info_row.addWidget(self.lb_info)
        card.add_widget(info_wrap)

        # 波形预览
        self.wave = WaveformWidget()
        card.add_widget(self.wave)
        self.wave.time_picked.connect(self._on_pick)

        # 起止时间行
        time_wrap = QWidget()
        time_row = QHBoxLayout(time_wrap)
        time_row.setContentsMargins(0, 0, 0, 0)
        time_row.setSpacing(8)
        time_row.addWidget(CaptionLabel("开始"))
        self.ed_start = LineEdit()
        self.ed_start.setText("00:00:00")
        self.ed_start.setFixedWidth(100)
        self.ed_start.textChanged.connect(self._marks_changed)
        time_row.addWidget(self.ed_start)
        time_row.addWidget(CaptionLabel("结束"))
        self.ed_end = LineEdit()
        self.ed_end.setText("00:00:00")
        self.ed_end.setFixedWidth(100)
        self.ed_end.textChanged.connect(self._marks_changed)
        time_row.addWidget(self.ed_end)
        self.lb_dur = CaptionLabel("时长: --")
        time_row.addWidget(self.lb_dur)
        time_row.addStretch(1)
        btn_refresh = PushButton("刷新波形")
        btn_refresh.clicked.connect(self._refresh_waveform)
        time_row.addWidget(btn_refresh)
        card.add_widget(time_wrap)

        # 淡入淡出
        fade_grid = FormGrid(columns=2)
        self.cb_fade_in = fade_grid.add_field(
            "淡入(秒)", self._fade_combo("0"),
            hint="淡入时长，0 表示不淡入")
        self.cb_fade_out = fade_grid.add_field(
            "淡出(秒)", self._fade_combo("0"),
            hint="淡出时长，0 表示不淡出")
        card.add_form(fade_grid)

        # 输出目录（并入裁剪设置卡片，与 tkinter 版一致）
        out_lbl = CaptionLabel("输出目录")
        out_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: #6b7280;"
            "border: none; background: transparent;")
        card.add_widget(out_lbl)
        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        card.add_widget(self.out_row)
        lay.addWidget(card)

        self.action_bar = ActionBar("开始裁剪")
        lay.addWidget(self.action_bar)

        self._wave_worker = None
        self._wire_tasks()

    # ── 波形加载 ─────────────────────────────────
    def _on_files_changed(self):
        self._refresh_waveform()

    def _refresh_waveform(self):
        files = self.file_card.files()
        if not files:
            self.lb_file.setText("未选择音频文件")
            self.lb_info.setText("")
            self.lb_dur.setText("时长: --")
            self.wave.set_wave([], 0.0)
            return
        fp = files[0]
        self.lb_file.setText(os.path.basename(fp))
        self._wave_worker = _WaveWorker(fp, 300, self)
        self._wave_worker.sig_done.connect(self._on_wave_done)
        self._wave_worker.start()

    def _on_wave_done(self, fp, info, data):
        files = self.file_card.files()
        if not files or files[0] != fp:
            return  # 文件已变化，丢弃过期结果
        duration = 0.0
        if info:
            duration = float(info.get("duration") or 0.0)
            self.lb_info.setText(
                f"{info.get('codec', '')} · {info.get('sample_rate', '')}Hz"
                f" · {info.get('channels', '')}ch")
            self.lb_dur.setText(f"时长: {duration:.1f}s")
            self.ed_end.setText(f"{duration:.2f}")
        self.wave.set_wave(data, duration)
        self._marks_changed()

    def _marks_changed(self, *_a):
        self.wave.set_marks(parse_time(self.ed_start.text()),
                            parse_time(self.ed_end.text()))

    def _on_pick(self, sec, is_end):
        if is_end:
            self.ed_end.setText(f"{sec:.2f}")
        else:
            self.ed_start.setText(f"{sec:.2f}")

    def _fade_combo(self, default):
        cb = ComboBox()
        cb.addItems(FADE_VALUES)
        cb.setCurrentText(default)
        return cb

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "start_sec": parse_time(self.ed_start.text()),
            "end_sec": parse_time(self.ed_end.text()),
            "fade_in": float(self.cb_fade_in.currentText()),
            "fade_out": float(self.cb_fade_out.currentText()),
        }

    def collect_prefs(self) -> dict:
        return {
            "fade_in": self.cb_fade_in.currentText(),
            "fade_out": self.cb_fade_out.currentText(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("fade_in") in FADE_VALUES:
            self.cb_fade_in.setCurrentText(prefs["fade_in"])
        if prefs.get("fade_out") in FADE_VALUES:
            self.cb_fade_out.setCurrentText(prefs["fade_out"])
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        from core.audio_trimmer import trim_audio
        p = task.params
        return trim_audio(
            task.file_path, task.output_path,
            start_sec=float(p.get("start_sec", 0)),
            end_sec=float(p.get("end_sec", 0)),
            fade_in=float(p.get("fade_in", 0)),
            fade_out=float(p.get("fade_out", 0)),
            progress_cb=prog)

    def _make_task(self, f):
        params = self.collect_params()
        nm = os.path.splitext(os.path.basename(f))[0]
        ext = os.path.splitext(f)[1]
        out_dir = self.out_row.resolve_dir(f)
        out_path = os.path.join(out_dir, nm + "_trim" + ext)
        return dict(
            name=f"音频裁剪 - {os.path.basename(f)}",
            task_type="audio_trim", file_path=f, output_path=out_path,
            params=params, runner=self._runner,
            history_type="音频裁剪", history_target="裁剪",
            need_ffmpeg=True)

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return "请先添加要裁剪的音频文件"
