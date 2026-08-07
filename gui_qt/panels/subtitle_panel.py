# -*- coding: utf-8 -*-
"""subtitle_panel — 视频字幕提取面板。

把视频里的硬字幕 OCR 识别出来生成 .srt 字幕文件
（core.subtitle_extract：FFmpeg 抽帧 + RapidOCR 逐帧识别 + 去重合并时间轴）。
"""
import os

from qfluentwidgets import ComboBox, FluentIcon

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
SOURCE_VALUES = [tr("画面文字（硬字幕 OCR）", "On-screen text (OCR)"),
                 tr("语音识别（ASR，中文）", "Speech recognition (ASR, Chinese)")]


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
        self._grid = FormGrid(columns=2)
        grid = self._grid

        def _combo(items, default):
            cb = ComboBox()
            cb.addItems(items)
            cb.setCurrentText(default)
            return cb

        self.cb_source = grid.add_field(
            tr("字幕来源", "Subtitle source"), _combo(SOURCE_VALUES, SOURCE_VALUES[0]),
            hint=tr("画面文字=提取屏幕上的字幕；语音识别=把讲解语音转成字幕", "OCR = extract on-screen subtitles; ASR = transcribe speech into subtitles"))
        self.cb_source.currentIndexChanged.connect(self._source_changed)
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
        lay.addWidget(card)

        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        lay.addWidget(self.out_row)

        self.action_bar = ActionBar(tr("开始提取", "Extract"))
        lay.addWidget(self.action_bar)

        self.services.task_manager.register_runner(
            "subtitle", lambda task: self._runner)
        self.services.task_manager.register_runner(
            "asr_srt", lambda task: self._runner)
        self.cb_source.currentIndexChanged.connect(self._source_changed)
        self._source_changed()
        self._wire_tasks()

    def _source_changed(self):
        """来源切换：语音识别模式隐藏 OCR 专用参数。"""
        is_asr = self.cb_source.currentIndex() == 1
        for cb in (self.cb_fps, self.cb_lang, self.cb_region, self.cb_height):
            self._grid.set_row_visible(cb, not is_asr)

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "source": "asr" if self.cb_source.currentIndex() == 1 else "ocr",
            "fps": self.cb_fps.currentText(),
            "lang": self.cb_lang.currentText(),
            "region": self.cb_region.currentText(),
            "height": self.cb_height.currentText(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return self.collect_params()

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("source") == "asr":
            self.cb_source.setCurrentIndex(1)
        if prefs.get("fps") in FPS_VALUES:
            self.cb_fps.setCurrentText(str(prefs["fps"]))
        if prefs.get("lang") in LANG_VALUES:
            self.cb_lang.setCurrentText(str(prefs["lang"]))
        if prefs.get("region") in REGION_VALUES:
            self.cb_region.setCurrentText(str(prefs["region"]))
        if prefs.get("height") in HEIGHT_VALUES:
            self.cb_height.setCurrentText(str(prefs["height"]))
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        p = task.params
        if p.get("source") == "asr":
            # 语音识别：模型未就绪先下载（首次约 100MB）
            from core.asr_tool import (is_model_ready, download_model,
                                       audio_to_srt)
            if not is_model_ready():
                prog(5, tr("首次使用需下载语音模型（约 100MB）…",
                           "First use downloads the speech model (~100MB)…"))
                if not download_model(prog):
                    task.error = tr("语音模型下载失败，请检查网络后重试",
                                    "Speech model download failed, check network")
                    return False
            return audio_to_srt(task.file_path, task.output_path, prog)

        # OCR 硬字幕
        from core.subtitle_extract import extract_subtitles
        fps_sel = p.get("fps", FPS_VALUES[1])
        fps = 2 if fps_sel == FPS_VALUES[0] else (0.5 if fps_sel == FPS_VALUES[2] else 1)
        region_sel = p.get("region", REGION_VALUES[0])
        region = "bottom" if region_sel == REGION_VALUES[0] else (
            "top" if region_sel == REGION_VALUES[1] else "full")
        height = float(p.get("height", "15%").replace("%", "")) / 100.0
        return extract_subtitles(
            task.file_path, task.output_path, fps,
            p.get("lang", "chi_sim+eng"), region, height, prog)

    def _make_task(self, f):
        params = self.collect_params()
        out_dir = self.out_row.resolve_dir(f)
        nm = os.path.splitext(os.path.basename(f))[0]
        out_path = os.path.join(out_dir, nm + ".srt")
        is_asr = params.get("source") == "asr"
        return dict(
            name=f"{tr('语音转字幕', 'Speech to subtitles') if is_asr else tr('字幕提取', 'Subtitle extract')} - {os.path.basename(f)}",
            task_type="asr_srt" if is_asr else "subtitle",
            file_path=f, output_path=out_path,
            params=params, runner=self._runner,
            runner_key="asr_srt" if is_asr else "subtitle",
            history_type=tr("语音转字幕", "Speech to subtitles") if is_asr else tr("字幕提取", "Subtitle extract"),
            history_target=tr("语音识别", "ASR") if is_asr else params["lang"],
            need_ffmpeg=True)

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要提取字幕的视频文件", "Add videos to extract subtitles first")
