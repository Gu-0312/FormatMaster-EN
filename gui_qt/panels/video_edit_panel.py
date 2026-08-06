"""video_edit_panel — 视频处理面板（剪辑 / 合并 / 字幕烧录 / 变速）。

基于 core/video_tools（FFmpeg），模式用 SegmentedWidget 切换，
复用 TaskPanelMixin 的文件列表 + 任务队列联动。
"""
import os

from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QVBoxLayout,
                               QWidget)
from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon, LineEdit,
                            PushButton, SegmentedWidget)

from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.components.form_widgets import FormGrid, FormSection
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
              ".m4v", ".mpg", ".mpeg", ".ts"}

MODES = [
    ("clip", "剪辑片段"),
    ("merge", "合并视频"),
    ("subtitle", "字幕烧录"),
    ("speed", "变速处理"),
]

SUB_EXTS = {".srt", ".ass", ".ssa", ".vtt"}


def _parse_time(s):
    """把 'HH:MM:SS' / 'MM:SS' 或纯秒数转秒；非法/空返回 None。"""
    s = (s or "").strip()
    if not s:
        return None
    try:
        parts = s.split(":")
        if len(parts) == 1:
            return float(parts[0])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError:
        return None
    return None


class VideoToolsPanelPage(BaseQtPanel, TaskPanelMixin):
    """视频处理页。"""

    panel_key = "video_tools"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("视频处理", "Video Tools")))
        lay.addWidget(CaptionLabel(
            "剪辑 · 合并 · 字幕烧录 · 变速，一站式视频处理"))

        self.file_card = FileListCard("文件列表", file_exts=VIDEO_EXTS)
        lay.addWidget(self.file_card)
        self.file_card.set_target_fmt("视频处理")

        lay.addWidget(self._build_params_card())

        from gui_qt.components.form_widgets import FormSection
        out_card = FormSection(tr("输出目录", "Output Folder"), FluentIcon.FOLDER)
        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        out_card.add_widget(self.out_row)
        lay.addWidget(out_card)

        self.action_bar = ActionBar(tr("开始处理", "Start"))
        lay.addWidget(self.action_bar)

        self._wire_tasks()

    def _build_params_card(self):
        sec = FormSection(tr("处理设置", "Settings"), FluentIcon.SETTING)

        # 模式分段选择
        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_row.addWidget(CaptionLabel("处理模式"))
        self.sg_mode = SegmentedWidget()
        for key, label in MODES:
            self.sg_mode.addItem(key, label)
        self.sg_mode.setCurrentItem("clip")
        self.sg_mode.currentItemChanged.connect(
            lambda _k: self._mode_changed())
        mode_row.addWidget(self.sg_mode, 1)
        sec.add_layout(mode_row)

        # 剪辑：起止时间
        self.w_clip = QWidget()
        g1 = FormGrid(columns=2)
        self.ed_start = LineEdit()
        self.ed_start.setPlaceholderText("如 00:30 或 30")
        self.ed_end = LineEdit()
        self.ed_end.setPlaceholderText("留空表示到结尾")
        g1.add_field(tr("开始时间", "Start time"), self.ed_start, hint="HH:MM:SS")
        g1.add_field(tr("结束时间", "End time"), self.ed_end, hint="HH:MM:SS")
        v1 = QVBoxLayout(self.w_clip)
        v1.setContentsMargins(0, 0, 0, 0)
        v1.addLayout(g1)
        sec.add_widget(self.w_clip)

        # 字幕：字幕文件选择
        self.w_sub = QWidget()
        srow = QHBoxLayout(self.w_sub)
        srow.setContentsMargins(0, 0, 0, 0)
        srow.setSpacing(8)
        self.ed_sub = LineEdit()
        self.ed_sub.setPlaceholderText("选择 SRT / ASS 字幕文件…")
        self.ed_sub.setReadOnly(True)
        self.btn_sub = PushButton(FluentIcon.DOCUMENT, tr("选择字幕", "Pick"))
        self.btn_sub.clicked.connect(self._pick_subtitle)
        srow.addWidget(self.ed_sub, 1)
        srow.addWidget(self.btn_sub)
        sec.add_widget(self.w_sub)

        # 变速：倍速
        self.w_speed = QWidget()
        srow2 = QHBoxLayout(self.w_speed)
        srow2.setContentsMargins(0, 0, 0, 0)
        srow2.setSpacing(8)
        self.cb_speed = ComboBox()
        self.cb_speed.addItems(["0.5x", "0.75x", "1.25x", "1.5x",
                                "1.75x", "2.0x"])
        self.cb_speed.setCurrentText("1.5x")
        srow2.addWidget(CaptionLabel(tr("播放倍速", "Speed")))
        srow2.addWidget(self.cb_speed)
        srow2.addStretch(1)
        sec.add_widget(self.w_speed)

        self._mode_changed()
        return sec

    def _pick_subtitle(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择字幕文件", "",
            "字幕文件 (*.srt *.ass *.ssa *.vtt)")
        if path:
            self.ed_sub.setText(path)

    def _mode_changed(self):
        mode = self.sg_mode.currentRouteKey()
        self.w_clip.setVisible(mode == "clip")
        self.w_sub.setVisible(mode == "subtitle")
        self.w_speed.setVisible(mode == "speed")
        # 提示文案随模式变化
        if mode == "merge":
            self.file_card.set_target_fmt("合并为 1 个文件")
        elif mode == "subtitle":
            self.file_card.set_target_fmt("烧录字幕")
        elif mode == "speed":
            self.file_card.set_target_fmt("变速处理")
        else:
            self.file_card.set_target_fmt("剪辑片段")

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        mode = self.sg_mode.currentRouteKey()
        return {
            "mode": mode,
            "start": _parse_time(self.ed_start.text()),
            "end": _parse_time(self.ed_end.text()),
            "subtitle_path": self.ed_sub.text().strip(),
            "rate": float(self.cb_speed.currentText().replace("x", "")),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return {
            "mode": self.sg_mode.currentRouteKey(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        mode = prefs.get("mode")
        if mode in dict(MODES):
            self.sg_mode.setCurrentItem(mode)
            self._mode_changed()
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务 ─────────────────────────────────────
    def _start(self):
        self._submit_files()

    def _empty_hint(self) -> str:
        return "请先添加要处理的视频文件"

    def _make_task(self, f: str) -> dict:
        mode = self.sg_mode.currentRouteKey()
        params = self.collect_params()
        files = self.file_card.files()

        if mode == "clip":
            if params["start"] is None:
                from gui_qt.components import toast
                toast.show_warning(self, "请填写开始时间")
                return None
            ext = os.path.splitext(f)[1] or ".mp4"
            out = tm.make_output_path(f, self.out_row.path(), ext)
            return dict(name=tr("视频剪辑", "Video Clip"), task_type="video_tools",
                        file_path=f, output_path=out, params=params,
                        runner=self._runner,
                        history_type="视频处理", history_target="剪辑",
                        need_ffmpeg=True)
        if mode == "merge":
            if len(files) < 2:
                from gui_qt.components import toast
                toast.show_warning(self, "合并至少需要 2 个视频文件")
                return None
            if f != files[0]:
                return None  # 合并只提交一个任务（携带全部文件）
            ext = os.path.splitext(files[0])[1] or ".mp4"
            out = tm.make_output_path(files[0], self.out_row.path(), ext)
            params = dict(params, files=files)
            return dict(name=tr("视频合并", "Video Merge"), task_type="video_tools",
                        file_path=f, output_path=out, params=params,
                        runner=self._runner,
                        history_type="视频处理", history_target="合并",
                        need_ffmpeg=True)
        if mode == "subtitle":
            if not params["subtitle_path"]:
                from gui_qt.components import toast
                toast.show_warning(self, "请先选择字幕文件")
                return None
            out = tm.make_output_path(f, self.out_row.path(), ".mp4")
            return dict(name=tr("字幕烧录", "Burn Subtitle"), task_type="video_tools",
                        file_path=f, output_path=out, params=params,
                        runner=self._runner,
                        history_type="视频处理", history_target="字幕",
                        need_ffmpeg=True)
        # speed
        out = tm.make_output_path(f, self.out_row.path(),
                                  os.path.splitext(f)[1] or ".mp4")
        return dict(name=tr("视频变速", "Change Speed"), task_type="video_tools",
                    file_path=f, output_path=out, params=params,
                    runner=self._runner,
                    history_type="视频处理", history_target="变速",
                    need_ffmpeg=True)

    def _runner(self, task, prog):
        from core import video_tools
        p = task.params
        mode = p.get("mode", "clip")
        if mode == "clip":
            return video_tools.clip_video(task.file_path, task.output_path,
                                          p.get("start"), p.get("end"),
                                          progress_cb=prog)
        if mode == "merge":
            return video_tools.merge_videos(p.get("files") or [task.file_path],
                                            task.output_path, progress_cb=prog)
        if mode == "subtitle":
            return video_tools.burn_subtitle(task.file_path,
                                             p.get("subtitle_path", ""),
                                             task.output_path, progress_cb=prog)
        return video_tools.change_speed(task.file_path, task.output_path,
                                        p.get("rate", 1.0), progress_cb=prog)
