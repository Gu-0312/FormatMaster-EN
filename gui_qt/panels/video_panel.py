"""video_panel — 视频转换示范面板（阶段1 唯一真实功能面板）。

打通完整链路：文件管理 → 参数设置 → 任务队列 → 逐文件进度 → 完成提示。
collect_params() 字段与 tkinter 版 gui/panels/video_panel.py 保持一致。
"""
import os

from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout
from qfluentwidgets import (CaptionLabel, CheckBox, ComboBox,
                            FluentIcon, LineEdit, PrimaryPushButton,
                            PushButton, SubtitleLabel)

from gui_qt import task_manager as tm
from gui_qt.components import toast
from gui_qt.components import design_system as ds
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow
from utils.config import (RESOLUTIONS, SUPPORTED_VIDEO, VIDEO_CODECS,
                          VIDEO_CONVERT_PRESETS, VIDEO_PRESETS)

FPS_VALUES = ["原始帧率", "24", "25", "30", "60"]
BR_VALUES = ["自动", "1M", "2M", "5M", "8M", "10M", "20M"]


class VideoPanelPage(BaseQtPanel):
    """视频转换页。"""

    panel_key = "video"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title("视频转换"))

        # 文件列表（升级版：拖拽/单文件移除/逐文件进度）
        exts = set(SUPPORTED_VIDEO.values())
        self.file_card = FileListCard("文件列表", file_exts=exts)
        lay.addWidget(self.file_card)
        self.file_card.set_target_fmt("MP4")

        # 参数卡片
        lay.addWidget(self._build_params_card())

        # 输出目录
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

        # TaskManager 信号接入
        mgr = self.services.task_manager
        mgr.sig_progress.connect(self._on_progress)
        mgr.sig_state.connect(self._on_state)

        self._task_rows = {}   # task_id -> (file_path, row)

    def _build_params_card(self):
        from gui_qt.components.form_widgets import FormSection, FormGrid

        sec = FormSection("转换参数", FluentIcon.SETTING)

        # 预设模板选择器
        from qfluentwidgets import ComboBox as Cb
        preset_row = FormGrid(columns=1)
        self.cb_preset_tpl = Cb()
        self.cb_preset_tpl.addItems(list(VIDEO_CONVERT_PRESETS.keys()))
        self.cb_preset_tpl.setCurrentText("自定义")
        self.cb_preset_tpl.currentTextChanged.connect(self._apply_preset)
        preset_row.add_field("快速预设", self.cb_preset_tpl,
                             hint="选择预设自动填充下方参数")
        sec.add_form(preset_row)

        grid = FormGrid(columns=2)

        self.cb_fmt = grid.add_field(
            "目标格式", self._combo(list(SUPPORTED_VIDEO), "MP4"),
            hint="输出容器格式（如 MP4 / AVI / MKV）")
        self.cb_codec = grid.add_field(
            "编码器", self._combo(list(VIDEO_CODECS), "默认"),
            hint="视频编码标准，H.265 压缩率更高")
        self.cb_preset = grid.add_field(
            "质量预设", self._combo(list(VIDEO_PRESETS), "原始质量"))
        self.cb_res = grid.add_field(
            "分辨率", self._combo(list(RESOLUTIONS), "原始分辨率"))
        self.cb_fps = grid.add_field(
            "帧率", self._combo(FPS_VALUES, "原始帧率"))
        self.cb_br = grid.add_field(
            "码率", self._combo(BR_VALUES, "自动"),
            hint="自动由编码器决定，或手动指定")
        self.cb_hw = grid.add_field(
            "硬件加速", self._combo(self._hw_options(), "自动"),
            hint="NVIDIA / AMD / Intel 显卡加速编码")
        sec.add_form(grid)

        self.cb_copy = CheckBox("直接复制流（不重新编码，速度最快）")
        sec.add_widget(self.cb_copy)

        # 字幕烧录
        self.btn_sub = PushButton(FluentIcon.DOCUMENT, "选择字幕文件")
        self.btn_sub.clicked.connect(self._pick_subtitle)
        self._subtitle_path = ""
        self._lbl_sub = CaptionLabel("未选择字幕", self)
        self._lbl_sub.setStyleSheet(
            f"font-size: 12px; color: {ds.ink_sec()};")
        from PySide6.QtWidgets import QHBoxLayout as HLAY
        sub_row = HLAY()
        sub_row.setSpacing(8)
        sub_row.addWidget(self.btn_sub)
        sub_row.addWidget(self._lbl_sub, 1)
        sub_row.addStretch(1)
        from PySide6.QtWidgets import QWidget as QW
        sub_wrap = QW()
        sub_wrap.setLayout(sub_row)
        sec.add_widget(sub_wrap)

        return sec

    def _combo(self, items, default):
        cb = ComboBox()
        cb.addItems(items)
        cb.setCurrentText(default)
        return cb

    def _hw_options(self):
        """硬件加速选项：自动 / 检测到的 GPU / 关闭硬件加速。"""
        try:
            from utils.hardware_accel import detect_hardware_acceleration
            available = detect_hardware_acceleration()
        except Exception:  # noqa: BLE001 - 检测失败不应阻断 UI
            available = []
        return ["自动"] + [a["name"] for a in available] + ["关闭硬件加速"]

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
            self, "选择字幕文件", "",
            "字幕文件 (*.srt *.ass *.ssa *.vtt);;所有文件 (*)")
        if path:
            self._subtitle_path = path
            name = os.path.basename(path)
            self._lbl_sub.setText(name)
        else:
            self._subtitle_path = ""
            self._lbl_sub.setText("未选择字幕")

    def _resolve_hw_accel(self):
        """显示名 → 内部 key（与 tkinter 版 _resolve_hw_accel 一致）。"""
        display = self.cb_hw.currentText()
        if display == "自动":
            return "auto"
        if display == "关闭硬件加速":
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
        }

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

    # ── 任务提交 ─────────────────────────────────
    def _start(self):
        files = self.file_card.files()
        if not files:
            toast.show_warning(self, "请先添加要转换的视频文件")
            return
        if not self.services.ffmpeg_ready():
            toast.show_error(self, "FFmpeg 未就绪，请稍后重试")
            return
        if self.out_row.mode() == OutputDirRow.MODE_CUSTOM and not self.out_row.path():
            toast.show_warning(self, "请先选择自定义输出目录")
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
        if state == tm.SUCCESS:
            toast.show_success(self, f"转换完成：{os.path.basename(task.file_path)}")
        elif state == tm.FAILED:
            toast.show_error(self,
                             f"转换失败：{os.path.basename(task.file_path)}"
                             f"（{task.error or '未知错误'}）")
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
