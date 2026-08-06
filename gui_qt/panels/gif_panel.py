"""gif_panel — 视频转 GIF 面板（阶段2 迁移自 gui/panels/gif_panel.py）。

将视频片段转换为 GIF 动图，支持自定义宽度/帧率/起始时间/时长。
FFmpeg 命令与 tkinter 版 _run_task_general 的 gif 分支一致：
-vf fps=..,scale=..:flags=lanczos -loop 0，-progress pipe:1 解析进度。
"""
import os
import subprocess

from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon)

from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow
from utils.config import get_ffmpeg_path

# 预置值（与 tkinter 版 gif_panel 一致）
WIDTH_VALUES = [tr("原始", "Original"), "640", "480", "320", "240"]
FPS_VALUES = ["10", "15", "20", "24", "30"]
START_VALUES = ["0"]
DURATION_VALUES = ["5", "10", "15", "30", "60", tr("全部", "All")]

GIF_SRC_EXTS = {".mp4", ".avi", ".mkv", ".mov", ".flv", ".webm", ".ts"}


class GifPanelPage(BaseQtPanel, TaskPanelMixin):
    """视频转 GIF 页。"""

    panel_key = "gif"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("GIF转换", "GIF convert")))
        lay.addWidget(CaptionLabel(
            tr("将视频片段转换为GIF动图，支持自定义分辨率和帧率", "Convert video clips to GIF with custom resolution and FPS")))

        self.file_card = FileListCard(tr("文件列表", "Files"), file_exts=GIF_SRC_EXTS)
        lay.addWidget(self.file_card)
        self.file_card.set_target_fmt("GIF")

        from gui_qt.components.form_widgets import FormSection, FormGrid
        card = FormSection(tr("GIF设置", "GIF settings"), FluentIcon.MOVIE)
        grid = FormGrid(columns=2)

        def _combo(items, default):
            cb = ComboBox()
            cb.addItems(items)
            cb.setCurrentText(default)
            return cb

        self.cb_w = grid.add_field(
            tr("宽度", "Width"), _combo(WIDTH_VALUES, "480"),
            hint=tr("输出 GIF 宽度，原始保持原尺寸", "Output GIF width, original = keep size"))
        self.cb_fps = grid.add_field(
            tr("帧率", "Frame rate"), _combo(FPS_VALUES, "15"),
            hint=tr("帧率越高动图越流畅，文件也越大", "Higher FPS = smoother GIF, larger file"))
        self.cb_start = grid.add_field(
            tr("开始(秒)", "Start (sec)"), _combo(START_VALUES, "0"))
        self.cb_dur = grid.add_field(
            tr("时长(秒)", "Duration (sec)"), _combo(DURATION_VALUES, "10"),
            hint=tr("片段时长，全部为整个视频", "Segment duration, all = whole video"))
        card.add_form(grid)
        lay.addWidget(card)

        out_card = FormSection(tr("输出目录", "Output folder"), FluentIcon.FOLDER)
        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        out_card.add_widget(self.out_row)
        lay.addWidget(out_card)

        self.action_bar = ActionBar(tr("开始转换", "Convert"))
        lay.addWidget(self.action_bar)
        self._proc_holder = {}   # 串行队列下共享当前 ffmpeg 进程句柄
        self._wire_tasks()

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "width": self.cb_w.currentText(),
            "fps": self.cb_fps.currentText(),
            "start": self.cb_start.currentText(),
            "duration": self.cb_dur.currentText(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return {
            "width": self.cb_w.currentText(),
            "fps": self.cb_fps.currentText(),
            "start": self.cb_start.currentText(),
            "duration": self.cb_dur.currentText(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("width") in WIDTH_VALUES:
            self.cb_w.setCurrentText(prefs["width"])
        if prefs.get("fps") in FPS_VALUES:
            self.cb_fps.setCurrentText(prefs["fps"])
        if prefs.get("start") in START_VALUES:
            self.cb_start.setCurrentText(prefs["start"])
        if prefs.get("duration") in DURATION_VALUES:
            self.cb_dur.setCurrentText(prefs["duration"])
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        p = task.params
        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            task.error = tr("FFmpeg 未找到", "FFmpeg not found")
            return False

        cmd = [ffmpeg, "-y", "-progress", "pipe:1"]
        start = p.get("start", "0")
        dur = p.get("duration", tr("全部", "All"))
        fps = p.get("fps", "10")
        w_val = p.get("width", tr("原始", "Original"))
        if start != "0":
            cmd += ["-ss", start]
        cmd += ["-i", task.file_path]
        if dur != tr("全部", "All"):
            cmd += ["-t", dur]
        vf = f"fps={fps}"
        if w_val != tr("原始", "Original"):
            vf += f",scale={w_val}:-1:flags=lanczos"
        cmd += ["-vf", vf, "-loop", "0", task.output_path]

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self._proc_holder["p"] = proc

        total_ms = None
        if dur != tr("全部", "All"):
            try:
                total_ms = float(dur) * 1000000
            except (ValueError, TypeError):
                total_ms = None

        while proc.poll() is None:
            if task.state == tm.CANCELLED:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return False
            line = proc.stdout.readline()
            if line and "out_time_ms=" in line:
                try:
                    ms = int(line.split("=")[1].strip())
                    if total_ms:
                        pct = min(100, int(ms / total_ms * 100))
                        prog(pct, tr("正在转换...", "Converting…"))
                except (ValueError, IndexError, TypeError):
                    pass
        self._proc_holder["p"] = None
        return proc.returncode == 0

    def _cancel_proc(self):
        proc = self._proc_holder.get("p")
        if proc is not None:
            proc.terminate()

    def _make_task(self, f):
        params = self.collect_params()
        out_dir = self.out_row.resolve_dir(f)
        out_path = tm.make_output_path(f, out_dir, ".gif")
        return dict(
            name=f"{tr('视频转GIF', 'Video to GIF')} - {os.path.basename(f)}",
            task_type="gif", file_path=f, output_path=out_path,
            params=params, runner=self._runner, canceller=self._cancel_proc,
            history_type=tr("视频转 GIF", "Video to GIF"), history_target="GIF")

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要转换的视频文件", "Add video files to convert first")
