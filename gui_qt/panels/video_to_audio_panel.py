"""video_to_audio_panel — 视频提取音频面板。

将视频文件中的音频流提取为独立音频文件（AAC / MP3 / FLAC / WAV），
支持自定义码率与输出目录。任务经 TaskManager 通用链路执行
core.video_converter.VideoConverter.extract_audio（FFmpeg -vn）。
"""
import os

from PySide6.QtCore import Qt
from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon,
                            Slider)

from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.components import toast
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow
from utils.config import SUPPORTED_VIDEO

# 输出格式 → 扩展名
AUDIO_OUT_EXT = {"AAC": ".aac", "MP3": ".mp3", "FLAC": ".flac", "WAV": ".wav"}
# 输出格式 → extract_audio 编码器 ID
AUDIO_OUT_CODEC = {"AAC": "aac", "MP3": "mp3", "FLAC": "flac", "WAV": "wav"}
BR_VALUES = ["128k", "192k", "256k", "320k"]


class VideoToAudioPanelPage(BaseQtPanel):
    """视频提取音频页。"""

    panel_key = "video_to_audio"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("视频提取音频", "Extract Audio")))
        lay.addWidget(CaptionLabel(
            tr("从视频中提取音频流，输出为独立音频文件",
               "Extract the audio track from videos as standalone audio files")))

        # 文件列表：仅接受视频格式
        exts = set(SUPPORTED_VIDEO.values())
        self.file_card = FileListCard(tr("文件列表", "Files"), file_exts=exts)
        lay.addWidget(self.file_card)
        self.file_card.set_target_fmt("AAC")

        lay.addWidget(self._build_params_card())

        # 输出目录
        from gui_qt.components.form_widgets import FormSection
        out_card = FormSection(tr("输出目录", "Output folder"), FluentIcon.FOLDER)
        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        out_card.add_widget(self.out_row)
        lay.addWidget(out_card)

        # 底部操作栏
        self.action_bar = ActionBar(tr("开始提取", "Start"))
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

        sec = FormSection(tr("提取参数", "Extract settings"), FluentIcon.SETTING)
        grid = FormGrid(columns=2)

        def _combo(items, default):
            cb = ComboBox()
            cb.addItems(items)
            cb.setCurrentText(default)
            return cb

        self.cb_fmt = grid.add_field(
            tr("输出格式", "Output format"),
            _combo(list(AUDIO_OUT_EXT), "AAC"),
            hint=tr("支持的音频编码格式", "Supported audio encoding formats"))
        self.cb_br = grid.add_field(
            tr("比特率", "Bitrate"),
            _combo(BR_VALUES, "192k"),
            hint=tr("码率越高音质越好，文件也越大",
                    "Higher bitrate = better audio, larger file"))
        sec.add_form(grid)
        return sec

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        fmt = self.cb_fmt.currentText()
        return {
            "fmt": fmt,
            "codec": AUDIO_OUT_CODEC.get(fmt, "aac"),
            "bitrate": self.cb_br.currentText(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return {
            "fmt": self.cb_fmt.currentText(),
            "br": self.cb_br.currentText(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("fmt") in AUDIO_OUT_EXT:
            self.cb_fmt.setCurrentText(prefs["fmt"])
        if prefs.get("br") in BR_VALUES:
            self.cb_br.setCurrentText(prefs["br"])
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器（TaskManager 通用链路）────────
    def _runner(self, task, prog):
        p = task.params
        return self.services.video_conv.extract_audio(
            task.file_path, task.output_path,
            audio_codec=p.get("codec", "aac"),
            bitrate=p.get("bitrate", "192k"),
            progress_callback=prog)

    # ── 任务提交 ─────────────────────────────────
    def _start(self):
        files = self.file_card.files()
        if not files:
            toast.show_warning(self,
                tr("请先添加要提取音频的视频文件",
                   "Add video files to extract audio from first"))
            return
        if not self.services.ffmpeg_ready():
            toast.show_error(self,
                tr("FFmpeg 未就绪，请稍后重试", "FFmpeg not ready"))
            return
        if self.out_row.mode() == OutputDirRow.MODE_CUSTOM and \
                not self.out_row.path():
            toast.show_warning(self,
                tr("请先选择自定义输出目录",
                   "Choose an output folder first"))
            return

        params = self.collect_params()
        self.save_prefs()
        fmt_ext = AUDIO_OUT_EXT[params["fmt"]]
        mgr = self.services.task_manager
        conv = self.services.video_conv
        added = 0
        used_out = set()
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
                name=f"{tr('提取音频', 'Extract Audio')} - "
                     f"{os.path.basename(f)}",
                task_type="audio",
                file_path=f,
                output_path=out_path,
                params=params,
                runner=self._runner,
                canceller=conv.cancel,
                history_type=tr("提取音频", "Extract Audio"),
                history_target=params["fmt"])
            if tid is not None:
                self._task_rows[tid] = (f, self.file_card.row_of_file(f))
                added += 1
        if added:
            self.btn_go.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self.bar_total.setValue(0)
            self.status_label.setText(
                tr("已提交 {} 个任务", "Submitted {} tasks").format(added))
        else:
            toast.show_error(self,
                tr("任务提交失败：FFmpeg 未就绪",
                   "Submit failed: FFmpeg not ready"))

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
        _file, idx = row
        if state in (tm.SUCCESS, tm.FAILED, tm.CANCELLED):
            self.file_card.set_row_progress(idx, -1, tm.state_text(state))
        self.file_card.set_row_state(idx, tm.state_text(state))
        task = self.services.task_manager.get_task(task_id)
        if state == tm.FAILED and task:
            toast.show_error(self,
                tr("提取失败：{}", "Failed: {}")
                .format(os.path.basename(task.file_path)) +
                tr("（{}）", " ({})")
                .format(task.error or tr("未知错误", "unknown error")))
        if state in (tm.SUCCESS, tm.FAILED, tm.CANCELLED):
            self._task_rows.pop(task_id, None)
            self._update_total()
        active = [self.services.task_manager.get_task(t)
                  for t in self._task_rows]
        if not any(t and t.state in (tm.WAITING, tm.RUNNING, tm.PAUSED)
                   for t in active):
            self.btn_go.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self.bar_total.setValue(0)

    def _update_total(self):
        tasks = [self.services.task_manager.get_task(t)
                 for t in self._task_rows]
        tasks = [t for t in tasks if t]
        if not tasks:
            return
        self.bar_total.setValue(sum(t.progress for t in tasks) // len(tasks))
