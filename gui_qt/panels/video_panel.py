"""video_panel — 视频转换示范面板（阶段1 唯一真实功能面板）。

打通完整链路：文件管理 → 参数设置 → 任务队列 → 逐文件进度 → 完成提示。
collect_params() 字段与 tkinter 版 gui/panels/video_panel.py 保持一致。
"""
import os

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout
from qfluentwidgets import (CaptionLabel, CheckBox, ComboBox,
                            EditableComboBox, FluentIcon, LineEdit,
                            PrimaryPushButton, PushButton, SubtitleLabel)

from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.components import toast
from gui_qt.components import design_system as ds
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow
from utils.config import (RESOLUTIONS, SUPPORTED_VIDEO, VIDEO_CODECS,
                          VIDEO_CONVERT_PRESETS, VIDEO_PRESETS)

FPS_VALUES = [tr("原始帧率", "Original FPS"), "24", "25", "30", "60"]
BR_VALUES = [tr("自动", "Auto"), "1M", "2M", "5M", "8M", "10M", "20M"]
SUB_FONT_VALUES = [tr("自动", "Auto"), "16", "24", "32", "40"]


class VideoPanelPage(BaseQtPanel):
    """视频转换页。"""

    panel_key = "video"
    # 硬件加速检测完成（后台 daemon 线程 → 主线程信号，更新下拉不阻塞 UI）
    _hw_ready = Signal(list)

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("视频转换", "Video convert")))

        # 文件列表（升级版：拖拽/单文件移除/逐文件进度）
        exts = set(SUPPORTED_VIDEO.values())
        self.file_card = FileListCard(tr("文件列表", "Files"), file_exts=exts)
        lay.addWidget(self.file_card)
        self.file_card.set_target_fmt("MP4")

        # 参数卡片
        lay.addWidget(self._build_params_card())

        # 输出目录
        from gui_qt.components.form_widgets import FormSection
        out_card = FormSection(tr("输出目录", "Output folder"), FluentIcon.FOLDER)
        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        out_card.add_widget(self.out_row)
        lay.addWidget(out_card)

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

        # TaskManager 信号接入
        mgr = self.services.task_manager
        mgr.sig_progress.connect(self._on_progress)
        mgr.sig_state.connect(self._on_state)

        self._task_rows = {}   # task_id -> (file_path, row)

        # 硬件加速下拉异步补全（缓存未命中时后台检测，不阻塞构建）
        self._hw_ready.connect(self._fill_hw_options)
        self._ensure_hw_options_async()

    def _build_params_card(self):
        from gui_qt.components.form_widgets import FormSection, FormGrid
        from qfluentwidgets import ComboBox as Cb
        from PySide6.QtWidgets import QHBoxLayout as HLAY, QWidget as QW

        sec = FormSection(tr("转换参数", "Convert settings"), FluentIcon.SETTING)

        # 快速预设（一键填充，主路径）
        preset_row = FormGrid(columns=1)
        self.cb_preset_tpl = Cb()
        self.cb_preset_tpl.addItems(list(VIDEO_CONVERT_PRESETS.keys()))
        self.cb_preset_tpl.setCurrentText(tr("自定义", "Custom"))
        self.cb_preset_tpl.currentTextChanged.connect(self._apply_preset)
        preset_row.add_field(tr("快速预设", "Quick preset"), self.cb_preset_tpl,
                             hint=tr("选择预设自动填充下方参数", "Pick a preset to fill parameters"))
        sec.add_form(preset_row)

        # 主参数（最常见，直接可见，渐进式披露的主路径）
        main_grid = FormGrid(columns=2)
        self.cb_fmt = main_grid.add_field(
            tr("目标格式", "Target format"), self._combo(list(SUPPORTED_VIDEO), "MP4"),
            hint=tr("输出容器格式（如 MP4 / AVI / MKV）", "Output container (e.g. MP4 / AVI / MKV)"))
        self.cb_res = main_grid.add_field(
            tr("分辨率", "Resolution"), self._combo(list(RESOLUTIONS), tr("原始分辨率", "Original resolution")))
        sec.add_form(main_grid)

        self.cb_copy = CheckBox(tr("直接复制流（不重新编码，速度最快）", "Copy stream directly (no re-encode, fastest)"))
        self.cb_copy.toggled.connect(self._on_copy_toggled)
        sec.add_widget(self.cb_copy)

        # 高级设置（渐进式披露：默认折叠，降低认知负载）
        adv_head = QW()
        adv_h = HLAY(adv_head)
        adv_h.setContentsMargins(0, 0, 0, 0)
        adv_h.setSpacing(8)
        self.btn_adv = PushButton(FluentIcon.SETTING, tr("高级设置 ▸", "Advanced ▸"))
        self.btn_adv.setCheckable(True)
        self.btn_adv.clicked.connect(self._toggle_advanced)
        adv_h.addWidget(self.btn_adv)
        adv_hint = CaptionLabel(
            tr("编码器 / 质量 / 帧率 / 码率 / 硬件加速 / 字幕（通常无需调整）",
               "Encoder / quality / FPS / bitrate / HW accel / subtitle (usually leave as-is)"))
        adv_hint.setStyleSheet(
            f"font-size: 12px border: none; background: transparent;")
        adv_h.addWidget(adv_hint)
        adv_h.addStretch(1)
        sec.add_widget(adv_head)

        self.adv_wrap = QW()
        adv_v = QVBoxLayout(self.adv_wrap)
        adv_v.setContentsMargins(0, 0, 0, 0)
        adv_v.setSpacing(12)
        adv_grid = FormGrid(columns=2)
        self.cb_codec = adv_grid.add_field(
            tr("编码器", "Encoder"), self._combo(list(VIDEO_CODECS), tr("默认", "Default")),
            hint=tr("视频编码标准，H.265 压缩率更高", "Video codec, H.265 compresses better"))
        self.cb_preset = adv_grid.add_field(
            tr("质量预设", "Quality preset"), self._combo(list(VIDEO_PRESETS), tr("原始质量", "Original quality")))
        self.cb_fps = adv_grid.add_field(
            tr("帧率", "Frame rate"), self._combo(FPS_VALUES, tr("原始帧率", "Original FPS")))
        self.cb_br = adv_grid.add_field(
            tr("码率", "Bitrate"), self._combo_editable(BR_VALUES, tr("自动", "Auto")),
            hint=tr("自动由编码器决定，或手动指定（可自定义输入，如 3.5M）",
                    "Auto (encoder default) or manual (custom values allowed, e.g. 3.5M)"))
        self.cb_hw = adv_grid.add_field(
            tr("硬件加速", "HW acceleration"), self._combo(self._hw_options(), tr("自动", "Auto")),
            hint=tr("NVIDIA / AMD / Intel 显卡加速编码", "NVIDIA / AMD / Intel GPU accelerated encoding"))
        # 设置里「默认硬件引擎」指定时覆盖初始值
        try:
            _eng = self.services.get_pref("hw_accel_engine", "auto")
            if _eng == "off":
                self.cb_hw.setCurrentText(tr("关闭硬件加速", "Disable HW accel"))
            elif _eng != "auto":
                from utils.hardware_accel import HW_ACCEL_ENCODERS
                if _eng in HW_ACCEL_ENCODERS:
                    self.cb_hw.setCurrentText(HW_ACCEL_ENCODERS[_eng]["name"])
        except Exception:  # noqa: BLE001 - 引擎默认值读取失败不影响
            pass
        adv_v.addLayout(adv_grid)

        # 字幕烧录
        self.btn_sub = PushButton(FluentIcon.DOCUMENT, tr("选择字幕文件", "Pick subtitle file"))
        self.btn_sub.clicked.connect(self._pick_subtitle)
        self._subtitle_path = ""
        self._lbl_sub = CaptionLabel(tr("未选择字幕", "No subtitle"), self)
        self._lbl_sub.setStyleSheet(
            f"font-size: 12px")
        sub_row = HLAY()
        sub_row.setSpacing(8)
        sub_row.addWidget(self.btn_sub)
        sub_row.addWidget(self._lbl_sub, 1)
        # 字幕字号（手动选择，随面板记忆保存）
        self.cb_sub_font = self._combo(SUB_FONT_VALUES, tr("自动", "Auto"))
        sub_row.addWidget(CaptionLabel(tr("字号", "Font size")))
        sub_row.addWidget(self.cb_sub_font)
        sub_row.addStretch(1)
        sub_wrap = QW()
        sub_wrap.setLayout(sub_row)
        adv_v.addWidget(sub_wrap)

        # 元数据（标题/艺术家，写入输出文件信息）
        md_grid = FormGrid(columns=2)
        self.ed_md_title = LineEdit()
        self.ed_md_title.setPlaceholderText(tr("可选，如「我的视频」", "Optional, e.g. 'My video'"))
        self.ed_md_artist = LineEdit()
        self.ed_md_artist.setPlaceholderText(tr("可选，如作者名", "Optional, e.g. author"))
        md_grid.add_field(tr("标题", "Title"), self.ed_md_title,
                          hint=tr("写入输出文件的标题元数据", "Write title metadata to output"))
        md_grid.add_field(tr("艺术家/作者", "Artist"), self.ed_md_artist,
                          hint=tr("写入输出文件的艺术家元数据", "Write artist metadata to output"))
        adv_v.addLayout(md_grid)

        sec.add_widget(self.adv_wrap)
        self.adv_wrap.setVisible(False)
        return sec

    def _toggle_advanced(self, checked):
        """展开 / 收起高级设置（渐进式披露）。"""
        self.adv_wrap.setVisible(checked)
        self.btn_adv.setText(
            tr("高级设置 ▾", "Advanced ▾") if checked else tr("高级设置 ▸", "Advanced ▸"))

    def _combo(self, items, default):
        cb = ComboBox()
        cb.addItems(items)
        cb.setCurrentText(default)
        return cb

    def _combo_editable(self, items, default):
        """可编辑下拉（EditableComboBox）：保留预设选项 + 允许手输自定义值。
        用于码率等「预设 + 自由输入」场景（如 3.5M）。"""
        cb = EditableComboBox()
        cb.addItems(items)
        cb.setCurrentText(default)
        return cb

    def _hw_options(self):
        """硬件加速选项（非阻塞）：只读缓存，不触发 subprocess。

        启动时 prewarm_hw_accel_async 已在后台预热，缓存命中直接返回
        完整选项（0ms）；未命中先返回基础选项（自动/关闭），由
        _ensure_hw_options_async 后台检测完成后经 Signal 补全，避免
        UI 线程同步跑 `ffmpeg -encoders`（~85ms）卡顿。
        """
        try:
            from utils.hardware_accel import get_cached_hw_accel
            available = get_cached_hw_accel() or []
        except Exception:  # noqa: BLE001 - 检测失败不应阻断 UI
            available = []
        return [tr("自动", "Auto")] + [a["name"] for a in available] + [tr("关闭硬件加速", "Disable HW accel")]

    def _ensure_hw_options_async(self):
        """缓存未命中时：后台线程检测硬件加速，完成后 Signal 补全下拉。"""
        try:
            from utils.hardware_accel import get_cached_hw_accel, detect_hardware_acceleration
            if get_cached_hw_accel() is not None:
                return  # 预热已命中，无需异步
        except Exception:  # noqa: BLE001 - 探测入口失败直接跳过
            return

        def _run():
            try:
                available = detect_hardware_acceleration()
            except Exception:  # noqa: BLE001 - 检测失败保持基础选项
                available = []
            self._hw_ready.emit(available)

        import threading
        threading.Thread(target=_run, daemon=True).start()

    def _fill_hw_options(self, available):
        """后台检测完成：补齐硬件加速下拉选项（保留当前选择）。"""
        try:
            if not hasattr(self, "cb_hw") or self.cb_hw is None:
                return
            current = self.cb_hw.currentText()
            opts = ([tr("自动", "Auto")] + [a["name"] for a in available]
                    + [tr("关闭硬件加速", "Disable HW accel")])
            self.cb_hw.blockSignals(True)
            self.cb_hw.clear()
            self.cb_hw.addItems(opts)
            if current in opts:
                self.cb_hw.setCurrentText(current)  # 保留用户/偏好选择
            self.cb_hw.blockSignals(False)
        except Exception:  # noqa: BLE001 - 补全失败不影响面板
            pass

    def _apply_preset(self, name):
        """应用预设模板：自动填充各参数控件。"""
        tpl = VIDEO_CONVERT_PRESETS.get(name, {})
        if not tpl:
            return
        if "codec" in tpl and tpl["codec"] in VIDEO_CODECS:
            self.cb_codec.setCurrentText(tpl["codec"])
        if "preset" in tpl and tpl["preset"] in VIDEO_PRESETS:
            self.cb_preset.setCurrentText(tpl["preset"])
        if "res" in tpl and tpl["res"] in RESOLUTIONS:
            self.cb_res.setCurrentText(tpl["res"])
        if "fps" in tpl and tpl["fps"] in FPS_VALUES:
            self.cb_fps.setCurrentText(tpl["fps"])
        if "br" in tpl and tpl["br"] in BR_VALUES:
            self.cb_br.setCurrentText(tpl["br"])
        if "copy_mode" in tpl:
            self.cb_copy.setChecked(bool(tpl["copy_mode"]))

    def _pick_subtitle(self):
        """选择字幕文件（SRT/ASS/SSA）。"""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, tr("选择字幕文件", "Pick subtitle file"), "",
            tr("字幕文件 (*.srt *.ass *.ssa *.vtt);;所有文件 (*)", "Subtitle files (*.srt *.ass *.ssa *.vtt);;All files (*)"))
        if path:
            # 复制流模式不支持烧录字幕（会静默忽略），自动切回重编码
            if self.cb_copy.isChecked():
                self.cb_copy.setChecked(False)
                toast.show_info(self, tr("烧录字幕需要重新编码，已自动关闭「直接复制流」",
                                         "Burning subtitles requires re-encode, turned off copy stream"))
            self._subtitle_path = path
            name = os.path.basename(path)
            self._lbl_sub.setText(name)
        else:
            self._subtitle_path = ""
            self._lbl_sub.setText(tr("未选择字幕", "No subtitle"))

    def _on_copy_toggled(self, checked):
        """勾选「直接复制流」时，若已选字幕则清除（copy 模式无法烧录字幕）。"""
        if checked and self._subtitle_path:
            self._subtitle_path = ""
            self._lbl_sub.setText(tr("未选择字幕", "No subtitle"))
            toast.show_info(self, tr("「直接复制流」不支持烧录字幕，已清除已选字幕",
                                     "Copy stream cannot burn subtitles, cleared subtitle selection"))

    def _resolve_hw_accel(self):
        """显示名 → 内部 key（与 tkinter 版 _resolve_hw_accel 一致）。"""
        display = self.cb_hw.currentText()
        if display == tr("自动", "Auto"):
            return "auto"
        if display == tr("关闭硬件加速", "Disable HW accel"):
            return None
        from utils.hardware_accel import HW_ACCEL_ENCODERS
        for key, info in HW_ACCEL_ENCODERS.items():
            if info["name"] == display:
                return key
        return None

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "fmt": self.cb_fmt.currentText(),
            "codec": self.cb_codec.currentText(),
            "preset": self.cb_preset.currentText(),
            "res": self.cb_res.currentText(),
            "fps": self.cb_fps.currentText(),
            "br": self.cb_br.currentText(),
            "copy_mode": self.cb_copy.isChecked(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
            "hw_accel": self._resolve_hw_accel(),
            "subtitle_path": self._subtitle_path,
            "sub_font_size": self._resolve_sub_font(),
            "metadata": {
                "title": self.ed_md_title.text().strip(),
                "artist": self.ed_md_artist.text().strip(),
            },
        }

    def _resolve_sub_font(self):
        """字幕字号：显示文本 → int（「自动」返回 None）。"""
        try:
            t = self.cb_sub_font.currentText()
            return int(t) if t.strip().isdigit() else None
        except Exception:  # noqa: BLE001
            return None

    def collect_prefs(self) -> dict:
        return {
            "fmt": self.cb_fmt.currentText(),
            "codec": self.cb_codec.currentText(),
            "preset": self.cb_preset.currentText(),
            "res": self.cb_res.currentText(),
            "fps": self.cb_fps.currentText(),
            "br": self.cb_br.currentText(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
            "hw_accel": self.cb_hw.currentText(),
            "sub_font_size": self.cb_sub_font.currentText(),
        }

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("fmt") in SUPPORTED_VIDEO:
            self.cb_fmt.setCurrentText(prefs["fmt"])
        if prefs.get("codec") in VIDEO_CODECS:
            self.cb_codec.setCurrentText(prefs["codec"])
        if prefs.get("preset") in VIDEO_PRESETS:
            self.cb_preset.setCurrentText(prefs["preset"])
        if prefs.get("res") in RESOLUTIONS:
            self.cb_res.setCurrentText(prefs["res"])
        if prefs.get("fps") in FPS_VALUES:
            self.cb_fps.setCurrentText(prefs["fps"])
        if prefs.get("br") in BR_VALUES:
            self.cb_br.setCurrentText(prefs["br"])
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))
        if prefs.get("hw_accel"):
            _opts = self._hw_options()
            if prefs["hw_accel"] in _opts:
                self.cb_hw.setCurrentText(prefs["hw_accel"])
        if prefs.get("sub_font_size") in SUB_FONT_VALUES:
            self.cb_sub_font.setCurrentText(prefs["sub_font_size"])

    # ── 任务提交 ─────────────────────────────────
    def _start(self):
        files = self.file_card.files()
        if not files:
            toast.show_warning(self, tr("请先添加要转换的视频文件", "Add video files to convert first"))
            return
        if not self.services.ffmpeg_ready():
            toast.show_error(self, tr("FFmpeg 未就绪，请稍后重试", "FFmpeg not ready"))
            return
        if self.out_row.mode() == OutputDirRow.MODE_CUSTOM and not self.out_row.path():
            toast.show_warning(self, tr("请先选择自定义输出目录", "Choose an output folder first"))
            return

        params = self.collect_params()
        self.save_prefs()
        fmt_ext = SUPPORTED_VIDEO[params["fmt"]]
        mgr = self.services.task_manager
        max_retries = int(self.services.get_pref("max_retries", 0) or 0)
        added = 0
        for f in files:
            out_dir = self.out_row.resolve_dir(f)
            out_path = tm.make_output_path(f, out_dir, fmt_ext)
            tid = mgr.add_video_task(f, out_path, params, max_retries=max_retries)
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
        if state == tm.FAILED:
            # 失败即时提示（具体文件+原因）；成功统一走全局完成通知，
            # 避免与「全部转换完成」重复弹两条提示
            toast.show_error(self,
                             tr("转换失败：{}", "Failed: {}").format(os.path.basename(task.file_path)) +
                             tr("（{}）", " ({})").format(task.error or tr("未知错误", "unknown error")))
        if state in (tm.SUCCESS, tm.FAILED, tm.CANCELLED):
            self._task_rows.pop(task_id, None)
            self._update_total()
        # 全部结束 → 恢复按钮，总进度条重置归零（等待下一批任务）
        active = [self.services.task_manager.get_task(t)
                  for t in self._task_rows]
        if not any(t and t.state in (tm.WAITING, tm.RUNNING, tm.PAUSED)
                   for t in active):
            self.btn_go.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self.bar_total.setValue(0)

    def _update_total(self):
        tasks = [self.services.task_manager.get_task(t) for t in self._task_rows]
        tasks = [t for t in tasks if t]
        if not tasks:
            return
        self.bar_total.setValue(sum(t.progress for t in tasks) // len(tasks))
