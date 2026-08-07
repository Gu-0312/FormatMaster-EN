# -*- coding: utf-8 -*-
"""subtitle_panel — 视频字幕提取面板（硬字幕 OCR）。

把视频里的硬字幕 OCR 识别出来生成 .srt 字幕文件
（core.subtitle_extract：FFmpeg 抽帧 + RapidOCR 逐帧识别 + 去重合并时间轴）。
"""
import os

from qfluentwidgets import CheckBox, ComboBox, FluentIcon

from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".wmv", ".mov", ".flv", ".webm", ".ts",
              ".m4v", ".mpg", ".mpeg", ".3gp"}
FPS_VALUES = [tr("0.5 秒/帧（最快）", "0.5s/frame (fast)"),
              tr("1 秒/帧（推荐）", "1s/frame (recommended)"),
              tr("2 秒/帧（最准）", "2s/frame (accurate)")]
LANG_VALUES = ["chi_sim+eng", "chi_sim", "eng", "jpn", "kor", "chi_tra+eng"]
REGION_VALUES = [tr("底部字幕区（推荐）", "Bottom (recommended)"),
                 tr("顶部字幕区", "Top"),
                 tr("全屏（会连屏幕文字一起识别）", "Full screen (may include on-screen UI text)")]
HEIGHT_VALUES = ["10%", "15%", "20%", "25%"]


class SubtitlePanelPage(BaseQtPanel, TaskPanelMixin):
    """视频字幕提取页。"""

    panel_key = "subtitle"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("字幕提取", "Subtitle extract")))
        lay.addWidget(self.make_subtitle(
            tr("把视频里的硬字幕识别成 .srt 字幕文件，支持外语视频/录播课",
               "Extract hard subtitles from videos into .srt files")))

        self.file_card = FileListCard(tr("视频列表", "Video list"), file_exts=VIDEO_EXTS)
        lay.addWidget(self.file_card)

        from gui_qt.components.form_widgets import FormGrid, FormSection
        card = FormSection(tr("识别设置", "Extract settings"), FluentIcon.LANGUAGE)
        grid = FormGrid(columns=2)

        def _combo(items, default):
            cb = ComboBox()
            cb.addItems(items)
            cb.setCurrentText(default)
            return cb

        self.cb_fps = grid.add_field(
            tr("抽帧精度", "Frame rate"), _combo(FPS_VALUES, FPS_VALUES[1]),
            hint=tr("帧率越高时间轴越准，识别越慢", "Higher frame rate = more accurate timeline, slower OCR"))
        self.cb_lang = grid.add_field(
            tr("识别语言", "Language"), _combo(LANG_VALUES, "chi_sim+eng"),
            hint=tr("chi_sim=中文  eng=英文  jpn=日文", "chi_sim=Chinese  eng=English  jpn=Japanese"))
        self.cb_region = grid.add_field(
            tr("字幕区域", "Subtitle area"), _combo(REGION_VALUES, REGION_VALUES[0]),
            hint=tr("只识别底部字幕区，避免把屏幕上其他文字当字幕", "OCR the subtitle area only to avoid on-screen UI text"))
        self.cb_height = grid.add_field(
            tr("区域高度", "Area height"), _combo(HEIGHT_VALUES, "15%"),
            hint=tr("越小越精准；若字幕被截断请调大", "Smaller = more precise; enlarge if subtitles get cut off"))
        card.add_form(grid)

        self.cb_auto = CheckBox(
            tr("自动检测字幕区域（推荐，适应各种视频布局）",
               "Auto-detect subtitle area (recommended, adapts to any layout)"))
        self.cb_auto.setChecked(True)
        card.add_widget(self.cb_auto)
        lay.addWidget(card)

        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        lay.addWidget(self.out_row)

        self.action_bar = ActionBar(tr("开始提取", "Extract"))
        lay.addWidget(self.action_bar)

        self.services.task_manager.register_runner(
            "subtitle", lambda task: self._runner)
        self._wire_tasks()

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "fps": self.cb_fps.currentText(),
            "lang": self.cb_lang.currentText(),
            "region": self.cb_region.currentText(),
            "height": self.cb_height.currentText(),
            "auto_detect": self.cb_auto.isChecked(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return self.collect_params()

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("fps") in FPS_VALUES:
            self.cb_fps.setCurrentText(str(prefs["fps"]))
        if prefs.get("lang") in LANG_VALUES:
            self.cb_lang.setCurrentText(str(prefs["lang"]))
        if prefs.get("region") in REGION_VALUES:
            self.cb_region.setCurrentText(str(prefs["region"]))
        if prefs.get("height") in HEIGHT_VALUES:
            self.cb_height.setCurrentText(str(prefs["height"]))
        if "auto_detect" in prefs:
            self.cb_auto.setChecked(bool(prefs["auto_detect"]))
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        from core.subtitle_extract import extract_subtitles
        p = task.params
        fps_sel = p.get("fps", FPS_VALUES[1])
        fps = 2 if fps_sel == FPS_VALUES[0] else (0.5 if fps_sel == FPS_VALUES[2] else 1)
        region_sel = p.get("region", REGION_VALUES[0])
        region = "bottom" if region_sel == REGION_VALUES[0] else (
            "top" if region_sel == REGION_VALUES[1] else "full")
        height = float(p.get("height", "15%").replace("%", "")) / 100.0
        return extract_subtitles(
            task.file_path, task.output_path, fps,
            p.get("lang", "chi_sim+eng"), region, height,
            bool(p.get("auto_detect", True)), prog)

    def _make_task(self, f):
        params = self.collect_params()
        out_dir = self.out_row.resolve_dir(f)
        nm = os.path.splitext(os.path.basename(f))[0]
        out_path = os.path.join(out_dir, nm + ".srt")
        return dict(
            name=f"{tr('字幕提取', 'Subtitle extract')} - {os.path.basename(f)}",
            task_type="subtitle", file_path=f, output_path=out_path,
            params=params, runner=self._runner, runner_key="subtitle",
            history_type=tr("字幕提取", "Subtitle extract"), history_target=params["lang"],
            need_ffmpeg=True)

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要提取字幕的视频文件", "Add videos to extract subtitles first")
