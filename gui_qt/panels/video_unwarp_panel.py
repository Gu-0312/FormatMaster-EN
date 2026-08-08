"""video_unwarp_panel — 视频反挤压（宽高比修复）面板。

老视频 / 非正方形像素视频画面被压扁拉长时，恢复到正确显示比例。
- 自动修复：按视频自带 DAR 修正 SAR 元数据（流复制，快）
- 手动反挤压：按目标比例（4:3 / 16:9 / 9:16 / 1:1 / 自定义）重编码拉伸
"""

import os

from PySide6.QtWidgets import QHBoxLayout, QSpinBox, QWidget
from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon, PushButton)

from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v",
              ".mpg", ".mpeg", ".ts"}

# 目标比例下拉（显示名 ↔ 值）
RATIO_VALUES = [tr("自动修复（按视频 DAR）", "Auto (video DAR)"),
                "16:9", "4:3", "9:16", "1:1",
                tr("自定义…", "Custom…")]
_RATIO_KEYS = ["auto", "16:9", "4:3", "9:16", "1:1", "custom"]


class VideoUnwarpPanelPage(BaseQtPanel, TaskPanelMixin):
    """视频反挤压页。"""

    panel_key = "video_unwarp"

    # ── UI ──────────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("视频反挤压", "Unwarp Video")))
        lay.addWidget(CaptionLabel(
            tr("修复视频画面被压扁/拉长的问题（如老 DVD、非正方形像素视频）",
               "Fix stretched/squashed video (old DVDs, non-square pixels)")))

        self.file_card = FileListCard(tr("视频列表", "Video list"),
                                      file_exts=VIDEO_EXTS)
        lay.addWidget(self.file_card)
        self.file_card.files_changed.connect(self._refresh_info)

        from gui_qt.components.form_widgets import FormGrid, FormSection
        sec = FormSection(tr("反挤压设置", "Unwarp settings"),
                          FluentIcon.MEDIA)

        grid = FormGrid(columns=2)
        self.cb_ratio = grid.add_field(
            tr("目标比例", "Target ratio"), self._ratio_combo(),
            hint=tr("自动修复最快（仅改元数据）；手动比例会重编码拉伸画面",
                    "Auto is fastest (metadata only); manual re-encodes"))
        sec.add_form(grid)

        # 自定义宽高比（仅自定义模式可见）
        self.w_custom = QWidget()
        crow = QHBoxLayout(self.w_custom)
        crow.setContentsMargins(0, 0, 0, 0)
        crow.setSpacing(8)
        crow.addWidget(CaptionLabel(tr("宽", "W")))
        self.sb_w = QSpinBox()
        self.sb_w.setRange(1, 10000)
        self.sb_w.setValue(16)
        crow.addWidget(self.sb_w)
        crow.addWidget(CaptionLabel(tr("高", "H")))
        self.sb_h = QSpinBox()
        self.sb_h.setRange(1, 10000)
        self.sb_h.setValue(9)
        crow.addWidget(self.sb_h)
        crow.addStretch(1)
        sec.add_widget(self.w_custom)

        # 视频信息
        self.lb_info = CaptionLabel(
            tr("导入视频后显示当前分辨率与比例", "Shows resolution & ratio after import"))
        self.lb_info.setStyleSheet(
            f"font-size: 12px; color: {self._ink_sec()};")
        sec.add_widget(self.lb_info)
        lay.addWidget(sec)

        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        lay.addWidget(self.out_row)

        self.action_bar = ActionBar(tr("开始修复", "Unwarp"))
        lay.addWidget(self.action_bar)

        self.cb_ratio.currentIndexChanged.connect(self._ratio_changed)
        self._ratio_changed()
        self.services.task_manager.register_runner(
            "video_unwarp", lambda task: self._runner)
        self._wire_tasks()

    def _ratio_combo(self):
        cb = ComboBox()
        cb.addItems(RATIO_VALUES)
        cb.setCurrentText(RATIO_VALUES[0])
        return cb

    def _ink_sec(self):
        from gui_qt.components import design_system as ds
        return ds.ink_sec()

    def _ratio_changed(self):
        key = _RATIO_KEYS[self.cb_ratio.currentIndex()]
        self.w_custom.setVisible(key == "custom")

    def _refresh_info(self):
        files = self.file_card.files()
        if not files:
            self.lb_info.setText(tr("导入视频后显示当前分辨率与比例",
                                    "Shows resolution & ratio after import"))
            return
        from core.video_unwarp import get_video_dar
        meta = get_video_dar(files[0])
        if not meta:
            self.lb_info.setText(tr("无法读取视频信息", "Cannot read video info"))
            return
        w, h, dar, sar = meta
        self.lb_info.setText(
            tr("当前", "Current") + f"  {w}×{h} · "
            + tr("显示比例", "DAR") + f" {dar} · "
            + tr("像素比例", "SAR") + f" {sar}")

    # ── 参数 ────────────────────────────────────
    def _target_ratio(self):
        key = _RATIO_KEYS[self.cb_ratio.currentIndex()]
        if key == "auto":
            return "auto"
        if key == "custom":
            return f"{self.sb_w.value()}:{self.sb_h.value()}"
        return key

    def collect_params(self) -> dict:
        return {
            "ratio": self._target_ratio(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return {
            "ratio": self._target_ratio(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        r = prefs.get("ratio")
        if r and r in _RATIO_KEYS and r != "custom":
            self.cb_ratio.setCurrentIndex(_RATIO_KEYS.index(r))
            self._ratio_changed()
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务 ────────────────────────────────────
    def _runner(self, task, prog):
        from core.video_unwarp import fix_aspect
        return fix_aspect(task.file_path, task.output_path,
                          task.params.get("ratio", "auto"),
                          progress_cb=prog)

    def _make_task(self, f):
        params = self.collect_params()
        out = os.path.splitext(f)[1] or ".mp4"
        target = os.path.join(self.out_row.resolve_dir(f),
                              os.path.splitext(os.path.basename(f))[0]
                              + "_反挤压" + out)
        return dict(
            name=f"{tr('视频反挤压', 'Unwarp')} - {os.path.basename(f)}",
            task_type="video_unwarp", file_path=f, output_path=target,
            params=params, runner=self._runner,
            history_type=tr("视频反挤压", "Unwarp"),
            history_target=params["ratio"], need_ffmpeg=True)

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要修复的视频", "Add videos to unwarp first")
